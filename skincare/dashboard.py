"""Interactive HTML dashboard (Plotly). One self-contained page, opens in any browser."""
from __future__ import annotations

import html

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import analysis as a

TN, TN_LIGHT, NO = "#b4536b", "#e3a3b3", "#3b6ea8"
INK, MUTED, GRID = "#1f2430", "#6b7280", "#eceef2"
GREEN, RED = "#2f855a", "#c0392b"
SEGMENT_COLORS = {"Tunisia online": TN, "Tunisia parapharmacy": TN_LIGHT, "Norway online": NO}
PLOTLY_JS = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"


def _style(fig: go.Figure, title: str, height: int = 360) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0, "font": {"size": 16, "color": INK}},
        template="plotly_white", height=height,
        font={"family": "Inter, 'Segoe UI', system-ui, sans-serif", "color": INK, "size": 12},
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        legend={"orientation": "h", "y": -0.18, "x": 0},
        paper_bgcolor="white", plot_bgcolor="white",
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor="#cfd3da")
    return fig


def cash_flow_chart(ds) -> go.Figure:
    cf = a.cash_flow(ds)
    months = [m.strftime("%b %y") for m in cf["month"]]
    fig = go.Figure()
    fig.add_bar(x=months, y=cf["net"], name="Net cash in the month",
                marker_color=[GREEN if v >= 0 else RED for v in cf["net"]], opacity=0.55)
    fig.add_scatter(x=months, y=cf["cumulative"], name="Cumulative", mode="lines+markers",
                    line={"color": INK, "width": 3})
    t = a.totals(ds)
    title = "Cash flow"
    if t["payback_month"] is not None:
        fig.add_annotation(x=t["payback_month"].strftime("%b %y"), y=0, text="Money back",
                           showarrow=True, arrowhead=2, ay=-45, font={"color": GREEN})
        title = ("Cash flow: production paid up front, money back by "
                 + t["payback_month"].strftime("%B %Y"))
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return _style(fig, title)


def monthly_units_chart(ds) -> go.Figure:
    m = a.monthly(ds)
    fig = go.Figure()
    for (market, channel), color in ((("TN", "Online"), TN), (("TN", "Parapharmacy"), TN_LIGHT),
                                     (("NO", "Online"), NO)):
        g = m[(m["market"] == market) & (m["channel"] == channel)]
        fig.add_bar(x=[p.strftime("%b %y") for p in g["month"]], y=g["units"],
                    name=f"{a.MARKETS[market]} {channel.lower()}", marker_color=color)
    fig.update_layout(barmode="stack")
    return _style(fig, "Units sold per month")


def unit_economics_chart(ds) -> go.Figure:
    ue = a.unit_economics(ds)
    fig = make_subplots(rows=1, cols=len(ue), subplot_titles=list(ue["segment"]),
                        shared_yaxes=True, horizontal_spacing=0.03)
    steps = [("Price", "price", 1), ("Product", "product_cost", -1), ("Freight", "freight", -1),
             ("Customs", "customs_clearance", -1), ("Delivery", "delivery_payment", -1),
             ("Ads", "marketing", -1)]
    for i, r in enumerate(ue.itertuples(), start=1):
        values = [sign * getattr(r, col) for _, col, sign in steps] + [r.profit]
        fig.add_trace(go.Waterfall(
            x=[s[0] for s in steps] + ["Profit"], y=values,
            measure=["absolute"] + ["relative"] * (len(steps) - 1) + ["total"],
            text=[f"${abs(v):.2f}" for v in values], textposition="outside",
            textfont={"size": 10},
            increasing={"marker": {"color": SEGMENT_COLORS[r.segment]}},
            decreasing={"marker": {"color": "#c9ced6"}},
            totals={"marker": {"color": GREEN if r.profit >= 0 else RED}},
            connector={"line": {"color": GRID}}, showlegend=False), row=1, col=i)
    fig.update_yaxes(tickprefix="$", range=[min(0, ue["profit"].min()) - 3, ue["price"].max() * 1.18])
    fig.update_annotations(font={"size": 13})
    return _style(fig, "Where the money goes, per unit sold (USD, excl. VAT, before shared brand costs)",
                  height=420).update_layout(margin={"t": 80})


def landed_cost_chart(ds) -> go.Figure:
    lb = a.landed_by_batch(ds)
    labels = [f"{b}<br>{d:%b %y}" for b, d in zip(lb["batch"], lb["arrival_date"])]
    fig = go.Figure()
    for col, name, color in (("product_cost", "Product (Korea)", "#9aa3b2"),
                             ("freight", "Freight", "#e0a458"),
                             ("duty", "Customs & import taxes", "#c56a4a"),
                             ("clearance", "Clearance", "#7c5c7a")):
        fig.add_bar(x=labels, y=lb[col], name=name, marker_color=color)
    fig.add_scatter(x=labels, y=lb["landed"], mode="text", text=[f"${v:.2f}" for v in lb["landed"]],
                    textposition="top center", showlegend=False)
    fig.update_layout(barmode="stack")
    fig.update_yaxes(tickprefix="$", range=[0, lb["landed"].max() * 1.2])
    return _style(fig, "Landed cost per unit, by shipment")


