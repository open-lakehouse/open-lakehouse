#!/usr/bin/env python3
"""Generate open-lakehouse architecture diagrams as SVG.

Source of truth: docs/architecture.md and README.md. Emits self-contained SVGs
(light + dark for the hero, single for the flow) that are rendered to PNG by
render.sh via rsvg-convert. Regenerate with: python3 docs/img/_gen_diagrams.py
"""
from html import escape

FONT = "Arial, 'Helvetica Neue', Helvetica, sans-serif"
MONO = "'SF Mono', 'DejaVu Sans Mono', Menlo, Consolas, monospace"

THEMES = {
    "light": {
        "page": "#ffffff",
        "ink": "#1b2430",
        "muted": "#5b6472",
        "arrow": "#94a3b8",
        "chip_fill": "#ffffff",
        "chip_stroke": "#cbd5e1",
        "chip_ink": "#334155",
        "layers": {
            "clients": ("#eef2ff", "#6366f1", "#4338ca"),
            "compute": ("#fff7ed", "#f97316", "#c2410c"),
            "catalog": ("#f0fdfa", "#14b8a6", "#0f766e"),
            "storage": ("#f8fafc", "#64748b", "#475569"),
            "stream":  ("#f5f3ff", "#8b5cf6", "#6d28d9"),
            "ops":     ("#f0f9ff", "#0ea5e9", "#0369a1"),
        },
    },
    "dark": {
        "page": "#0d1117",
        "ink": "#e6edf3",
        "muted": "#8b949e",
        "arrow": "#6e7681",
        "chip_fill": "#1c2230",
        "chip_stroke": "#30363d",
        "chip_ink": "#c9d1d9",
        "layers": {
            "clients": ("#1a1e3a", "#818cf8", "#a5b4fc"),
            "compute": ("#2a1e13", "#fb923c", "#fdba74"),
            "catalog": ("#0f2723", "#2dd4bf", "#5eead4"),
            "storage": ("#1a2028", "#94a3b8", "#cbd5e1"),
            "stream":  ("#1e1a33", "#a78bfa", "#c4b5fd"),
            "ops":     ("#0d2233", "#38bdf8", "#7dd3fc"),
        },
    },
}


def esc(s):
    return escape(str(s), quote=True)


class SVG:
    def __init__(self, w, h, theme):
        self.w, self.h, self.t = w, h, theme
        self.el = []

    def rect(self, x, y, w, h, rx, fill, stroke=None, sw=1.5, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.el.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}"{s}{d}/>'
        )

    def text(self, x, y, s, size=15, fill=None, weight="400", anchor="start",
             font=None, spacing=None):
        fill = fill or self.t["ink"]
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        self.el.append(
            f'<text x="{x}" y="{y}" font-family="{font or FONT}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}"{ls}>{esc(s)}</text>'
        )

    def line(self, x1, y1, x2, y2, stroke=None, sw=2, dash=None, marker=True):
        stroke = stroke or self.t["arrow"]
        d = f' stroke-dasharray="{dash}"' if dash else ""
        m = ' marker-end="url(#arrow)"' if marker else ""
        self.el.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{sw}"{d}{m}/>'
        )

    def path(self, d, stroke=None, sw=2, dash=None, marker=True, fill="none"):
        stroke = stroke or self.t["arrow"]
        da = f' stroke-dasharray="{dash}"' if dash else ""
        m = ' marker-end="url(#arrow)"' if marker else ""
        self.el.append(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}"{da}{m}/>'
        )

    def chip(self, x, y, label, pad=13, h=30, size=13.5):
        w = int(len(label) * size * 0.60) + pad * 2
        self.rect(x, y, w, h, h / 2, self.t["chip_fill"],
                  self.t["chip_stroke"], 1.25)
        self.text(x + w / 2, y + h / 2 + size * 0.35, label, size,
                  self.t["chip_ink"], "500", "middle")
        return w

    def chip_row(self, x, y, labels, gap=10, **kw):
        cx = x
        for lb in labels:
            cx += self.chip(cx, y, lb, **kw) + gap
        return cx

    def band(self, x, y, w, h, key, title, subtitle=None):
        fill, stroke, tink = self.t["layers"][key]
        self.rect(x, y, w, h, 14, fill, stroke, 2)
        self.rect(x, y, 6, h, 3, stroke)  # accent spine
        self.text(x + 22, y + 30, title, 17, tink, "800", "start",
                  spacing="1.5")
        if subtitle:
            self.text(x + 22, y + 50, subtitle, 12.5, self.t["muted"], "400")

    def render(self):
        defs = (
            '<defs>'
            '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{self.t["arrow"]}"/>'
            '</marker></defs>'
        )
        body = "\n".join(self.el)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
            f'height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
            f'{defs}'
            f'<rect width="{self.w}" height="{self.h}" fill="{self.t["page"]}"/>'
            f'{body}</svg>'
        )


