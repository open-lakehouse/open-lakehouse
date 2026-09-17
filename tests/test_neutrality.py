"""Neutrality guards (PR #13 / D8, §3.8).

Static assertions that the merge keeps the platform format- and engine-neutral
rather than letting the Databricks-flavored surface crowd out the open one:

    U-35  dual-format extensions stay enabled (Iceberg AND Delta)
    U-36  all three catalog namespaces stay configured
          (unity=UCSingleCatalog, iceberg=RESTCatalog@UC REST URI, spark_catalog=DeltaCatalog)
    U-40  no staging-registry image references survive (newfrontdocker/) outside
          CHANGELOG / docs/merge

(U-37 multi-engine demo + U-38 optional-services are the later CP-feature PR.)
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPARK_DEFAULTS = REPO_ROOT / "config" / "spark" / "spark-defaults.conf.example"

pytestmark = pytest.mark.merge


class TestU35DualFormatExtensions:
    def test_both_extensions_enabled(self):
        text = SPARK_DEFAULTS.read_text()
        ext_line = next(
            (
                ln
                for ln in text.splitlines()
                if ln.strip().startswith("spark.sql.extensions")
            ),
            "",
        )
        assert (
            "IcebergSparkSessionExtensions" in ext_line
        ), "Iceberg extension must stay enabled"
        assert (
            "DeltaSparkSessionExtension" in ext_line
        ), "Delta extension must stay enabled"


class TestU36CatalogNamespaces:
    def test_three_namespaces_configured(self):
        text = SPARK_DEFAULTS.read_text()
        # unity -> UC connector
        assert "spark.sql.catalog.unity" in text
        assert "io.unitycatalog.spark.UCSingleCatalog" in text
        # iceberg -> RESTCatalog at the UC Iceberg REST URI (read path)
        assert "spark.sql.catalog.iceberg" in text
        assert "RESTCatalog" in text
        assert "unity-catalog/iceberg" in text
        # spark_catalog -> DeltaCatalog
        assert "spark.sql.catalog.spark_catalog" in text
        assert "org.apache.spark.sql.delta.catalog.DeltaCatalog" in text


class TestU40NoStagingRegistryImage:
    def test_no_newfrontdocker_references(self):
        offenders = []
        exts = ("*.md", "*.yml", "*.yaml", "*.py", "*.sh", "*.conf", "*.example")
        for ext in exts:
            for path in REPO_ROOT.rglob(ext):
                rel = path.relative_to(REPO_ROOT)
                parts = set(rel.parts)
                # Allowed to mention it: the merge provenance/analysis, a CHANGELOG,
                # and the test suite (assertions/docstrings reference the string).
                if "merge" in parts or rel.name.upper().startswith("CHANGELOG"):
                    continue
                if parts & {".venv", "jars", ".git", "tests"}:
                    continue
                try:
                    if "newfrontdocker/" in path.read_text():
                        offenders.append(str(rel))
                except (UnicodeDecodeError, OSError):
                    continue
        assert not offenders, f"staging-registry image references survive: {offenders}"
