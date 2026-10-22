# Official source audit and data contracts

Audit date: 11 September 2026, Pacific/Auckland. Historical scope: one recent file from each of four core Electricity Authority sources. source-audit is complete. The subsequently approved pilot is documented in [bounded-pilot validation](release_validation.md); the findings below retain their original sample scope.

## Decision summary

Review update, 19 September 2026: the controlled bounded-pilot pilot is complete. [Current gate status](release_validation.md) recommends pilot-scope closure of PRE01/03/04/05 and retains PRE02's invalid historical DST boundaries. warehouse remains on hold. This update does not reinterpret the original August sample as historical validation.

The proposed price/demand/generation architecture is feasible, but its grains and geographical relationships require changes. Prices have a complete August panel and every observed reconciliation record can be priced. Generation must retain connection/network detail before plant aggregation. NSP is a history table, not a unique node lookup. Use effective periods and preserve unmatched or ambiguous geography.

The latest common **published and calendar-covered** month found in this audit is **August 2026**. All three fact sources cover 1–31 August, and all 1,488 date/TP combinations occur. This is not certification of complete participant/plant coverage: reconciliation is sparse, four generation series have fewer than 31 days, and reconciliation remains revision-eligible. No earlier fully certified common month can be established from one sample per source. The release eligibility rule separately assesses file availability, date/period coverage, sparse activity, revision finality and mapping coverage. Do not call this a finalised settlement dataset.

## Official sources and retained samples

