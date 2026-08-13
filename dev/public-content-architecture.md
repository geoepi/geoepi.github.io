# GeoEpi public content architecture

This note records the intended direction for later website automation. It is
an internal development document and is not part of the public navigation.

## Source of truth

```text
GeoEpi Hub / canonical sources
                ↓
      website synchronization
                ↓
 generated public presentation
```

The group website should describe who GeoEpi is and what the group produces.
The GeoEpi Hub should describe current project activity and portfolio state.
The GeoEpi Lab Book should describe how the group works. The website should
not become another manually maintained source of project truth.

## Future research publication model

The current `projects/*/index.qmd` records are retained as a temporary Phase 1
content source. A future system should allow the GeoEpi Hub to own project
identity and public project context, while each canonical subproject repository
owns scientific implementation and detailed subproject documentation. The
group website would publish generated public-facing summaries.

One option to evaluate later is a project-level public record such as
`projects/<project_id>/public.yml` (or another clearly named metadata file)
with fields such as:

```yaml
schema_version:
project_id:
title:
short_summary:
abstract:
image:
keywords:
featured:
links:
```

This is an architectural proposal only. Do not add these fields to
`.geoepi.yml` Version 1. That file should remain portfolio-state metadata;
public research narrative belongs at the project/publication level. Project
scientists could update a Hub record through normal pull requests, and the
website could render those records automatically.

The Hub and subproject repositories are intentionally outside the scope of
this phase.

## Future Zotero publication model

The desired publication workflow is:

```text
GeoEpi Zotero group library
                ↓
 dedicated website collection/folder
                ↓
       Zotero API synchronization
                ↓
    generated publication metadata
                ↓
          Publications page
```

The Zotero library should remain the authoritative bibliographic source. A
later phase should determine the GeoEpi Zotero group/library ID, the collection
key or folder used for website publications, whether all items or only tagged
items appear, how preprints differ from published articles, how missing
abstracts are handled, and how projects/topics are tagged.

When available in Zotero, the generated metadata may include title, authors,
year/date, journal or source, DOI, URL, abstract, and citation metadata. The
website must never fabricate a missing abstract. No Zotero API integration,
credentials, or private keys are added in Phase 1.

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
