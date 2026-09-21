# Restaking Slashing, Measured: 15 Events Ever, All Tests or Spam — and $5.25M Actually Slashable

*Reproducible analysis · 2026-09-20 · code, data and preregistration linked below*

## TL;DR

Slashing has been live on EigenLayer mainnet since the `AllocationManager` deployment. The
widely repeated framing is that roughly $15B of restaked ETH is now exposed to slashing risk.
We went to the chain to price that risk and found there is nothing to price it with:

| | On-chain, verified |
|---|---|
| `OperatorSlashed` events, **ever** | **15** |
| Of those, operational slashings | **0** — every one is a dummy test, a demo, or advertising |
| Operators who have opted into a slashable operator set | **24** |
| Stake actually slashable today | **$5,251,813** |
| As a share of ERC20 strategy deposits ($815.8M) | **0.64%** |
| As a share of protocol TVL (DefiLlama, $6.89B) | **≈0.08%** |
| Native restaked ETH allocated to slashable sets | **zero — never once** |

This is not a claim that restaking is safe. It is a claim that **realized-loss data does not
exist**, and that current exposure is two to three orders of magnitude below the headline.

## Every slashing event on record

Full scan of `AllocationManager` (`0x948a420b8CC1d6BFd0B6087C2E7c344a2CD0bc39`) from its
deployment block **22,218,956** — located by binary search on `eth_getCode`, so there is no
missed range — to block 26,017,000. That is 3,798,044 blocks.

| Block | Operator | AVS | wad | description |
|---|---|---|---|---|
| 23442944 | `0x01d120db` | `0x26ddbf2a` | 0.1000 | `slash 10%` |
| 23447970 | `0x01d120db` | `0x26ddbf2a` | 0.1000 | `slash 10%` |
| 24167653 | `0x5accc904` | `0x90c68bf0` | 1.0000 | `AlephAVS redistributable slash` |
| 24442918 | `0x4cd2086e` | `0x90c68bf0` | 0.9961 | *(none)* |
| 24450302 | `0x4cd2086e` | `0x90c68bf0` | 0.9928 | *(none)* |
| 24763745 – 25314910 (10 events) | `0x5accc904` | `0x12b75d5e` | 1.0000 | `👉 eigenyields.xyz/vaults` |

Identifying the three AVSs by their registered metadata URI settles what these are:

```
0x26ddbf2a   metadataURI = "dummy://opset1"
0x90c68bf0   AlephFi — the description says "redistributable slash", i.e. a demo
0x12b75d5e   eigenyields.xyz — 10 events with a marketing link in the description field
```

Three operators, three AVSs, and ten of fifteen events slash exactly 100% of allocation — a
value that is hard to reach in operational slashing. Four legacy slashing signatures return
zero events.

**One widely cited figure we could not reproduce**: a claim of "33 slashing events in Q1 2026."
There is no such record on Ethereum mainnet. It may refer to Ethereum consensus-layer validator
slashing, which is an entirely different mechanism, or to a testnet. We could not determine which.

## Why exposure is arithmetic, not a forecast

EigenLayer slashing is **opt-in at the operator level**. From `AllocationManager.sol`:

```solidity
// 2. Skip if the operator does not have a slashable allocation
if (allocation.currentMagnitude == 0) {
    continue;
}
```

Unallocated stake is not slashable. Default allocation is zero. So "how much can be slashed" is
a sum over allocations, not a probability estimate.

Reconstructing every `AllocationUpdated` event and keeping the latest value per
`(operator, avs, setId, strategy)`:

```
75 allocation events → 54 currently effective → 53 with magnitude > 0
24 operators · 9 AVSs · 16 strategies
allocated magnitude: median 16.67%, 75th pct 81%, max 100%
```

Priced with an independent source (DefiLlama coins, confidence attached), with the 36 of 86
strategies that have no price **excluded rather than zeroed** — zeroing would shrink the
denominator and inflate the ratio:

```
ERC20 strategy deposits    $815,797,329
held by opted-in operators $  5,365,541   (0.66%)
actually slashable         $  5,251,813   (0.64%)
    composition: mETH $3.50M (6 operators) · stETH $115K (10) · remainder $23
```

## A correction we had to make to our own number

Our first pass computed the slashable share as `magnitude / 1e18`. The contract says otherwise:

```solidity
slashedMagnitude = allocation.currentMagnitude.mulWadRoundUp(params.wadsToSlash[i]);
wadSlashed[i]    = uint256(slashedMagnitude).divWad(info.maxMagnitude);   // denominator
```

The slashable fraction of an operator's delegated stake is `currentMagnitude / maxMagnitude`.
Reading `getMaxMagnitude` on-chain, **12 of 34 (operator, strategy) pairs have
`maxMagnitude < 1e18`** — one as low as 1.0 — because magnitude is burned down by prior slashing.

```
before (÷1e18)          $3,614,347
after  (÷maxMagnitude)  $5,251,813      +45.3%
```

We also checked for double counting across operator sets: **0 of 34 pairs** have summed slashable
exceeding delegated stake, consistent with `encumberedMagnitude` bounding the total.

The direction of the conclusion did not change. The number was wrong by 45% until we read the
contract instead of trusting our reading of the docs.

## What this does and does not support

```
Supported    No operational slashing has occurred. Loss frequency and severity cannot be
             estimated from realized events, because there are none.
Supported    Current slashable exposure is ~0.08% of protocol TVL, and native restaked ETH —
             the largest pool — has never been allocated to a slashable operator set.
Not supported   "Restaking is safe." Absence of events is not absence of risk. Slashing is
             designed to be rare and large; five months of quiet carries little information.
Not supported   Any pricing of the tail. We deliberately did not build a model — our
             preregistration required n ≥ 20 events, 10 operators, 3 AVSs and we found 15/3/3.
```

## Limits

- Ethereum mainnet only. EigenLayer is deployed on other chains; those are unchecked.
- The denominator excludes native restaked ETH (not an ERC20 strategy). The numerator excludes it
  too — no allocation exists — so the basis is consistent, but the TVL-relative figure uses
  DefiLlama's total and is labelled separately.
- 36 of 86 strategies lack a price and were dropped from both sides. One allocation row lost a
  price, which biases the numerator **downward**.
- We verified the ERC20 slashing path in contract code. We did not line-by-line verify that the
  native-ETH path behaves identically; it does not affect the result because allocation there is zero.
- This is a snapshot. Allocations can grow, and whether they are growing is the one thing worth
  watching. A panel has been recording since 2026-09-19.

## Preregistration

Written and committed **before** looking at the data (`PREREGISTRATION.md`). It fixed the gates
(`n ≥ 20` events, `≥10` operators, `≥3` AVSs) and, in section 3, anticipated exactly what we found:

> *"An AVS may slash its own operator as a test → separate by the `description` field and the
> magnitude of `wad`. Do not pool them."*

That line, written before any data was pulled, is what kept fifteen advertising and test events
from being read as a loss history.

## Reproduce

```bash
python restake/fetch_slashing.py 22218956   # full event scan (~4 min)
python restake/verify_formula.py            # contract-semantics check
python restake/snapshot_restake.py          # incremental daily panel
```

Free RPCs mostly refuse historical `eth_getLogs` — `publicnode` returns *"Archive requests require
a personal token"*, several others cap ranges at 10–50 blocks. We surveyed 15 and only
`gateway.tenderly.co` and `rpc.mevblocker.io` served the range. Without checking this you get zero
results and conclude, wrongly, that nothing happened.

Live monitor: <https://janghyukchoi.github.io/morpho-risk-monitor/>

Corrections welcome — in particular on the "33 events" figure, if someone can point to what it
actually counted.
