"""Build the dashboard and the Power BI tables from the CSV data.

    python build.py

Writes:
    docs/index.html     interactive dashboard (also works as a GitHub Pages site)
    powerbi/*.csv       star schema to load into Power BI Desktop
"""
from pathlib import Path

from skincare import analysis, dashboard, powerbi

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ds = analysis.load(ROOT / "data")
    page = ROOT / "docs" / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(dashboard.build_html(ds), encoding="utf-8")
    tables = powerbi.export(ds, ROOT / "powerbi")

    print("Key findings:")
    for line in analysis.findings(ds):
        print("  -", line)
    print(f"\nDashboard: {page}")
    print(f"Power BI tables: {len(tables)} files in {tables[0].parent}")


if __name__ == "__main__":
    main()
