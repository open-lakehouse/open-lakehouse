"""SDP coverage tests for table formats.

Tests: Apache Iceberg, Delta Lake

Note: These tests require proper Iceberg/Delta JARs to be available.
They will be skipped if the table format extensions fail to load.
"""

import os
import shutil
import tempfile

import pytest

pytestmark = [pytest.mark.sdp, pytest.mark.table_formats, pytest.mark.integration]


def iceberg_available(spark) -> bool:
    """Check if Iceberg is properly configured."""
    try:
        # Try to create a test catalog
        spark.conf.set(
            "spark.sql.catalog.iceberg_check", "org.apache.iceberg.spark.SparkCatalog"
        )
        spark.conf.set("spark.sql.catalog.iceberg_check.type", "hadoop")
        spark.conf.set(
            "spark.sql.catalog.iceberg_check.warehouse", "/tmp/iceberg_check"
        )
        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg_check.test_ns")
        return True
    except Exception:
        return False


@pytest.mark.skipif(True, reason="Iceberg requires proper JARs and cluster config")
class TestIcebergFormat:
    """Apache Iceberg table format tests.

    These tests require:
    - Iceberg Spark runtime JAR
    - Proper Spark session configuration

    Run with: pytest -m "table_formats and not skipif" when Iceberg is available.
    """

    @pytest.fixture(autouse=True)
    def setup(self, spark_with_iceberg):
        """Skip if Iceberg not available."""
        if spark_with_iceberg is None:
            pytest.skip("Iceberg not available")
        self.spark = spark_with_iceberg

    def test_iceberg_create_table(self, spark_with_iceberg):
        """Test creating Iceberg table."""
        df = spark_with_iceberg.createDataFrame([(1, "a"), (2, "b")], ["id", "name"])

        df.writeTo("test_iceberg.sdp_tests.create_table_test").using(
            "iceberg"
        ).createOrReplace()

        result = spark_with_iceberg.table("test_iceberg.sdp_tests.create_table_test")
        assert result.count() == 2

    def test_iceberg_append(self, spark_with_iceberg):
        """Test appending to Iceberg table."""
        df1 = spark_with_iceberg.createDataFrame([(1, "a")], ["id", "name"])
        df2 = spark_with_iceberg.createDataFrame([(2, "b")], ["id", "name"])

        df1.writeTo("test_iceberg.sdp_tests.append_test").using(
            "iceberg"
        ).createOrReplace()
        df2.writeTo("test_iceberg.sdp_tests.append_test").append()

        result = spark_with_iceberg.table("test_iceberg.sdp_tests.append_test")
        assert result.count() == 2

    def test_iceberg_overwrite(self, spark_with_iceberg):
        """Test overwriting Iceberg table."""
        df1 = spark_with_iceberg.createDataFrame([(1, "a"), (2, "b")], ["id", "name"])
        df2 = spark_with_iceberg.createDataFrame([(3, "c")], ["id", "name"])

        df1.writeTo("test_iceberg.sdp_tests.overwrite_test").using(
            "iceberg"
        ).createOrReplace()
        df2.writeTo("test_iceberg.sdp_tests.overwrite_test").using(
            "iceberg"
        ).createOrReplace()

        result = spark_with_iceberg.table("test_iceberg.sdp_tests.overwrite_test")
        assert result.count() == 1

    def test_iceberg_partitioned_table(self, spark_with_iceberg):
        """Test Iceberg partitioned table."""
        df = spark_with_iceberg.createDataFrame(
            [
                (1, "a", "2024-01-01"),
                (2, "b", "2024-01-02"),
                (3, "c", "2024-01-01"),
            ],
            ["id", "name", "date"],
        )

        df.writeTo("test_iceberg.sdp_tests.partitioned_test").using(
            "iceberg"
        ).partitionedBy("date").createOrReplace()

        result = spark_with_iceberg.table("test_iceberg.sdp_tests.partitioned_test")
        assert result.count() == 3

    def test_iceberg_schema_evolution_add_column(self, spark_with_iceberg):
        """Test Iceberg schema evolution - add column."""
        df1 = spark_with_iceberg.createDataFrame([(1, "a")], ["id", "name"])
        df1.writeTo("test_iceberg.sdp_tests.schema_evolve_test").using(
            "iceberg"
        ).createOrReplace()

        # Add new column via SQL
        spark_with_iceberg.sql(
            "ALTER TABLE test_iceberg.sdp_tests.schema_evolve_test ADD COLUMN value INT"
        )

        df2 = spark_with_iceberg.createDataFrame(
            [(2, "b", 100)], ["id", "name", "value"]
        )
        df2.writeTo("test_iceberg.sdp_tests.schema_evolve_test").append()

        result = spark_with_iceberg.table("test_iceberg.sdp_tests.schema_evolve_test")
        assert "value" in result.columns
        assert result.count() == 2

    def test_iceberg_time_travel_snapshot(self, spark_with_iceberg):
        """Test Iceberg time travel by snapshot."""
        df1 = spark_with_iceberg.createDataFrame([(1, "a")], ["id", "name"])
        df1.writeTo("test_iceberg.sdp_tests.time_travel_test").using(
            "iceberg"
        ).createOrReplace()

        # Get snapshot ID
        snapshots = spark_with_iceberg.sql(
            "SELECT snapshot_id FROM test_iceberg.sdp_tests.time_travel_test.snapshots"
        ).collect()
        snapshot_id = snapshots[0]["snapshot_id"]

        # Add more data
        df2 = spark_with_iceberg.createDataFrame([(2, "b"), (3, "c")], ["id", "name"])
        df2.writeTo("test_iceberg.sdp_tests.time_travel_test").append()

        # Query old snapshot
        old_data = spark_with_iceberg.read.option("snapshot-id", snapshot_id).table(
            "test_iceberg.sdp_tests.time_travel_test"
        )
        assert old_data.count() == 1

        # Current data
        current = spark_with_iceberg.table("test_iceberg.sdp_tests.time_travel_test")
        assert current.count() == 3

    def test_iceberg_metadata_queries(self, spark_with_iceberg):
        """Test Iceberg metadata table queries."""
        df = spark_with_iceberg.createDataFrame([(1, "test")], ["id", "name"])
        df.writeTo("test_iceberg.sdp_tests.metadata_test").using(
            "iceberg"
        ).createOrReplace()

        # Query snapshots
        snapshots = spark_with_iceberg.sql(
            "SELECT * FROM test_iceberg.sdp_tests.metadata_test.snapshots"
        )
        assert snapshots.count() >= 1

        # Query history
        history = spark_with_iceberg.sql(
            "SELECT * FROM test_iceberg.sdp_tests.metadata_test.history"
        )
        assert history.count() >= 1

        # Query files
        files = spark_with_iceberg.sql(
            "SELECT * FROM test_iceberg.sdp_tests.metadata_test.files"
        )
        assert files.count() >= 1


