#!/usr/bin/env python3

"""Synchronize the public GeoEpi Zotero library into generated site sources."""

import argparse
import copy
import html
import json
import os
import re
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_CONFIG = Path("config/publications.json")
DEFAULT_SNAPSHOT = Path("data/zotero-publications.json")
DEFAULT_PAGE = Path("publications.qmd")
API_ROOT = "https://api.zotero.org"
API_VERSION = "3"
PAGE_SIZE = 100
EXCLUDED_ITEM_TYPES = {"attachment", "note", "annotation"}
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def load_config(path=DEFAULT_CONFIG):
    path = Path(path)
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("publication configuration must be a JSON object")
    group_id = config.get("zotero_group_id")
    if type(group_id) is not int or group_id <= 0:
        raise ValueError("zotero_group_id must be a positive integer")
    collection_key = config.get("collection_key")
    if collection_key is not None and (
        not isinstance(collection_key, str) or not collection_key.strip()
    ):
        raise ValueError("collection_key must be null or a non-empty string")
    for field in ("citation_style", "locale"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    return config


def endpoint_for_config(config):
    group_id = config["zotero_group_id"]
    collection_key = config.get("collection_key")
    if collection_key:
        return f"{API_ROOT}/groups/{group_id}/collections/{collection_key}/items/top"
    return f"{API_ROOT}/groups/{group_id}/items/top"


def _request_url(config):
    query = urlencode(
        {
            "include": "data,bib",
            "style": config["citation_style"],
            "locale": config["locale"],
            "linkwrap": "1",
            "sort": "date",
            "direction": "desc",
            "limit": str(PAGE_SIZE),
        }
    )
    return f"{endpoint_for_config(config)}?{query}"


def _header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _next_link(headers):
    value = _header(headers, "Link")
    if not value:
        return None
    for part in value.split(","):
        match = re.match(r"\s*<([^>]+)>\s*;\s*rel=\"?([^\";]+)", part)
        if match and match.group(2).strip() == "next":
            return match.group(1)
    return None


def _backoff_seconds(headers):
    for name in ("Backoff", "Retry-After"):
        value = _header(headers, name)
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                pass
    return 0.0


def _fetch_page(url):
    for attempt in range(4):
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "geoepi-website-publications",
                "Zotero-API-Version": API_VERSION,
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload = response.read()
                headers = response.headers
            break
        except HTTPError as exc:
            if exc.code in {429, 502, 503, 504} and attempt < 3:
                time.sleep(_backoff_seconds(exc.headers) or min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"Zotero API request failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Zotero API request failed: {exc.reason}") from exc
    try:
        payload = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Zotero API returned malformed JSON") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Zotero API response must be a JSON array")
    wait = _backoff_seconds(headers)
    if wait:
        time.sleep(wait)
    return payload, _next_link(headers)


def fetch_all_items(config):
    """Retrieve every page by following Zotero's HTTP Link header."""
    items = []
    url = _request_url(config)
    seen_urls = set()
    pages = 0
    while url:
        if url in seen_urls:
            raise RuntimeError("Zotero pagination repeated the same next URL")
        seen_urls.add(url)
        page, url = _fetch_page(url)
        pages += 1
        items.extend(page)
    return items, pages


