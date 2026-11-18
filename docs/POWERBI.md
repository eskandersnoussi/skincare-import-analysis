# Build the dashboard in Power BI Desktop

`python build.py` writes six CSV files to `powerbi/`, already shaped as a star
schema. This guide turns them into a Power BI report in about an hour.

## 1. Load the tables

**Home → Get data → Text/CSV**, and load each file from the `powerbi` folder:

| Table | What it holds |
|---|---|
| `fact_sales` | one row per order line: units, revenue (local + USD, excl. VAT), landed cost split into product, freight, duty, clearance |
| `fact_costs` | every cost: production, freight, customs, delivery, payment fees, ads, design... with `cost_group` |
| `dim_date` | calendar May 2025 – May 2026 |
| `dim_product` | the 3 products and their production cost |
| `dim_market` | Tunisia, Norway, Shared (brand) |
| `dim_shipment` | landed cost per unit for each of the 5 shipments |

In Power Query, check that `date` columns are type **Date** and money columns
are **Decimal number**.

## 2. Relationships (Model view)

| From | To | Cardinality |
|---|---|---|
| `fact_sales[date]` | `dim_date[date]` | many-to-one |
| `fact_costs[date]` | `dim_date[date]` | many-to-one |
| `fact_sales[sku]` | `dim_product[sku]` | many-to-one |
| `fact_sales[market]` | `dim_market[market]` | many-to-one |
| `fact_costs[market]` | `dim_market[market]` | many-to-one |
| `fact_sales[batch]` | `dim_shipment[batch]` | many-to-one |

Mark `dim_date` as the date table (**Table tools → Mark as date table**).

## 3. Measures (DAX)

Create a table called `_Measures` (**Enter data**, one empty column) and add:

```DAX
Units Sold = SUM ( fact_sales[units] )

Revenue = SUM ( fact_sales[net_usd] )

Landed Cost = SUM ( fact_sales[landed_usd] )

Gross Profit = [Revenue] - [Landed Cost]

Selling & Marketing Costs =
CALCULATE (
    SUM ( fact_costs[amount_usd] ),
    fact_costs[cost_group] IN { "Delivery & payment", "Marketing" }
)

Brand & Admin Costs =
CALCULATE ( SUM ( fact_costs[amount_usd] ), fact_costs[cost_group] = "Brand & admin" )

Profit Before Tax = [Revenue] - SUM ( fact_costs[amount_usd] )

Profit Margin = DIVIDE ( [Profit Before Tax], [Revenue] )

Profit per Unit = DIVIDE ( [Gross Profit] - [Selling & Marketing Costs], [Units Sold] )

Landed Cost per Unit = DIVIDE ( [Landed Cost], [Units Sold] )

Average Price per Unit = DIVIDE ( [Revenue], [Units Sold] )

Cash Flow = [Revenue] - SUM ( fact_costs[amount_usd] )

Cumulative Cash =
CALCULATE (
    [Cash Flow],
    FILTER ( ALL ( dim_date ), dim_date[date] <= MAX ( dim_date[date] ) )
)
```

Format money measures as **Currency ($)**, margin as **Percentage**.

Note: `Profit Before Tax` counts shared brand costs (market "ALL") only when no
market filter is applied. For the per-market view, use the market slicer and
compare with the Python dashboard, which splits shared costs by units sold.

## 4. Report pages

**Page 1 – Overview**
- Cards: Units Sold, Revenue, Profit Before Tax, Profit Margin
- Line chart: `dim_date[month_start]` × Cumulative Cash
- Stacked column: `dim_date[month_start]` × Units Sold, legend `fact_sales[channel]`, small multiples or slicer by market
- Slicer: `dim_market[market_name]`

**Page 2 – Unit economics**
- Waterfall: category = cost type, value per unit (or use a clustered bar with Average Price, Landed Cost per Unit, Profit per Unit)
- Matrix: rows `dim_market[market_name]`, `fact_sales[channel]`; values Units Sold, Average Price per Unit, Landed Cost per Unit, Profit per Unit

**Page 3 – Shipments**
- Stacked column: `dim_shipment[batch]` × product_cost, freight, duty, clearance
- Column: `fact_sales[batch]` × Profit per Unit

Theme suggestion: **View → Themes**, pick a dark-rose accent close to `#b4536b`
to match the brand.