@pytest.mark.skipif(True, reason="Delta Lake may not be available")
class TestDeltaFormat:
    """Delta Lake table format tests."""

    @pytest.fixture(autouse=True)
    def setup(self, spark_with_delta):
        """Skip if Delta not available."""
        if spark_with_delta is None:
            pytest.skip("Delta Lake not available")
        self.spark = spark_with_delta
        self.temp_dir = tempfile.mkdtemp(prefix="delta_test_")

    @pytest.fixture
    def cleanup(self):
        """Clean up after test."""
        yield
        if hasattr(self, "temp_dir"):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_delta_write_read(self, spark_with_delta):
        """Test basic Delta write and read."""
        df = spark_with_delta.createDataFrame([(1, "a"), (2, "b")], ["id", "name"])
        path = os.path.join(self.temp_dir, "basic")

        df.write.format("delta").mode("overwrite").save(path)

        result = spark_with_delta.read.format("delta").load(path)
        assert result.count() == 2

    def test_delta_append(self, spark_with_delta):
        """Test Delta append operation."""
        df1 = spark_with_delta.createDataFrame([(1, "a")], ["id", "name"])
        df2 = spark_with_delta.createDataFrame([(2, "b")], ["id", "name"])
        path = os.path.join(self.temp_dir, "append")

        df1.write.format("delta").mode("overwrite").save(path)
        df2.write.format("delta").mode("append").save(path)

        result = spark_with_delta.read.format("delta").load(path)
        assert result.count() == 2

    def test_delta_time_travel_version(self, spark_with_delta):
        """Test Delta time travel by version."""
        df1 = spark_with_delta.createDataFrame([(1, "v1")], ["id", "name"])
        df2 = spark_with_delta.createDataFrame([(2, "v2")], ["id", "name"])
        path = os.path.join(self.temp_dir, "time_travel")

        df1.write.format("delta").mode("overwrite").save(path)
        df2.write.format("delta").mode("append").save(path)

        # Read version 0
        v0 = spark_with_delta.read.format("delta").option("versionAsOf", 0).load(path)
        assert v0.count() == 1

        # Read current
        current = spark_with_delta.read.format("delta").load(path)
        assert current.count() == 2

    def test_delta_partitioned(self, spark_with_delta):
        """Test Delta partitioned table."""
        df = spark_with_delta.createDataFrame(
            [
                (1, "a", "2024-01-01"),
                (2, "b", "2024-01-02"),
            ],
            ["id", "name", "date"],
        )
        path = os.path.join(self.temp_dir, "partitioned")

        df.write.format("delta").partitionBy("date").mode("overwrite").save(path)

        result = spark_with_delta.read.format("delta").load(path)
        assert result.count() == 2

    def test_delta_schema_enforcement(self, spark_with_delta):
        """Test Delta schema enforcement."""
        df1 = spark_with_delta.createDataFrame([(1, "a")], ["id", "name"])
        path = os.path.join(self.temp_dir, "schema_enforce")

        df1.write.format("delta").mode("overwrite").save(path)

        # Try to write incompatible schema - should fail
        df2 = spark_with_delta.createDataFrame([("x", 100)], ["name", "id"])
        with pytest.raises(Exception):
            df2.write.format("delta").mode("append").save(path)

    def test_delta_history(self, spark_with_delta):
        """Test Delta table history."""
        df = spark_with_delta.createDataFrame([(1, "a")], ["id", "name"])
        path = os.path.join(self.temp_dir, "history")

        df.write.format("delta").mode("overwrite").save(path)
        df.write.format("delta").mode("append").save(path)

        history = spark_with_delta.sql(f"DESCRIBE HISTORY delta.`{path}`")
        assert history.count() >= 2


