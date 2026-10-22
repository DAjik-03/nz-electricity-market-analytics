-- Independent generation aggregation; no participant/price join.
SELECT f.interval_id,f.zone,count(*) AS source_rows,sum(f.kilowatt_hours) AS generation_kwh,
 sum(CASE WHEN r.energy_status='Renewable' THEN f.kilowatt_hours ELSE 0 END) AS renewable_kwh,
 sum(CASE WHEN r.energy_status='Fossil' THEN f.kilowatt_hours ELSE 0 END) AS fossil_kwh,
 sum(CASE WHEN r.energy_status='Storage' THEN f.kilowatt_hours ELSE 0 END) AS storage_kwh,
 sum(CASE WHEN r.energy_status IS NULL OR r.energy_status='Unclassified'
          THEN f.kilowatt_hours ELSE 0 END) AS unclassified_kwh
FROM core.v_selected_generation f
CROSS JOIN analytics.configuration c
LEFT JOIN analytics.ref_generation_classification r
 ON r.classification_version=c.classification_version AND r.fuel_code=f.fuel_code AND r.tech_code=f.tech_code
GROUP BY f.interval_id,f.zone
