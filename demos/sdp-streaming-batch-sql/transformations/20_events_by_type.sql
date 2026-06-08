-- BATCH semantics in SQL.
--
-- CREATE MATERIALIZED VIEW is a batch dataset: every pipeline run recomputes
-- it in full from its inputs. There is no checkpoint and no notion of "new"
-- rows — the aggregate is always a complete, consistent snapshot of whatever
-- `sxb_clean` contains right now.
CREATE MATERIALIZED VIEW sxb_rollup
AS SELECT event_type, count(*) AS event_count
   FROM sxb_clean
   GROUP BY event_type;