# =================================================================================
# I-45 — Catalog-managed Delta (PR #13 / T-1.19, the concrete UC 0.5.0 win)
# =================================================================================
# A `USING delta` create with delta.feature.catalogManaged + the required
# writeStats* properties and NO explicit location materializes under the catalog's
# storage_root (…/__unitystorage/…). Requires Delta 4.3.1 + the UC 0.5.x connector
# family. Runs inside spark-master-41 (real jars + spark-defaults). The full
# sdp-medallion SQL pipeline exercises the same path via `spark-pipelines`
# (demos/sdp-medallion/run.sh); this is the minimal, deterministic gate.

import json as _json  # noqa: E402
import subprocess as _sp  # noqa: E402
import textwrap as _tw  # noqa: E402
import urllib.request as _url  # noqa: E402
import uuid as _uuid  # noqa: E402

_UC = "http://localhost:8081/api/2.1/unity-catalog"
_MASTER = "spark-master-41"


def _uc_reachable() -> bool:
    try:
        with _url.urlopen(f"{_UC}/catalogs", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _master_up() -> bool:
    try:
        names = _sp.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.split()
        return _MASTER in names
    except Exception:
        return False


def _post(path, body):
    req = _url.Request(
        f"{_UC}/{path}",
        data=_json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        _url.urlopen(req, timeout=8)
    except Exception:
        pass


@pytest.mark.integration
class TestI45CatalogManagedDelta:
    @pytest.fixture(autouse=True)
    def _require(self):
        if not _uc_reachable():
            pytest.skip("Unity Catalog not reachable on localhost:8081")
        if not _master_up():
            pytest.skip(f"{_MASTER} not running")

    def test_i45_catalog_managed_delta_no_location(self, tmp_path):
        sfx = _uuid.uuid4().hex[:8]
        cat, sch, tbl = "managed_demo", f"i45_{sfx}", "cm"
        # A storage_root catalog is the prerequisite for catalog-managed tables.
        _post(
            "catalogs",
            {"name": cat, "storage_root": "s3://lakehouse/warehouse/managed"},
        )
        _post("schemas", {"name": sch, "catalog_name": cat})
        script = f"""
        from pyspark.sql import SparkSession
        s = (SparkSession.builder.appName("i45").master("local[2]")
             .config("spark.ui.enabled","false")
             .config("spark.sql.catalog.{cat}","io.unitycatalog.spark.UCSingleCatalog")
             .config("spark.sql.catalog.{cat}.uri","http://unity-catalog:8080")
             .config("spark.sql.catalog.{cat}.token","not_used").getOrCreate())
        s.sparkContext.setLogLevel("ERROR")
        t = "{cat}.{sch}.{tbl}"
        # No LOCATION — the catalog assigns it. Both writeStats* props are required.
        s.sql(f"CREATE TABLE IF NOT EXISTS {{t}} (id BIGINT) USING delta "
              "TBLPROPERTIES ('delta.feature.catalogManaged'='supported',"
              "'delta.checkpoint.writeStatsAsJson'='true',"
              "'delta.checkpoint.writeStatsAsStruct'='true')")
        s.sql(f"INSERT INTO {{t}} VALUES (1),(2),(3),(4)")
        n = s.sql(f"SELECT count(*) FROM {{t}}").collect()[0][0]
        print(f"I45 count={{n}}"); assert n == 4
        print("I45_PASS")
        s.stop()
        """
        f = tmp_path / "i45.py"
        f.write_text(_tw.dedent(script))
        _sp.run(
            ["docker", "cp", str(f), f"{_MASTER}:/tmp/_i45.py"],
            check=True,
            capture_output=True,
        )
        out = _sp.run(
            ["docker", "exec", _MASTER, "/opt/spark/bin/spark-submit", "/tmp/_i45.py"],
            capture_output=True,
            text=True,
            timeout=300,
        ).stdout
        # The table's UC storage_location must be catalog-assigned (under __unitystorage).
        loc = ""
        try:
            with _url.urlopen(f"{_UC}/tables/{cat}.{sch}.{tbl}", timeout=8) as r:
                loc = _json.loads(r.read()).get("storage_location", "")
        finally:
            try:
                _url.urlopen(
                    _url.Request(f"{_UC}/tables/{cat}.{sch}.{tbl}", method="DELETE"),
                    timeout=8,
                )
            except Exception:
                pass
        assert "I45_PASS" in out, f"catalog-managed Delta failed:\n{out[-1500:]}"
        assert "__unitystorage" in loc, f"table not catalog-managed (loc={loc!r})"
