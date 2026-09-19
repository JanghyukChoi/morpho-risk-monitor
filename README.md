# Reading Morpho Market Data: Nominal Interest Accrual Overstates Impairment by ~589×

*Reproducible analysis · 2026-09-19 · code and data linked below*

## TL;DR

When a Morpho Blue market loses its collateral backing, borrowers can no longer repay and
utilization locks at 100% (`borrowAssets / supplyAssets = 1.000` in all 17 markets we found).
From that point both figures keep growing on a position that is economically dead, and they
diverge without bound from the principal that was actually deposited.

Any tool reading current `supplyAssetsUsd` at face value therefore overstates exposure
to impaired markets. Measured across all Morpho vaults:

| | Nominal (as reported) | Reconstructed principal |
|---|---|---|
| Impaired markets, total supply | **$15,552,344,406** | **$41,687,199** (373× lower) |
| Vault allocations into those markets | **$482,404,560** | **$819,198** (589× lower) |

Concretely: one market (PAXG/USDC) shows **$9.1B** supplied against **$260** of collateral.
Its actual principal was **$95,034**, deposited in October 2024. Everything above that
accumulated over the ~700 days since, at an implied continuous rate of ~557%/yr.

## What we observe, and what we could not confirm

**Observed, directly measured:**

```
collateral value → ~0
  → utilization pinned at 1.0 (borrow == supply, exactly — 17 of 17 markets)
  → both figures keep growing for as long as the market stays in that state
  → nominal values diverge from deposited principal by orders of magnitude
```

**Confirmed — the causal mechanism**, on a preregistered second test. Getting there took two
attempts, and both are reported:

- A zero-parameter test (predict supply from the reported `supplyApy`) was unusable: the API
  reports APYs of 180,000–300,000% for these markets, while PAXG's realized growth over 90 days
  was 7.2×, implying ~800%/yr. **The reported APY field is off by roughly 300× and should not
  be used for these markets.**
- A one-parameter out-of-sample test (fit growth on the first half of the impaired period,
  predict the second half) gave median error 41% for an exponential model versus 92% linear and
  81% no-change — exponential is the best of the three, but it beat **both** alternatives in only
  **4 of 9 markets**. Below our preregistered bar.

**Second attempt — preregistered.** We fixed a definition of the "inflation regime" *before*
looking (coverage < 0.5, utilization ≥ 0.99, sustained ≥ 30 days, starting supply ≥ $1,000),
committed it, then re-ran on an expanded sample. Result across 21 segments (8 of them disjoint
from the first sample): median error **4.8%**, exponential beats both alternatives in **20 of 21**
segments, consistent across duration terciles. Estimated rates cluster at **415–800%/yr** across
different collaterals, chains and periods.

The first attempt failed because the sample mixed regimes: deUSD/USDC averaged −245% over its
whole history but **+799% with 0.9% error** once restricted to its actual inflation regime.

So: the gap is measured, and the compounding explanation is supported. The reported `supplyApy`
field remains unusable — the implied rate must be recovered from the supply curve itself.

## Method (no event-log parsing required)

1. For each market, pull the daily time series of `collateralAssetsUsd`,
   `borrowAssetsUsd`, `supplyAssetsUsd` from the public GraphQL API.
2. Compute coverage = collateral / borrow.
3. Find the **last day coverage ≥ 1**. That is the last economically healthy day.
4. Supply on that day = **principal at risk**. Everything after is accrual.
5. For a vault's position: `real ≈ nominal ÷ inflation_factor`, since vault claims
   inflate pro-rata with the market.

## Validation: the method recovers known incident dates

We did **not** supply any incident dates. The detected "death dates" fell out of the data:

| Collateral | Detected date | Known event |
|---|---|---|
| deUSD, sdeUSD | **2025-11-06** | Stream Finance collapse (Nov 4–6, 2025) |
| USR, wstUSR, RLP | **2026-03-22** | Resolv exploit (Mar 22, 2026) |

