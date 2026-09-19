# Preregistration - Morpho impairment measurement

Written before running each analysis. Two documents, merged here for publication.

---

## A. Impairment measurement

### Problem
`realizedBadDebt` is a cumulative scalar with no timestamp, and `MarketHistory` exposes
no bad-debt series. A time-to-event label therefore cannot be constructed from the API.

### Design
Morpho Blue markets are immutable in five parameters (collateral, loan asset, oracle,
IRM, LLTV). These cannot be contaminated by the outcome, and they are exactly what a
supplier decides on. Features are restricted to creation-time observables plus market
state at a fixed age of 30 days. The split is walk-forward by market creation time.

### Gates (fixed in advance)
```
G1  beats the "collateral not used as a loan asset elsewhere" baseline in every fold
G2  top-10% capture >= 40%
G3  risk-score deciles monotone in realized incident rate
G4  sign consistent across chain splits
G5  leakage recheck by leave-one-feature-out
Any gate missed -> publish as a rejection.
```

**Outcome: rejected.** G2 (39% vs 40%) and G3 failed, and G5 showed the apparent signal
was driven by exposure time. Controlling for exposure, top-decile capture fell to 8%,
below the 10% random baseline.

---

## B. Inflation regime definition

Written after the first mechanism test came back inconclusive (exponential model won in
4 of 9 markets). A pattern was visible - only markets with large positive fitted rates
passed - but redefining the sample after seeing that pattern would be post-hoc. So the
definition was fixed and committed first, then tested on an expanded sample.

### Regime definition (fixed before looking)
```
A market is in the inflation regime at time t iff ALL hold:
  C1  coverage (collateral USD / borrow USD) < 0.5
  C2  utilization >= 0.99
  C3  C1 and C2 sustained for >= 30 consecutive days
  C4  supply at segment start >= $1,000
```

### Sample requirement
At least 5 segments disjoint from the first test's sample, otherwise the result is held
as underpowered rather than reported.

### Gates (fixed in advance)
```
G1  exponential model median absolute error < 30%
G2  exponential beats BOTH no-change and linear in >= 70% of segments
G3  sign consistent across duration terciles
Any gate missed -> "mechanism unconfirmed", final, no retry.
```

**Outcome: passed.** 21 segments (8 disjoint from the first sample);
median error 4.8%, exponential wins 20 of 21, terciles 86% / 100% / 100%.

### What does not depend on this test
The measured gap between nominal and reconstructed principal is a direct reading of the
supply series at the last day with coverage >= 1. It uses no model.
