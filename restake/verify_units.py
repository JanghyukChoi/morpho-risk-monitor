# -*- coding: utf-8 -*-
"""★★ 단위 검증 — shares 가 정말 토큰인가. 주장 전 마지막 관문.

왜 필요한가
  slashable.py 가 "배분된 총 지분 5,879"를 냈다. ETH 라면 약 $17M 인데
  업계는 "$15B 노출"이라고 말한다. **1,000배 차이**다.
  Morpho 때 '스테이블은 $1' 가정으로 틀렸던 교훈 — 가정을 검증한다.

검증 항목
  U1 전략 → 기초자산 토큰 (StrategyBase.underlyingToken)
  U2 shares → underlying 환산 (sharesToUnderlyingView) — 1:1 이 아닐 수 있다
  U3 전략별 총예치 (totalShares) → EigenLayer 전체 규모와 대조
  U4 외부 기준(DefiLlama EigenCloud TVL)과 ±20% 안에서 맞는가
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


def sel(sig):
    h = keccak.new(digest_bits=256)
    h.update(sig.encode())
    return "0x" + h.hexdigest()[:8]


def rpc(method, params, tries=3):
    for i in range(tries):
        for u in RPCS:
            try:
                d = requests.post(u, json={"jsonrpc": "2.0", "id": 1,
                                           "method": method, "params": params}, timeout=60).json()
                if "result" in d:
                    return d["result"]
            except Exception:
                pass
        time.sleep(1 + i)
    return None


def call(to, data):
    r = rpc("eth_call", [{"to": to, "data": data}, "latest"])
    return r if r and r != "0x" else None


def addr_of(hexstr):
    return "0x" + hexstr[-40:] if hexstr else None


def main():
    M = pd.read_parquet(OUT / "allocations.parquet")
    strats = sorted(M.strategy.unique())
    print("[ U1~U3 전략 %d종 검증 ]" % len(strats))
    print("   %-44s %-10s %8s %14s %14s"
          % ("전략", "토큰", "decimals", "총shares", "총underlying"))
    rows = []
    for s in strats:
        tok = addr_of(call(s, sel("underlyingToken()")))
        tot = call(s, sel("totalShares()"))
        tot = int(tot, 16) if tot else 0
        # shares → underlying (1e18 shares 를 넣어 환산비 확인)
        conv = call(s, sel("sharesToUnderlyingView(uint256)") + hex(10**18)[2:].rjust(64, "0"))
        ratio = int(conv, 16) / 1e18 if conv else float("nan")
        sym = dec = None
        if tok:
            d = call(tok, sel("decimals()"))
            dec = int(d, 16) if d else 18
            sy = call(tok, sel("symbol()"))
            if sy:
                try:
                    raw = bytes.fromhex(sy[2:])
                    sym = raw[64:].rstrip(b"\x00").decode("utf-8", "ignore") or None
                except Exception:
                    sym = None
        rows.append(dict(strategy=s, token=tok, symbol=sym, decimals=dec,
                         total_shares=float(tot) / 1e18, share_ratio=ratio))
        print("   %-44s %-10s %8s %14.4f %14.4f"
              % (s[:44], (sym or (tok[:8] if tok else "?"))[:10], dec,
                 float(tot) / 1e18, float(tot) / 1e18 * (ratio if ratio == ratio else 1)))
        time.sleep(0.05)
    S = pd.DataFrame(rows)
    S.to_parquet(OUT / "strategies.parquet")
    print("\n[ ★ shares→underlying 환산비 ]")
    r = S.share_ratio.dropna()
    print("   중앙 %.6f · 최소 %.6f · 최대 %.6f · 1.0 에서 5%% 이상 벗어난 전략 %d종"
          % (r.median(), r.min(), r.max(), ((r - 1).abs() > 0.05).sum()))
    print("   → 1.0 에 가까우면 shares ≈ 토큰 수량으로 읽어도 된다")

    print("\n[ U3 EigenLayer 전체 규모 vs 배분된 규모 ]")
    tot_all = (S.total_shares * S.share_ratio.fillna(1)).sum()
    act = M[M.magnitude > 0]
    print("   전 전략 총 예치(underlying 환산)   %.2f" % tot_all)
    print("   배분 참여 오퍼레이터의 지분 합      %.2f" % act.shares.sum())
    print("   그중 슬래싱 가능                   %.2f" % act.slashable_shares.sum())
    if tot_all > 0:
        print("   → 전체 예치 대비 **슬래싱 가능 비율 %.4f%%**"
              % (act.slashable_shares.sum() / tot_all * 100))

    print("\n[ U4 외부 기준과 대조 — DefiLlama EigenCloud ]")
    try:
        d = requests.get("https://api.llama.fi/protocol/eigenlayer", timeout=45).json()
        tvl = d.get("currentChainTvls", {})
        eth_tvl = sum(v for k, v in tvl.items() if isinstance(v, (int, float)) and "borrow" not in k.lower())
        print("   DefiLlama TVL $%s" % format(eth_tvl, ",.0f"))
        # ETH 가격
        p = requests.get("https://coins.llama.fi/prices/current/coingecko:ethereum", timeout=30).json()
        px = p["coins"]["coingecko:ethereum"]["price"]
        print("   ETH $%s · 온체인 총예치 %.0f 단위 → 약 $%s (전 전략이 ETH계열이라 가정 시)"
              % (format(px, ",.0f"), tot_all, format(tot_all * px, ",.0f")))
        if tot_all * px > 0:
            print("   대조 배율 %.2fx  %s"
                  % (eth_tvl / (tot_all * px),
                     "✅ ±20% 이내" if 0.8 <= eth_tvl / (tot_all * px) <= 1.2
                     else "⚠ 불일치 — 단위/범위 재검토 필요"))
    except Exception as e:
        print("   조회 실패:", str(e)[:80])


if __name__ == "__main__":
    main()