def architecture(theme_name):
    t = THEMES[theme_name]
    W, H = 1320, 900
    s = SVG(W, H, t)

    # ---- column geometry ----
    cx, cw = 330, 660          # center stack
    lx, lw = 40, 250           # left: streaming
    rx, rw = 1030, 250         # right: ops/tooling
    mid = cx + cw / 2

    # ---- CLIENTS ----
    y = 60
    s.band(cx, y, cw, 116, "clients", "CLIENTS",
           "any engine — Spark or not")
    s.chip_row(cx + 20, y + 62, ["PySpark  sc://", "spark-pipelines (SDP)",
                                 "DuckDB"])
    s.chip_row(cx + 20, y + 62 + 38, ["PyIceberg", "Trino", "JupyterLab"])

    # ---- COMPUTE ----
    yc = 250
    s.band(cx, yc, cw, 176, "compute", "COMPUTE — Spark 4.1 (Connect-first)")
    s.chip_row(cx + 20, yc + 62,
               ["spark-connect-41  :15002 (gRPC)",
                "spark-master-41  :7078"])
    s.chip_row(cx + 20, yc + 62 + 36,
               ["spark-worker-41  UI :8083", "master UI :8082"])
    # medallion mini-flow inside compute
    my = yc + 138
    med = [("BRONZE", "compute"), ("SILVER", "compute"), ("GOLD", "compute")]
    mw, mgap, mstart = 120, 46, cx + 40
    _, mstroke, mink = t["layers"]["compute"]
    for i, (lab, _k) in enumerate(med):
        bx = mstart + i * (mw + mgap)
        s.rect(bx, my, mw, 30, 8, t["chip_fill"], mstroke, 1.5)
        s.text(bx + mw / 2, my + 20, lab, 13, mink, "700", "middle",
               spacing="1")
        if i < 2:
            s.line(bx + mw + 6, my + 15, bx + mw + mgap - 6, my + 15,
                   mstroke, 2)
    s.text(mstart + 3 * mw + 2 * mgap + 14, my + 20, "medallion", 12,
           t["muted"], "400", "start")

    # ---- CATALOG ----
    yg = 500
    s.band(cx, yg, cw, 128, "catalog", "CATALOG — Unity Catalog OSS (only catalog)")
    s.chip_row(cx + 20, yg + 62,
               ["UC OSS  :8081", "Iceberg REST (read)", "Delta (write)"])
    s.chip_row(cx + 20, yg + 62 + 36,
               ["PostgreSQL  :5432", "UC metastore"])

    # ---- STORAGE ----
    yst = 700
    s.band(cx, yst, cw, 138, "storage", "STORAGE — SeaweedFS (S3-compatible)")
    s.text(cx + 22, yst + 62, "SeaweedFS  :8333   →   s3://lakehouse/warehouse/", 14,
           t["ink"], "600", font=MONO)
    s.chip_row(cx + 20, yst + 82,
               ["bronze/", "silver/", "gold/", "_checkpoints/",
                "pipeline-history/"],
               size=12.5)

    # ---- center vertical arrows ----
    lay = t["layers"]
    def dn(y1, y2, label=None, offset=0):
        x = mid + offset
        s.line(x, y1, x, y2)
        if label:
            s.rect(x + 10, (y1 + y2) / 2 - 12, len(label) * 6.6 + 16, 22, 6,
                   t["page"])
            s.text(x + 18, (y1 + y2) / 2 + 3, label, 11.5, t["muted"], "500")
    dn(y + 116, yc, "Spark Connect gRPC  sc://:15002", offset=-140)
    dn(yc + 176, yg, "Iceberg REST  /  Delta API")
    dn(yg + 128, yst, "data files (Parquet)")

    # multi-engine read: clients bypass compute straight to catalog (right curve)
    rxc = cx + cw - 30
    s.path(f"M {rxc} {y+116} C {cx+cw+22} {y+190}, {cx+cw+22} {yg-50}, "
           f"{rxc} {yg}", lay["catalog"][1], 2, dash="6 5")
    s.text(cx + cw + 30, 322, "Iceberg REST", 11.5,
           lay["catalog"][2], "700", "start")
    s.text(cx + cw + 30, 340, "multi-engine read", 11.5,
           t["muted"], "400", "start")

    # ---- LEFT: streaming ----
    s.band(lx, yc, lw, 176, "stream", "STREAMING")
    s.chip_row(lx + 18, yc + 62, ["Kafka  :9092"])
    s.chip_row(lx + 18, yc + 62 + 36, ["Zookeeper  :2181"])
    s.text(lx + 18, yc + 150, "events → readStream", 12, t["muted"],
           "400")
    s.line(lx + lw, yc + 88, cx, yc + 88, lay["stream"][1], 2.2)
    s.text((lx + lw + cx) / 2, yc + 80, "stream", 11, t["muted"], "500",
           "middle")

    # ---- RIGHT: ops & tooling (aligned beside catalog + storage) ----
    s.text(rx, 480 - 14, "OPERATIONS & TOOLING", 12.5, t["muted"], "700",
           spacing="1.2")
    cards = [
        ("Airflow  :8085", "orchestration", 480),
        ("MLflow  :5000 / :5001", "tracking + AI gateway", 558),
        ("Dashboard  :3000", "read-only Next.js viewer", 636),
        ("Delta Sharing  :8443", "OpenSharing + proxy", 714),
    ]
    _, ostroke, oink = lay["ops"]
    for label, sub, oy in cards:
        s.rect(rx, oy, rw, 62, 12, t["layers"]["ops"][0], ostroke, 1.75)
        s.text(rx + 18, oy + 27, label, 14, oink, "700")
        s.text(rx + 18, oy + 47, sub, 12, t["muted"], "400")

    return s.render()


