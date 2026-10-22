# Analytical KPI dictionary — version 1

## continuous-release continuous-window extension

Implementation is validated for September 2025–August 2026. National has 336 complete thirty-day windows from 30 September 2025; the first 29 dates are ineligible. Spring/fall DST, missing-date/TP, independent volatility and stale-input fixtures pass. Current thresholds, coverage and event counts are in [continuous-release validation](release_validation.md). The original scope below records the analytical-mart baseline; metric definitions remain in force.

| Added metric | Exact calculation and contract |
|---|---|
| Thirty-day weighted price | Sum interval price × priced Offtake kWh divided by sum priced Offtake kWh; NZD/MWh. Never average daily prices for this primary metric. |
| Thirty-day demand | Sum native Offtake kWh / 1,000,000; GWh. Includes actual 23/25-hour dates. |
| Thirty-day price volatility | Population SD of all non-null interval weighted prices, using pooled count/sum/squared-sum; NZD/MWh. Equal interval weights, not equal daily weights. |

All three are exposed by `analytics.mart_market_daily_rolling_30d` and require exactly thirty complete consecutive local dates within a region's contiguous block. A complete price/demand day uses the date-specific expected TP count. The first 29 dates and any window with missing/incomplete dates yield null metrics. Zero denominators remain null; signed source energy and coverage limitations remain visible. These metrics describe the observed continuous population; they are not seasonally adjusted and do not imply causality. No YoY is implemented. Existing seven-day outputs remain separate.

Original analytical-mart scope: September 2025, April 2026 and August 2026, three non-contiguous historical observations. continuous-release extends these definitions to the continuous approved year and recalculates population-dependent metrics. No YoY, causal claims, commercial targets or official EA high-price classifications are implemented. Classification evidence and SQL dependencies are in [analytics design](analytics_design.md).

## Shared source and coverage contract

`I` means `analytics.mart_market_interval` (or its National/Zone views), `D` the equivalent `mart_market_daily`, `M` `mart_market_monthly`, `R` `mart_market_daily_rolling`, `T` `mart_price_pressure_threshold`, and `E` `mart_price_pressure_event` / `mart_price_event_context`. Never sum National and Zone rows together. Underlying sources are selected reconciled Offtake, unique interval/full-POC price and independently aggregated Generation_MD. Zone comes from effective Offtake/generation NSP evidence; national includes Unknown. Units are NZD/MWh, kWh, MW, GWh, hours or percentages as specified.

Let O = total Offtake kWh; Q = priced Offtake kWh; N = sum(price NZD/MWh × priced Offtake kWh); G = listed generation kWh; B = classified renewable primary kWh; F = classified fossil primary kWh; S = storage kWh; U = unclassified kWh; p = N/Q for an interval. Zero denominators produce NULL. Additive components retain signed native energy; missing populations are not zero-filled. All metrics inherit source revision eligibility, NSP quarantine/gaps and incomplete gross-generation coverage. Public marts reject stale source selections. Coverage accompanies the measure, not an invented universal acceptance threshold.

Every entry supplies the business question, exact definition/formula, grain/source, unit/weighting, exclusions/coverage and interpretation/limitation.

## Price and demand

### Offtake-weighted wholesale price

- **Question / definition:** What wholesale price is associated with observed priced demand? `weighted_price = SUM(N)/NULLIF(SUM(Q),0)`.
- **Grain / source:** National or Zone interval, local day, selected month, seven-day window or event; I/D/M/R/E, selected price + reconciled Offtake.
- **Unit / weighting:** NZD/MWh; Offtake energy weights at the same interval and full POC. Reaggregate numerator and denominator, never average daily weighted prices.
- **Exclusions / coverage:** Excludes unpriced energy from N/Q, but retains it in O and coverage Q/O. National does not require Zone. Report Q, O and price-weighting coverage; no classification requirement.
- **Interpretation / limitation:** Price exposure of the observed Offtake population, not a retail tariff, settlement invoice or unweighted node-price mean. A low covered denominator can change representativeness.

### P95 interval weighted price

- **Question / definition:** How high is the upper tail of interval prices? `percentile_cont(0.95) WITHIN GROUP (ORDER BY p)`.
- **Grain / source:** National or individual Zone within local day or selected month; D/M from I.
- **Unit / weighting:** NZD/MWh; equal weight per non-null interval, after energy weighting within each interval.
- **Exclusions / coverage:** Null interval prices excluded. Review price observation count, day completeness and Q/O; classification irrelevant.
- **Interpretation / limitation:** Interpolated 95th percentile of the named region's intervals, not node prices, an energy-weighted percentile or a causal risk forecast. Partial populations must remain labelled.

