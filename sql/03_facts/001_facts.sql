CREATE TABLE core.fact_price (
 publication_id bigint NOT NULL REFERENCES metadata.source_publication,
 interval_id bigint NOT NULL REFERENCES core.dim_trading_interval,
 pricing_node_id bigint NOT NULL REFERENCES core.dim_pricing_node,
 source_row_number bigint NOT NULL,
 dollars_per_mwh numeric(20,8) NOT NULL CHECK (dollars_per_mwh<>'NaN'::numeric),
 PRIMARY KEY (publication_id,interval_id,pricing_node_id),
 FOREIGN KEY (publication_id,source_row_number) REFERENCES staging.final_energy_price
);
CREATE TABLE core.fact_reconciled_volume (
 publication_id bigint NOT NULL REFERENCES metadata.source_publication,
 interval_id bigint NOT NULL REFERENCES core.dim_trading_interval,
 connection_id bigint NOT NULL REFERENCES core.dim_connection,
 participant_id bigint NOT NULL REFERENCES core.dim_participant,
 flow_direction text NOT NULL CHECK (flow_direction IN ('Offtake','Injection')),
 source_row_number bigint NOT NULL,
 island_original text NOT NULL,
 local_start_label text NOT NULL,
 kilowatt_hours numeric(20,6) NOT NULL CHECK (kilowatt_hours<>'NaN'::numeric),
 megawatt_hours numeric GENERATED ALWAYS AS (kilowatt_hours/1000) STORED,
 nsp_snapshot_publication_id bigint NOT NULL REFERENCES metadata.source_publication,
 nsp_version_id bigint,
 mapping_status text NOT NULL CHECK (mapping_status IN ('mapped','unmapped','ambiguous')),
 PRIMARY KEY (publication_id,interval_id,connection_id,participant_id,flow_direction),
 FOREIGN KEY (publication_id,source_row_number) REFERENCES staging.reconciled_volume,
 FOREIGN KEY (nsp_version_id,nsp_snapshot_publication_id) REFERENCES core.dim_nsp_version(nsp_version_id,publication_id),
 CHECK ((mapping_status='mapped') = (nsp_version_id IS NOT NULL))
);
CREATE TABLE core.fact_generation_connection (
 publication_id bigint NOT NULL REFERENCES metadata.source_publication,
 interval_id bigint NOT NULL REFERENCES core.dim_trading_interval,
 generator_id bigint NOT NULL REFERENCES core.dim_generator,
 connection_id bigint NOT NULL REFERENCES core.dim_connection,
 source_row_number bigint NOT NULL,
 source_tp smallint NOT NULL CHECK (source_tp BETWEEN 1 AND 50),
 site_code text NOT NULL,
 fuel_code text NOT NULL,
 tech_code text NOT NULL,
 kilowatt_hours numeric(20,6) NOT NULL CHECK (kilowatt_hours<>'NaN'::numeric),
 megawatt_hours numeric GENERATED ALWAYS AS (kilowatt_hours/1000) STORED,
 nsp_snapshot_publication_id bigint NOT NULL REFERENCES metadata.source_publication,
 nsp_version_id bigint,
 mapping_status text NOT NULL CHECK (mapping_status IN ('mapped','unmapped','ambiguous')),
 PRIMARY KEY (publication_id,interval_id,generator_id,connection_id),
 FOREIGN KEY (publication_id,source_row_number) REFERENCES staging.generation_daily,
 FOREIGN KEY (nsp_version_id,nsp_snapshot_publication_id) REFERENCES core.dim_nsp_version(nsp_version_id,publication_id),
 CHECK ((mapping_status='mapped') = (nsp_version_id IS NOT NULL))
);
-- Publication-first primary indexes serve selected versions and monthly loads.
-- Interval-first indexes support cross-source interval joins; no partitioning.
CREATE INDEX price_interval_node ON core.fact_price(interval_id,pricing_node_id);
CREATE INDEX volume_interval_connection ON core.fact_reconciled_volume(interval_id,connection_id);
CREATE INDEX generation_interval_connection ON core.fact_generation_connection(interval_id,connection_id);

CREATE VIEW core.v_selected_price AS
 SELECT f.* FROM core.fact_price f
 JOIN metadata.publication_selection s ON s.publication_id=f.publication_id AND s.source_name='prices';
CREATE VIEW core.v_selected_reconciled_volume AS
 SELECT f.*,coalesce(n.zone,'Unknown') AS zone,
   coalesce(n.island,'Unknown') AS nsp_island,
   coalesce(n.network_reporting_region,'Unknown') AS network_reporting_region
 FROM core.fact_reconciled_volume f
 JOIN metadata.publication_selection s ON s.publication_id=f.publication_id AND s.source_name='reconciliation'
 LEFT JOIN core.dim_nsp_version n ON n.nsp_version_id=f.nsp_version_id;
CREATE VIEW core.v_selected_generation AS
 SELECT f.*,coalesce(n.zone,'Unknown') AS zone,
   coalesce(n.island,'Unknown') AS nsp_island,
   coalesce(n.network_reporting_region,'Unknown') AS network_reporting_region
 FROM core.fact_generation_connection f
 JOIN metadata.publication_selection s ON s.publication_id=f.publication_id AND s.source_name='generation'
 LEFT JOIN core.dim_nsp_version n ON n.nsp_version_id=f.nsp_version_id;

-- Price nodes deliberately have no single NSP FK. No consensus geography or
-- potentially additive many-to-many bridge is implemented in this phase.