def medallion(theme_name):
    t = THEMES[theme_name]
    W, H = 1600, 380
    s = SVG(W, H, t)
    lay = t["layers"]

    s.text(40, 46, "Streaming path: Kafka → Spark → Delta (medallion)",
           18, t["ink"], "800")
    s.text(40, 70, "driven by the Spark Connect client  ·  sc://localhost:15002",
           13, t["muted"], "400", font=MONO)

    boxes = [
        ("Kafka topic", ":9092", "stream", 40),
        ("Structured\nStreaming", "Spark 4.1", "compute", 370),
        ("BRONZE", "Delta / UC", "storage", 700),
        ("SILVER", "SDP", "catalog", 1030),
        ("GOLD", "SDP", "clients", 1360),
    ]
    bw, bh, by = 200, 96, 140
    labels = ["readStream", "writeStream", "spark-pipelines", "spark-pipelines"]
    for i, (title, sub, key, bx) in enumerate(boxes):
        fill, stroke, tink = lay[key]
        s.rect(bx, by, bw, bh, 14, fill, stroke, 2)
        lines = title.split("\n")
        ty = by + bh / 2 - (len(lines) - 1) * 11 + 4
        for ln in lines:
            s.text(bx + bw / 2, ty, ln, 17, tink, "800", "middle")
            ty += 22
        s.text(bx + bw / 2, by + bh - 16, sub, 12.5, t["muted"], "500",
               "middle", font=MONO)
        if i < len(boxes) - 1:
            gap_x1 = bx + bw + 8
            gap_x2 = bx + bw + (boxes[i + 1][3] - (bx + bw)) - 8
            s.line(gap_x1, by + bh / 2, gap_x2, by + bh / 2, t["arrow"], 2.2)
            lbl = labels[i]
            s.text((gap_x1 + gap_x2) / 2, by + bh / 2 - 12, lbl, 12,
                   t["muted"], "600", "middle", font=MONO)

    s.text(40, by + bh + 54,
           "Checkpoints live under  s3://lakehouse/warehouse/_checkpoints/<dataset>/  "
           "so streams resume cleanly after restart.",
           13, t["muted"], "400", font=MONO)
    return s.render()


if __name__ == "__main__":
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    out = {
        "architecture-light.svg": architecture("light"),
        "architecture-dark.svg": architecture("dark"),
        "medallion-flow-light.svg": medallion("light"),
        "medallion-flow-dark.svg": medallion("dark"),
    }
    for name, svg in out.items():
        with open(os.path.join(here, name), "w") as f:
            f.write(svg)
        print("wrote", name)
