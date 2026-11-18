"""All calculations: landed cost, profit and loss, unit economics, cash flow, scenarios.

Money is in USD. Revenue is always net of VAT.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

MARKETS = {"TN": "Tunisia", "NO": "Norway"}
SHIPPING = ["Freight", "Customs duty & import taxes", "Clearance & local transport"]
SELLING = ["Delivery to customers", "Failed deliveries", "Payment fees"]
MARKETING = ["Advertising", "Influencer gifting"]


@dataclass
class Dataset:
    products: pd.DataFrame
    shipments: pd.DataFrame
    sales: pd.DataFrame
    costs: pd.DataFrame


def load(data_dir: Path) -> Dataset:
    data_dir = Path(data_dir)
    read = lambda name: pd.read_csv(data_dir / f"{name}.csv")  # noqa: E731
    products, shipments, sales, costs = (read(n) for n in
                                         ("products", "shipments", "sales", "costs"))
    sales["date"] = pd.to_datetime(sales["date"])
    costs["date"] = pd.to_datetime(costs["date"])
    shipments["arrival_date"] = pd.to_datetime(shipments["arrival_date"])
    costs[["batch", "channel"]] = costs[["batch", "channel"]].fillna("")
    for df in (sales, costs):
        df["month"] = df["date"].dt.to_period("M")
    ds = Dataset(products, shipments, sales, costs)
    _add_unit_costs(ds)
    return ds


# ------------------------------------------------------------ landed cost
def landed_cost(ds: Dataset) -> pd.DataFrame:
    """Cost per unit for each shipment and product: product + freight + duty + clearance."""
    unit_cost = ds.products.set_index("sku")["unit_cost_usd"]
    ship = ds.shipments.copy()
    ship["product_cost"] = ship["sku"].map(unit_cost)
    per_batch = ds.costs[ds.costs["category"].isin(SHIPPING)].pivot_table(
        index="batch", columns="category", values="amount_usd", aggfunc="sum").reindex(
        columns=SHIPPING, fill_value=0.0).fillna(0.0)
    units = ship.groupby("batch")["units"].sum()
    ship["freight"] = ship["batch"].map(per_batch["Freight"] / units)
    ship["clearance"] = ship["batch"].map(per_batch["Clearance & local transport"] / units)
    # Duty is charged on value (goods + freight), so share it by value.
    value = ship["units"] * (ship["product_cost"] + ship["freight"])
    batch_value = value.groupby(ship["batch"]).transform("sum")
    duty_total = ship["batch"].map(per_batch["Customs duty & import taxes"])
    ship["duty"] = np.where(batch_value > 0, duty_total * value / batch_value / ship["units"], 0)
    ship["landed"] = ship[["product_cost", "freight", "duty", "clearance"]].sum(axis=1)
    return ship


def landed_by_batch(ds: Dataset) -> pd.DataFrame:
    """Average landed cost per unit per shipment (all products)."""
    ship = landed_cost(ds)
    cols = ["product_cost", "freight", "duty", "clearance", "landed"]
    weighted = ship[cols].mul(ship["units"], axis=0).assign(
        units=ship["units"], batch=ship["batch"], market=ship["market"],
        arrival_date=ship["arrival_date"])
    out = weighted.groupby(["batch", "market", "arrival_date"]).sum()
    out[cols] = out[cols].div(out["units"], axis=0)
    return out.drop(columns="units").reset_index().sort_values("arrival_date").reset_index(drop=True)


def _add_unit_costs(ds: Dataset) -> None:
    """Attach the landed cost of the exact shipment each sale came from."""
    lc = landed_cost(ds).set_index(["batch", "sku"])
    keys = list(zip(ds.sales["batch"], ds.sales["sku"]))
    for col in ("product_cost", "freight", "duty", "clearance"):
        ds.sales[f"{col}_usd"] = lc.loc[keys, col].to_numpy() * ds.sales["units"].to_numpy()
    ds.sales["landed_usd"] = ds.sales[["product_cost_usd", "freight_usd", "duty_usd",
                                       "clearance_usd"]].sum(axis=1)


# -------------------------------------------------------- profit and loss
def _shared_costs(ds: Dataset) -> pd.DataFrame:
    """Costs paid for the whole brand (design, advice, website...), excl. production."""
    return ds.costs[(ds.costs["market"] == "ALL") & (ds.costs["category"] != "Production")]


def pnl(ds: Dataset) -> pd.DataFrame:
    """Profit and loss per market. Shared brand costs are split by units sold."""
    units = ds.sales.groupby("market")["units"].sum()
    shared_total = _shared_costs(ds)["amount_usd"].sum()
    rows = {}
    for m in MARKETS:
        s = ds.sales[ds.sales["market"] == m]
        c = ds.costs[ds.costs["market"] == m].groupby("category")["amount_usd"].sum()
        get = lambda cats: float(sum(c.get(x, 0.0) for x in cats))  # noqa: E731
        other = float(c.drop(SHIPPING + SELLING + MARKETING, errors="ignore").sum())
        rows[MARKETS[m]] = {
            "Units sold": float(units[m]),
            "Revenue (excl. VAT)": float(s["net_usd"].sum()),
            "Product cost": float(s["product_cost_usd"].sum()),
            "Freight": get(["Freight"]),
            "Customs & clearance": get(["Customs duty & import taxes", "Clearance & local transport"]),
            "Delivery & payment": get(SELLING),
            "Marketing": get(MARKETING),
            "Other market costs": other,
            "Shared brand costs": shared_total * units[m] / units.sum(),
        }
    out = pd.DataFrame(rows)
    out["Total"] = out.sum(axis=1)
    cost_rows = out.index.drop(["Units sold", "Revenue (excl. VAT)"])
    out.loc["Profit before tax"] = out.loc["Revenue (excl. VAT)"] - out.loc[cost_rows].sum()
    out.loc["Profit margin"] = out.loc["Profit before tax"] / out.loc["Revenue (excl. VAT)"]
    out.loc["Profit per unit"] = out.loc["Profit before tax"] / out.loc["Units sold"]
    return out


def totals(ds: Dataset) -> dict:
    p = pnl(ds)["Total"]
    invested = ds.costs.loc[ds.costs["date"] < ds.sales["date"].min(), "amount_usd"].sum()
    flow = cash_flow(ds)
    payback = flow.loc[flow["cumulative"] >= 0, "month"]
    return {
        "units": int(p["Units sold"]),
        "revenue": float(p["Revenue (excl. VAT)"]),
        "profit": float(p["Profit before tax"]),
        "margin": float(p["Profit margin"]),
        "invested_before_launch": float(invested),
        "roi": float(p["Profit before tax"] / invested),
        "payback_month": payback.iloc[0] if not payback.empty else None,
    }


# ------------------------------------------------------- unit economics
def unit_economics(ds: Dataset) -> pd.DataFrame:
    """Average result per unit sold, per market and channel (before shared brand costs).

    Advertising and influencer costs only drive online sales, so they are charged
    to the online channel. Parapharmacies order in bulk without advertising.
    """
    s = ds.sales
    rows = []
    for (market, channel), g in s.groupby(["market", "channel"]):
        c = ds.costs[(ds.costs["market"] == market) & (ds.costs["channel"] == channel)]
        units = g["units"].sum()
        selling = c.loc[c["category"].isin(SELLING), "amount_usd"].sum()
        marketing = c.loc[c["category"].isin(MARKETING), "amount_usd"].sum()
        rows.append({
            "segment": f"{MARKETS[market]} {channel.lower()}", "market": market, "channel": channel,
            "units": units,
            "price": g["net_usd"].sum() / units,
            "product_cost": g["product_cost_usd"].sum() / units,
            "freight": g["freight_usd"].sum() / units,
            "customs_clearance": (g["duty_usd"].sum() + g["clearance_usd"].sum()) / units,
            "delivery_payment": selling / units,
            "marketing": marketing / units,
        })
    out = pd.DataFrame(rows)
    out["profit"] = out["price"] - out[["product_cost", "freight", "customs_clearance",
                                        "delivery_payment", "marketing"]].sum(axis=1)
    return out.sort_values("profit", ascending=False).reset_index(drop=True)


def profit_by_batch(ds: Dataset) -> pd.DataFrame:
    """Profit per unit for each shipment: shows how rising fees ate the margin."""
    ue = unit_economics(ds).set_index(["market", "channel"])
    s = ds.sales
    rows = []
    for batch, g in s.groupby("batch"):
        market = g["market"].iloc[0]
        selling = (g.groupby("channel")["units"].sum() *
                   (ue.loc[market]["delivery_payment"] + ue.loc[market]["marketing"])).sum()
        units = g["units"].sum()
        rows.append({"batch": batch, "market": market, "arrival": g["date"].min(),
                     "units": units,
                     "price": g["net_usd"].sum() / units,
                     "landed": g["landed_usd"].sum() / units,
                     "selling_marketing": selling / units})
    out = pd.DataFrame(rows)
    out["profit_per_unit"] = out["price"] - out["landed"] - out["selling_marketing"]
    return out.sort_values("arrival").reset_index(drop=True)


# ----------------------------------------------------------- over time
def monthly(ds: Dataset) -> pd.DataFrame:
    s = ds.sales.groupby(["month", "market", "channel"]).agg(
        units=("units", "sum"), revenue=("net_usd", "sum")).reset_index()
    return s


def cash_flow(ds: Dataset) -> pd.DataFrame:
    """Money out (costs, incl. the production order paid up front) and in (sales), per month."""
    cash_in = ds.sales.groupby("month")["net_usd"].sum()
    cash_out = ds.costs.groupby("month")["amount_usd"].sum()
    months = pd.period_range(min(cash_out.index.min(), cash_in.index.min()),
                             max(cash_out.index.max(), cash_in.index.max()), freq="M")
    out = pd.DataFrame({"month": months})
    out["cash_in"] = out["month"].map(cash_in).fillna(0.0)
    out["cash_out"] = out["month"].map(cash_out).fillna(0.0)
    out["net"] = out["cash_in"] - out["cash_out"]
    out["cumulative"] = out["net"].cumsum()
    return out


def by_product(ds: Dataset) -> pd.DataFrame:
    s = ds.sales.merge(ds.products[["sku", "product"]], on="sku")
    out = s.groupby(["product", "market"]).agg(
        units=("units", "sum"), revenue=("net_usd", "sum"), landed=("landed_usd", "sum"))
    out["gross_profit"] = out["revenue"] - out["landed"]
    return out.reset_index()


# ------------------------------------------------------------ scenarios
def freight_sensitivity(ds: Dataset, freights=np.arange(0.5, 6.01, 0.25)) -> pd.DataFrame:
    """Profit per unit if freight per unit were X (duty follows, as it is charged on value)."""
    ue = unit_economics(ds)
    duty_rate = _duty_rates(ds)
    rows = []
    for r in ue.itertuples():
        for f in freights:
            customs = r.customs_clearance + duty_rate[r.market] * (f - r.freight)
            rows.append({"segment": r.segment, "freight": f,
                         "profit": r.profit - (f - r.freight) - (customs - r.customs_clearance)})
    return pd.DataFrame(rows)


def break_even_freight(ds: Dataset) -> dict:
    """Freight per unit at which each segment stops making money."""
    ue = unit_economics(ds)
    rate = _duty_rates(ds)
    return {r.segment: r.freight + r.profit / (1 + rate[r.market]) for r in ue.itertuples()}


def _duty_rates(ds: Dataset) -> dict:
    lc = landed_cost(ds)
    rates = {}
    for m in MARKETS:
        g = lc[lc["market"] == m]
        value = (g["units"] * (g["product_cost"] + g["freight"])).sum()
        rates[m] = float((g["units"] * g["duty"]).sum() / value) if value else 0.0
    return rates


def next_run(ds: Dataset, freight_growth: float = 0.25, ads_growth: float = 0.15) -> pd.DataFrame:
    """Projected result of a second identical production run.

    Freight starts at the level of the LAST shipment to each market and rises a further
    `freight_growth`; advertising costs rise `ads_growth`. Prices and volumes stay the same.
    """
    ue = unit_economics(ds)
    lb = landed_by_batch(ds)
    rate = _duty_rates(ds)
    rows = []
    for r in ue.itertuples():
        last = lb[lb["market"] == r.market].iloc[-1]
        freight = last["freight"] * (1 + freight_growth)
        customs = last["clearance"] + rate[r.market] * (r.product_cost + freight)
        marketing = r.marketing * (1 + ads_growth)
        profit = r.price - r.product_cost - freight - customs - r.delivery_payment - marketing
        rows.append({"segment": r.segment, "units": r.units, "profit_per_unit_now": r.profit,
                     "profit_per_unit_next": profit, "profit_now": r.profit * r.units,
                     "profit_next": profit * r.units})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- findings
def findings(ds: Dataset) -> list:
    p, t = pnl(ds), totals(ds)
    ue = unit_economics(ds).set_index("segment")
    lb = landed_by_batch(ds)
    tn_first, tn_last = lb[lb["market"] == "TN"].iloc[0], lb[lb["market"] == "TN"].iloc[-1]
    nr = next_run(ds)
    out = [
        f"All {t['units']:,} units sold out in 9 months: USD {t['revenue']:,.0f} revenue "
        f"(excl. VAT) and USD {t['profit']:,.0f} profit before tax ({t['margin']:.0%} margin).",
        f"Tunisia made most of the money: {p.loc['Profit margin', 'Tunisia']:.0%} margin and "
        f"USD {p.loc['Profit per unit', 'Tunisia']:.2f} profit per unit. Norway was only just "
        f"profitable ({p.loc['Profit margin', 'Norway']:.0%} margin, "
        f"USD {p.loc['Profit per unit', 'Norway']:.2f} per unit): lower price (200 NOK), "
        f"discounts to compete and expensive ads and delivery.",
        f"Best channel: {ue.index[0]} at USD {ue['profit'].iloc[0]:.2f} per unit. "
        f"Parapharmacies paid less per unit but needed no advertising and bought in bulk.",
        f"The landed cost of a unit in Tunisia rose from USD {tn_first['landed']:.2f} "
        f"(first shipment) to USD {tn_last['landed']:.2f} (last), "
        f"+{tn_last['landed'] / tn_first['landed'] - 1:.0%}, driven by freight and the duty charged on it.",
        f"A second run with freight 25% above the last shipment and ads +15% would make "
        f"USD {nr['profit_next'].sum():,.0f} instead of USD {nr['profit_now'].sum():,.0f} "
        f"before brand costs ({nr['profit_next'].sum() / nr['profit_now'].sum() - 1:+.0%}), "
        f"with USD 20,000+ paid up front again, so the project was stopped.",
    ]
    if t["payback_month"] is not None:
        out.insert(1, f"The USD {t['invested_before_launch']:,.0f} spent before the first sale "
                      f"(production, design, first shipments) "
                      f"was earned back in {t['payback_month'].strftime('%B %Y')}.")
    return out