def load_source_items(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        payload = payload["items"]
    if not isinstance(payload, list):
        raise ValueError("source file must contain a JSON array of Zotero items")
    return payload


def _clean(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _creator_name(creator):
    name = _clean(creator.get("name"))
    if name:
        return name
    first = _clean(creator.get("firstName"))
    last = _clean(creator.get("lastName"))
    return " ".join(part for part in (first, last) if part) or None


def _normalize_creators(creators):
    normalized = []
    for creator in creators if isinstance(creators, list) else []:
        if not isinstance(creator, dict):
            continue
        first = _clean(creator.get("firstName"))
        last = _clean(creator.get("lastName"))
        name = _clean(creator.get("name"))
        creator_type = _clean(creator.get("creatorType")) or "author"
        if not (first or last or name):
            continue
        normalized.append(
            {
                "creator_type": creator_type,
                "first_name": first,
                "last_name": last,
                "name": name,
            }
        )
    return normalized


def _creator_display(creators):
    authors = [creator for creator in creators if creator["creator_type"] == "author"]
    visible = authors or creators
    names = []
    for creator in visible:
        name = creator["name"] or " ".join(
            part for part in (creator["first_name"], creator["last_name"]) if part
        )
        if name:
            names.append(name)
    return ", ".join(names) or None


def _year_from_date(date_value):
    match = YEAR_RE.search(date_value or "")
    return int(match.group(1)) if match else None


def _zotero_url(item):
    links = item.get("links") if isinstance(item, dict) else None
    if not isinstance(links, dict):
        return None
    alternate = links.get("alternate")
    if isinstance(alternate, dict):
        return _clean(alternate.get("href"))
    self_link = links.get("self")
    return _clean(self_link.get("href")) if isinstance(self_link, dict) else None


def _formatted_reference(item):
    bib = item.get("bib") if isinstance(item, dict) else None
    if isinstance(bib, str):
        return _clean(bib)
    if isinstance(bib, dict):
        return _clean(bib.get("content") or bib.get("html"))
    return None


def normalize_item(item):
    if not isinstance(item, dict):
        return None, "malformed record"
    data = item.get("data") if isinstance(item.get("data"), dict) else item
    item_type = _clean(data.get("itemType"))
    if item_type in EXCLUDED_ITEM_TYPES:
        return None, f"excluded:{item_type}"
    title = _clean(data.get("title"))
    if not title:
        return None, "missing-title"
    creators = _normalize_creators(data.get("creators"))
    tags = []
    for tag in data.get("tags") if isinstance(data.get("tags"), list) else []:
        value = _clean(tag.get("tag")) if isinstance(tag, dict) else _clean(tag)
        if value:
            tags.append(value)
    version = item.get("version", data.get("version"))
    url = _clean(data.get("url"))
    doi = _clean(data.get("DOI") or data.get("doi"))
    record = {
        "key": _clean(item.get("key") or data.get("key")),
        "version": version,
        "item_type": item_type,
        "title": title,
        "creators": creators,
        "creator_display": _creator_display(creators),
        "date": _clean(data.get("date")),
        "year": _year_from_date(data.get("date")),
        "publication_title": _clean(data.get("publicationTitle")),
        "journal_abbreviation": _clean(data.get("journalAbbreviation")),
        "volume": _clean(data.get("volume")),
        "issue": _clean(data.get("issue")),
        "pages": _clean(data.get("pages")),
        "publisher": _clean(data.get("publisher")),
        "place": _clean(data.get("place")),
        "doi": doi,
        "url": url,
        "abstract": _clean(data.get("abstractNote") or data.get("abstract")),
        "tags": tags,
        "zotero_url": _zotero_url(item),
        "formatted_reference": _formatted_reference(item),
    }
    return record, None


def normalize_items(items):
    records = []
    excluded = Counter()
    skipped = Counter()
    for item in items:
        record, diagnostic = normalize_item(item)
        if record is not None:
            records.append(record)
        elif diagnostic and diagnostic.startswith("excluded:"):
            excluded[diagnostic.split(":", 1)[1]] += 1
        else:
            skipped[diagnostic or "unknown"] += 1
    records.sort(
        key=lambda record: (
            record["year"] is None,
            -(record["year"] or 0),
            record["title"].casefold(),
            record["key"] or "",
        )
    )
    stats = {
        "retrieved": len(items),
        "excluded": sum(excluded.values()),
        "excluded_types": dict(sorted(excluded.items())),
        "skipped": dict(sorted(skipped.items())),
        "normalized": len(records),
        "abstracts": sum(record["abstract"] is not None for record in records),
        "dois": sum(record["doi"] is not None for record in records),
        "without_year": sum(record["year"] is None for record in records),
        "item_types": dict(
            sorted(
                Counter(record["item_type"] or "unknown" for record in records).items()
            )
        ),
    }
    return records, stats


def build_snapshot(records, config):
    return {
        "schema_version": 1,
        "source": {
            "provider": "Zotero",
            "group_id": config["zotero_group_id"],
            "collection_key": config.get("collection_key"),
        },
        "publications": records,
    }


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise ValueError("publication snapshot schema_version must equal 1")
    source = snapshot.get("source")
    if not isinstance(source, dict) or source.get("provider") != "Zotero":
        raise ValueError("publication snapshot source is invalid")
    publications = snapshot.get("publications")
    if not isinstance(publications, list):
        raise ValueError("publication snapshot publications must be a list")
    for index, record in enumerate(publications):
        if not isinstance(record, dict) or not _clean(record.get("title")):
            raise ValueError(f"publication {index} has no usable title")
        if "abstract" not in record or "year" not in record:
            raise ValueError(f"publication {index} is missing normalized fields")
    return snapshot


def _inline(value):
    return html.escape(str(value), quote=True)


def _publication_context(record):
    parts = []
    if record.get("publication_title"):
        parts.append(record["publication_title"])
    if record.get("volume"):
        volume = record["volume"]
        if record.get("issue"):
            volume += f"({record['issue']})"
        parts.append(volume)
    if record.get("pages"):
        parts.append(record["pages"])
    if record.get("year"):
        parts.append(str(record["year"]))
    return " · ".join(parts)


def _record_links(record):
    links = []
    if record.get("doi"):
        doi_url = "https://doi.org/" + record["doi"]
        links.append(f'<a href="{_inline(doi_url)}">DOI</a>')
    if record.get("url"):
        links.append(f'<a href="{_inline(record["url"])}">Publication link</a>')
    if record.get("zotero_url"):
        links.append(f'<a href="{_inline(record["zotero_url"])}">Zotero item</a>')
    return " · ".join(links)


def generate_publications_page(snapshot):
    group_id = snapshot["source"]["group_id"]
    lines = [
        "---",
        'title: "Publications"',
        "page-layout: full",
        "toc: false",
        "comments: false",
        "---",
        "",
        '<div class="geoepi-publications">',
        '<p class="geoepi-eyebrow">SCIENTIFIC OUTPUTS</p>',
        "# Publications",
        "",
        f'GeoEpi publications are synchronized from the group\'s <a href="https://www.zotero.org/groups/{group_id}">public Zotero library</a>. Zotero remains the authoritative source for bibliographic metadata and abstracts.',
        "",
    ]
    publications = snapshot["publications"]
    grouped = {}
    for record in publications:
        grouped.setdefault(str(record["year"]) if record["year"] else "Undated", []).append(record)
    year_keys = sorted((key for key in grouped if key != "Undated"), key=int, reverse=True)
    if "Undated" in grouped:
        year_keys.append("Undated")
    for year in year_keys:
        lines.extend([f"## {year}", ""])
        for record in grouped[year]:
            lines.extend(
                [
                    '<article class="geoepi-publication">',
                    f'<h3>{_inline(record["title"])}</h3>',
                ]
            )
            if record.get("creator_display"):
                lines.append(f'<p class="geoepi-publication-creators">{_inline(record["creator_display"])}</p>')
            context = _publication_context(record)
            if context:
                lines.append(f'<p class="geoepi-publication-context">{_inline(context)}</p>')
            if record.get("formatted_reference"):
                lines.append(
                    f'<div class="geoepi-publication-reference">{record["formatted_reference"]}</div>'
                )
            link_html = _record_links(record)
            if link_html:
                lines.append(f'<p class="geoepi-publication-links">{link_html}</p>')
            visible_tags = [tag for tag in record.get("tags", []) if not tag.startswith("/")]
            if visible_tags:
                tags = "".join(
                    f'<span class="geoepi-publication-tag">{_inline(tag)}</span>'
                    for tag in visible_tags
                )
                lines.append(f'<div class="geoepi-publication-tags">{tags}</div>')
            if record.get("abstract"):
                lines.extend(
                    [
                        "",
                        '<details class="geoepi-publication-abstract">',
                        "<summary>Abstract</summary>",
                        f'<p>{_inline(record["abstract"])}</p>',
                        "</details>",
                    ]
                )
            lines.extend(["</article>", ""])
    if not publications:
        lines.append("No publications are currently listed in the public Zotero library.")
    lines.extend(["</div>", ""])
    return "\n".join(lines)


def snapshot_json(snapshot):
    normalized = copy.deepcopy(snapshot)
    normalized["publications"] = sorted(
        normalized["publications"],
        key=lambda record: (
            record["year"] is None,
            -(record["year"] or 0),
            record["title"].casefold(),
            record.get("key") or "",
        ),
    )
    return json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"


def replace_outputs(snapshot, repo_root=Path(".")):
    repo_root = Path(repo_root).resolve()
    staging = Path(tempfile.mkdtemp(prefix=".zotero-publications-", dir=repo_root))
    backups = []
    replaced_targets = []
    targets = [repo_root / "data" / "zotero-publications.json", repo_root / "publications.qmd"]
    try:
        staged = [staging / "zotero-publications.json", staging / "publications.qmd"]
        staged[0].write_text(snapshot_json(snapshot), encoding="utf-8", newline="\n")
        staged[1].write_text(generate_publications_page(snapshot), encoding="utf-8", newline="\n")
        targets[0].parent.mkdir(parents=True, exist_ok=True)
        for target in targets:
            if target.exists():
                backup = repo_root / f".{target.name}.zotero-backup-{os.getpid()}"
                os.replace(target, backup)
                backups.append((target, backup))
        for staged_file, target in zip(staged, targets):
            os.replace(staged_file, target)
            replaced_targets.append(target)
        for _, backup in backups:
            backup.unlink(missing_ok=True)
    except Exception:
        for target in replaced_targets:
            if target.exists():
                target.unlink()
        for target, backup in backups:
            if backup.exists():
                os.replace(backup, target)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def outputs_match(snapshot, repo_root=Path(".")):
    repo_root = Path(repo_root)
    snapshot_path = repo_root / "data" / "zotero-publications.json"
    page_path = repo_root / "publications.qmd"
    return (
        snapshot_path.is_file()
        and page_path.is_file()
        and snapshot_path.read_text(encoding="utf-8") == snapshot_json(snapshot)
        and page_path.read_text(encoding="utf-8") == generate_publications_page(snapshot)
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--page", default=str(DEFAULT_PAGE))
    parser.add_argument("--source-file")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.check:
        snapshot = validate_snapshot(json.loads(Path(args.snapshot).read_text(encoding="utf-8")))
        if outputs_match(snapshot):
            print("Generated Zotero publication sources are current.")
            return 0
        print("Generated Zotero publication sources are out of date.")
        return 1

    config = load_config(args.config)
    if args.source_file:
        items = load_source_items(args.source_file)
        pages = None
    else:
        items, pages = fetch_all_items(config)
    records, stats = normalize_items(items)
    snapshot = build_snapshot(records, config)
    validate_snapshot(snapshot)
    replace_outputs(snapshot)
    print(f"Retrieved top-level Zotero items: {stats['retrieved']}")
    print(f"Excluded non-bibliographic items: {stats['excluded']} {stats['excluded_types']}")
    print(f"Skipped malformed/title-less items: {sum(stats['skipped'].values())} {stats['skipped']}")
    print(f"Normalized publications: {stats['normalized']}")
    print(f"With abstracts: {stats['abstracts']}")
    print(f"With DOI values: {stats['dois']}")
    print(f"Without parseable year: {stats['without_year']}")
    print(f"Item types: {stats['item_types']}")
    if pages is not None:
        print(f"Zotero API pages retrieved: {pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
