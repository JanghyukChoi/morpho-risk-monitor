"""Generate the monthly refusal report required by CURATION.md rule R6.

R6 says every market considered and rejected gets published with its reason, before
anything happens to it. A refusal published after a failure is worth nothing.

Two categories, and the distinction matters:

- **Impaired**: collateral is priceable and coverage is below 1. We can say the position
  is under water and by how much.
- **Unpriceable**: no collateral price is available at all. Coverage reads zero because the
  input is missing, not because the collateral is gone. An earlier version of this work
  flagged 19 of 34 markets as impaired on exactly this confusion; see PREREGISTRATION.md.
  These are refused for a different reason — a market whose collateral cannot be priced
  cannot be underwritten either way.

    python curator/refusal_report.py > reports/2026-10.md
"""

import datetime
import pathlib

import pandas as pd

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
STREAK_DAYS = 7  # R1: coverage below 1 for more than this many consecutive days


def load() -> tuple[pd.DataFrame, pd.Timestamp]:
    pm = pd.read_parquet(DATA / "panel_markets.parquet").sort_values(["mid", "date"])
    return pm, pm["date"].max()


def streaks(pm: pd.DataFrame) -> pd.DataFrame:
    """Consecutive days ending at the latest observation with coverage below 1."""
    rows = []
    for mid, d in pm.groupby("mid"):
        d = d.sort_values("date")
        run = 0
        for under in reversed((d["cover"] < 1.0).tolist()):
            if not under:
                break
            run += 1
        if run:
            last = d.iloc[-1]
            rows.append(
                {
                    "mid": mid,
                    "coll": last["coll"],
                    "loan": last["loan"],
                    "lltv": last["lltv"],
                    "cover": last["cover"],
                    "supply_usd": last["supply_usd"],
                    "coll_usd": last["coll_usd"],
                    "price_ok": bool(last["price_ok"]),
                    "days": run,
                    "observed": len(d),
                }
            )
    return pd.DataFrame(rows)


def pair(r) -> str:
    return f'{r["coll"] if pd.notna(r["coll"]) else "?"}/{r["loan"]}'


def main() -> None:
    pm, date = load()
    s = streaks(pm)
    panel_days = pm["date"].nunique()
    refused = s[s["days"] >= STREAK_DAYS]
    impaired = refused[refused["price_ok"]]
    unpriceable = refused[~refused["price_ok"]]
    watching = s[s["days"] < STREAK_DAYS]
    universe = pm[pm["date"] == date]

    print(f"# Refusal report — {date:%Y-%m}")
    print()
    print(f"As of **{date:%Y-%m-%d}**. Markets observed: {len(universe)}. "
          f"Panel depth: {panel_days} days.")
    print()
    print("Rule R1 refuses any market whose collateral coverage has been below 1 for more "
          f"than {STREAK_DAYS} consecutive days. Rule R3 refuses any market whose collateral "
          "I cannot independently price. Both are applied before anything happens to the "
          "market, which is the only time a refusal means anything.")
    print()
    print("| | Markets | Nominal supply | Collateral |")
    print("|---|---|---|---|")
    for name, df in (("Refused — impaired", impaired), ("Refused — unpriceable", unpriceable),
                     ("Watching (under 7 days)", watching)):
        print(f'| {name} | {len(df)} | ${df["supply_usd"].sum():,.0f} | ${df["coll_usd"].sum():,.0f} |')
    print()

    print("## Refused: impaired")
    print()
    print("Collateral is priceable and worth less than the debt it backs.")
    print()
    print("| Market | LLTV | Coverage | Days | Nominal supply | Collateral |")
    print("|---|---|---|---|---|---|")
    for _, r in impaired.nlargest(15, "supply_usd").iterrows():
        cap = "≥" if r["days"] >= panel_days else ""
        print(f'| {pair(r)} | {r["lltv"]:.2f} | {r["cover"]:.4f} | {cap}{r["days"]} | '
              f'${r["supply_usd"]:,.0f} | ${r["coll_usd"]:,.0f} |')
    print()

    print("## Refused: collateral cannot be priced")
    print()
    print("Coverage reads zero because no collateral price is available, not because the")
    print("collateral is known to be gone. These are refused as un-underwritable, not")
    print("reported as impaired — the distinction is the one this project got wrong once.")
    print()
    print("| Market | LLTV | Days | Nominal supply |")
    print("|---|---|---|---|")
    for _, r in unpriceable.nlargest(15, "supply_usd").iterrows():
        cap = "≥" if r["days"] >= panel_days else ""
        print(f'| {pair(r)} | {r["lltv"]:.2f} | {cap}{r["days"]} | ${r["supply_usd"]:,.0f} |')
    print()

    if len(watching):
        print("## Watching")
        print()
        print(f"Coverage below 1 for fewer than {STREAK_DAYS} days. Not refused yet — this is")
        print("the window in which an oracle outage resolves and an insolvency does not.")
        print()
        print("| Market | Coverage | Days | Nominal supply |")
        print("|---|---|---|---|")
        for _, r in watching.nlargest(10, "supply_usd").iterrows():
            print(f'| {pair(r)} | {r["cover"]:.4f} | {r["days"]} | ${r["supply_usd"]:,.0f} |')
        print()

    print("## Limits")
    print()
    print(f"- The panel is {panel_days} days deep, so any streak reported as {panel_days} days")
    print("  is censored — the market may have been impaired far longer. Streaks at the")
    print("  panel limit are marked with ≥.")
    print("- Nominal supply is the protocol's own figure and is inflated by interest accruing")
    print("  on positions that cannot be repaid. See CURATION.md for the reconstruction.")
    print("- A market appearing here is not a claim about any curator. It is a market I would")
    print("  not allocate to, published in advance.")


if __name__ == "__main__":
    main()
