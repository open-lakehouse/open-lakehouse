# Spark 4.1 standalone image for ECS Fargate (open-lakehouse / terraform/spark-ecs).
#
# A thin layer over the official Apache Spark image that bakes in the lakehouse
# JARs (Delta, Iceberg, Unity Catalog connector, Hadoop-AWS, Spark Connect), a
# default spark-defaults.conf, and an entrypoint that wires the standalone
# master / worker / connect roles to Cloud Map service discovery.
#
# Built for linux/arm64 to match the Fargate ARM64 runtime (see scripts/terraform/spark-ecr-push.sh).
FROM apache/spark:4.1.0-scala2.13-java21-python3-r-ubuntu

# Pinned JAR versions — mirror scripts/tools/download-jars.sh and the version
# pins in CLAUDE.md. Do not bump without testing against Spark 4.1.
ARG ICEBERG_VERSION=1.10.0
ARG DELTA_VERSION=4.2.0
ARG UC_CONNECTOR_VERSION=0.3.0
ARG HADOOP_AWS_VERSION=3.4.1
ARG AWS_SDK_V1_VERSION=1.12.780
ARG AWS_SDK_V2_VERSION=2.24.6
ARG SPARK_VERSION=4.1.0
ARG SCALA_BINARY=2.13

# Maven mirror (override in restricted networks). Defaults to Maven Central.
ARG MAVEN_PROXY_URL=https://repo1.maven.org/maven2

# Daemons load their classpath from /opt/spark/jars, so copy the extra JARs there
# (spark.jars only affects driver/executor classpaths, not the standalone daemons).
USER root

RUN set -eux; \
    base="${MAVEN_PROXY_URL%/}"; \
    dest=/opt/spark/jars; \
    # Stall-resilient fetch: abort if throughput drops below 10 KB/s for 60s and
    # retry (handles flaky mirrors/proxies on the large multi-hundred-MB bundles).
    fetch() { echo "  fetching $1"; curl -fSL \
      --connect-timeout 30 --speed-limit 10240 --speed-time 60 \
      --retry 5 --retry-delay 5 --retry-all-errors \
      -o "${dest}/$(basename "$1")" "${base}/$1"; }; \
    fetch "org/apache/iceberg/iceberg-spark-runtime-4.0_${SCALA_BINARY}/${ICEBERG_VERSION}/iceberg-spark-runtime-4.0_${SCALA_BINARY}-${ICEBERG_VERSION}.jar"; \
    fetch "io/delta/delta-spark_${SCALA_BINARY}/${DELTA_VERSION}/delta-spark_${SCALA_BINARY}-${DELTA_VERSION}.jar"; \
    fetch "io/delta/delta-storage/${DELTA_VERSION}/delta-storage-${DELTA_VERSION}.jar"; \
    fetch "io/unitycatalog/unitycatalog-spark_${SCALA_BINARY}/${UC_CONNECTOR_VERSION}/unitycatalog-spark_${SCALA_BINARY}-${UC_CONNECTOR_VERSION}.jar"; \
    fetch "io/unitycatalog/unitycatalog-client/${UC_CONNECTOR_VERSION}/unitycatalog-client-${UC_CONNECTOR_VERSION}.jar"; \
    fetch "org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar"; \
    fetch "com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_V1_VERSION}/aws-java-sdk-bundle-${AWS_SDK_V1_VERSION}.jar"; \
    fetch "software/amazon/awssdk/bundle/${AWS_SDK_V2_VERSION}/bundle-${AWS_SDK_V2_VERSION}.jar"; \
    fetch "org/apache/spark/spark-connect_${SCALA_BINARY}/${SPARK_VERSION}/spark-connect_${SCALA_BINARY}-${SPARK_VERSION}.jar"; \
    chown -R spark:spark "${dest}"

# Baked default config (catalogs, S3A, reverse proxy, event logging). Overridable
# at runtime via the SPARK_EXTRA_CONF env (rendered by Terraform's extra_spark_conf).
COPY spark-defaults.conf /opt/spark/conf/spark-defaults.conf
COPY entrypoint.sh /opt/entrypoint.sh

RUN chmod +x /opt/entrypoint.sh \
    && mkdir -p /opt/spark-data/logs \
    && chown -R spark:spark /opt/spark/conf /opt/spark-data

USER spark
WORKDIR /opt/spark

ENTRYPOINT ["/opt/entrypoint.sh"]
