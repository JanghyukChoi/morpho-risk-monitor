"""Reported vault size vs reconstructed principal, from the daily panel.

Why this exists. The 589x gap in MORPHO.md is usually read as "exposure to impaired markets
is overstated". That understates it. When a vault's assets sit mostly in impaired markets,
the inflation propagates into the vault's own reported total, so the vault reports as large
rather than as dead.

Method. A vault's real exposure to a market is its share of that market multiplied by the
principal ever actually deposited there:

    real = (vault_supply / market_supply) * principal_at_last_covered_day

Healthy markets are left alone. Reported TVL is never used as a denominator — on these
vaults it carries the same inflation as the numerator.

    python curator/vault_exposure.py
"""

import pathlib

import pandas as pd

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
MIN_TVL = 500_000
# Allocations must sum to roughly the reported TVL. A vault holding idle assets has a
# legitimate gap between the two, and mixing those in produces ratios that mean nothing.
ALLOC_BAND = (0.95, 1.05)


def current(date=None) -> pd.DataFrame:
    """One day of the panel, joined to reconstructed principal."""
    alloc = pd.read_parquet(DATA / "panel_alloc.parquet")
    markets = pd.read_parquet(DATA / "panel_markets.parquet")[["date", "mid", "supply_usd"]]
    principal = pd.read_parquet(DATA / "principal2.parquet")[["mid", "sym", "s_pre"]]

    date = date or alloc["date"].max()
    m = (
        alloc[alloc["date"] == date]
        .merge(markets[markets["date"] == date].drop(columns="date"), on="mid", how="left")
        .merge(principal, on="mid", how="left")
    )
    impaired = m["s_pre"].notna()
    share = (m["my_supply"] / m["supply_usd"]).clip(upper=1.0)
    m["real"] = m["my_supply"].where(~impaired, (share * m["s_pre"]).fillna(0.0))
    m["impaired"] = impaired
    return m


def by_vault(m: pd.DataFrame) -> pd.DataFrame:
    g = (
        m.groupby("vault")
        .apply(
            lambda d: pd.Series(
                {
                    "reported": d["vault_tvl"].iloc[0],
                    "allocated": d["my_supply"].sum(),
                    "real": d["real"].sum(),
                    "impaired_real": d.loc[d["impaired"], "real"].sum(),
                    "n_impaired": int(d["impaired"].sum()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    g["alloc_ratio"] = g["allocated"] / g["reported"].replace(0, float("nan"))
    g["ratio"] = (g["reported"] / g["real"].replace(0, float("nan"))).round(1)
    g["impaired_pct"] = (g["impaired_real"] / g["real"].replace(0, float("nan")) * 100).round(1)
    return g[
        g["alloc_ratio"].between(*ALLOC_BAND)
        & (g["reported"] >= MIN_TVL)
        & (g["n_impaired"] > 0)
    ].sort_values("ratio", ascending=False)


def trajectory(vault: str) -> pd.DataFrame:
    """Reported vs real over every day in the panel. The point is that one moves."""
    alloc = pd.read_parquet(DATA / "panel_alloc.parquet")
    markets = pd.read_parquet(DATA / "panel_markets.parquet")[["date", "mid", "supply_usd"]]
    principal = pd.read_parquet(DATA / "principal2.parquet")[["mid", "s_pre"]]
    d = (
        alloc[alloc["vault"] == vault]
        .merge(markets, on=["date", "mid"], how="left")
        .merge(principal, on="mid", how="left")
    )
    d["real"] = (d["my_supply"] / d["supply_usd"]).clip(upper=1.0) * d["s_pre"]
    return d.groupby("date").agg(reported=("vault_tvl", "first"), real=("real", "sum")).reset_index()


def main() -> None:
    m = current()
    date = m["date"].iloc[0].date()
    g = by_vault(m)

    print(f"Fully allocated vaults holding impaired markets, {date}\n")
    print(f'{"vault":30}{"reported":>16}{"real":>13}{"ratio":>9}{"impaired":>10}')
    for _, r in g.iterrows():
        print(
            f'{str(r["vault"])[:28]:30}${r["reported"]:>15,.0f}${r["real"]:>12,.0f}'
            f'{r["ratio"]:>8.1f}x{r["impaired_pct"]:>9.1f}%'
        )

    for v in g["vault"].head(2):
        t = trajectory(v)
        a, b = t.iloc[0], t.iloc[-1]
        days = (b["date"] - a["date"]).days
        print(
            f'\n{v}: over {days} days reported +${b["reported"] - a["reported"]:,.0f}, '
            f'real +${b["real"] - a["real"]:,.0f}'
        )


if __name__ == "__main__":
    main()
