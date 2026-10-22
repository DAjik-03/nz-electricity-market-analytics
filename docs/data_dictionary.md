# Actual source field dictionary

August 2026 fact samples and the 10 September 2026 NSP snapshot. Types below are recommended PostgreSQL staging types after validated parsing; raw source text remains unchanged. Pandas categorical encodings in profiles.json are memory optimisation, not source types. Null counts describe the retained sample only.

## Prices

366,048 rows, 4 columns.

| Source field | Suggested type | Nulls | Distinct populated values | Meaning / treatment |
|---|---|---:|---:|---|
| TradingDate | date | 0 | 31 | Local NZ trading date, ISO YYYY-MM-DD. |
| TradingPeriod | smallint | 0 | 48 | Consecutive half-hour period number for the local date; 1–46/48/50. |
| PointOfConnection | text | 0 | 246 | Full grid point-of-connection code; preserve as text. |
| DollarsPerMegawattHour | numeric | 0 | 21,511 | Final energy price in NZD/MWh; retain zero, negative and extreme values when present. |

## Reconciliation

6,403,492 rows, 9 columns.

| Source field | Suggested type | Nulls | Distinct populated values | Meaning / treatment |
|---|---|---:|---:|---|
| PointOfConnection | text | 0 | 221 | Full grid point-of-connection code; preserve as text. |
| Network | text | 0 | 60 | Network code; part of the reconciled-volume natural key. |
| Island | text | 0 | 2 | Source island code NI or SI; retain and compare with mapping source. |
| Participant | text | 0 | 74 | Reconciliation participant code, distinct from network. |
| TradingDate | date | 0 | 31 | Local NZ trading date, ISO YYYY-MM-DD. |
| TradingPeriod | smallint | 0 | 48 | Consecutive half-hour period number for the local date; 1–46/48/50. |
| TradingPeriodStartTime | text | 0 | 48 | Local HH:MM start label; no date or timezone offset; not a unique instant. |
| FlowDirection | text | 0 | 2 | Observed Offtake or Injection; separate measures, not additive demand. |
| KilowattHours | numeric | 0 | 56,047 | Loss-adjusted reconciled energy for the interval in kWh. |

## Generation

3,157 rows, 57 columns.

