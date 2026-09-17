# JupyterLab on Apache Spark 4.1 (Python 3, Java 21)
# Matches the Spark 4.1 runtime used by the rest of the stack so notebooks
# can execute pyspark 4.1 features (SDP, VARIANT, RTM, etc.) in local mode.
FROM apache/spark:4.1.0-scala2.13-java21-python3-r-ubuntu

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-pip python3-venv curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Use a venv to sidestep PEP 668 on newer Ubuntu base images (and to avoid
# clobbering the base image's system-site-packages). Pin pip first so the
# jupyterlab resolver has a modern version.
ENV VIRTUAL_ENV=/opt/jupyter-venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Package index. Defaults to public PyPI so vanilla builds (CI, contributors)
# work unchanged; override at build time on networks that require an internal
# mirror:  docker build --build-arg PIP_INDEX_URL=<mirror>/simple ...
ARG PIP_INDEX_URL=https://pypi.org/simple

RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --upgrade "pip>=24.0" setuptools wheel
# jupyterlab + pyspark, plus the Python deps `spark-pipelines` (the SDP CLI)
# imports — the stock apache/spark:4.1.0 image ships none of these, so without
# them `pyspark/pipelines/cli.py` fails with ModuleNotFoundError (§1.6, T-1.13).
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" \
      jupyterlab==4.3.0 \
      ipykernel==6.29.5 \
      pyspark==4.1.0 \
      pandas==2.2.3 \
      pyarrow==18.1.0 \
      matplotlib==3.9.2 \
      "httpx<0.28" \
      pyyaml grpcio grpcio-status protobuf zstandard kafka-python

ENV JUPYTER_ENABLE_LAB=yes \
    PYSPARK_PYTHON=python3 \
    PYSPARK_DRIVER_PYTHON=python3

# Put the mounted extra jars (S3/Delta/Iceberg/UC/Kafka) on the Spark classpath
# so local-mode Spark and `spark-pipelines` in a notebook find them. The jars
# themselves arrive via the compose bind mount (./jars -> /home/jovyan/jars);
# spark-defaults points Spark at that directory.
ENV SPARK_HOME=/opt/spark
RUN mkdir -p "$SPARK_HOME/conf" \
    && printf '%s\n' \
      'spark.driver.extraClassPath /home/jovyan/jars/*' \
      'spark.executor.extraClassPath /home/jovyan/jars/*' \
      > "$SPARK_HOME/conf/spark-defaults.conf"

WORKDIR /home/jovyan
EXPOSE 8889

# Token auth (T-1.14 / D5): the token comes from JUPYTER_TOKEN in the environment
# (wired from .env by compose); jupyter_server reads it natively and XSRF stays
# ON (no --disable_check_xsrf). Guard the footgun: jupyter treats an explicitly
# EMPTY JUPYTER_TOKEN as "no auth", so if it is empty we UNSET it — jupyter then
# mints a random token (locked, not open). It never runs tokenless.
CMD ["bash", "-lc", \
     "if [ -z \"${JUPYTER_TOKEN:-}\" ]; then unset JUPYTER_TOKEN; echo 'WARN: JUPYTER_TOKEN empty — minting a random token; see logs for the URL'; fi; \
      exec jupyter lab --ip=0.0.0.0 --port=8889 --no-browser --allow-root"]
