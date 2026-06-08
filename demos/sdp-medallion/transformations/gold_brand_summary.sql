-- Gold: revenue and order metrics per brand. Pure SQL aggregation over silver.
CREATE MATERIALIZED VIEW gold_brand_summary
USING delta
TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported')
AS
SELECT
  brand_name,
  count(*)                          AS total_orders,
  round(sum(order_total), 2)        AS total_revenue,
  round(avg(order_total), 2)        AS avg_order_value,
  count(DISTINCT location_id)       AS locations_served
FROM orders_enriched
WHERE event_type = 'order_created'
GROUP BY brand_name
ORDER BY total_revenue DESC;
