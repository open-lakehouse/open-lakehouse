-- STREAMING semantics in SQL.
--
-- CREATE STREAMING TABLE + `FROM STREAM <source>` is an incremental,
-- append-only dataset. Each pipeline run consumes only the rows that arrived
-- since the last run; the checkpoint under the pipeline `storage` directory
-- remembers where it left off. It never recomputes already-processed rows.
CREATE STREAMING TABLE sxb_clean
AS SELECT event_id, event_type, order_id, event_time
   FROM STREAM sxb_raw
   WHERE event_type IS NOT NULL;
