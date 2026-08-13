# GeoEpi Research Group website

The public site is a Quarto website published from the generated `docs/`
directory: [GeoEpi Website](https://geoepi.github.io/).

- Research pages are synchronized from public metadata in
  [GeoEpi Hub](https://github.com/geoepi/geoepi-hub).
- Publications are synchronized from the public GeoEpi Zotero group.
- Generated research, publication, and `docs/` files should not be hand-edited;
  use the synchronization scripts and rerender the site instead.

Page design inspired by [Quantum Jitter](https://www.quantumjitter.com/).

## Maintainer note: publications

To add a publication to the website:

1. Add or move the bibliographic item into the public GeoEpi Zotero group.
2. Ensure its metadata are correct in Zotero.
3. Add the abstract in Zotero if the abstract should appear publicly.
4. Allow the daily publication sync to run or manually run **Sync GeoEpi publications**.
5. Verify the website.

Do not edit generated `data/zotero-publications.json` or `publications.qmd`
directly; Zotero is the authoritative bibliographic source.
