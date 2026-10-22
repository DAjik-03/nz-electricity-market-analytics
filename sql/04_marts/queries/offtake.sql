-- Reduce participant/network detail BEFORE joining a unique interval/full-POC price.
SELECT f.interval_id,c.poc,f.zone,sum(f.kilowatt_hours) AS offtake_kwh,
       count(*) AS source_rows
FROM core.v_selected_reconciled_volume f
JOIN core.dim_connection c USING(connection_id)
WHERE f.flow_direction='Offtake'
GROUP BY f.interval_id,c.poc,f.zone
