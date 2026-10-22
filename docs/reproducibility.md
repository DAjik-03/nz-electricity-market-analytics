# Reproducibility and review

## Review without a database

Read the [case study](portfolio_case_study.md), [findings](findings.md), [KPI dictionary](kpi_dictionary.md) and [Desktop acceptance](desktop_acceptance.md). Source code, tests, publication manifests and derived analytical evidence are included. Raw publications, five-row raw extracts, database files, credentials, private runtime captures and Power BI import caches are excluded.

The saved [103-test result](../outputs/analysis/full_test_results.json) and [analysis validation](analysis_validation.md) document executed checks. They are not claims that every test can run without its raw/database dependencies. Public export does not rerun expensive analytical suites.

## Reconstructing a local environment

Use Python 3.12, PostgreSQL 17 and a compatible Power BI Desktop. Create a virtual environment and install requirements.txt plus the relevant requirements-warehouse.txt / requirements-powerbi.txt for the layer being used. Docker Compose supplies a local PostgreSQL service. Copy .env.example to ignored .env and replace its placeholder password locally. The loopback endpoint and warehouse_owner role are local development defaults, not private server credentials.

Raw files must be restored or reacquired from the official URLs recorded in the manifests. Exact historic restoration requires bytes matching the pinned hashes; a publisher revision must fail validation rather than silently replace an approved source. Git alone cannot restore a historical database or source version.

The [ingestion design](ingestion_design.md) explains versioning, eligible-month rules and effective mapping. The [warehouse design](warehouse_design.md) explains transactions and selected versions. For a fresh reconstruction, inspect the supplied CLI help before running acquisition/load commands:

```text
python src/run_historical_scale_up.py --help
python src/run_warehouse.py --help
python src/run_data_quality.py --help
python src/run_analytics.py --help
```

The historical configuration covers September 2025-August 2026. Original three-month pilot commands are not a substitute for this release. Use an isolated fresh database for reconstruction; preserve any existing Docker volume. Database suites and raw-source tests require those fixtures to exist.

## Targeted review checks

```text
python src/validate_findings.py
python powerbi/validate_native_project.py
python -m unittest discover -s tests -p test_native_powerbi.py -v
```

The native validator requires a Microsoft schema cache, obtained using powerbi/fetch_pbip_schemas.py. The public visualContainer 2.14 schema was unavailable at acceptance; references and actual Desktop runtime were checked separately. Do not downgrade the emitted report to an older schema.

Open powerbi/NZ_Electricity_Market.pbip in Desktop; acceptance used Store 2.159.883.0. A fresh clone has no import cache and must connect to a reconstructed compatible warehouse before refresh. Enter credentials only in Desktop. Do not run the construction generator over the accepted report definitions merely to open them.

## Export boundaries

The implementation and accepted Power BI source are unchanged. Documentation is rewritten for public review, and development Git-reference fields are omitted from selected evidence metadata. Numerical results, source hashes, SQL hashes and release fingerprints are retained. The [public export audit](public_export_audit.md) distinguishes snapshot review from runtime testing; the [file manifest](../PUBLIC_EXPORT_MANIFEST.json) lists the intended files.