def batch_profit_chart(ds) -> go.Figure:
    pb = a.profit_by_batch(ds)
    fig = go.Figure()
    for m, color in (("TN", TN), ("NO", NO)):
        g = pb[pb["market"] == m]
        fig.add_bar(x=g["batch"], y=g["profit_per_unit"], name=a.MARKETS[m], marker_color=color,
                    text=[f"${v:.2f}" for v in g["profit_per_unit"]], textposition="outside")
    fig.update_yaxes(tickprefix="$", range=[min(0, pb["profit_per_unit"].min()) * 1.2,
                                            pb["profit_per_unit"].max() * 1.2])
    return _style(fig, "Profit per unit, by shipment (before shared brand costs)")


def sensitivity_chart(ds) -> go.Figure:
    sens = a.freight_sensitivity(ds)
    lb = a.landed_by_batch(ds)
    fig = go.Figure()
    for seg, g in sens.groupby("segment"):
        fig.add_scatter(x=g["freight"], y=g["profit"], name=seg, mode="lines",
                        line={"color": SEGMENT_COLORS[seg], "width": 3})
    fig.add_hline(y=0, line={"color": RED, "dash": "dot"})
    for r in lb.itertuples():
        fig.add_vline(x=r.freight, line={"color": GRID, "width": 1})
    fig.update_xaxes(title="Freight per unit (USD)", tickprefix="$")
    fig.update_yaxes(title="Profit per unit", tickprefix="$")
    return _style(fig, "What if freight keeps rising? (grey lines = actual shipments)")


def next_run_chart(ds) -> go.Figure:
    nr = a.next_run(ds)
    fig = go.Figure()
    fig.add_bar(x=nr["segment"], y=nr["profit_now"], name="This run (actual)", marker_color="#9aa3b2")
    fig.add_bar(x=nr["segment"], y=nr["profit_next"], name="Next run (projected)",
                marker_color=[SEGMENT_COLORS[s] for s in nr["segment"]])
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return _style(fig, "Projected profit of a second production run")


