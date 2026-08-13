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

## Hub-generated research publishing

The first research publishing path is implemented:

```text
Hub projects/<project_id>/public.yml
                ↓
      Hub generated/public-research.json
                ↓
 website data/hub-public-research.json
                ↓
       generated research/<project_id>/index.qmd
                ↓
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
credentials, or private keys are added in Phase 2.

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
