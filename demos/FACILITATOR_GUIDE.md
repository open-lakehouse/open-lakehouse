# Booth Facilitator Guide — open-lakehouse demos

For booth staff. **The audience reads the notebook on screen, so this guide is *yours* —
your script, timing, and answers. The notebooks themselves carry only what a viewer should see.**

You don't install anything. If you can open a URL and press `Shift`+`Enter`, you can run these.

---

## Per-visitor flow (do this every time)

1. **Run the top "Run me first" cell.** It resets to a clean slate *and* warms up Spark (~10s).
   Doing this for each visitor means you never hit a stale-table error.
2. Press `Shift`+`Enter` down the notebook, one cell at a time, talking over each.
3. When they walk away, you're already reset for the next person — just run the top cell again.

Open your station at **`https://nb-<your-name>.openlakehousedemos.dev`** (token from your lead).
Each station is isolated — your tables land in `managed_demo.<your-name>`, so simultaneous stations never collide.

---

## The 60-second hook (for foot traffic)

If someone's just passing, run **only** the dependency-error cell in the SDP notebook:

> "This is open-source Spark. I've got a data pipeline with a typo in a table name. Watch — one
> command checks the entire pipeline before running it... and there it is, caught instantly. No job,
> no wasted compute. Want to see it build the real thing?"

That's a 10-second win that pulls people in.

---

## Demo 1 — `sdp_medallion.ipynb`  (~2 min with the fast row count)

| You do | You say |
|--------|---------|
| Run warm-up | "Quick reset, starting Spark." |
| Show `ls` + the silver SQL | "A whole pipeline here is just SQL files — one `SELECT` per table. No orchestration, no write code." |
| Run the **dry-run** | "Before running anything, Spark validates the whole dependency graph. I've left a typo in here on purpose..." → point at `orderz` in the output. "Caught it. That bug would've crashed a normal job halfway through." |
| Run the pipeline | "Now the real run — bronze, silver, gold, in order, no orchestration code from me." (≈20–30s; narrate the layers) |
| Show the chart | "And there's real revenue per brand, computed by the pipeline, registered in the catalog." |

## Demo 2 — `rtm_trigger.ipynb`  (~2 min)

| You do | You say |
|--------|---------|
| Run warm-up | "Starting a live stream of order events." |
| Show the guardrails | "Every order is screened — oversized, too many items, leaked credentials — and routed allow or quarantine." |
| Point at the trigger block | "Turning on Real-Time Mode isn't a rewrite — it's **one line**, the trigger." |
| Run micro-batch, then real-time | "Same query both times. The only thing I changed is the trigger." → point at `use_realtime`. |

## Demo 3 — `imperative_vs_declarative.ipynb`  (~2 min, nothing runs)

| You do | You say |
|--------|---------|
| Show `imperative_medallion.py` | "Here's the same pipeline the old way — session setup, manual ordering, a write for every table, ~90 lines." |
| Show the SQL | "And here it is declaratively — a few `SELECT`s, ~30 lines." |
| Show the table | "Shorter, validated before it runs, and easy to hand off. That's the case for declarative." |

---

## "Wait, is this Databricks?" — the answer

**No.** Everything here is **open source**: Apache Spark 4.1 (declarative pipelines + Real-Time Mode
are OSS Spark features), Unity Catalog OSS as the catalog, Delta Lake for the tables. No proprietary
runtime is involved — it runs on a laptop or any cluster. That's the whole point of the demo.

---

## If something goes wrong

| Symptom | Fix |
|---------|-----|
| Stale-table / truncate error on the pipeline run | You skipped the warm-up. Run the top cell (it resets), then re-run. |
| First cell hangs | Spark is still starting — give it ~15s. |
| Kernel stuck | Kernel menu → **Restart Kernel** → run the warm-up cell. |
| Chart empty | The `run` cell hadn't finished (`Run is COMPLETED`) before the query cell. |

## Under the hood (for the curious)

- **Compute:** Spark 4.1 in your hosted environment — a real local JVM, which is why Real-Time Mode
  and `spark-pipelines` work.
- **Catalog + storage:** shared Unity Catalog OSS (`managed_demo`) on AWS; your Delta tables register
  there and are browsable in the UC console.
- **Streaming:** a small Kafka broker runs alongside your notebook for the Real-Time Mode demo.
