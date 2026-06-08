# Facilitator Guide — open-lakehouse demo notebooks

Everything you need to deliver these demos. **You do not need to install anything** — the
environment runs in your browser. If you can open a URL and press `Shift`+`Enter`, you can run this.

## 1. Open your environment

1. Go to your assigned URL: **`https://nb-<your-name>.openlakehousedemos.dev`**
2. Enter your token when asked (your facilitator gives you both).
3. You'll see JupyterLab. The three demo notebooks are in the file list on the left.

That's it — Spark, Kafka, and the catalog are already running inside your environment.

## 2. The three demos (run in any order)

| Notebook | Teaches | ~Time |
|----------|---------|-------|
| `sdp_medallion.ipynb` | Declarative SQL pipelines + SDP catching a bug before it runs | ~4 min |
| `rtm_trigger.ipynb` | Real-Time Mode is a one-line trigger change | ~3 min |
| `imperative_vs_declarative.ipynb` | Why declarative is easier to own (code read, nothing runs) | ~3 min |

## 3. How to run any notebook

- Press `Shift`+`Enter` to run a cell and move to the next.
- **Always run the first "warm-up" cell first** — it starts Spark (~10s). Do this while you talk
  through the intro so there's no dead air.
- The **markdown cells are your script.** Look for:
  - **💬 Say:** the line to deliver
  - **👀 Point at:** what to highlight on screen
- Run cells **top to bottom**, one at a time, narrating as you go. Don't use "Run All" — you want
  to pace it and let each result land.

## 4. The one slow step

In `sdp_medallion.ipynb`, the **`spark-pipelines run`** cell takes ~1–1.5 minutes (it processes real
data). Narrate the bronze → silver → gold layers as they print `COMPLETED`. If you want it faster for
a tight slot, ask your facilitator to lower `MEDALLION_MAX_ROWS` on your environment.

## 5. If something goes wrong

| Symptom | Fix |
|---------|-----|
| A cell hangs on the first run | The kernel is still starting Spark — give the warm-up cell ~15s. |
| `spark-pipelines run` errors with "table ... already exists" / truncate | You ran it twice. Run the **Reset** cell at the bottom of the SDP notebook, then re-run. |
| Charts/tables look empty | Make sure the `run` cell finished (`Run is COMPLETED`) before the query cell. |
| Kernel seems stuck | Kernel menu → **Restart Kernel**, then re-run the warm-up cell. |

## 6. Between sessions / handing off to the next person

- SDP notebook: run the **Reset** cell (drops your tables; Unity Catalog has no truncate).
- RTM notebook: nothing to clean up; just re-run the warm-up cell.
- Each environment is isolated — your tables land in your own schema (`managed_demo.<your-name>`),
  so you won't collide with anyone running at the same time.

## 7. What's actually running (for the curious / for Q&A)

- **Compute:** Spark 4.1 in your browser-hosted environment (real local JVM — that's why Real-Time
  Mode and `spark-pipelines` work).
- **Catalog + storage:** a shared **Unity Catalog** (`managed_demo`) on AWS; your Delta tables register
  there and you can browse them in the UC console.
- **Streaming:** a small Kafka broker runs alongside your notebook for the Real-Time Mode demo.
