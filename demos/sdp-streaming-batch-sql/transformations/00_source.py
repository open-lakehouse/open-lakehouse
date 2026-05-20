"""Streaming source — ingests the seed Delta table as a stream.

SDP picks up `.py` and `.sql` files from the same `transformations/` glob.
This one Python dataset is the faucet; the streaming/batch contrast itself
(10_events_clean.sql, 20_events_by_type.sql) is written in SQL.

`spark.readStream` makes `sxb_raw` a STREAMING TABLE: each pipeline run
consumes only the rows that arrived in the source since the last run, tracked
by a checkpoint. The source is the Delta table that seed.py writes — see
seed.py for why a seeded table rather than a `rate` stream.
"""

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

spark = SparkSession.active()


@dp.table(name="sxb_raw", comment="Events ingested as a stream from the seed table.")
def sxb_raw():
    return spark.readStream.format("delta").load("file:///tmp/sxb-seed")
