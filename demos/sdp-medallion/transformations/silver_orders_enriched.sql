-- Silver: parse the JSON body, derive time features, join the city dimension.
-- Pure SQL. SDP infers the dependency on orders_bronze and dim_locations from
-- the table references below.
CREATE MATERIALIZED VIEW orders_enriched
USING delta
TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported')
AS
WITH parsed AS (
  SELECT
    *,
    from_json(
      body,
      'struct<brand_id:int, brand_name:string, total:double, items:array<struct<quantity:int>>>'
    ) AS details
  FROM orders_bronze
)
SELECT
  p.event_id,
  p.event_type,
  p.event_timestamp,
  p.order_id,
  p.location_id,
  p.details.brand_id            AS brand_id,
  p.details.brand_name          AS brand_name,
  p.details.total               AS order_total,
  size(p.details.items)         AS num_items,
  hour(p.event_timestamp)       AS event_hour,
  to_date(p.event_timestamp)    AS event_date,
  l.city                        AS city_name
FROM parsed p
LEFT JOIN dim_locations l ON p.location_id = l.id;