| Source field | Suggested type | Nulls | Distinct populated values | Meaning / treatment |
|---|---|---:|---:|---|
| Site_Code | text | 0 | 75 | Source geographic site code; retain it, never use a three-letter match as a substitute for a verified POC join. |
| POC_Code | text | 0 | 88 | Generation point of connection; may be embedded under another pricing connection. |
| Nwk_Code | text | 0 | 38 | Generation network code; part of tested connection identity. |
| Gen_Code | text | 0 | 91 | Source plant name/code, including Unicode; multiple connection series can share it. |
| Fuel_Code | text | 0 | 13 | Source fuel label; mixed aliases observed; classification must be explicit. |
| Tech_Code | text | 0 | 11 | Source technology label; preserve separately from fuel. |
| Trading_Date | date | 0 | 31 | Local NZ trading date, ISO YYYY-MM-DD. |
| TP1 | numeric | 0 | 2,008 | Energy in kWh in trading period 1; structural null if that TP does not exist on the date. |
| TP2 | numeric | 0 | 1,933 | Energy in kWh in trading period 2; structural null if that TP does not exist on the date. |
| TP3 | numeric | 0 | 1,918 | Energy in kWh in trading period 3; structural null if that TP does not exist on the date. |
| TP4 | numeric | 0 | 1,906 | Energy in kWh in trading period 4; structural null if that TP does not exist on the date. |
| TP5 | numeric | 0 | 1,892 | Energy in kWh in trading period 5; structural null if that TP does not exist on the date. |
| TP6 | numeric | 0 | 1,874 | Energy in kWh in trading period 6; structural null if that TP does not exist on the date. |
| TP7 | numeric | 0 | 1,862 | Energy in kWh in trading period 7; structural null if that TP does not exist on the date. |
| TP8 | numeric | 0 | 1,875 | Energy in kWh in trading period 8; structural null if that TP does not exist on the date. |
| TP9 | numeric | 0 | 1,862 | Energy in kWh in trading period 9; structural null if that TP does not exist on the date. |
| TP10 | numeric | 0 | 1,897 | Energy in kWh in trading period 10; structural null if that TP does not exist on the date. |
| TP11 | numeric | 0 | 1,949 | Energy in kWh in trading period 11; structural null if that TP does not exist on the date. |
| TP12 | numeric | 0 | 2,008 | Energy in kWh in trading period 12; structural null if that TP does not exist on the date. |
| TP13 | numeric | 0 | 2,072 | Energy in kWh in trading period 13; structural null if that TP does not exist on the date. |
| TP14 | numeric | 0 | 2,112 | Energy in kWh in trading period 14; structural null if that TP does not exist on the date. |
| TP15 | numeric | 0 | 2,253 | Energy in kWh in trading period 15; structural null if that TP does not exist on the date. |
| TP16 | numeric | 0 | 2,310 | Energy in kWh in trading period 16; structural null if that TP does not exist on the date. |
| TP17 | numeric | 0 | 2,311 | Energy in kWh in trading period 17; structural null if that TP does not exist on the date. |
| TP18 | numeric | 0 | 2,299 | Energy in kWh in trading period 18; structural null if that TP does not exist on the date. |
| TP19 | numeric | 0 | 2,329 | Energy in kWh in trading period 19; structural null if that TP does not exist on the date. |
| TP20 | numeric | 0 | 2,310 | Energy in kWh in trading period 20; structural null if that TP does not exist on the date. |
| TP21 | numeric | 0 | 2,313 | Energy in kWh in trading period 21; structural null if that TP does not exist on the date. |
| TP22 | numeric | 0 | 2,297 | Energy in kWh in trading period 22; structural null if that TP does not exist on the date. |
| TP23 | numeric | 0 | 2,301 | Energy in kWh in trading period 23; structural null if that TP does not exist on the date. |
| TP24 | numeric | 0 | 2,276 | Energy in kWh in trading period 24; structural null if that TP does not exist on the date. |
| TP25 | numeric | 0 | 2,260 | Energy in kWh in trading period 25; structural null if that TP does not exist on the date. |
| TP26 | numeric | 0 | 2,240 | Energy in kWh in trading period 26; structural null if that TP does not exist on the date. |
| TP27 | numeric | 0 | 2,256 | Energy in kWh in trading period 27; structural null if that TP does not exist on the date. |
| TP28 | numeric | 0 | 2,241 | Energy in kWh in trading period 28; structural null if that TP does not exist on the date. |
| TP29 | numeric | 0 | 2,247 | Energy in kWh in trading period 29; structural null if that TP does not exist on the date. |
| TP30 | numeric | 0 | 2,226 | Energy in kWh in trading period 30; structural null if that TP does not exist on the date. |
| TP31 | numeric | 0 | 2,242 | Energy in kWh in trading period 31; structural null if that TP does not exist on the date. |
| TP32 | numeric | 0 | 2,256 | Energy in kWh in trading period 32; structural null if that TP does not exist on the date. |
| TP33 | numeric | 0 | 2,277 | Energy in kWh in trading period 33; structural null if that TP does not exist on the date. |
| TP34 | numeric | 0 | 2,278 | Energy in kWh in trading period 34; structural null if that TP does not exist on the date. |
| TP35 | numeric | 0 | 2,280 | Energy in kWh in trading period 35; structural null if that TP does not exist on the date. |
| TP36 | numeric | 0 | 2,228 | Energy in kWh in trading period 36; structural null if that TP does not exist on the date. |
| TP37 | numeric | 0 | 2,154 | Energy in kWh in trading period 37; structural null if that TP does not exist on the date. |
| TP38 | numeric | 0 | 2,142 | Energy in kWh in trading period 38; structural null if that TP does not exist on the date. |
| TP39 | numeric | 0 | 2,145 | Energy in kWh in trading period 39; structural null if that TP does not exist on the date. |
| TP40 | numeric | 0 | 2,133 | Energy in kWh in trading period 40; structural null if that TP does not exist on the date. |
| TP41 | numeric | 0 | 2,144 | Energy in kWh in trading period 41; structural null if that TP does not exist on the date. |
| TP42 | numeric | 0 | 2,122 | Energy in kWh in trading period 42; structural null if that TP does not exist on the date. |
| TP43 | numeric | 0 | 2,148 | Energy in kWh in trading period 43; structural null if that TP does not exist on the date. |
| TP44 | numeric | 0 | 2,135 | Energy in kWh in trading period 44; structural null if that TP does not exist on the date. |
| TP45 | numeric | 0 | 2,126 | Energy in kWh in trading period 45; structural null if that TP does not exist on the date. |
| TP46 | numeric | 0 | 2,094 | Energy in kWh in trading period 46; structural null if that TP does not exist on the date. |
| TP47 | numeric | 0 | 2,049 | Energy in kWh in trading period 47; structural null if that TP does not exist on the date. |
| TP48 | numeric | 0 | 2,023 | Energy in kWh in trading period 48; structural null if that TP does not exist on the date. |
| TP49 | numeric | 3,157 | 0 | Energy in kWh in trading period 49; structural null if that TP does not exist on the date. |
| TP50 | numeric | 3,157 | 0 | Energy in kWh in trading period 50; structural null if that TP does not exist on the date. |