### Interval-price volatility

- **Question / definition:** How dispersed are observed interval weighted prices? `STDDEV_POP(p) = sqrt(SUM((p-mean(p))^2)/COUNT(p))`.
- **Grain / source:** Region/local day or month D/M; seven-day interval population R.
- **Unit / weighting:** NZD/MWh; population, equal interval weights. Rolling implementation uses exact numeric moments `sqrt(max(0,SUM(p^2)/n-(SUM(p)/n)^2))`.
- **Exclusions / coverage:** Null p excluded; empty population returns NULL. Seven-day metric requires full contiguous price/demand days. Report observations and priced coverage; classification irrelevant.
- **Interpretation / limitation:** Describes the observed population, not sample standard deviation, returns volatility or a confidence interval. DST days contribute their actual interval counts.

### Interval-average demand and peak demand

- **Question / definition:** How much demand occurs, and what is its maximum half-hour level? `demand_mw=O/500`; `peak_demand_mw=MAX(O/500)`.
- **Grain / source:** Interval average I; peak by region/day/month/event D/M/E; reconciled Offtake.
- **Unit / weighting:** MW; energy divided by half-hour duration. Peak is an extremum of aggregated interval demand, not a participant record.
- **Exclusions / coverage:** Injection excluded. Include Unknown nationally. Review demand interval population and Zone coverage regionally; price/classification not required.
- **Interpretation / limitation:** Average power over an interval, not instantaneous peak load. Source population and reconciliation revisions can change it.

### Total demand

- **Question / definition:** How much measured Offtake occurred? `demand_gwh=SUM(O)/1000000`; event output also retains `total_offtake_kwh`.
- **Grain / source:** Region/day/month/event, D/M/E; reconciled Offtake. Interval kWh retained in I.
- **Unit / weighting:** GWh or explicitly labelled kWh; additive energy, no averaging.
- **Exclusions / coverage:** Injection excluded; no geographic exclusion nationally. Require/disclose observed dates/intervals, keep Unknown separate regionally. No price/classification requirement.
- **Interpretation / limitation:** Selected reconciled demand, not a claim about final revisions or gross national energy balance. DST days sum actual energy without 24-hour scaling.

### Continuity-safe price change

- **Question / definition:** How did price change from the immediately observed prior interval/day? `p-LAG(p)` or daily `weighted_price-LAG(weighted_price)`.
- **Grain / source:** Region/interval I and region/local day R; same price sources as weighted price.
- **Unit / weighting:** NZD/MWh absolute difference; each operand is its own energy-weighted price.
- **Exclusions / coverage:** NULL unless current UTC start equals previous UTC end, or local date equals previous date+1 respectively. Null prices propagate; disclose underlying price coverage. No classification requirement.
- **Interpretation / limitation:** Short-period observed difference, not percentage return or gap-spanning trend. Both September→April and April→August changes are NULL. No YoY.

### Continuity-safe demand change

- **Question / definition:** How did demand change from the immediately prior interval/day? `demand_mw-LAG(demand_mw)` or `demand_gwh-LAG(demand_gwh)`.
- **Grain / source:** Region/interval I or region/local day R; reconciled Offtake.
- **Unit / weighting:** MW interval difference or GWh daily difference; differences of additive interval/day energy-derived measures.
- **Exclusions / coverage:** Same actual UTC/date adjacency gates; missing demand propagates NULL. Geographic population and demand completeness disclosed; no price/classification needed for the change itself.
- **Interpretation / limitation:** Daily energy changes include genuine 23/25-hour day length effects. Not weather-adjusted, seasonally adjusted or normalised to 24 hours; no YoY.

## Generation and coverage

### Total listed generation

- **Question / definition:** How much generation is represented in Generation_MD? `listed_generation_gwh=SUM(G)/1000000`.
- **Grain / source:** Region/day/month D/M; I and E retain kWh. Independently aggregated selected connection-level generation.
- **Unit / weighting:** GWh or labelled kWh; additive energy.
- **Exclusions / coverage:** Include storage and unclassified rows in the listed total; no invented plant/date rows. Report generation Zone and classification coverage; price not required.
- **Interpretation / limitation:** Listed measured/estimated injection representation, not complete gross generation. Do not equate it to reconciled Offtake or infer losses from their difference.

### Renewable share of classified primary generation

- **Question / definition:** What fraction of supported primary generation is renewable? `100*SUM(B)/NULLIF(SUM(B+F),0)`.
- **Grain / source:** Region/interval/day/month/event I/D/M/E; generation + pinned exact-pair classification.
- **Unit / weighting:** Percent; primary-generation kWh weights, recomputed from additive components.
- **Exclusions / coverage:** Both storage S and unclassified U excluded from numerator/denominator. Report classification coverage and U alongside this share, plus Zone coverage regionally.
- **Interpretation / limitation:** Share of classified primary listed generation only; never label it all-NZ renewable share. Unsupported codes can materially affect the denominator.

