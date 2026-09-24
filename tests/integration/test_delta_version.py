"""Delta Lake version / ABI gate (PR #13 / T-1.11, I-02).

    I-02  Delta 4.3.1 on Spark 4.1.0 / Java 21: write + append + read +
          time-travel via the stack's configured jars, with no ABI break
          (NoSuchMethodError / AbstractMethodError). Also pins the version:
          the stack runs Delta 4.3.1 (4.3.0 NPEs through the UC connector;
          4.2.0 can't do catalog-managed Delta).

Runs inside spark-master-41 (which mounts the pinned jars and spark-defaults),
so it exercises the exact classpath the stack ships. Skips when the container
is not running.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MASTER = "spark-master-41"

pytestmark = [pytest.mark.integration]


def _master_running() -> bool:
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.split()
        return MASTER in out
    except Exception:
        return False


def _spark_submit(script: str, tmp_path: Path) -> str:
    """docker cp a helper into spark-master and run it via spark-submit."""
    f = tmp_path / "helper.py"
    f.write_text(textwrap.dedent(script))
    subprocess.run(
        ["docker", "cp", str(f), f"{MASTER}:/tmp/_ivtest.py"],
        check=True,
        capture_output=True,
    )
    r = subprocess.run(
        ["docker", "exec", MASTER, "/opt/spark/bin/spark-submit", "/tmp/_ivtest.py"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    # Return BOTH streams: spark-submit writes the driver's print() to stdout but
    # every error (stack trace, ABI NoSuchMethodError, S3A/connectivity failure)
    # to stderr. Capturing stdout only made a failed run look like empty output,
    # which is undiagnosable and lets the negative gate "pass" for the wrong
    # reason. The I02_PASS / error-signature assertions scan the combined text.
    return f"{r.stdout}\n--- stderr ---\n{r.stderr}"


@pytest.fixture(autouse=True)
def _require_master():
    if not _master_running():
        pytest.skip(f"{MASTER} not running")


def test_i02_delta_431_pinned_in_config():
    conf = (REPO_ROOT / "config" / "spark" / "spark-defaults.conf.example").read_text()
    assert "delta-spark_2.13-4.3.1.jar" in conf, "stack must pin Delta 4.3.1"
    assert "delta-spark_2.13-4.2.0.jar" not in conf
    assert "delta-spark_2.13-4.3.0.jar" not in conf


def test_i02_delta_write_read_timetravel(tmp_path):
    out = _spark_submit(
        """
        from pyspark.sql import SparkSession
        s = (SparkSession.builder.appName("i02").master("local[2]")
             .config("spark.ui.enabled","false").getOrCreate())
        s.sparkContext.setLogLevel("ERROR")
        p = "s3a://lakehouse/warehouse/_i02_delta"
        s.range(0,5).write.format("delta").mode("overwrite").save(p)   # v0
        s.range(5,10).write.format("delta").mode("append").save(p)     # v1
        latest = s.read.format("delta").load(p).count()
        v0 = s.read.format("delta").option("versionAsOf",0).load(p).count()
        print(f"I02 latest={latest} v0={v0}")
        assert latest==10 and v0==5, "time-travel/counts wrong"
        print("I02_PASS")
        s.stop()
        """,
        tmp_path,
    )
    assert "I02_PASS" in out, f"Delta write/read/time-travel failed:\n{out[-1500:]}"
    assert "NoSuchMethodError" not in out and "AbstractMethodError" not in out
