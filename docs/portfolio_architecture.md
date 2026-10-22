# Architecture: official data to analytical reporting

The design keeps source lineage, quality decisions and reporting scope visible throughout the workflow. PostgreSQL performs the substantive transformations and analysis; Python supports acquisition, parsing and validation.

![Architecture from official data to Power BI](assets/architecture.svg)

| Layer | Responsibility | Reviewable implementation |
|---|---|---|
| Sources | Prices, reconciled volumes, generation and NSP history | [Source audit](source_audit.md) |
| Acquisition | Versioned immutable storage, SHA-256, rerun safety | [Ingestion design](ingestion_design.md), [Python modules](../src/) |
| Warehouse | Source-aligned staging, natural keys, UTC/local intervals, effective mappings | [Warehouse design](warehouse_design.md), [SQL](../sql/) |
| Quality | Block unexplained failures; retain known warnings and coverage | [DQ framework](data_quality_framework.md) |
| Marts | Separate National/Zone grains, pooled ratios, fixed thresholds, contiguous events | [Analytical design](analytics_design.md), [KPI dictionary](kpi_dictionary.md) |
| Investigation | Read-only SQL, saved outputs, month/hour comparisons, official context | [Findings](findings.md), [Analysis SQL](../sql/05_analysis/) |
| Reporting | Power Query imports, DAX, TMDL model, PBIR pages | [Native project](../powerbi/NZ_Electricity_Market.pbip), [Model specification](powerbi_model_spec.md) |

## Model decisions that prevent misleading totals

The core warehouse preserves three distinct grains: price at interval/pricing POC; reconciled volume at interval/POC/network/participant/flow; generation at interval/generator/POC/network. Effective NSP mapping does not overwrite source identity or backfill unknown history.

Power BI imports reporting marts rather than joining the three core facts directly. Eight single-direction relationships serve dates, intervals, Zones, events and source months. National and Zone facts are separate; threshold and benchmark tables stay disconnected where intended. Event membership applies through approved measures rather than a physical bridge to every fact. See the [relationship diagram](../powerbi/model_relationships.mmd).

## Release and validation boundaries

The accepted report is pinned to analytical refresh 38 and DQ run 5 for September 2025–August 2026. Publication selection, source versions and reference changes affect release validity. Import gates prevent silently displaying an incompatible release. Raw files, database storage, credentials and Power BI local cache are outside Git; a clone alone cannot restore the database or imported model cache.

This is a local portfolio implementation. No scheduled production service, gateway, Power BI Service deployment or operational alerting is claimed. [Reproducibility guide](reproducibility.md) · [Runtime acceptance](desktop_acceptance.md)