### Fossil thermal share and generation

- **Question / definition:** What supported primary generation is fossil thermal? Share `100*SUM(F)/NULLIF(SUM(B+F),0)`; volume `SUM(F)/1000000`.
- **Grain / source:** Share I/D/E; volume kWh I/D/E and `fossil_thermal_gwh` M; generation + classification. Monthly share can be derived directly from summed B/F rather than averaging shares.
- **Unit / weighting:** Percent energy share or GWh/kWh additive volume.
- **Exclusions / coverage:** Storage/unclassified excluded from primary share, retained separately. Classifies gas cogeneration by fuel; Wood/Cogen is not fossil. Report classification/Zone coverage.
- **Interpretation / limitation:** Supported fossil-fuel output, not all heat-based technologies, emissions or storage. No CO2 factor is inferred.

### Storage discharge and unclassified generation

- **Question / definition:** How much listed energy is stored-energy output or lacks supported classification? `SUM(S)` and `SUM(U)` (divide by 1e6 for GWh).
- **Grain / source:** Region/interval/day/month/event I/D/M/E; generation exact-pair mapping, with unseen pairs falling back to U.
- **Unit / weighting:** kWh or GWh; additive source energy.
- **Exclusions / coverage:** Neither contributes to primary renewable/fossil shares. ELE/BAT remains Storage; unknown codes are never guessed. Report classification and Zone coverage.
- **Interpretation / limitation:** Storage output does not reveal charging origin or round-trip efficiency. Unclassified is uncertainty, not zero, fossil or renewable by default.

### Generation classification coverage

- **Question / definition:** What portion of listed energy has supported analytical treatment? `100*(SUM(G)-SUM(U))/NULLIF(SUM(G),0)`.
- **Grain / source:** Region/interval/day/month/event I/D/M/E; generation + versioned reference.
- **Unit / weighting:** Percent of native listed kWh; reviewed storage counts as classified.
- **Exclusions / coverage:** Unclassified excluded from numerator only; zero G gives NULL. Classification version and unresolved pairs must be disclosed; no price requirement.
- **Interpretation / limitation:** Coverage of classification, not renewable share, completeness of gross generation or accuracy score. Signed-energy denominators are retained.

### Price-weighting coverage

- **Question / definition:** How much demand contributes to weighted price? `100*SUM(Q)/NULLIF(SUM(O),0)`.
- **Grain / source:** Region/interval/day/month/event I/D/M/E; price and Offtake full-POC match.
- **Unit / weighting:** Percent of Offtake kWh; energy, not row count.
- **Exclusions / coverage:** Unpriced demand excluded only from numerator. Unknown geography is eligible for pricing. Zero/absent demand gives NULL, not 100%; classification irrelevant.
- **Interpretation / limitation:** Matching coverage, not evidence of final source revisions or complete market capture. Pilot value is 100% in each national month.

### Offtake and generation Zone coverage

- **Question / definition:** What energy has known effective geography? `100*SUM(known_zone_offtake_kwh)/SUM(O)` and `100*SUM(known_zone_generation_kwh)/SUM(G)` with NULLIF denominators.
- **Grain / source:** I/D/M/E; effective NSP-associated energy, with national monthly coverage the main summary.
- **Unit / weighting:** Percent native kWh independently for the two sources.
- **Exclusions / coverage:** Unknown excluded from numerator, retained in denominator. No name-based inference/backfill. Price or generation classification is not required.
- **Interpretation / limitation:** National coverage exposes missing geography; a known Zone's own value is typically 100%, not proof of national mapping completeness. Price-node row coverage in the DQ output is a separate diagnostic and is not this KPI.

## Rolling and regional metrics

### Seven-day weighted average price

- **Question / definition:** What energy-weighted price applies to the latest full observed week? `SUM(N) OVER 7 dates / NULLIF(SUM(Q) OVER 7 dates,0)`.
- **Grain / source:** Region/local date R, derived from D.
- **Unit / weighting:** NZD/MWh; seven-day priced-energy weights.
- **Exclusions / coverage:** Partition by contiguous date block; exactly seven consecutive local dates and complete price/demand interval populations required, otherwise NULL. No cross-month-gap or partial-window substitution; classification irrelevant.
- **Interpretation / limitation:** Historical trailing observed week, not forecast. Separate `rolling_7d_mean_daily_price=AVG(daily weighted_price)` uses equal day weights and is a labelled diagnostic, never a replacement for this primary price.

