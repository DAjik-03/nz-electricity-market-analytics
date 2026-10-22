SELECT e.event_id,i.interval_id
FROM analytics.mart_price_pressure_event e
JOIN analytics.mart_market_interval_national i
 ON i.start_utc>=e.start_utc AND i.start_utc<e.end_utc;
