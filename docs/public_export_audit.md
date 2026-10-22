# Public snapshot audit

Reviewed 22 October 2026. This is a standalone file snapshot with **no .git directory or inherited commit history**. No public repository has been created and no visibility setting has changed.

## Included and excluded

Included: validated implementation, SQL, configuration, tests, native PBIP/TMDL/PBIR, portfolio documents, five genuine report screenshots, source manifests and useful derived validation evidence. The [file manifest](../PUBLIC_EXPORT_MANIFEST.json) records relative paths, sizes and SHA-256 values.

Excluded: development handoff and branch history, obsolete build/recovery documents, interrupted-run logs, superseded execution records, raw official files and five-row source extracts, PostgreSQL files/volumes, actual .env values, credentials, local Power BI caches, binary PBIX and private runtime screenshots. Notebook execution outputs were cleared to avoid exporting raw preview rows or local execution context; notebook code remains available.

Documentation now explains the completed implementation and practical reproduction requirements. The approved landing-page structure is retained. Career-facing language refers to regional pressure **not captured by the National P99 indicator**, not to failure of an official monitoring system. Analytical values are unchanged.

## Privacy and security review

- Independently scanned exported text and decompressed analytical JSON for personal absolute paths, usernames, email addresses, credentials, private keys, tokens and session identifiers. No unresolved sensitive candidates were found.
- A numeric match resembling a workstation identifier was confirmed to be part of a price numerator, not an identity; the analytical value was retained.
- .env.example contains a replacement placeholder, not a real password. Loopback addresses and the warehouse_owner role are generic local reconstruction defaults. They do not identify a private server or personal account.
- Native report/model GUIDs are artifact identifiers; source/publication/event IDs and release fingerprints are analytical lineage. They are not GitHub user, authentication or session identifiers. Operational development Git-reference fields were removed from selected exported evidence; source/data/SQL hashes remain.
- The schema-fetching code's project-relative cache location is a runtime destination, not an exported cache. No cache files are included.
- Five public screenshots retain the accepted genuine report pixels. They contain no visible personal information, credentials, local paths or unrelated desktop content. They have no EXIF fields; only generic JFIF density metadata is present. The [image manifest](assets/powerbi/manifest.json) records public-copy hashes.

This is a targeted publication audit, not a guarantee against every possible future disclosure. New files or edits require a new review.

## Fidelity and presentation QA

All **340 protected implementation files** checked against the approved snapshot are byte-identical: Python source, SQL, config, tests, Power BI sources and dependency/configuration files. No new analysis, feature, report regeneration or warehouse operation was performed.

README, case study, gallery and architecture were rendered from the exported tree in a local browser. All images loaded and no horizontal page overflow occurred. The README was visually inspected. Links and heading fragments were checked independently after documentation cleanup.

The change-only whitespace comparison against the approved snapshot passed using `git diff --no-index --check`. A whole-tree comparison against an empty directory also exposed 20 pre-existing final blank lines in Desktop-emitted TMDL files. Those harmless formatting lines are retained to preserve the exact accepted semantic-model source; they are not new export defects.

The largest retained file is the derived analytical import snapshot (7,858,229 bytes), not a raw official publication or private cache. Other sizes are listed in the manifest. Raw data and a loaded warehouse must be reconstructed separately for a fresh refresh; the code and stored validation results alone are not a portable live database.

## Publication decision

The snapshot is suitable to initialise as a **new** Git repository following owner approval. Do not copy development Git history into it. Suggested default branch is main; description/topics and the no-licence versus MIT choice are documented in [repository metadata](repository_metadata.md). No licence has been added. Official data and third-party material retain their own terms; a licence for original code would not relicense them.
