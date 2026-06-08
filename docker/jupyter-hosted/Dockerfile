# Hosted JupyterLab + Spark 4.1 image for the per-presenter demo environment.
#
# Self-contained: bakes the extra jars, both demos, the SDP/RTM Python deps, and
# an entrypoint that injects the UC token into spark-defaults.conf at start.
# Compute is real local Spark (JVM) in the kernel — needed for real SDP + RTM.
# Build context = repo root:  docker build -f docker/jupyter-hosted/Dockerfile -t openlakehouse-notebooks .
FROM apache/spark:4.1.0-scala2.13-java21-python3-r-ubuntu

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-pip python3-venv gettext-base \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/jupyter-venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install --no-cache-dir --upgrade "pip>=24.0" setuptools wheel
RUN pip install --no-cache-dir \
      jupyterlab==4.3.0 ipykernel==6.29.5 pyspark==4.1.0 \
      pandas==2.2.3 pyarrow==18.1.0 matplotlib==3.9.2 "httpx<0.28" \
      pyyaml grpcio grpcio-status protobuf zstandard kafka-python

# Bake the jars (S3/Delta/Iceberg/UC/Kafka) so Spark + spark-pipelines find them.
COPY jars/ /opt/spark/jars-extra/

# Bake the demos (notebooks + transforms + libs + specs).
COPY demos/sdp-medallion/   /home/jovyan/demos/sdp-medallion/
COPY demos/realtime-mode/   /home/jovyan/demos/realtime-mode/
# Surface the notebooks at the Lab root for presenters.
RUN cp /home/jovyan/demos/sdp-medallion/notebooks/sdp_medallion.ipynb /home/jovyan/ \
 && cp /home/jovyan/demos/realtime-mode/notebooks/rtm_trigger.ipynb   /home/jovyan/

COPY docker/jupyter-hosted/spark-defaults.conf.template /opt/spark/conf/spark-defaults.conf.template
COPY docker/jupyter-hosted/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Defaults (overridable per task): the SDP demo reads these at runtime.
ENV PYSPARK_PYTHON=python3 PYSPARK_DRIVER_PYTHON=python3 \
    SDP_DEMO_DIR=/home/jovyan/demos/sdp-medallion \
    ORDERS_PATH=s3a://uc-quickstart-207734640204-usw2/medallion-demo/raw/orders \
    DIMS_PATH=s3a://uc-quickstart-207734640204-usw2/medallion-demo/raw/dimensions \
    MEDALLION_WAREHOUSE=s3://uc-quickstart-207734640204-usw2/warehouse/medallion \
    MEDALLION_MAX_ROWS=300000

WORKDIR /home/jovyan
EXPOSE 8889
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8889/api || exit 1
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
