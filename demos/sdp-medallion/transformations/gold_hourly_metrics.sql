-- Gold: orders and revenue per hour and city. Pure SQL aggregation over silver.
CREATE MATERIALIZED VIEW gold_hourly_metrics
USING delta
TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported')
AS
SELECT
  event_date,
  event_hour,
  city_name,
  count(*)                     AS order_count,
  round(sum(order_total), 2)   AS total_revenue,
  round(avg(order_total), 2)   AS avg_order_value
FROM orders_enriched
WHERE event_type = 'order_created'
GROUP BY event_date, event_hour, city_name;
