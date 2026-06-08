CREATE MATERIALIZED VIEW gold_revenue AS
SELECT brand_id, round(sum(amount), 2) AS revenue
FROM orderz          -- BUG: typo — the table is 'orders', not 'orderz'
GROUP BY brand_id;
