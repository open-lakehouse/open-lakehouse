# Building Images Behind a Package Proxy

The Airflow and Jupyter images default to public PyPI. Their package source can
be overridden at build time without changing or committing repository files.

## Public defaults

With no proxy variables set, builds use:

- Python packages: `https://pypi.org/simple`
- Airflow's Spark distribution:
  `https://archive.apache.org/dist/spark/spark-4.1.0/spark-4.1.0-bin-hadoop3.tgz`

These public defaults keep the normal online build path unchanged.

## Build through a proxy

Set the build arguments only for the invocation that needs them:

```bash
PIP_INDEX_URL=https://proxy.example.com/pypi/simple \
PIP_TRUSTED_HOST=proxy.example.com \
SPARK_DIST_URL=https://proxy.example.com/apache/spark-4.1.0-bin-hadoop3.tgz \
./lakehouse start airflow
```

`PIP_TRUSTED_HOST` is optional. Leave it unset when the proxy presents a
certificate trusted by the build image.

A mirrored `SPARK_DIST_URL` must serve the same tarball as the Apache archive:
the build extracts it and expects a top-level `spark-4.1.0-bin-hadoop3/`
directory. Re-hosting the identical file under a different name is fine; a
repackaged archive with a different internal layout is not.

Jupyter accepts the same Python package arguments:

```bash
PIP_INDEX_URL=https://proxy.example.com/pypi/simple \
PIP_TRUSTED_HOST=proxy.example.com \
./lakehouse start notebooks
```

`./lakehouse start notebooks` builds the Jupyter image through the proxy only
when it does not yet exist. If `lakehouse-jupyter:spark-4.1.0` was already built
(for example against public PyPI), the command reuses that image and the proxy
arguments have no effect. To re-point an existing image at a proxy, rebuild it
explicitly first, then start:

```bash
PIP_INDEX_URL=https://proxy.example.com/pypi/simple \
PIP_TRUSTED_HOST=proxy.example.com \
docker compose -f docker-compose-notebooks.yml build
./lakehouse start notebooks
```

`./lakehouse start airflow` rebuilds on every start (`up --build`), so its proxy
arguments always take effect without this step.

The hosted Jupyter image is not part of the local Compose stack. Pass its
arguments directly:

```bash
docker build \
  --build-arg PIP_INDEX_URL=https://proxy.example.com/pypi/simple \
  --build-arg PIP_TRUSTED_HOST=proxy.example.com \
  -f docker/jupyter-hosted/Dockerfile \
  -t openlakehouse-notebooks .
```

Do not commit an internal proxy URL or credentials. Keep real values in the
shell environment or another local, ignored configuration source.

## Other dependency sources

- The dashboard sibling PR (#16) uses `NPM_REGISTRY` and `NPM_STRICT_SSL`
  build arguments in its own Compose file.
- Spark's lakehouse JARs are downloaded on the host by
  `scripts/tools/download-jars.sh`, then bind-mounted from `jars/`. Override
  `MAVEN_BASE_URL` when running that script; the images above do not resolve
  Maven dependencies during their builds.
- The local MLflow image only installs `postgresql-client` with `apt`; it does
  not run pip. Configuring an apt mirror is environment-specific and outside
  the scope of these package-index arguments.

This is proxy-friendly online building, not a fully air-gapped workflow. Image
base layers and package artifacts must remain reachable through the configured
network paths.
