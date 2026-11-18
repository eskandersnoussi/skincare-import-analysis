"""Checks that the analysis matches the known facts and adds up."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import make_data  # noqa: E402
from skincare import analysis as a  # noqa: E402
from skincare import dashboard, powerbi  # noqa: E402


@pytest.fixture(scope="module")
def ds(tmp_path_factory):
    folder = tmp_path_factory.mktemp("data")
    for name, df in make_data.generate().items():
        df.to_csv(folder / f"{name}.csv", index=False)
    return a.load(folder)


# ------------------------------------------------- the facts of the business
def test_every_unit_sold(ds):
    units = ds.sales.groupby(["market", "sku"])["units"].sum()
    assert units.loc["TN"].tolist() == [1000, 1000, 1000]
    assert units.loc["NO"].tolist() == [500, 500, 500]


def test_production_cost_is_20k(ds):
    production = ds.costs.loc[ds.costs["category"] == "Production", "amount_usd"].sum()
    assert production == pytest.approx(20000, abs=0.05)
    assert ds.sales["product_cost_usd"].sum() == pytest.approx(20000, abs=1)


def test_prices(ds):
    online = ds.sales[(ds.sales["channel"] == "Online") & (ds.sales["discount"] == 0)]
    tn = online[online["market"] == "TN"]
    no = online[online["market"] == "NO"]
    assert (tn["gross_local"] / tn["units"]).round(2).eq(110).all()
    assert (no["gross_local"] / no["units"]).round(2).eq(200).all()


def test_never_sells_stock_before_it_arrives(ds):
    arrival = ds.shipments.groupby("batch")["arrival_date"].first()
    assert (ds.sales["date"] >= ds.sales["batch"].map(arrival)).all()


# --------------------------------------------------------- the analysis
def test_landed_cost_covers_all_shipping_costs(ds):
    lc = a.landed_cost(ds)
    shipping = ds.costs.loc[ds.costs["category"].isin(a.SHIPPING), "amount_usd"].sum()
    allocated = (lc["units"] * (lc["freight"] + lc["duty"] + lc["clearance"])).sum()
    assert allocated == pytest.approx(shipping, rel=1e-6)


def test_landed_cost_rises_with_each_tunisia_shipment(ds):
    tn = a.landed_by_batch(ds).query("market == 'TN'")["landed"].tolist()
    assert tn == sorted(tn) and tn[-1] > tn[0]


def test_pnl_total_matches_cash(ds):
    p = a.pnl(ds)
    cash = a.cash_flow(ds)["cumulative"].iloc[-1]
    assert p.loc["Profit before tax", "Total"] == pytest.approx(cash, abs=1)


def test_both_markets_profitable_tunisia_much_more(ds):
    p = a.pnl(ds)
    assert p.loc["Profit before tax", "Norway"] > 0
    assert p.loc["Profit margin", "Tunisia"] > 3 * p.loc["Profit margin", "Norway"]


def test_unit_economics_add_up(ds):
    ue = a.unit_economics(ds)
    total = (ue["profit"] * ue["units"]).sum()
    p = a.pnl(ds)["Total"]
    before_shared = p["Profit before tax"] + p["Shared brand costs"] + p["Other market costs"]
    assert total == pytest.approx(before_shared, abs=1)


def test_next_run_is_less_profitable(ds):
    nr = a.next_run(ds)
    assert (nr["profit_per_unit_next"] < nr["profit_per_unit_now"]).all()


def test_break_even_freight_gives_zero_profit(ds):
    be = a.break_even_freight(ds)
    sens = a.freight_sensitivity(ds, freights=[be["Norway online"]])
    assert sens.query("segment == 'Norway online'")["profit"].iloc[0] == pytest.approx(0, abs=1e-9)


# ------------------------------------------------------------- outputs
def test_dashboard_and_powerbi_files(ds, tmp_path):
    page = dashboard.build_html(ds)
    assert page.startswith("<!doctype html>") and "Key findings" in page
    files = powerbi.export(ds, tmp_path)
    assert {f.name for f in files} == {"fact_sales.csv", "fact_costs.csv", "dim_date.csv",
                                       "dim_product.csv", "dim_market.csv", "dim_shipment.csv"}
