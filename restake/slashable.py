# -*- coding: utf-8 -*-
"""★ 실제로 슬래싱 가능한 금액은 얼마인가 — 예측이 아니라 회계.

배경
  업계는 "$15B 재스테이킹 ETH 가 슬래싱 위험에 노출됐다"고 말한다.
  그런데 EigenLayer 의 슬래싱은 **옵트인**이다:
    ① 오퍼레이터가 오퍼레이터셋에 등록해야 하고
    ② 전략별로 **매그니튜드를 배분**해야 슬래싱 대상이 된다
  배분하지 않은 지분은 슬래싱되지 않는다.

측정 (가정 없음 · 순수 회계)
  슬래싱 가능액 = Σ (오퍼레이터의 전략별 위임액 × 그 전략의 배분 매그니튜드 비율)
  매그니튜드는 1e18 = 100% 스케일이다.

검증된 전제
  · AllocationManager 0x948a...bc39, 배포 블록 22,218,956 (eth_getCode 이분탐색)
  · 이벤트 시그니처는 keccak 검산 + 실로그 대조로 확인
  · archive 로그가 되는 무료 RPC 2곳만 사용
"""
from __future__ import annotations
import time, json
from pathlib import Path
import requests
import pandas as pd
from Crypto.Hash import keccak
from eth_abi import decode as abi_decode

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_restake"
OUT.mkdir(parents=True, exist_ok=True)

RPCS = ["https://gateway.tenderly.co/public/mainnet", "https://rpc.mevblocker.io"]
AM = "0x948a420b8CC1d6BFd0B6087C2E7c344a2CD0bc39"
DM = "0x39053D51B77DC0d36036Fc1fCc8Cb819df8Ef37A"   # DelegationManager
DEPLOY = 22_218_956


def topic0(sig):
    h = keccak.new(digest_bits=256)
    h.update(sig.encode())
    return "0x" + h.hexdigest()


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


def scan(addr, t0, frm=DEPLOY, to=None, step=50_000):
    if to is None:
        to = int(rpc("eth_blockNumber", []), 16)
    out, cur = [], frm
    while cur <= to:
        e = min(cur + step - 1, to)
        r = rpc("eth_getLogs", [{"address": addr, "topics": [t0],
                                 "fromBlock": hex(cur), "toBlock": hex(e)}])
        if r:
            out += r
        cur = e + 1
    return out


def call(to, data):
    """eth_call 로 뷰 함수를 읽는다."""
    return rpc("eth_call", [{"to": to, "data": data}, "latest"])


def selector(sig):
    return topic0(sig)[:10]