def _pnl_table(ds) -> str:
    p = a.pnl(ds)
    rows = []
    for label, values in p.iterrows():
        cells = []
        for v in values:
            if label == "Units sold":
                cells.append(f"{v:,.0f}")
            elif label == "Profit margin":
                cells.append(f"{v:.0%}")
            elif label == "Profit per unit":
                cells.append(f"${v:,.2f}")
            elif label in ("Revenue (excl. VAT)", "Profit before tax"):
                cells.append(f"${v:,.0f}")
            elif round(v) == 0:
                cells.append("$0")
            else:
                cells.append(f"&minus;${v:,.0f}")
        cls = ' class="strong"' if label in ("Revenue (excl. VAT)", "Profit before tax") else ""
        neg = lambda c, v: f'<td class="neg">{c}</td>' if (  # noqa: E731
            label in ("Profit before tax", "Profit margin", "Profit per unit") and v < 0) else f"<td>{c}</td>"
        rows.append(f"<tr{cls}><th>{html.escape(label)}</th>" +
                    "".join(neg(c, v) for c, v in zip(cells, values)) + "</tr>")
    head = "".join(f"<th>{c}</th>" for c in p.columns)
    return f'<table class="pnl"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def build_html(ds) -> str:
    t = a.totals(ds)
    sold_pct = t["units"] / ds.products["units_made"].sum()
    kpis = [
        ("Units sold", f"{t['units']:,}", f"{sold_pct:.0%} of stock, sold out"),
        ("Revenue", f"${t['revenue'] / 1000:,.1f}k", "excl. VAT"),
        ("Profit before tax", f"${t['profit'] / 1000:,.1f}k", f"{t['margin']:.0%} margin"),
        ("Money back", t["payback_month"].strftime("%b %Y") if t["payback_month"] else "-",
         f"${t['invested_before_launch'] / 1000:,.1f}k spent before first sale"),
        ("Return", f"{t['roi']:.0%}", "profit / money spent before first sale"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="label">{l}</div><div class="value">{v}</div>'
        f'<div class="sub">{s}</div></div>' for l, v, s in kpis)
    findings = "".join(f"<li>{html.escape(f)}</li>" for f in a.findings(ds))
    charts = {
        "cash": cash_flow_chart(ds), "units": monthly_units_chart(ds),
        "unit": unit_economics_chart(ds), "landed": landed_cost_chart(ds),
        "batch": batch_profit_chart(ds), "sens": sensitivity_chart(ds),
        "next": next_run_chart(ds),
    }
    div = {k: f.to_html(full_html=False, include_plotlyjs=False,
                        config={"displayModeBar": False, "responsive": True})
           for k, f in charts.items()}
    be = a.break_even_freight(ds)
    be_text = "; ".join(f"{k}: ${v:.2f}" for k, v in be.items())

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aphrodite Skincare - Import & Sales Analysis</title>
<script src="{PLOTLY_JS}"></script>
<style>
 :root {{ --ink:{INK}; --muted:{MUTED}; --line:#e5e7eb; --bg:#f6f4f2; --accent:{TN}; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--ink);
        font-family:Inter,'Segoe UI',system-ui,sans-serif; }}
 header {{ background:#2b1d26; color:#fff; padding:28px 16px 24px; }}
 .wrap {{ max-width:1240px; margin:0 auto; padding:0 16px; }}
 header .wrap {{ padding:0; }}
 h1 {{ margin:0; font-size:30px; letter-spacing:-0.5px; }}
 header p {{ margin:6px 0 0; color:#d9c7cf; }}
 .note {{ font-size:13px; color:#c9b2bd; margin-top:10px; }}
 .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:20px 0; }}
 .kpi {{ background:#fff; border-radius:12px; padding:14px 16px; border-left:4px solid var(--accent); }}
 .kpi .label {{ font-size:12px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); }}
 .kpi .value {{ font-size:26px; font-weight:700; margin-top:4px; }}
 .kpi .sub {{ font-size:12px; color:var(--muted); margin-top:2px; }}
 .card {{ background:#fff; border-radius:12px; padding:14px 16px; margin-bottom:16px; min-width:0; }}
 .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
 .grid > .card {{ margin-bottom:0; }}
 .row {{ margin-bottom:16px; }}
 h2 {{ font-size:16px; margin:0 0 10px; }}
 ul.findings {{ margin:0; padding-left:20px; line-height:1.6; }}
 table.pnl {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
 table.pnl th, table.pnl td {{ padding:7px 8px; border-bottom:1px solid var(--line); text-align:right; }}
 table.pnl th:first-child {{ text-align:left; font-weight:500; }}
 table.pnl thead th {{ color:var(--muted); font-weight:600; }}
 table.pnl tr.strong th, table.pnl tr.strong td {{ font-weight:700; }}
 td.neg {{ color:{RED}; }}
 .decision {{ border-left:4px solid {RED}; }}
 footer {{ color:var(--muted); font-size:12.5px; padding:8px 0 32px; }}
 @media (max-width: 860px) {{ .grid {{ grid-template-columns:1fr; }} h1 {{ font-size:24px; }} }}
</style></head>
<body>
<header><div class="wrap">
 <h1>Aphrodite Skincare &ndash; Import &amp; Sales Analysis</h1>
 <p>3 products made in Korea &middot; sold in Tunisia and Norway &middot; Sep 2025 &ndash; May 2026</p>
 <div class="note">Reconstructed figures: the key facts are real, detailed records were not kept,
 so volumes and fees are realistic estimates. All amounts in USD, revenue excluding VAT.</div>
</div></header>
<main class="wrap">
 <section class="kpis">{kpi_html}</section>
 <section class="card"><h2>Key findings</h2><ul class="findings">{findings}</ul></section>
 <section class="grid row"><div class="card">{div['cash']}</div><div class="card">{div['units']}</div></section>
 <section class="card">{div['unit']}</section>
 <section class="grid row"><div class="card">{div['landed']}</div><div class="card">{div['batch']}</div></section>
 <section class="grid row">
  <div class="card"><h2>Profit and loss by market</h2>{_pnl_table(ds)}
   <p style="font-size:12.5px;color:{MUTED}">Shared brand costs (design, formulation advice,
   samples, photos, website, bank fees) are split by units sold.</p></div>
  <div class="card">{div['sens']}
   <p style="font-size:12.5px;color:{MUTED}">Break-even freight per unit: {be_text}.</p></div>
 </section>
 <section class="grid row">
  <div class="card">{div['next']}</div>
  <div class="card decision"><h2>Decision: stop after the first run</h2>
   <ul class="findings">
    <li>Tunisia was clearly profitable, especially online, but every shipment cost more to land.</li>
    <li>Norway stayed only just profitable at 200 NOK: with strong competition, freight, delivery
        and ads took almost the whole price. Higher fees would push it to break-even.</li>
    <li>A second run needs USD 20,000+ up front again, for clearly less profit.</li>
    <li>What could have changed the result: sea freight in one bigger shipment, focus on Tunisia
        (online + parapharmacies) and leave Norway, or raise the Norway price with a smaller range.</li>
   </ul></div>
 </section>
 <footer>Built with Python, pandas and Plotly. Source code and data:
 github.com/eskandersnoussi/skincare-import-analysis</footer>
</main>
</body></html>"""
