# Thin, data-free client container for the remote-Connect medallion demo.
#
# It is a PURE Spark Connect client — no JVM, no Spark cluster, no data baked
# in. Compute runs on the remote cluster (connect.openlakehousedemos.dev);
# raw data lives in S3; the only thing this image needs at runtime is a UC
# bearer token passed as an env var.
#
# Build (context = this demo dir):
#   docker build -t openlakehouse-medallion demos/sdp-medallion
#
# Run (each laptop, with that user's UC token):
#   docker run --rm -e UC_TOKEN="$(cat ~/.uc_token)" openlakehouse-medallion
#   docker run --rm -e UC_TOKEN="$(cat ~/.uc_token)" openlakehouse-medallion --show
#
# pyspark pinned to a released 4.1.x (server is 4.1.0; Connect is wire-compatible
# within the minor). Bump if the server moves.
FROM python:3.11-slim

RUN pip install --no-cache-dir "pyspark[connect]==4.1.2"

WORKDIR /app
COPY remote_client_medallion.py /app/

# Fail fast with a clear message if the token wasn't provided.
ENTRYPOINT ["python3", "/app/remote_client_medallion.py"]
