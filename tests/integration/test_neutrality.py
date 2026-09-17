"""Format/engine neutrality — live (PR #13 / D8, I-42).

    I-42  In a single Spark session (the stack's spark-defaults, both extensions
          wired): write+read a **Delta** table via `unity.*`, AND resolve the
          read-only **Iceberg** REST catalog `iceberg.*` — with BOTH
          `spark.sql.extensions` loaded. Records the current Iceberg-write
          limitation (UC OSS is Delta-write / Iceberg-read-only) rather than
          asserting Iceberg writes work.

Runs inside spark-master-41 so it inherits config/spark/spark-defaults.conf
(Iceberg + Delta extensions, and the unity / iceberg / spark_catalog catalogs).
Skips when the container isn't running.
"""

from __future__ import annotations

import subprocess
import textwrap
import uuid

import pytest

MASTER = "spark-master-41"
pytestmark = [pytest.mark.integration, pytest.mark.merge]


def _master_running() -> bool:
    try:
        return (
            MASTER
            in subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.split()
        )
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _require_master():
    if not _master_running():
        pytest.skip(f"{MASTER} not running")


def test_i42_both_formats_one_session(tmp_path):
    sfx = uuid.uuid4().hex[:8]
    script = f"""
    from pyspark.sql import SparkSession
    s = SparkSession.builder.appName("i42").master("local[2]").config("spark.ui.enabled","false").getOrCreate()
    s.sparkContext.setLogLevel("ERROR")
    # Both extensions must be loaded in the one session.
    ext = s.conf.get("spark.sql.extensions", "")
    assert "IcebergSparkSessionExtensions" in ext, ext
    assert "DeltaSparkSessionExtension" in ext, ext
    # Delta WRITE+READ via the UC catalog (the write path).
    s.sql("CREATE SCHEMA IF NOT EXISTS unity.neut_{sfx}")
    t = "unity.neut_{sfx}.d"
    s.sql(f"CREATE TABLE IF NOT EXISTS {{t}} (id BIGINT) USING delta LOCATION 's3://lakehouse/warehouse/neut/{sfx}'")
    s.sql(f"INSERT INTO {{t}} VALUES (1),(2)")
    n = s.sql(f"SELECT count(*) FROM {{t}}").collect()[0][0]
    assert n == 2, n
    # Iceberg READ catalog resolves in the same session (read-only surface).
    s.sql("SHOW NAMESPACES IN iceberg").collect()
    print("I42_DELTA_OK read=%d" % n)
    # Record (do NOT assert success) the Iceberg-write limitation.
    try:
        s.sql("CREATE TABLE iceberg.neut_{sfx}.i (id BIGINT) USING iceberg")
        print("I42_ICEBERG_WRITE=UNEXPECTEDLY_ALLOWED")
    except Exception as e:
        print("I42_ICEBERG_WRITE=BLOCKED", type(e).__name__)
    print("I42_PASS")
    s.stop()
    """
    f = tmp_path / "i42.py"
    f.write_text(textwrap.dedent(script))
    subprocess.run(
        ["docker", "cp", str(f), f"{MASTER}:/tmp/_i42.py"],
        check=True,
        capture_output=True,
    )
    out = subprocess.run(
        ["docker", "exec", MASTER, "/opt/spark/bin/spark-submit", "/tmp/_i42.py"],
        capture_output=True,
        text=True,
        timeout=300,
    ).stdout
    # cleanup the UC table
    try:
        import urllib.request

        urllib.request.urlopen(
            urllib.request.Request(
                f"http://localhost:8081/api/2.1/unity-catalog/tables/unity.neut_{sfx}.d",
                method="DELETE",
            ),
            timeout=8,
        )
    except Exception:
        pass
    assert "I42_PASS" in out, f"neutrality session failed:\n{out[-1500:]}"
    assert "I42_DELTA_OK" in out
    # Iceberg write must NOT be silently allowed (pins the read-only story).
    assert (
        "I42_ICEBERG_WRITE=BLOCKED" in out
    ), f"Iceberg write not blocked:\n{out[-800:]}"