## What this means for dashboards and risk tools

Two failure modes, in opposite directions:

- **Overstating risk.** A dashboard may show a vault with "$312M at risk" where the
  real principal is **$450,655**. Curators can be unfairly labelled as impaired.
- **Understating coverage.** `realizedBadDebt` is a cumulative scalar with no timestamp
  and no netting, so it cannot be used to date or size an incident on its own.

Two named examples, stated as **corrections downward**:

| Vault | Nominal exposure | Reconstructed |
|---|---|---|
| Apostro "Resolv USDC" | $1,008,886 | **$36,488** |
| MEV Capital "Elixir USDC" | $976,276 | **$3,150** |

Both are single-asset vaults created for that specific strategy; neither reflects the
curator's wider book (MEV Capital operates 29 vaults, ~$10.4M TVL).

## Cross-protocol check: the phenomenon is structural, the magnitude is not

Euler v2 shows the same signature — 11 of 108 borrowing vaults sit at
`borrow/supply = 1.000`, with borrow APYs of 4,000% (median) to 10,000% (max).
So this is a property of permissionless lending, not a Morpho-specific bug.

The difference is what happens next:

| | Morpho | Euler v2 |
|---|---|---|
| Rate behaviour at 100% utilization | Adaptive, no effective cap observed | Caps at round values (1200%, 4000%, 10000%) — *inferred from data, contract not read* |
| Bad-debt accounting | Cumulative scalar; must be reconstructed | Dedicated endpoint returning **net** bad debt (debt − collateral), verified to reconcile exactly |
| Practical result | 373–589× nominal overstatement persists | Suppressed |

## Limits (stated plainly)

- These are **exposure** figures at the moment of impairment, not realized losses.
  Some positions may already be written down or partially recovered.
- Markets with partial coverage (e.g. msY/USDC at 0.14) retain recovery value.
- If a vault deposited or withdrew mid-life, the pro-rata deflation introduces error.
- Where a vault's own TVL has already been written down, "% of TVL" inflates.
- Two protocols only (Morpho, Euler). Silo and others are untested.
- The compounding explanation rests on a 21-segment preregistered test; the measured gap itself
  does not depend on it.
- `supplyApy` / `borrowApy` for impaired markets are unreliable by ~300× and were excluded.
- The Euler IRM cap is inferred from round-numbered APYs; we did not read the contract.
- The largest single principal we found — msY/USDC, **$20.8M**, impaired 2026-06-20 —
  reached the market through **direct supply, not a curated vault**.

## What we also tried and rejected

Published alongside, because rejections are part of the record:

1. **A predictive bad-debt model.** Apparent 3.8× lift on held-out markets turned out to be
   an **exposure-time artifact** — older markets have had longer to fail. Controlling for
   exposure, top-decile capture fell to 8%, below the 10% random baseline. Rejected on a
   preregistered gate.
2. **A first-pass impairment scan.** Flagged 34 markets; 19 were false positives caused by
   missing price feeds (quantity > 0, USD = 0), not by collapsed collateral.
3. **Our first mechanism test.** Failed (4 of 9 markets) because the sample mixed inflation and
   non-inflation regimes. We closed it as unconfirmed rather than redefining the sample after
   seeing the pattern, then preregistered a regime definition and re-tested. Both are in the record.
4. **Our own conclusion that "Morpho's USD conversion is broken."** It is not. Cross-checked
   against an independent price source (490/490 within ±5%), token decimals (7/7), and
   token addresses (275/275 official). The error was our assumption that a stablecoin must
   trade at $1 — USR genuinely trades near $0.10 after the March 2026 exploit.

## Reproduce

```bash
python curator/run_all.py          # full pipeline, ~7 min
python curator/run_all.py --quick  # recompute from cached data
```

Preregistration: `PREREGISTRATION.md`. Code: `curator/`. Data: `data/`.

A daily snapshot panel is now running and records each day's impairment flags, so that
forward predictions can be scored against outcomes rather than asserted.
