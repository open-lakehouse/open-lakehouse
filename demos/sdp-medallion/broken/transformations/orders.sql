CREATE MATERIALIZED VIEW orders AS
SELECT id AS order_id, id % 5 AS brand_id, round(id * 9.99, 2) AS amount
FROM range(1000);
