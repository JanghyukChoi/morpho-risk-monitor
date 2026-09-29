# Curation notes

What I would and would not allocate to, and the measurement behind it.

[MORPHO.md](MORPHO.md) measures what already happened. This document says what I would do
about it, and shows the one consequence that matters most for allocation.

Data: the daily panel, **2026-09-29**. Reproduce with `python curator/vault_exposure.py`.

---

## 1. A dead vault does not report as dead. It reports as large.

The 589x gap in [MORPHO.md](MORPHO.md) is usually read as "exposure to impaired markets is
overstated." That understates it. When a vault's assets sit almost entirely in impaired
markets, the inflation propagates into the vault's own reported total.

Over the eleven days the panel covers:

| | 2026-09-19 | 2026-09-29 | Change |
|---|---|---|---|
| **Adpend USDC**, reported | $312,474,068 | $390,731,829 | **+$78,257,762** |
| **Adpend USDC**, reconstructed | $450,903 | $450,903 | **+$0** |
| **1337 USDC**, reported | $166,624,225 | $208,387,690 | **+$41,763,466** |
| **1337 USDC**, reconstructed | $240,440 | $240,479 | **+$38** |

**$120M of reported growth across two vaults in eleven days, against $38 of real change.**

Neither vault's share of the market moved over those eleven days, so the reported growth is
not deposits. Both are 100% allocated to sdeUSD/USDC, a market whose collateral coverage
broke on **2025-11-06** — the Stream Finance date — and which has been dead for **327 days**.
The reported figure is interest compounding against nothing.

Four vaults clear the filter at this snapshot:

| Vault | Reported | Reconstructed | Ratio |
|---|---|---|---|
| 1337 USDC | $208,387,690 | $240,479 | 866.6x |
| Adpend USDC | $390,731,829 | $450,903 | 866.6x |
| MEV Capital Elixir USDC | $1,199,286 | $3,154 | 380.3x |
| Duplicated Key | $1,745,129 | $82,114 | 21.3x |

**These are abandoned positions, not active mismanagement.** Nobody is steering them. The
numbers kept compounding after everyone left. Naming them is a description of a state
anyone can verify on chain, not a claim about any curator's judgment — the inflation is
protocol accounting, and it is equally invisible to everyone reading the same dashboard.

---

## 2. Why it matters for allocation

**Size is not evidence of adoption.** Anything that ranks, filters, or benchmarks vaults by
reported TVL is partly ranking an accounting artifact. A curator comparing themselves to
peers, or a depositor picking the largest vault in a category, can be measuring against a
number with no principal behind it.

**The inflation factor is not uniform.** It runs from 21x to 867x in this sample, so
deflating by an average does not work. It has to be done per market, from that market's own
supply history.

---

## 3. Method

For each market that lost collateral backing, take the supply on the last day coverage was
at or above 1. That is principal actually deposited; everything after is interest accruing
against nothing. A vault's real exposure is its share of the market applied to that
principal:

```
real = (vault_supply / market_supply) * principal_at_last_covered_day
```

Healthy markets are left alone. Markets whose supply fell rather than grew are left alone —
there is nothing to deflate.

The check I trust more than the headline: the method is never given any incident dates, and
known ones fall out of it anyway. Stream Finance surfaces at **2025-11-06** and the Resolv
exploit at **2026-03-22**, from the supply series alone.

---

## 4. What I would refuse

Allocation rules, fixed in advance so they cannot be bent after seeing a yield.

**R1. No market where coverage has been below 1 for more than 7 consecutive days.**
Not "no impaired markets" — impairment is detected late. Seven days is the window in which
a genuine oracle outage resolves and a genuine insolvency does not.

**R2. No reliance on a supplied figure I have not deflated, including my own vault's total.**
This rule exists because I got it wrong first. My initial pass measured impaired exposure as
a share of reported TVL, which put Adpend at 0.14%. Numerator and denominator carried the
same inflation. The correct reading is that essentially all of that vault's real assets are
impaired.

**R3. No collateral whose price I can only obtain from the protocol reporting it.**
One market in this sample reports $9.1B supplied against $260 of collateral. A screen
sourcing both numbers from the same place cannot catch that.

**R4. No recursive exposure.** In November 2025, USDC was supplied against xUSD collateral
and the borrowed USDC looped back into more xUSD, inflating the apparent footprint far past
the real backing. Anything where collateral and loan asset resolve to the same underlying is
out, however the yield looks.

**R5. No position I cannot exit without moving the price.** Sized to observed depth, not to
a cap.

**R6. Publish refusals monthly.** Every market considered and rejected, with the reason,
before anything happens to it. A refusal published after a failure is worth nothing.
→ [reports/](reports/), starting [2026-09](reports/2026-09.md): 103 markets refused of 596
observed, split between impaired and un-priceable.

---

## 5. Limits

- **Eleven days of panel.** Enough to show the divergence is ongoing, not enough to
  characterise how often it starts.
- **25 markets flagged impaired** out of 596 priced on this date. This measures a tail.
- **Restricted to fully allocated vaults** — allocations within 5% of reported TVL — because
  a vault holding idle assets has a legitimate gap between the two. Four vaults clear that
  filter at $500K or more.
- **The last covered day is inferred** from the supply and coverage series, not read from an
  event. A market that recovered and re-impaired is treated as one episode.
- **That cut is generous to the market.** For a market that degraded gradually rather than
  failing at once, more of the reported figure is real than this method credits.

Rejected approaches, including a predictive model whose apparent lift turned out to be an
exposure-time artifact, are in [PREREGISTRATION.md](PREREGISTRATION.md).
