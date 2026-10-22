# PostgreSQL warehouse design

PostgreSQL staging, core dimensions and version-aware facts underpin the validated twelve-month release. Python verifies hashes and streams COPY; SQL performs transformations and reconciliation. [Reproduction](reproducibility.md) | [Release validation](release_validation.md)

## SQL design and source lineage

The [schema dictionary and ERD](schema_dictionary.md) document every table, identity, constraint and relationship. Source text staging retains all official columns, wide TP1–TP50 and original row ordinals. Core facts retain publication + approved business grain and stage-row foreign keys. Numeric native units remain kWh and dollars/MWh; MWh is a generated kWh/1000 column. Generator classifications remain observed fact attributes rather than expanding the approved key.

NSP conversion retains original inclusive boundaries and derives `[start,end)` only for valid source dates/TPs. Three known impossible end TPs become explicit quarantined records with reasons and null derived endpoints, separate from genuinely open histories. Unique effective POC/network/interval matches receive an NSP key; unmatched/ambiguous facts remain present. Every mapped fact also retains the particular NSP snapshot used. Price nodes have no forced NSP identity. Geographic consensus and coverage marts remain later work.

`core.v_selected_*` views restrict facts to selected source publications. They are safe entry points for later analysis; querying physical facts across publications requires deliberate version filtering. Selection updates the complete candidate release atomically after successful loading. A later revision can be retained physically and selected without deleting its predecessor. A later NSP snapshot cannot silently remap an already loaded fact publication: the loader rejects that case pending an explicit remapping release policy.

## Integrity and load failure handling

Primary/unique keys enforce source row identity and approved fact grains. Foreign keys enforce publication, stage row, interval, dimension and snapshot lineage. CHECKs cover flow labels, native measures, interval duration and distinct temporal statuses. A trigger disallows selecting an unloaded publication. Core objects reject duplicate generation business keys instead of hiding them with a larger fuel/technology key.

The initial pilot uses text staging and batch SQL with all constraints active. COPY streams raw gzip contents without millions of Python INSERT calls. Temporary observed connection/interval keys are materialised once, indexed and used for effective-date resolution before joining participant rows. Statistics are refreshed after bulk COPY; JIT is disabled for loader transactions. `core.ensure_calendar` produces only pilot dates. No partitioning is used.

Each source publication is a restartable transaction. Earlier successful publications survive a later failure; selection is unchanged until the complete release succeeds. Failure attempt metadata is committed separately. An interrupted `running` attempt is not success and may remain in the audit log; a retry resolves the registered/failed publication. Concurrent loader sessions are serialised with an advisory lock. Do not use concurrent ad hoc writers during loading or tests.


## Deviations and limitations

- No generation-series dimension is added: generator/connection dimensions plus observed fact attributes preserve the approved grain without implying permanent classifications.
- No price-to-NSP bridge or geographic consensus logic is introduced; possible fan-out is documented and deferred.
- Explicit source-aligned text staging increases storage but preserves original values and makes SQL conversion reviewable.
- Raw SHA-256 immutability remains in the existing external manifest; database content identity is source + hash and load attempts track operational state.
- The local development owner has broad privileges. Production role separation, concurrency beyond the loader lock, full-archive scaling and remapping release design remain out of scope.
- Pilot eligibility does not certify settlement finality, all expected plant activity, or stable regional coverage. All ingestion exceptions remain visible.

## Image provenance

Tested image: `postgres:17.9-bookworm`, pulled digest `postgres@sha256:47f917f7409eacd22fc5dfb1dee634e1b55cf0c01d1a7eb701be2227a03e0641`. Local service binds only to `127.0.0.1`; the Compose project and volume are isolated from other existing containers. Restart the service without `-v` to preserve the database.
