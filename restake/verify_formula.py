# -*- coding: utf-8 -*-
"""★★ 공식 검증 — 계약 코드가 말하는 대로 다시 계산한다.

■ 계약 코드에서 확인한 것 (AllocationManager.sol `_slashOperator`)
  ```
  if (allocation.currentMagnitude == 0) { continue; }        // 배분 0 → 슬래싱 없음 ✅
  slashedMagnitude = currentMagnitude.mulWadRoundUp(wadToSlash);
  wadSlashed[i]    = slashedMagnitude.divWad(info.maxMagnitude);   // ← 분모가 maxMagnitude
  ```
  즉 오퍼레이터 위임지분 중 슬래싱되는 최대 비율 = **currentMagnitude / maxMagnitude**
  (wadToSlash = 1e18 인 최악의 경우)

■ 내가 처음 쓴 공식
  slashable = shares × magnitude / 1e18        ← maxMagnitude 를 1e18 로 가정
  maxMagnitude < 1e18 인 오퍼레이터가 있으면 **과소평가**한다.

■ 그래서 여기서
  V1 오퍼레이터·전략별 maxMagnitude 를 체인에서 직접 읽는다
  V2 공식을 maxMagnitude 기준으로 고쳐 재계산한다
  V3 오퍼레이터별 합이 위임지분을 넘지 않는지 (중복계상 없는지) 검산한다
"""
from __future__ import annotations
import time
from pathlib import Path
import requests
import pandas as pd
from Crypto.Hash import keccak

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_restake"
RPCS = ["https://gateway.tenderly.co/public/mainnet", "https://rpc.mevblocker.io"]
AM = "0x948a420b8CC1d6BFd0B6087C2E7c344a2CD0bc39"


def sel(s):
    h = keccak.new(digest_bits=256)
    h.update(s.encode())
    return "0x" + h.hexdigest()[:8]


def rpc(m, p, t=3):
    for i in range(t):
        for u in RPCS:
            try:
                d = requests.post(u, json={"jsonrpc": "2.0", "id": 1,
                                           "method": m, "params": p}, timeout=60).json()
                if "result" in d:
                    return d["result"]
            except Exception:
                pass
        time.sleep(1)
    return None


def call(to, data):
    r = rpc("eth_call", [{"to": to, "data": data}, "latest"])
    return r if r and r != "0x" else None


def main():
    M = pd.read_parquet(OUT / "allocations_usd.parquet")
    act = M[M.magnitude > 0].copy()
    pairs = act[["operator", "strategy"]].drop_duplicates()
    print("[ V1 maxMagnitude 직접 조회 — %d쌍 ]" % len(pairs), flush=True)
    # getMaxMagnitude(address operator, IStrategy strategy) returns (uint64)
    rows = []
    for _, r in pairs.iterrows():
        d = (sel("getMaxMagnitude(address,address)")
             + r.operator[2:].lower().rjust(64, "0")
             + r.strategy[2:].lower().rjust(64, "0"))
        v = call(AM, d)
        rows.append(dict(operator=r.operator, strategy=r.strategy,
                         max_mag=float(int(v, 16)) if v else float("nan")))
        time.sleep(0.04)
    X = pd.DataFrame(rows)
    nz = X.max_mag.notna()
    print("   조회 성공 %d/%d" % (nz.sum(), len(X)))
    if nz.any():
        below = (X.loc[nz, "max_mag"] < 1e18).sum()
        print("   maxMagnitude < 1e18 인 쌍 **%d개** (과거 슬래싱 흔적)" % below)
        print("   분포: 최소 %.4e · 중앙 %.4e · 최대 %.4e"
              % (X.max_mag.min(), X.max_mag.median(), X.max_mag.max()))

    A = act.merge(X, on=["operator", "strategy"], how="left")
    A["max_mag"] = A.max_mag.fillna(1e18).replace(0, 1e18)
    # ★ 계약 공식: 슬래싱 비율 = currentMagnitude / maxMagnitude
    A["frac_correct"] = (A.magnitude / A.max_mag).clip(upper=1.0)
    A["frac_old"] = (A.magnitude / 1e18).clip(upper=1.0)
    A["usd_slash_correct"] = A.shares * A.ratio.fillna(1) * A.price * A.frac_correct
    A["usd_slash_old"] = A.usd_slashable

    print("\n[ V2 공식 교정 전후 ]")
    o, c = A.usd_slash_old.sum(skipna=True), A.usd_slash_correct.sum(skipna=True)
    print("   기존(÷1e18)          $%s" % format(o, ",.0f"))
    print("   교정(÷maxMagnitude)  $%s" % format(c, ",.0f"))
    print("   차이 %+.2f%%" % ((c / o - 1) * 100 if o else 0))

    print("\n[ V3 중복계상 검산 — 오퍼레이터별 합이 위임지분을 넘는가 ]")
    A["usd_shares_x"] = A.shares * A.ratio.fillna(1) * A.price
    g = A.groupby(["operator", "strategy"]).agg(
        sh=("usd_shares_x", "first"), sl=("usd_slash_correct", "sum"), n=("avs", "nunique"))
    bad = g[g.sl > g.sh * 1.0001]
    print("   (오퍼레이터,전략) %d쌍 · 슬래싱합 > 지분 인 쌍 **%d개**" % (len(g), len(bad)))
    if len(bad):
        print("   ⚠ 여러 오퍼레이터셋에 중복 배분된 경우다. 계약은 encumberedMagnitude 로")
        print("     총합을 maxMagnitude 이하로 제한한다 → 우리 합계는 **상한**으로 읽어야 한다")
        for k, r in bad.head(5).iterrows():
            print("      %s / %s  지분 $%s < 합 $%s (셋 %d개)"
                  % (k[0][:10], k[1][:10], format(r.sh, ",.0f"), format(r.sl, ",.0f"), r.n))
    else:
        print("   ✅ 중복계상 없음 — 합계를 그대로 읽어도 된다")

    A.to_parquet(OUT / "allocations_verified.parquet")
    print("\n[ ★ 최종 ]")
    tot = pd.read_parquet(OUT / "strategies_usd.parquet").usd.sum(skipna=True)
    print("   ERC20 전략 총 예치      $%s" % format(tot, ",.0f"))
    print("   ★ 슬래싱 가능(교정)     $%s  (**%.5f%%**)" % (format(c, ",.0f"), c / tot * 100))


if __name__ == "__main__":
    main()
