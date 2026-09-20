# Onchain Risk Monitor

Two numbers the ecosystem quotes, measured against the chain. Both came out smaller than the
headline — by 589x in one case and by roughly three orders of magnitude in the other. Code,
data, preregistrations and every rejected approach are in this repository.

**Live monitor, rebuilt daily:** <https://janghyukchoi.github.io/morpho-risk-monitor/>

---

## 1. Morpho — nominal interest accrual overstates impaired exposure by ~589x

When a Morpho Blue market loses its collateral backing, utilization pins at 100% and both
`borrowAssets` and `supplyAssets` keep compounding on a position that is economically dead.

| | Nominal | Reconstructed |
|---|---|---|
| Impaired markets, total supply | $15,552,344,406 | **$41,687,199** |
| Vault allocations into them | $482,404,560 | **$819,198** |

One market (PAXG/USDC) reports **$9.1B supplied against $260 of collateral**; the principal
actually deposited was **$95,034**, in October 2024.

The method recovers known incident dates without being given them — Stream Finance
(2025-11-06) and the Resolv exploit (2026-03-22) both fall out of the data.

→ **[MORPHO.md](MORPHO.md)**

---

## 2. Restaking — 15 slashing events ever, all tests or spam; $5.25M actually slashable

Slashing on EigenLayer is opt-in: unallocated stake is not slashable
(`currentMagnitude == 0 → continue`). So exposure is arithmetic, not a forecast.

| | On-chain |
|---|---|
| `OperatorSlashed` events, ever | **15** — every one a dummy test, demo, or advertising |
| Operators opted in | **24** |
| Slashable today | **$5,251,813** (0.64% of ERC20 strategy deposits, ≈0.08% of TVL) |
| Native restaked ETH allocated | **zero, never once** |

A widely cited "33 slashing events in Q1 2026" does not appear on Ethereum mainnet.

→ **[RESTAKING.md](RESTAKING.md)**

---

## What is also published here

Rejections, because they are what make the rest checkable:

- A predictive bad-debt model whose apparent 3.8x lift was an exposure-time artifact.
- A first impairment scan where 19 of 34 flags were false positives from missing price feeds.
- Our own conclusion that "Morpho's USD conversion is broken" — it is not; our assumption that a
  stablecoin must trade at $1 was wrong.
- A first mechanism test that failed, closed as unconfirmed rather than rescued by redefining the
  sample after the fact, then preregistered and re-run.
- Our own restaking figure, wrong by 45% until we read the contract instead of the docs.

## Reproduce

```bash
pip install -r requirements.txt
python curator/run_all.py          # Morpho pipeline, ~7 min
python restake/fetch_slashing.py 22218956
python restake/verify_formula.py
```

Daily collection runs in GitHub Actions; each day's calls are written to the panel so forward
claims can be scored against outcomes rather than asserted.

Preregistrations: **[PREREGISTRATION.md](PREREGISTRATION.md)** — including the gates that failed.
