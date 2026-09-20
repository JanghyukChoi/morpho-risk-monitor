# -*- coding: utf-8 -*-
"""★★ 슬래싱 가능 금액 — USD 환산. 예측이 아니라 회계.

■ 내가 직전에 틀린 것
  전략별 underlying 을 **토큰 단위 그대로 합산**했다. stETH 와 190억 단위짜리
  토큰을 더한 셈이라 의미가 없었다. 자산이 다르면 USD 로 환산하고 더해야 한다.

■ 측정 (가정 없음)
  슬래싱 가능액(USD) = Σ (오퍼레이터 위임지분 × 배분 매그니튜드/1e18 × 기초토큰 가격)
  분모(전체 예치, USD) = Σ (전략 총예치 × 환산비 × 기초토큰 가격)

■ 검증된 전제
  · shares→underlying 환산비 중앙 1.000 (verify_units.py)
  · 배분 이력은 AllocationUpdated 전수, 같은 키는 최신값만 유효
  · 가격은 DefiLlama coins (confidence 동반)
  · ⚠ 네이티브 ETH(EigenPod)는 ERC20 전략이 아니라 이 집계에 없다.
    분자에도 없으므로(배분에 beaconChainETHStrategy 미등장) 기준이 일관된다.
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
SM = "0x858646372CC42E1A627fcE94aa7A7033e7CF075A"


def sel(s):
    h = keccak.new(digest_bits=256)
    h.update(s.encode())
    return "0x" + h.hexdigest()[:8]


def t0(s):
    h = keccak.new(digest_bits=256)
    h.update(s.encode())
    return "0x" + h.hexdigest()


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


def prices(tokens, batch=60):
    """DefiLlama coins — 가격과 confidence. 없으면 그 자산은 **집계에서 뺀다**(0 처리 금지)."""
    out = {}
    ks = ["ethereum:" + t.lower() for t in tokens if t]
    for i in range(0, len(ks), batch):
        ch = ks[i:i + batch]
        for a in range(3):
            try:
                r = requests.get("https://coins.llama.fi/prices/current/" + ",".join(ch), timeout=60)
                if r.status_code == 429:
                    time.sleep(3 + a * 3)
                    continue
                out.update(r.json().get("coins") or {})
                break
            except Exception:
                time.sleep(2)
        time.sleep(0.25)
    return out


def strategy_info(strats):
    rows = []
    for s in strats:
        tok = call(s, sel("underlyingToken()"))
        tok = "0x" + tok[-40:] if tok else None
        ts = call(s, sel("totalShares()"))
        cv = call(s, sel("sharesToUnderlyingView(uint256)") + hex(10**18)[2:].rjust(64, "0"))
        dec = 18
        if tok:
            d = call(tok, sel("decimals()"))
            if d:
                dec = int(d, 16)
        rows.append(dict(strategy=s, token=tok, decimals=dec,
                         total_shares=float(int(ts, 16)) / 10**dec if ts else 0.0,
                         ratio=int(cv, 16) / 1e18 if cv else 1.0))
        time.sleep(0.03)
    return pd.DataFrame(rows)


def main():
    head = int(rpc("eth_blockNumber", []), 16)
    # ── 전 전략 목록
    lg, cur = [], 17_000_000
    while cur <= head:
        e = min(cur + 200_000 - 1, head)
        r = rpc("eth_getLogs", [{"address": SM,
                                 "topics": [t0("StrategyAddedToDepositWhitelist(address)")],
                                 "fromBlock": hex(cur), "toBlock": hex(e)}])
        if r:
            lg += r
        cur = e + 1
    ss = set()
    for x in lg:
        if len(x.get("topics", [])) > 1:
            ss.add("0x" + x["topics"][1][-40:])
        elif x.get("data") and len(x["data"]) >= 66:
            ss.add("0x" + x["data"][26:66])
    strats = sorted(ss)
    print("■ 화이트리스트 전략 %d종" % len(strats), flush=True)

    S = strategy_info(strats)
    P = prices(S.token.dropna().tolist())
    S["price"] = S.token.map(lambda t: (P.get("ethereum:" + t.lower()) or {}).get("price")
                             if t else None)
    S["conf"] = S.token.map(lambda t: (P.get("ethereum:" + t.lower()) or {}).get("confidence")
                            if t else None)
    S["underlying"] = S.total_shares * S.ratio
    S["usd"] = S.underlying * S.price
    S.to_parquet(OUT / "strategies_usd.parquet")

    npx = S.price.isna().sum()
    print("■ 가격 확보 %d/%d · 미확보 %d종은 **집계에서 제외**(0 처리하지 않는다)"
          % (S.price.notna().sum(), len(S), npx), flush=True)

    # ── 배분(분자)
    M = pd.read_parquet(OUT / "allocations.parquet")
    act = M[M.magnitude > 0].copy()
    act = act.merge(S[["strategy", "price", "decimals", "ratio", "token"]], on="strategy", how="left")
    act["usd_shares"] = act.shares * act.ratio.fillna(1) * act.price
    act["usd_slashable"] = act.slashable_shares * act.ratio.fillna(1) * act.price
    act.to_parquet(OUT / "allocations_usd.parquet")

    print("\n[ ★ 전략별 규모 (USD 상위) ]")
    for _, r in S.dropna(subset=["usd"]).nlargest(10, "usd").iterrows():
        print("   %-44s $%14s  (conf %.2f)"
              % (r.strategy[:44], format(r.usd, ",.0f"), r.conf if r.conf == r.conf else 0))
    print("\n[ ★★ 결과 ]")
    tot = S.usd.sum(skipna=True)
    a_sh = act.usd_shares.sum(skipna=True)
    a_sl = act.usd_slashable.sum(skipna=True)
    print("   ERC20 전략 총 예치            $%s" % format(tot, ",.0f"))
    print("   배분 참여 오퍼레이터 지분      $%s  (%.4f%%)" % (format(a_sh, ",.0f"), a_sh / tot * 100))
    print("   ★ 실제 슬래싱 가능            $%s  (**%.5f%%**)" % (format(a_sl, ",.0f"), a_sl / tot * 100))
    miss = act.price.isna().sum()
    if miss:
        print("   ⚠ 배분 중 가격 미확보 %d건 — 분자에서 빠졌다(과소평가 방향)" % miss)
    print("\n[ 슬래싱 가능액의 구성 ]")
    g = act.groupby("token").agg(usd=("usd_slashable", "sum"), n=("operator", "nunique"))
    for k, r in g.sort_values("usd", ascending=False).head(8).iterrows():
        print("   %s  $%s  (오퍼레이터 %d)" % (str(k)[:20], format(r.usd, ",.0f"), r.n))


if __name__ == "__main__":
    main()
