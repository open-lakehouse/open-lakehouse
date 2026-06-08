"""Drop this presenter's medallion tables so the pipeline can be re-run.
UC OSS has no TRUNCATE, so an existing table fails SDP's re-run; drop first.
Reads DEMO_NS + UC_TOKEN from the environment."""

import os
import urllib.request

NS = os.environ.get("DEMO_NS", "medallion_demo").rstrip("_") or "medallion_demo"
TOK = os.environ.get("UC_TOKEN", "")
BASE = "https://uc.openlakehousedemos.dev/api/2.1/unity-catalog"
HDR = {"Authorization": f"Bearer {TOK}"}

for t in (
    "gold_brand_summary",
    "gold_hourly_metrics",
    "orders_enriched",
    "orders_bronze",
    "dim_locations",
):
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"{BASE}/tables/managed_demo.{NS}.{t}", method="DELETE", headers=HDR
            )
        )
        print("dropped", t)
    except Exception:
        pass
print(f"reset complete (schema managed_demo.{NS})")