def main():
    head = int(rpc("eth_blockNumber", []), 16)
    print("■ 헤드 %d · 스캔 %d~%d" % (head, DEPLOY, head), flush=True)

    # ── 1. 배분 이력 — 누가 어느 오퍼레이터셋에 얼마를 걸었나
    # AllocationUpdated(address operator, OperatorSet operatorSet, IStrategy strategy,
    #                   uint64 newMagnitude, uint32 effectBlock)
    lg = scan(AM, topic0("AllocationUpdated(address,(address,uint32),address,uint64,uint32)"), to=head)
    rows = []
    for x in lg:
        op, os_, st, mag, eff = abi_decode(
            ["address", "(address,uint32)", "address", "uint64", "uint32"],
            bytes.fromhex(x["data"][2:]))
        rows.append(dict(block=int(x["blockNumber"], 16), operator=op, avs=os_[0],
                         set_id=os_[1], strategy=st, magnitude=int(mag), effect=int(eff)))
    A = pd.DataFrame(rows)
    print("■ AllocationUpdated %d건 · 오퍼레이터 %d · AVS %d · 전략 %d"
          % (len(A), A.operator.nunique() if len(A) else 0,
             A.avs.nunique() if len(A) else 0, A.strategy.nunique() if len(A) else 0), flush=True)
    if not len(A):
        return None
    # 같은 (operator, avs, set, strategy) 는 **최신 값만** 유효하다
    cur = (A.sort_values("block")
             .groupby(["operator", "avs", "set_id", "strategy"], as_index=False).last())
    cur["mag_pct"] = cur.magnitude / 1e18 * 100
    print("■ 현재 유효 배분 %d건 · 매그니튜드>0 인 것 %d건"
          % (len(cur), (cur.magnitude > 0).sum()), flush=True)

    # ── 2. 오퍼레이터별 전략 지분 — DelegationManager.operatorShares(operator, strategy)
    sel = selector("operatorShares(address,address)")
    shares = []
    todo = cur[cur.magnitude > 0][["operator", "strategy"]].drop_duplicates()
    print("■ 지분 조회 %d건" % len(todo), flush=True)
    for _, r in todo.iterrows():
        data = sel + r.operator[2:].lower().rjust(64, "0") + r.strategy[2:].lower().rjust(64, "0")
        res = call(DM, data)
        shares.append(dict(operator=r.operator, strategy=r.strategy,
                           shares=int(res, 16) if res and res != "0x" else 0))
        time.sleep(0.05)
    S = pd.DataFrame(shares)
    # ⚠ shares 는 uint256(wei 스케일)이라 parquet 에 int 로 못 넣는다 → 1e18 로 나눠 float
    S["shares"] = S.shares.astype(object).apply(lambda v: float(v) / 1e18)
    M = cur.merge(S, on=["operator", "strategy"], how="left")
    M["shares"] = pd.to_numeric(M.shares, errors="coerce").fillna(0.0)
    M["magnitude"] = M.magnitude.astype(object).apply(lambda v: float(v))
    # 슬래싱 가능 지분 = 위임지분 × 배분비율
    M["slashable_shares"] = M.shares * M.magnitude / 1e18
    M.to_parquet(OUT / "allocations.parquet")
    return M


if __name__ == "__main__":
    M = main()
    if M is None or not len(M):
        print("배분 데이터 없음")
        raise SystemExit
    act = M[M.magnitude > 0]
    print("\n[ ★ 슬래싱 가능 범위 ]")
    print("   배분한 오퍼레이터 **%d명** · AVS **%d곳** · 전략 **%d종**"
          % (act.operator.nunique(), act.avs.nunique(), act.strategy.nunique()))
    print("\n[ 매그니튜드 분포 — 위임지분 중 몇 %를 슬래싱 대상으로 걸었나 ]")
    for q in (0, 25, 50, 75, 100):
        print("   %3d분위  %.2f%%" % (q, act.mag_pct.quantile(q / 100)))
    print("\n[ 오퍼레이터별 — 지분 대비 슬래싱 노출 ]")
    g = (act.groupby("operator")
            .agg(sets=("avs", "nunique"), strat=("strategy", "nunique"),
                 shares=("shares", "sum"), slash=("slashable_shares", "sum")))
    g["pct"] = g.slash / g.shares.replace(0, pd.NA) * 100
    for k, r in g.sort_values("shares", ascending=False).head(15).iterrows():
        print("   %s  AVS %d · 전략 %d · 지분 %.4e · 슬래싱가능 %.4e (%.1f%%)"
              % (k[:12], r.sets, r.strat, r.shares, r.slash,
                 r.pct if r.pct == r.pct else 0))
    tot_sh, tot_sl = act.shares.sum(), act.slashable_shares.sum()
    print("\n[ ★★ 합계 ]")
    print("   배분에 참여한 오퍼레이터의 총 지분  %.6e" % tot_sh)
    print("   그중 실제 슬래싱 가능 지분          %.6e  (**%.1f%%**)"
          % (tot_sl, tot_sl / tot_sh * 100 if tot_sh else 0))
    print("\n   ※ shares 는 전략 토큰 단위다. USD 환산은 별도 검증이 필요하다.")
