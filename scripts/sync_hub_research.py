#!/usr/bin/env python3

"""Synchronize Hub public research JSON into generated Quarto pages."""

import argparse
import copy
import html
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen


DEFAULT_SOURCE_URL = (
    "https://raw.githubusercontent.com/geoepi/geoepi-hub/main/"
    "generated/public-research.json"
)
SCHEMA_VERSION = 1
CONTENT_STATUS_VALUES = {"scaffold", "reviewed"}
THEME_VALUES = {"geography", "epidemiology", "modeling", "ecology"}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OPERATIONAL_FIELDS = {
    "lead_name",
    "lead_github",
    "current_focus",
    "compute",
    "next_milestone",
    "milestone_target",
    "metadata_stale",
    "milestone_overdue",
    "overdue",
}


def _https_url(value):
    return isinstance(value, str) and value.startswith("https://") and len(value) > 8


def validate_feed(feed):
    """Return structural validation errors for a Hub public feed."""
    errors = []
    if not isinstance(feed, dict):
        return ["feed root must be a mapping"]
    if feed.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must equal 1")
    if not isinstance(feed.get("source"), str) or not feed["source"].strip():
        errors.append("source must be a non-empty string")
    projects = feed.get("projects")
    if not isinstance(projects, list):
        return errors + ["projects must be a list"]

    seen_projects = set()
    for index, project in enumerate(projects):
        prefix = f"projects[{index}]"
        if not isinstance(project, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        project_id = project.get("project_id")
        if not isinstance(project_id, str) or not ID_RE.fullmatch(project_id):
            errors.append(f"{prefix}.project_id is invalid")
        elif project_id in seen_projects:
            errors.append(f"{prefix}.project_id is duplicated: {project_id}")
        seen_projects.add(project_id)
        for field in ("title", "short_summary", "abstract", "hub_url"):
            if not isinstance(project.get(field), str) or not project[field].strip():
                errors.append(f"{prefix}.{field} is required")
        if not _https_url(project.get("hub_url")):
            errors.append(f"{prefix}.hub_url must be an HTTPS URL")
        if project.get("content_status") not in CONTENT_STATUS_VALUES:
            errors.append(f"{prefix}.content_status is invalid")
        if not isinstance(project.get("themes"), list):
            errors.append(f"{prefix}.themes must be a list")
        else:
            for theme in project["themes"]:
                if theme not in THEME_VALUES:
                    errors.append(f"{prefix}.themes contains invalid theme: {theme!r}")
        if not isinstance(project.get("keywords"), list) or not all(
            isinstance(keyword, str) for keyword in project["keywords"]
        ):
            errors.append(f"{prefix}.keywords must be a list of strings")
        if type(project.get("featured")) is not bool:
            errors.append(f"{prefix}.featured must be a boolean")
        if project.get("image") is not None and not _https_url(project["image"]):
            errors.append(f"{prefix}.image must be null or an HTTPS URL")
        if not isinstance(project.get("links"), list):
            errors.append(f"{prefix}.links must be a list")
        else:
            for link_index, link in enumerate(project["links"]):
                if not isinstance(link, dict):
                    errors.append(f"{prefix}.links[{link_index}] must be a mapping")
                    continue
                if not isinstance(link.get("label"), str) or not link["label"].strip():
                    errors.append(f"{prefix}.links[{link_index}].label is required")
                if not _https_url(link.get("url")):
                    errors.append(
                        f"{prefix}.links[{link_index}].url must be an HTTPS URL"
                    )
        for field in OPERATIONAL_FIELDS:
            if field in project:
                errors.append(f"{prefix} contains operational field: {field}")

        subprojects = project.get("subprojects")
        if not isinstance(subprojects, list):
            errors.append(f"{prefix}.subprojects must be a list")
            continue
        seen_subprojects = set()
        for sub_index, subproject in enumerate(subprojects):
            sub_prefix = f"{prefix}.subprojects[{sub_index}]"
            if not isinstance(subproject, dict):
                errors.append(f"{sub_prefix} must be a mapping")
                continue
            subproject_id = subproject.get("subproject_id")
            if not isinstance(subproject_id, str) or not ID_RE.fullmatch(subproject_id):
                errors.append(f"{sub_prefix}.subproject_id is invalid")
            elif subproject_id in seen_subprojects:
                errors.append(f"{sub_prefix}.subproject_id is duplicated")
            seen_subprojects.add(subproject_id)
            for field in ("title", "summary", "repository", "repository_url"):
                if not isinstance(subproject.get(field), str):
                    errors.append(f"{sub_prefix}.{field} must be a string")
            if not _https_url(subproject.get("repository_url")):
                errors.append(f"{sub_prefix}.repository_url must be an HTTPS URL")
            if "status" in subproject and not isinstance(subproject["status"], str):
                errors.append(f"{sub_prefix}.status must be a string")
            for field in OPERATIONAL_FIELDS:
                if field in subproject:
                    errors.append(f"{sub_prefix} contains operational field: {field}")
    return errors


def load_feed(source_url=DEFAULT_SOURCE_URL, source_file=None):
    if source_file:
        payload = Path(source_file).read_bytes()
    else:
        request = Request(
            source_url,
            headers={"Accept": "application/json", "User-Agent": "geoepi-website"},
        )
        with urlopen(request, timeout=30) as response:
            payload = response.read()
    feed = json.loads(payload.decode("utf-8"))
    errors = validate_feed(feed)
    if errors:
        raise ValueError("Invalid public research feed:\n- " + "\n- ".join(errors))
    return feed


def _inline(value):
    return html.escape(str(value), quote=True)


def _yaml_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def generate_project_page(project):
    """Return deterministic Quarto source for one feed project."""
    themes = project["themes"]
    categories = json.dumps(themes, ensure_ascii=False)
    lines = [
        "---",
        f"title: {_yaml_string(project['title'])}",
        f"description: {_yaml_string(project['short_summary'])}",
        f"categories: {categories}",
        f"content_status: {project['content_status']}",
        "page-layout: full",
        "comments: false",
    ]
    if project.get("image"):
        lines.append(f"image: {_yaml_string(project['image'])}")
    lines.extend(
        [
            "---",
            "",
            '<div class="geoepi-generated-project">',
            '<p class="geoepi-eyebrow">HUB-GENERATED RESEARCH</p>',
            f"# {_inline(project['title'])}",
        ]
    )
    if project["content_status"] == "scaffold":
        lines.extend(
            [
                "",
                '<p class="geoepi-scaffold-status">Scaffold project summary</p>',
                "",
                '<p class="geoepi-scaffold-note">This summary was assembled from current GeoEpi project metadata and is pending project-level review.</p>',
            ]
        )
    lines.extend(
        [
            "",
            f"<p class=\"geoepi-project-summary\">{_inline(project['short_summary'])}</p>",
            "",
            "## Abstract",
            "",
            project["abstract"],
            "",
            "## Themes and topics",
            "",
            '<div class="geoepi-project-tags">',
        ]
    )
    for theme in project["themes"]:
        lines.append(f'<span class="geoepi-project-tag">{_inline(theme)}</span>')
    for keyword in project["keywords"]:
        if keyword not in project["themes"]:
            lines.append(f'<span class="geoepi-project-tag">{_inline(keyword)}</span>')
    if not project["themes"] and not project["keywords"]:
        lines.append("<span>No topics recorded.</span>")
    lines.extend(["</div>", "", "## Associated subprojects", ""])
    if project["subprojects"]:
        lines.append('<div class="geoepi-subproject-grid">')
        for subproject in project["subprojects"]:
            lines.extend(
                [
                    '<article class="geoepi-subproject-card">',
                    f"### {_inline(subproject['title'])}",
                    "",
                    _inline(subproject["summary"]) or "Summary not provided.",
                    "",
                    f'<a href="{_inline(subproject["repository_url"])}">Canonical repository <span aria-hidden="true">&#8599;</span></a>',
                    "",
                    "</article>",
                ]
            )
        lines.append("</div>")
    else:
        lines.append("No registered subprojects are currently included in the public feed.")

    if project["links"]:
        lines.extend(["", "## Public links", ""])
        for link in project["links"]:
            lines.append(f'- [{_inline(link["label"])}]({_inline(link["url"])})')
    lines.extend(
        [
            "",
            f'<p class="geoepi-authority-link"><a href="{_inline(project["hub_url"])}">Authoritative Hub project record <span aria-hidden="true">&#8599;</span></a></p>',
            "</div>",
            "",
        ]
    )
    return "\n".join(lines)


def snapshot_json(feed):
    normalized = copy.deepcopy(feed)
    normalized["projects"] = sorted(
        normalized["projects"], key=lambda project: project["project_id"]
    )
    for project in normalized["projects"]:
        project["subprojects"] = sorted(
            project["subprojects"], key=lambda subproject: subproject["subproject_id"]
        )
    return json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"


def _staged_outputs(feed, staging_root):
    research_dir = staging_root / "research"
    data_dir = staging_root / "data"
    research_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    for project in sorted(feed["projects"], key=lambda item: item["project_id"]):
        project_dir = research_dir / project["project_id"]
        project_dir.mkdir()
        (project_dir / "index.qmd").write_text(
            generate_project_page(project), encoding="utf-8", newline="\n"
        )
    (data_dir / "hub-public-research.json").write_text(
        snapshot_json(feed), encoding="utf-8", newline="\n"
    )
    return research_dir, data_dir / "hub-public-research.json"


def replace_generated_sources(feed, repo_root=Path(".")):
    """Atomically replace generated research sources after full validation."""
    repo_root = Path(repo_root).resolve()
    staging_parent = Path(tempfile.mkdtemp(prefix=".hub-research-sync-", dir=repo_root))
    backup_dir = None
    try:
        staging_research, staging_snapshot = _staged_outputs(feed, staging_parent)
        target_research = repo_root / "research"
        target_snapshot = repo_root / "data" / "hub-public-research.json"
        target_snapshot.parent.mkdir(parents=True, exist_ok=True)
        if target_research.exists():
            backup_dir = repo_root / f".research-backup-{os.getpid()}"
            os.replace(target_research, backup_dir)
        os.replace(staging_research, target_research)
        os.replace(staging_snapshot, target_snapshot)
        if backup_dir and backup_dir.exists():
            shutil.rmtree(backup_dir)
    except Exception:
        target_research = repo_root / "research"
        if target_research.exists():
            shutil.rmtree(target_research)
        if backup_dir and backup_dir.exists():
            os.replace(backup_dir, target_research)
        raise
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)


def outputs_match(feed, repo_root=Path(".")):
    repo_root = Path(repo_root)
    snapshot = repo_root / "data" / "hub-public-research.json"
    if not snapshot.exists():
        return False
    if snapshot.read_text(encoding="utf-8") != snapshot_json(feed):
        return False
    expected = {
        project["project_id"]: generate_project_page(project)
        for project in feed["projects"]
    }
    research_dir = repo_root / "research"
    if not research_dir.exists():
        return False
    actual_ids = {path.name for path in research_dir.iterdir() if path.is_dir()}
    if actual_ids != set(expected):
        return False
    for project_id, content in expected.items():
        page = research_dir / project_id / "index.qmd"
        if not page.is_file() or page.read_text(encoding="utf-8") != content:
            return False
    return True


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    source.add_argument("--source-file")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the feed and fail if committed generated sources are stale",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    feed = load_feed(args.source_url, args.source_file)
    if args.check:
        if outputs_match(feed):
            print("Generated Hub research sources are current.")
            return 0
        print("Generated Hub research sources are out of date.")
        return 1
    replace_generated_sources(feed)
    print(f"Synchronized {len(feed['projects'])} generated research project(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