## Nsp

2,617 rows, 27 columns.

| Source field | Suggested type | Nulls | Distinct populated values | Meaning / treatment |
|---|---|---:|---:|---|
| Current flag | smallint / validated boolean | 0 | 2 | Source current-record indicator; not proof of validity at an observation date. |
| NSP | text | 0 | 1,151 | Network supply point identifier; repeats across effective versions. |
| NSP replaced by | text | 949 | 666 | Source successor NSP reference; not an automatic historical rewrite instruction. |
| POC code | text | 0 | 883 | Full connection code of this NSP version. |
| Network participant | text | 0 | 133 | Network participant for this NSP version. |
| Embedded under POC code | text | 1,301 | 95 | Official parent connection for an embedded NSP, if present. |
| Embedded under network participant | text | 1,301 | 29 | Parent connection network participant, if present. |
| Reconciliation type | text | 0 | 5 | Observed GN, EN, NP, GG or GD; preserve code, do not infer missing meanings. |
| X flow | smallint / validated boolean | 0 | 2 | Source offtake flow flag; observed reconciliation disagreements require investigation. |
| I flow | smallint / validated boolean | 0 | 2 | Source injection flow flag; not used as a row-deletion filter. |
| Description | text | 0 | 877 | Source location/NSP description. |
| NZTM easting | numeric | 596 | 302 | Source NZTM easting, not longitude; verify CRS and conversion before mapping. |
| NZTM northing | numeric | 596 | 309 | Source NZTM northing, not latitude; verify CRS and conversion before mapping. |
| Network reporting region ID | text | 5 | 40 | Official network reporting region identifier; not a regional council code. |
| Network reporting region | text | 5 | 40 | Network reporting region label; separate from market Zone. |
| Zone | text | 5 | 5 | Source pricing/market Zone: UNI, CNI, LNI, USI, LSI; null remains Unknown. |
| Island | text | 0 | 2 | Source island code NI or SI; retain and compare with mapping source. |
| Start date | date | 0 | 784 | Effective start date; combine with Start TP. |
| Start TP | smallint | 0 | 47 | Effective starting trading period on Start date. |
| End date | date | 777 | 590 | Effective final date when present; null treated as open-ended in this audit. |
| End TP | smallint | 777 | 48 | Effective final trading period; inclusive convention is an audit assumption supported by adjacent rows. |
| SB ICP | text | 2,067 | 165 | Source ICP reference; retain as text; operational role not needed for source-audit joins. |
| Balancing code | text | 0 | 1,114 | Source balancing reference code; retain without assuming analytical identity. |
| MEP | text | 1,649 | 17 | Source metering equipment provider code; optional metadata. |
| Responsible participant | text | 1,548 | 84 | Source responsible participant code; optional metadata, not the fact Participant. |
| Certification expiry | date | 1,708 | 683 | Source metering certification expiry date; not NSP mapping validity. |
| Metering information exemption expiry date | date | 2,616 | 1 | Source exemption expiry date; not NSP mapping validity. |
