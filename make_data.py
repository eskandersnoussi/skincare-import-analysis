"""Rebuild the business data for Aphrodite Skincare (Sep 2025 - May 2026).

    python make_data.py          # writes data/*.csv

The original sales records were not kept. These tables are a RECONSTRUCTION:
the facts below come from the real business, everything else is an estimate
chosen to be realistic for the two markets. All estimates are listed in
ASSUMPTIONS so they are easy to review and change.

Facts from the business
- 3 products made in Korea under the brand's own name and packaging,
  1,500 units each (4,500 units), USD 20,000 in total
- 3,000 units imported to Tunisia, 1,500 to Norway; everything sold out
- Tunisia: premium price 110 TND, sold online and to parapharmacies in bulk
- Norway: 200 NOK, online, harder competition, more expensive advertising
- Import and transport fees went up over time, which reduced the margin
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

ASSUMPTIONS = {
    "fx_per_usd": {"USD": 1.0, "TND": 3.05, "NOK": 10.6},
    # Share of the USD 20,000 production order per product
    "products": [
        ("SER", "Hydrating Serum", 0.375),
        ("CRM", "Repair Cream", 0.350),
        ("CLN", "Gentle Cleanser", 0.275),
    ],
    "units_per_product": 1500,
    "production_usd": 20000,
    "vat": {"TN": 0.19, "NO": 0.25},
    # Shipments from Korea: (batch, market, arrival date, units per product,
    #                        freight USD per unit, clearance + local transport USD)
    "shipments": [
        ("TN-1", "TN", date(2025, 9, 3), 334, 1.05, 180),
        ("NO-1", "NO", date(2025, 9, 10), 250, 1.70, 140),
        ("TN-2", "TN", date(2025, 12, 2), 333, 1.60, 260),
        ("NO-2", "NO", date(2026, 1, 12), 250, 2.40, 210),
        ("TN-3", "TN", date(2026, 3, 3), 333, 2.40, 380),
    ],
    # Customs duty + import taxes on cosmetics, share of goods + freight value
    "duty_rate": {"TN": 0.36, "NO": 0.0},
    # Units sold per month, Sep 2025 .. May 2026 (adds up to the stock per market)
    "monthly_units": {
        "TN": [250, 300, 380, 420, 300, 320, 380, 360, 290],
        "NO": [110, 160, 200, 240, 150, 150, 170, 170, 150],
    },
    "parapharmacy_share_tn": 0.45,          # from October
    "retail_price": {"TN": 110.0, "NO": 200.0},        # incl. VAT, local currency
    "parapharmacy_price_tnd": 55.0,          # per unit excl. VAT; 52 from 48 units
    "bundle_discount": 0.10,                 # 3-product bundle online
    "promo": {"TN": (0.15, 0.20), "NO": (0.15, 0.20)},  # (discount, share of orders)
    "black_friday": {"TN": 0.15, "NO": 0.20},           # November discount
    "delivery_per_order": {"TN_online": 8.0, "TN_parapharmacy": 25.0, "NO_online": 55.0},
    "failed_delivery_rate_tn": 0.15,         # cash-on-delivery orders that come back
    "payment_fee": {"TN_online": 0.015, "TN_parapharmacy": 0.0, "NO_online": 0.029},
    "ads_per_month": {"TN": 1800.0, "NO": 3000.0},     # local currency
    "one_off_usd": [
        (date(2025, 5, 15), "ALL", "Formulation advice", 900),
        (date(2025, 5, 20), "ALL", "Brand & packaging design", 1400),
        (date(2025, 6, 10), "ALL", "Samples & testing", 350),
        (date(2025, 7, 10), "ALL", "Bank & transfer fees", 300),
        (date(2025, 8, 1), "TN", "Product registration (Tunisia)", 1200),
        (date(2025, 8, 20), "ALL", "Product photos", 450),
        (date(2025, 9, 5), "TN", "Influencer gifting", 400),
        (date(2025, 12, 5), "TN", "Influencer gifting", 300),
        (date(2025, 9, 12), "NO", "Influencer gifting", 450),
    ],
    "website_usd_per_month": 45,
}

MONTHS = pd.period_range("2025-09", "2026-05", freq="M")


def _usd(amount, currency):
    return amount / ASSUMPTIONS["fx_per_usd"][currency]


class Stock:
    """FIFO stock per product and shipment batch."""

    def __init__(self, shipments):
        self.lots = []  # [arrival, batch, sku, units_left]
        for batch, _m, arrival, units, *_ in shipments:
            for sku, *_ in ASSUMPTIONS["products"]:
                self.lots.append([arrival, batch, sku, units])

    def available(self, sku, on):
        return sum(l[3] for l in self.lots if l[2] == sku and l[0] <= on)

    def total(self, on):
        return sum(l[3] for l in self.lots if l[0] <= on)

    def take(self, sku, units, on):
        """Remove units, oldest batch first. Returns [(batch, units)]."""
        out = []
        for lot in self.lots:
            if units == 0:
                break
            if lot[2] == sku and lot[0] <= on and lot[3] > 0:
                n = min(units, lot[3])
                lot[3] -= n
                units -= n
                out.append((lot[1], n))
        return out


def _pick_skus(rng, stock, units, on):
    """Split an order over products, in proportion to what is left in stock."""
    skus = [p[0] for p in ASSUMPTIONS["products"]]
    picked = {s: 0 for s in skus}
    for _ in range(units):
        weights = np.array([stock.available(s, on) - picked[s] for s in skus], float)
        if weights.sum() <= 0:
            break
        picked[skus[rng.choice(len(skus), p=weights / weights.sum())]] += 1
    return {s: n for s, n in picked.items() if n}


def _order_sizes(rng, units, channel):
    sizes = []
    while units > 0:
        if channel == "Parapharmacy":
            size = int(rng.choice([24, 30, 36, 42, 48, 60]))
        else:
            size = int(rng.choice([1, 2, 3], p=[0.55, 0.30, 0.15]))
        size = min(size, units)
        sizes.append(size)
        units -= size
    return sizes


def generate(seed: int = 7) -> dict:
    a = ASSUMPTIONS
    rng = np.random.default_rng(seed)
    lines, costs = [], []
    order_no = 0

    def cost(day, market, category, amount, currency, batch="", channel=""):
        costs.append({"date": day, "market": market, "channel": channel, "batch": batch,
                      "category": category,
                      "amount": round(amount, 2), "currency": currency,
                      "amount_usd": round(_usd(amount, currency), 2)})

    # Production order, split by product
    for sku, _name, share in a["products"]:
        cost(date(2025, 7, 10), "ALL", "Production", a["production_usd"] * share, "USD", sku)

    # Shipments: freight, duty, clearance
    unit_cost = {sku: a["production_usd"] * share / a["units_per_product"]
                 for sku, _n, share in a["products"]}
    for batch, market, arrival, units, freight, clearance in a["shipments"]:
        goods = sum(unit_cost[s] * units for s in unit_cost)
        n_units = units * len(unit_cost)
        cost(arrival, market, "Freight", freight * n_units, "USD", batch)
        cost(arrival, market, "Customs duty & import taxes",
             a["duty_rate"][market] * (goods + freight * n_units), "USD", batch)
        cost(arrival, market, "Clearance & local transport", clearance, "USD", batch)

    for market, currency in (("TN", "TND"), ("NO", "NOK")):
        stock = Stock([s for s in a["shipments"] if s[1] == market])
        arrivals = {s[2] for s in a["shipments"] if s[1] == market}
        for month, target in zip(MONTHS, a["monthly_units"][market]):
            arrival_days = [d.day for d in arrivals if d.year == month.year and d.month == month.month]
            first_day = max(arrival_days) + 2 if arrival_days else 1
            last_day = month.days_in_month
            if month == MONTHS[-1]:
                target = stock.total(date(2026, 5, 31))      # sell the remainder
            para = 0
            if market == "TN" and month > MONTHS[0]:
                para = int(round(target * a["parapharmacy_share_tn"] / 6) * 6)
            plan = [("Parapharmacy", para), ("Online", target - para)]
            orders_in_month = {"Online": 0, "Parapharmacy": 0}
            for channel, units in plan:
                for size in _order_sizes(rng, units, channel):
                    day = date(month.year, month.month, int(rng.integers(first_day, last_day + 1)))
                    split = _pick_skus(rng, stock, size, day)
                    if not split:
                        continue
                    order_no += 1
                    orders_in_month[channel] += 1
                    size = sum(split.values())
                    # Price per unit (local currency, incl. VAT for consumers)
                    if channel == "Parapharmacy":
                        price = 52.0 if size >= 48 else a["parapharmacy_price_tnd"]
                        discount, vat_included = 0.0, False
                    else:
                        price = a["retail_price"][market]
                        promo_discount, promo_share = a["promo"][market]
                        discount = 0.0
                        if month.month == 11:
                            discount = a["black_friday"][market]
                        elif rng.random() < promo_share:
                            discount = promo_discount
                        if size >= 3 and len(split) == 3:
                            discount = max(discount, a["bundle_discount"])
                        vat_included = True
                    for sku, n in split.items():
                        for batch, units_from_batch in stock.take(sku, n, day):
                            gross = units_from_batch * price * (1 - discount)
                            vat_rate = a["vat"][market]
                            if vat_included:
                                net = gross / (1 + vat_rate)
                            else:
                                net, gross = gross, gross * (1 + vat_rate)
                            lines.append({
                                "order_id": f"{market}-{order_no:05d}", "date": day,
                                "market": market, "channel": channel, "sku": sku,
                                "batch": batch, "units": units_from_batch,
                                "list_price": price, "discount": discount,
                                "gross_local": round(gross, 2), "vat_local": round(gross - net, 2),
                                "net_local": round(net, 2), "currency": currency,
                                "net_usd": round(_usd(net, currency), 2),
                            })
                    order_id = f"{market}-{order_no:05d}"
                    gross_order = sum(l["gross_local"] for l in lines if l["order_id"] == order_id)
                    key = f"{market}_{channel.lower()}"
                    fee = a["payment_fee"][key] * gross_order
                    if fee:
                        cost(day, market, "Payment fees", fee, currency, channel=channel)

            mid = date(month.year, month.month, 15)
            for channel, n in orders_in_month.items():
                key = f"{market}_{channel.lower()}"
                if n and key in a["delivery_per_order"]:
                    cost(mid, market, "Delivery to customers", n * a["delivery_per_order"][key],
                         currency, channel=channel)
            if market == "TN" and orders_in_month["Online"]:
                failed = round(orders_in_month["Online"] * a["failed_delivery_rate_tn"])
                cost(mid, market, "Failed deliveries", failed * 2 * a["delivery_per_order"]["TN_online"],
                     currency, channel="Online")
            cost(date(month.year, month.month, 1), market, "Advertising", a["ads_per_month"][market],
                 currency, channel="Online")

    for day, market, category, amount in a["one_off_usd"]:
        cost(day, market, category, amount, "USD",
             channel="Online" if category == "Influencer gifting" else "")
    for month in pd.period_range("2025-08", "2026-05", freq="M"):
        cost(date(month.year, month.month, 1), "ALL", "Website & tools", a["website_usd_per_month"], "USD")

    products = pd.DataFrame(
        [(sku, name, a["production_usd"] * share / a["units_per_product"], a["units_per_product"])
         for sku, name, share in a["products"]],
        columns=["sku", "product", "unit_cost_usd", "units_made"])
    shipments = pd.DataFrame(
        [(b, m, d, sku, u) for b, m, d, u, *_ in a["shipments"] for sku, *_ in a["products"]],
        columns=["batch", "market", "arrival_date", "sku", "units"])
    sales = pd.DataFrame(lines).sort_values(["date", "order_id"]).reset_index(drop=True)
    cost_table = pd.DataFrame(costs).sort_values(["date", "market"]).reset_index(drop=True)
    return {"products": products, "shipments": shipments, "sales": sales, "costs": cost_table}


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the business data as CSV files.")
    parser.add_argument("--out", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, df in generate().items():
        df.to_csv(args.out / f"{name}.csv", index=False)
        print(f"  {name}.csv: {len(df):,} rows")


if __name__ == "__main__":
    main()
