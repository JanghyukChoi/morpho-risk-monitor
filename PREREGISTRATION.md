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

---

## C. Restaking slashing risk

Written before any on-chain data was pulled.

### Question
```
H0  AVS rewards >= expected slashing loss   (adequately priced)
H1  AVS rewards <  expected slashing loss   (underpriced)
```

### Data policy
On-chain events only. Aggregator APIs are used for cross-checking, never as the primary
source — a prior project found an API reporting APYs off by ~300x.

### Gates (fixed in advance)
```
G0  sample: >= 20 slashing events, >= 10 operators, >= 3 AVSs
    below this -> publish as "underpowered", build no model
G1  conclusion survives removing the single largest loss
G2  sign consistent across AVS and strategy splits
G3  conclusion survives removing test-like events
G4  on-chain aggregate agrees with an external aggregate within +/-20%
```

### Anticipated failure modes
```
Small sample     slashing is a tail event; months of data cannot characterise a tail
Exposure time    longer-exposed operators accumulate more events; normalise by stake x time
Survivorship     an operator slashed and then exited must stay in the denominator
Test events      an AVS may slash its own operator as a test -> separate by the
                 `description` field and the magnitude of `wad`. Do not pool them.
Single event     if one event dominates, the mean is meaningless
Premium defn     token incentives inflate apparent rewards -> cash rewards only in the base case
```

**Outcome: G0 failed.** 15 events, 3 operators, 3 AVSs — and the `description` separation
anticipated above showed all fifteen to be dummy tests, a demo, or advertising. No model built.
Exposure was then measured directly instead, which requires no loss history.