### Seven-day demand and volatility

- **Question / definition:** What demand accumulated and how dispersed were prices in the complete week? `SUM(demand_gwh) OVER 7 dates`; interval-price population SD from pooled seven-day count/sum/squared sum.
- **Grain / source:** Region/local date R; Offtake and interval weighted prices in D.
- **Unit / weighting:** GWh additive demand; NZD/MWh equal-interval volatility.
- **Exclusions / coverage:** Same full seven-day gate as rolling price; NULL otherwise. No classification requirement; report demand/price/Zone coverage. DST contributes actual energy and intervals.
- **Interpretation / limitation:** Not seven-day mean demand and not SD of daily mean prices. No 30-day rolling metric is implemented.

### Regional weighted-price spread

- **Question / definition:** How far apart are contemporaneous known-Zone prices? `MAX(p)-MIN(p)` only when all expected CNI/LNI/LSI/UNI/USI have non-null p.
- **Grain / source:** Interval `mart_regional_spread`, carried into I; daily/event mean and event maximum in D/E.
- **Unit / weighting:** NZD/MWh; extremum across energy-weighted Zone prices. Mean spread is equal weight per covered interval.
- **Exclusions / coverage:** Unknown excluded. Require represented Zone count=5, else NULL; report expected/represented counts and aggregate spread-observation count. No generation classification requirement.
- **Interpretation / limitation:** Cross-Zone separation, not individual-node congestion, transmission cost or causality. National/Zone rows repeat the same interval spread; never sum those copies.

## Price-pressure threshold and events

### P99 price-pressure threshold

- **Question / definition:** What fixed statistical cutoff defines the pilot's upper-price tail? `percentile_cont(0.99) WITHIN GROUP(ORDER BY p)` for each scope over selected pilot intervals.
- **Grain / source:** One T row for National and each of five known Zones; I source components.
- **Unit / weighting:** NZD/MWh; equal weight per non-null region interval (4,368 each in this pilot).
- **Exclusions / coverage:** No Unknown threshold. Population months/count/endpoints stored; null prices excluded. Disclose Q/O and source selection fingerprint; no classification requirement.
- **Interpretation / limitation:** Project-defined retrospective threshold over the selected release population; not an EA official scarcity classification, tuned cutoff or prospective forecast.

### High-price interval count

- **Question / definition:** How many observed intervals meet the threshold? `COUNT(*) FILTER (WHERE p>=P99)`.
- **Grain / source:** Region/day/month D/M; event members and scope summaries E; threshold T.
- **Unit / weighting:** Number of half-hour intervals, equal weight.
- **Exclusions / coverage:** Unpriced intervals cannot be flagged; Unknown has no threshold and its count is not a market-pressure comparison. Disclose population and threshold; no classification requirement.
- **Interpretation / limitation:** Includes ties; not guaranteed exactly 1%. Counts may overlap among National and Zones, so do not sum into a unique nationwide occurrence count.

### Consecutive event duration

- **Question / definition:** How long did a continuous flagged episode last? `interval_count*0.5`, requiring every current start UTC=previous end UTC and no intervening unflagged interval.
- **Grain / source:** Region/event E; I flags and T.
- **Unit / weighting:** Hours, actual equal half-hours; event start inclusive/end exclusive.
- **Exclusions / coverage:** Split at UTC gaps, unflagged intervals and region boundary. No interpolation across unobserved months. Price/threshold population must be disclosed; classification irrelevant.
- **Interpretation / limitation:** Duration of an observed statistical episode, potentially censored by pilot edges; not duration of an officially declared market event.

### Event price, demand and generation context

- **Question / definition:** What measured conditions accompany an episode? Energy-weighted event price `SUM(N)/SUM(Q)`; mean interval price `AVG(p)`; peak price `MAX(p)`; mean demand `AVG(O/500)`; peak demand `MAX(O/500)`; total demand `SUM(O)`; generation components and shares as defined above.
- **Grain / source:** Region/event E and `mart_price_event_context`; independently combined I aggregates, T and retained DQ context.
- **Unit / weighting:** Prices NZD/MWh, demand MW/kWh, generation kWh, shares/coverage percent; each field's weights follow its named formula.
- **Exclusions / coverage:** Keep unclassified/storage/Unknown and Q/O visible. Spread summaries require valid per-interval five-Zone spread. Event generation is context, not joined plant×participant detail.
- **Interpretation / limitation:** Enables later drill-through; no causal attribution. Within-region `DENSE_RANK` of peak price is navigation, not a KPI performance target. Refresh/DQ IDs and DQ as-of disclose lineage and historical assessment age.