| Source | Official dataset | File actually downloaded | Rows × columns |
|---|---|---|---:|
| A — Prices | [Final energy prices, ByMonth](https://www.emi.ea.govt.nz/Wholesale/Datasets/DispatchAndPricing/FinalEnergyPrices/ByMonth) | `202608_FinalEnergyPrices.csv` | 366,048 × 4 |
| B — Reconciliation | [Reconciled injections and offtake](https://www.emi.ea.govt.nz/Wholesale/Datasets/Volumes/Reconciliation), [2026 files](https://www.emi.ea.govt.nz/Wholesale/Datasets/Volumes/Reconciliation/2026) | `ReconciledInjectionAndOfftake_202608_20260908_125215.csv.gz` | 6,403,492 × 9 |
| C — Generation | [Generation output by plant](https://www.emi.ea.govt.nz/Wholesale/Datasets/Generation/Generation_MD) | `202608_Generation_MD.csv` | 3,157 × 57 |
| D — NSP | [Network supply points table](https://www.emi.ea.govt.nz/Wholesale/Datasets/MappingsAndGeospatial/NetworkSupplyPointsTable) | `20260910_NetworkSupplyPointsTable.csv` | 2,617 × 27 |

The direct HTTP listings were fresher than the web search cache: NSP was 10 September, not the cached 8 September snapshot; reconciliation's HTTP Last-Modified was 10 September. The acquisition script followed the EMI download links to the official `emidatasets.blob.core.windows.net/publicdata` storage. The [EA access guidance](https://forum.emi.ea.govt.nz/thread/new-access-arrangements-to-emi-datasets-retirement-of-anonymous-ftp/) documents this endpoint. Public file links worked without credentials.

Original CSV/gzip bytes are unchanged and ignored by Git under `data/raw/<source>/<sha256>/<filename>`. The full [source manifest](../outputs/audit/source_manifest.json) records original and resolved URLs, filename, period, HTTP Last-Modified, ETag, preparation timestamp where present, UTC retrieval time, byte size, SHA-256 and local path. The four files total 44,743,254 bytes. Listing metadata and candidate month are in [source_discovery.json](../outputs/audit/source_discovery.json). Full local listing snapshots are ignored under `data/reference`; compact metadata is versioned. Five-row CSV extracts in `data/sample` are convenience examples, not representative statistical samples.

Reconciliation preparation time is `2026-09-08T12:52:15`, parsed from the filename. Its timezone is not specified by the filename and is deliberately not assigned UTC. Preparation time, HTTP modification time and retrieval time are different attributes. The official source allows revisions for up to 14 months and publishes an initial file by the seventh business day of the following month. A preparation timestamp alone does not identify the revision cycle. Record this sample as revision-eligible, not formally final.

## Actual schemas and natural keys

The [field dictionary](data_dictionary.md) lists every source column, storage recommendation, null count and example. [profiles.json](../outputs/audit/profiles.json) contains full-file profiles. All four files parse as comma-separated UTF-8 text (gzip for reconciliation). ISO dates use `YYYY-MM-DD`; identifiers must remain strings, including Unicode plant names and region labels.

### A — Final prices

Fields: `TradingDate`, `TradingPeriod`, `PointOfConnection`, `DollarsPerMegawattHour`.

Natural key within the selected source version: **TradingDate + TradingPeriod + PointOfConnection**. All 246 POCs have all 31 × 48 = 1,488 periods. No missing cells, duplicate keys, non-finite measures or negative prices were observed. Ten prices are zero; maximum is NZD 4,644.05/MWh. Retain extremes; this is a profile, not a price-event finding.

The [price source notes](https://www.emi.ea.govt.nz/Wholesale/Datasets/DispatchAndPricing/FinalEnergyPrices) distinguish interim `_I` files from final prices. Monthly file discovery must also inspect explicit incomplete markers: the listing contains `202512_FinalEnergyPrices_incomplete.csv`. Consequently a 2024–2026 historical run cannot assume every monthly filename is complete. The page's annual-packaging description differs from the currently available monthly 2026 files; discover actual files rather than encode that prose as a schedule.

### B — Reconciled volumes

Fields: `PointOfConnection`, `Network`, `Island`, `Participant`, `TradingDate`, `TradingPeriod`, `TradingPeriodStartTime`, `FlowDirection`, `KilowattHours`.

Natural key within one source version: **TradingDate + TradingPeriod + PointOfConnection + Network + Participant + FlowDirection**. It is unique. Using only date/TP/POC creates 6,077,589 duplicate rows beyond the first; these are separate participant/network/flow observations, not records to remove. There are 221 POCs, 60 networks and 74 participants. FlowDirection contains `Offtake` and `Injection`. All fields are populated; all energy values are positive, with no zeros in this sample.

| Flow | Source rows | kWh | GWh |
|---|---:|---:|---:|
| Offtake | 5,127,614 | 3,950,896,316 | 3,950.896316 |
| Injection | 1,275,878 | 4,117,158,550 | 4,117.158550 |

These are separate flows. Their combined sum is not demand. Preserve both in a reconciled-volume fact; expose offtake through a clearly labelled demand view. Observed quantities are loss-adjusted wholesale settlement energy, not household end-use consumption. [EA's reconciliation explanation](https://forum.emi.ea.govt.nz/thread/reconciled-demand-understanding/) explains the distribution-loss adjustment and exclusion of behind-the-meter self-consumption. Transmission losses are a different concept.

`TradingPeriodStartTime` is only an `HH:MM` label without date or offset. It matches all 1,488 August calendar positions, but is not a unique timestamp. Sparse participant/flow series are not proven missing-data errors or proven zeroes. Retain absence as unknown until zero-suppression, participant activity and publication completeness are understood.

The actual EMI column is **KilowattHours**. The underlying [GR-010 functional specification, section 8.32](https://www.ea.govt.nz/documents/7030/RM_FS_15.1.pdf) describes both participant kWh files and clearing-manager kW files. Do not apply the kW layout to this normalised EMI extract merely because both are called GR-010.

### C — Generation

Fields: `Site_Code`, `POC_Code`, `Nwk_Code`, `Gen_Code`, `Fuel_Code`, `Tech_Code`, `Trading_Date`, and **TP1 through TP50**. Each row is a connection/plant/day series; TP columns contain kWh.

The tested unique daily key is **Trading_Date + POC_Code + Nwk_Code + Gen_Code**. Keep all six identifier/classification columns in staging and test their functional dependencies over history. The sample contains 91 plant names, 88 POCs, 75 sites, 38 networks and 103 connection/fuel/technology series. Plant/date alone has 372 duplicates beyond the first (713 rows participate in collisions). Eleven plant names have multiple connection series. An [EA response on plant identifiers](https://forum.emi.ea.govt.nz/thread/report-q-generation-output-by-plant-how-to-identify-unique-plant-understand-duplicates/) confirms that multiple plants can share a POC and plants can change connections.

For August, TP1–TP48 contain 151,536 non-null observations, including 42,069 zero values. TP49 and TP50 are null in all 3,157 rows: **structural non-applicability, not missing generation**. No negative values were observed. Total listed output is 3,932,434,942 kWh. Preserve zero observations and investigate absent rows separately.

Four series have fewer than 31 dates:

| Series | Days present | Interpretation / treatment |
|---|---:|---|
| highbank / ASB0661 / EASH | 30 | Missing 1 August; reason not established |
| huntly_1_4 / HLY2201 / GENE / Coal | 30 | One absent day; reason not established |
| huntly_p40 / HLY2201 / GENE | 11 | Sparse output rows; no proof that absent days are zero |
| clandeboye_solar_farm / TMK0331 / ALPE | 17 | Begins 15 August, coinciding with an NSP version boundary; this is evidence of timing, not proof of commissioning |

The series uses 13 fuel labels and 11 technology labels. Labels include `Hydro/HYD`, `Solar/SOL`, `Wind/WIN`, `Geo/GEO`, and `ELE/BAT`. A proposed, reviewable alias crosswalk is in [model recommendations](warehouse_design.md); it is not an official code dictionary. Preserve original codes and fail classification gracefully for new values. Source code drift has happened before, as recorded in [EA's generation code discussion](https://forum.emi.ea.govt.nz/thread/changes-in-tech-codes-for-generation-md-files-causing-automation-errors/).

Three ELE/BAT series total 6,491,377 kWh. The implemented crosswalk treats ELE/BAT as Storage; do not automatically classify battery output as renewable primary generation. A recommended renewable-share denominator excludes storage and separately reports unclassified output. The implemented definitions are in the KPI dictionary.

The official dataset estimates plant output by allocating metered injections; it is not a comprehensive gross-generation census. Listed plant output is 184,723,608 kWh below reconciled injections (about 4.49%). This is a coverage/definition difference to investigate, not a balancing failure to force to zero. Do not add the two generation measures together or claim independence between them.

### D — Network supply points

The actual table has 27 fields, including NSP identity, replacement links, POC/network, embedded parent POC/network, reconciliation type, flow flags, description, NZTM coordinates, network reporting region, Zone, Island, start date/TP, end date/TP, and metering/participant metadata.

**NSP + Start date + Start TP** is unique within the snapshot. NSP alone has 1,466 duplicate rows beyond the first; POC alone has 1,734. There are 1,151 NSP identifiers and 883 POC codes. No overlapping intervals within the same NSP or reversed intervals were found using the source start/end ordering.

There are 13 future-starting records after the snapshot date despite `Current flag = 1`. Use validity at the observation date/TP, not Current flag, for historical joins. Source End date/TP is treated as inclusive for this audit, supported by adjoining rows such as TMK0331ALPEGN ending 14 August TP48 and restarting 15 August TP1. This convention must be independently confirmed or tested with transition/boundary samples before warehouse constraints are finalised. Store a converted exclusive UTC end in the warehouse while retaining original boundaries.

Five rows lack Zone and network reporting region; 596 lack both coordinate fields. Coordinates are NZTM eastings/northings, not latitude/longitude. A map requires a verified coordinate reference system and explicit conversion. No map was built.

## Join feasibility and measured coverage

All figures below come from [mapping_and_time.json](../outputs/audit/mapping_and_time.json) and corresponding exception CSVs. Joins compare full POC codes, never three-letter site-prefix guesses. Validity uses both source date and TP. Region uniqueness counts null as an unresolved value; multiple matching NSPs are safe to collapse to a zone only when every candidate has the same non-null zone.

| Candidate relationship | Observed result | Decision |
|---|---|---|
| Reconciliation → price on POC/date/TP | All 221 POCs; all 552,435 point/network/flow/TP aggregates match; no fanout; 100% observed offtake kWh priced | National demand weighting is feasible for this sample, using offtake only |
| Reconciliation → NSP on POC/network/effective interval | Every aggregate matches exactly one NSP; all 6,403,492 source rows covered | Preserve the composite bridge; no Current flag filter |
| Generation → NSP on POC/network/effective interval | All 151,536 long observations match exactly one NSP | Retain connection-level fact grain |
| Price → NSP on POC/effective interval | 22 nodes have no NSP match; 22 have multiple matches | Price identity and NSP identity must be separate |
| Price → unambiguous Zone | 220/246 nodes, 327,360/366,048 observations (89.43%) | Preserve unknown price geography; disclose denominator |
| Price → unambiguous network reporting region | 214/246 nodes, 318,432 observations (86.99%) | Prefer Zone for initial market comparisons; network regions are not interchangeable with zones or councils |
| Reconciliation offtake → Zone | 3,943,869,345 / 3,950,896,316 kWh (99.8221%) | Retain 7,026,971 kWh in Unknown; do not silently omit |
| Generation → Zone | 148,560/151,536 observations; 56,117,354 kWh lack Zone | Report Unknown generation explicitly |
| Generation → price directly | WPG0331 unmatched, containing 21,457,001 kWh | Official NSP parent route is required for grid price context |

NSP identifies WPG0331/TRPG as embedded under HWB0331/DUNE. The route leaves all 151,536 generation observations with exactly one matching grid price and no unmatched kWh. It does not relocate the plant's geography or make an exact plant settlement valuation. A future general parent resolver needs effective dates, cycle detection, multi-level traversal, and explicit ambiguity handling.

Missing active regional metadata affects GLN0332/CTCT, HAM0331/RUAK, KAW2201/TAOM and WAI0331/HEDL. A fifth missing-region NSP (ERA0011/EDCL) starts in October. Do not copy a neighbouring node's region or use a name-based guess. Missing zone does not mean missing Island: reconciliation Island and matching NSP Island agree throughout this sample. National and island monitoring can therefore be more complete than zone reporting.

NSP I/X flags disagree with 75,679 observed point/network/flow/TP aggregates, totalling 38,750,285 kWh. These flags are not used as a row-deletion rule. Their relationship to reconciled participant volumes, embedded flow aggregation and current metadata requires clarification. The disagreement export is retained for investigation.

For regional demand weighting, use the matched reconciliation connection's Zone and the same POC's price, aggregate each participant's offtake once, and retain an Unknown group. This avoids requiring a unique network region for every price-only node. Publish matched-energy coverage alongside the weighted price. Do not join a price table directly to multiple NSP rows and average the expanded result.

## Trading periods, DST and units

The [EA trading-period guidance](https://forum.emi.ea.govt.nz/thread/daylight-saving-time-and-trading-periods/) defines consecutive half-hour periods through clock changes. Use IANA `Pacific/Auckland`, not a permanent UTC+12 offset. Create date-specific intervals by converting local midnight and the next local midnight to UTC, then stepping by 30 minutes **in UTC**. Derive local endpoints, offset, DST status and repeated-hour fold from those UTC instants.

| Date | Expected periods | Key behaviour |
|---|---:|---|
| 7 April 2024 / 6 April 2025 / 5 April 2026 | 50 | Repeated 02:00 hour has distinct UTC instants |
| 29 September 2024 / 28 September 2025 / 27 September 2026 | 46 | Local 02:00–02:59 does not occur |
| 1 August 2026 | 48 | Normal winter day |

On 5 April 2026, TP5 starts 02:00+13:00 and TP7 starts 02:00+12:00. On 27 September 2026, TP4 starts 01:30+12:00 and TP5 starts 03:00+13:00. Both remain real 30-minute intervals. Endpoints may appear to jump forwards or backwards on the local clock. Store `trading_date`, `trading_period`, `start_utc`, `end_utc`, local endpoints, timezone and offset; local timestamp alone must never be unique. Price events use UTC continuity, not local-clock differences.

The offline calendar passed continuity and duration checks for every day in 2024–2026 and matched all August source time labels. [Trading-period examples](../outputs/audit/trading_period_examples.csv) retain the boundary cases. **No actual DST-transition market file was downloaded in this one-file-per-core-source audit.** Tests of the calendar prove the algorithm, not a future parser's handling of source transition rows. Require actual April and September source examples before scaling ingestion.

Units are explicit: price NZD/MWh; reconciled energy kWh; generation TP energy kWh. Convert kWh to MWh by dividing by 1,000; to GWh by 1,000,000; interval-average MW = MWh / interval duration hours, or kWh / 500 for these half-hour intervals. Peak Demand will mean maximum aggregate interval-average offtake MW, not a peak participant record or instantaneous metered demand. Never sum MW over time and label it energy.

## Data quality risk register

Statuses describe actual evidence, not a claim that every risk is resolved. High confidence refers to the measured sample evidence; causes may still be unknown.

| ID | Severity / dimension | Evidence and status | Business implication / treatment |
|---|---|---|---|
| DQ01 | High — grain | Plant/date collisions: 372 excess rows; confirmed | Connection-level generation fact, explicit later aggregation; do not deduplicate by plant |
| DQ02 | High — integrity | 22 price nodes lack NSP; another 22 match several; confirmed | Separate price node from NSP; bridge/collapse only unambiguous geography |
| DQ03 | High — completeness | 7,026,971 offtake kWh and 56,117,354 generation kWh lack Zone; confirmed | Unknown bucket and energy coverage; do not impute geography |
| DQ04 | High — semantics | Mixed fuel codes and 6,491,377 ELE/BAT kWh; Storage classification retained | Versioned crosswalk; storage separately reported; no guessed renewable share |
| DQ05 | High — completeness | Four generation series have <31 days; reconciliation contains no zeros; cause unresolved | Do not zero-fill absent rows; establish activity and suppression rules |
| DQ06 | High — versioning | Reconciliation mutable up to 14 months; revision cycle not identifiable here | Immutable snapshots, source version/hash and explicit latest-version selection |
| DQ07 | High — time | Actual DST market files untested; calendar tests pass | Block broad-scale loading until source boundary cases pass |
| DQ08 | Medium — consistency | 75,679 NSP flow-flag disagreement matches; unresolved | Preserve observations; investigate before using flags as filters |
| DQ09 | Medium — timeliness | Latest available fact month August; snapshot 10 September | Discover end month at runtime; record publication lag and qualification |
| DQ10 | Medium — source scope | Generation_MD total differs from reconciled injections by 184,723,608 kWh; confirmed | Separate definitions; no forced balance or additive merge |
| DQ11 | Medium — history | `202512_FinalEnergyPrices_incomplete.csv` appears in official listing | Per-file status and date/TP checks; future historical gap treatment required |
| DQ12 | Medium — geography | 596 NSP rows lack NZTM coordinates; no lat/lon columns | Defer map until CRS and spatial coverage are verified |
| DQ13 | Medium — validity | 13 future-start NSPs have Current flag=1; confirmed | Effective date/TP joins, including retained history |
| DQ14 | Low — price distribution | 10 zero prices, max 4,644.05; no negative in sample | Retain values; thresholds belong to subsequent distribution/event analysis |

Passing controls: zero duplicates at selected natural keys; zero core price/reconciliation nulls; zero generation nulls within valid August TP columns; complete price date/TP panel; no loss/fanout on observed reconciliation-to-price joins; unique effective NSP match for each volume/generation observation; no NSP interval overlap by NSP; all August clock labels agree. These results do not waive the open issues above.
