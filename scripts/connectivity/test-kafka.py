from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("KafkaStreaming").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

# Read from Kafka
kafka_df = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "localhost:9092")
    .option("subscribe", "events")
    .option("startingOffsets", "earliest")
    .load()
)

# Show raw Kafka data
query = (
    kafka_df.selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)")
    .writeStream
    .format("console")
    .option("truncate", False)
    .start()
)

print("Showing raw Kafka data... Press Ctrl+C to stop.")
query.awaitTermination()
