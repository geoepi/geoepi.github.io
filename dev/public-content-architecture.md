# GeoEpi public content architecture

This note records the implemented and planned website content automation. It
is an internal development document and is not part of the public navigation.

## Source of truth

```text
GeoEpi Hub / canonical sources
                |
      website synchronization
                |
 generated public presentation
```

The group website should describe who GeoEpi is and what the group produces.
The GeoEpi Hub should describe current project activity and portfolio state.
The GeoEpi Lab Book should describe how the group works. The website should
not become another manually maintained source of project truth.

## Hub-generated research publishing

The first research publishing path is implemented:

```text
Hub projects/<project_id>/public.yml
                |
      Hub generated/public-research.json
                |
 website data/hub-public-research.json
                |
       generated research/<project_id>/index.qmd
                |
             Research page
```

The Hub is authoritative for public project identity and narrative. Its
`public.yml` Version 1 schema is separate from `.geoepi.yml` Version 1, which
remains portfolio-state metadata. Only `publish: true` records enter the
public feed. `content_status: scaffold` identifies wording that still needs
project-level review; `content_status: reviewed` indicates that a scientist
has reviewed the public record.

To update a public project description:

1. Edit `projects/<project_id>/public.yml` in `geoepi/geoepi-hub`.
2. Validate and merge the Hub change.
3. Allow or manually run Hub synchronization.
4. Allow or manually run website research synchronization.
5. Verify the generated Research page.

The website consumes the committed snapshot at
`data/hub-public-research.json` and generated pages under `research/`. Do not
edit generated website `research/` pages directly. The authoritative editable
record is the Hub `public.yml`; the website sync workflow retrieves the public
Hub feed explicitly and does not fetch it during ordinary Quarto rendering.

Legacy `projects/*` pages remain rendered for historical URLs and redirects,
but they no longer power the Research listing.

The Hub and subproject repositories remain separate from the website source;
scientific implementation and detailed analytical provenance stay in the
canonical subproject repositories.

## Zotero publication publishing — Phase 3A implemented

The basic public publication workflow is implemented:

```text
GeoEpi public Zotero group (6637692)
                |
       Zotero Web API v3
                |
 data/zotero-publications.json
                |
       publications.qmd
                |
          Publications page
```

Zotero is the authoritative bibliographic source. Website publication files
are generated; maintainers and scientists should edit Zotero rather than
`publications.qmd`. Abstracts are displayed only when present in Zotero, and
the website never fabricates or externally enriches a missing abstract. The
public group requires no credentials while it remains public.

The entire group library is currently used because the group is dedicated to
GeoEpi publications. The source configuration uses `collection_key: null`; a
future specific collection key can switch the endpoint without redesigning
the publication system.

To publish an item, add or correct it in the public Zotero group, then allow
the daily **Sync GeoEpi publications** workflow to retrieve the API v3 feed or
run it manually. The committed snapshot and generated Publications page keep
ordinary rendering and pull-request validation offline-safe.

## Future People page

The future People page should be generated from a structured source rather
than requiring HTML or Quarto layout edits for each person. A possible record
could include name, role, photo, short research interests, GitHub, ORCID,
Google Scholar, other appropriate professional links, and active projects.
People are not populated in this phase, and group membership should not be
inferred from GitHub organization membership.

## Future Software & Tools page

A future Software & Tools page should highlight intentionally reusable GeoEpi
outputs such as R packages, scientific software, modeling frameworks,
reusable data-acquisition tools, tutorials, and analytical frameworks. The
page should use an authoritative curated source; it should not automatically
treat every GitHub repository as software.
