"""Export a star schema (fact + dimension tables) ready to load into Power BI."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import analysis as a


def export(ds: a.Dataset, out_dir: Path) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sales = ds.sales.assign(
        date=ds.sales["date"].dt.date,
        market_name=ds.sales["market"].map(a.MARKETS),
    )[["order_id", "date", "market", "channel", "sku", "batch", "units", "discount",
       "gross_local", "vat_local", "net_local", "currency", "net_usd",
       "product_cost_usd", "freight_usd", "duty_usd", "clearance_usd", "landed_usd"]]

    costs = ds.costs.assign(date=ds.costs["date"].dt.date)[
        ["date", "market", "channel", "batch", "category", "amount", "currency", "amount_usd"]]
    costs["cost_group"] = costs["category"].map(
        lambda c: "Production" if c == "Production" else
        "Shipping & customs" if c in a.SHIPPING else
        "Delivery & payment" if c in a.SELLING else
        "Marketing" if c in a.MARKETING else "Brand & admin")

    dates = pd.DataFrame({"date": pd.date_range("2025-05-01", "2026-05-31", freq="D")})
    dates["year"] = dates["date"].dt.year
    dates["month_number"] = dates["date"].dt.month
    dates["month"] = dates["date"].dt.strftime("%b %Y")
    dates["month_start"] = dates["date"].dt.to_period("M").dt.start_time.dt.date
    dates["date"] = dates["date"].dt.date

    markets = pd.DataFrame([
        {"market": "TN", "market_name": "Tunisia", "currency": "TND", "vat_rate": 0.19},
        {"market": "NO", "market_name": "Norway", "currency": "NOK", "vat_rate": 0.25},
        {"market": "ALL", "market_name": "Shared (brand)", "currency": "USD", "vat_rate": None},
    ])
    shipments = a.landed_by_batch(ds).assign(arrival_date=lambda d: d["arrival_date"].dt.date)

    tables = {"fact_sales": sales, "fact_costs": costs, "dim_date": dates,
              "dim_product": ds.products, "dim_market": markets, "dim_shipment": shipments}
    paths = []
    for name, df in tables.items():
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        paths.append(path)
    return paths
