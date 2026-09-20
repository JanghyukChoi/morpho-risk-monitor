# -*- coding: utf-8 -*-
"""재스테이킹 일별 스냅샷 — **증분** 수집. 매일 전수 스캔은 낭비다.

■ 무엇을 남기나
  · 슬래싱 이벤트 (신규분만 이어붙임)
  · 현재 배분 상태와 **슬래싱 가능액(USD)** — 계약 공식(÷maxMagnitude) 기준
  · 배분이 늘고 있는지 = 위험이 실재화되고 있는지의 유일한 선행 지표

■ 증분 방식
  마지막 스캔 블록을 상태 파일에 남기고, 다음 실행은 거기부터만 본다.
  하루치 ≈ 7,200블록 = getLogs 한 번. 전수(380만 블록)는 최초 1회면 된다.

■ 검증된 전제 (docs/RESULT_RESTAKE_RISK.md 3부)
  · `_slashOperator` 는 currentMagnitude == 0 이면 건너뛴다 → 배분 0 = 슬래싱 불가
  · 슬래싱 비율 = currentMagnitude / **maxMagnitude** (÷1e18 아님)

사용  python restake/snapshot_restake.py          적재
      python restake/snapshot_restake.py --check  신선도
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import requests
import pandas as pd
from Crypto.Hash import keccak
from eth_abi import decode as abi_decode

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_restake"
OUT.mkdir(parents=True, exist_ok=True)
STATE = OUT / "restake_state.json"
PANEL = OUT / "panel_restake.parquet"
EVENTS = OUT / "slashing_events.parquet"

RPCS = ["https://gateway.tenderly.co/public/mainnet", "https://rpc.mevblocker.io"]
AM = "0x948a420b8CC1d6BFd0B6087C2E7c344a2CD0bc39"
DM = "0x39053D51B77DC0d36036Fc1fCc8Cb819df8Ef37A"
DEPLOY = 22_218_956
SIG_SLASH = "OperatorSlashed(address,(address,uint32),address[],uint256[],string)"
SIG_ALLOC = "AllocationUpdated(address,(address,uint32),address,uint64,uint32)"


def _kec(s):
    h = keccak.new(digest_bits=256)
    h.update(s.encode())
    return h.hexdigest()


def t0(s):
    return "0x" + _kec(s)


def sel(s):
    return "0x" + _kec(s)[:8]


def rpc(m, p, tries=3):
    for i in range(tries):
        for u in RPCS:
            try:
                d = requests.post(u, json={"jsonrpc": "2.0", "id": 1,
                                           "method": m, "params": p}, timeout=60).json()
                if "result" in d:
                    return d["result"]
            except Exception:
                pass
        time.sleep(1 + i)
    return None


def call(to, data):
    r = rpc("eth_call", [{"to": to, "data": data}, "latest"])
    return r if r and r != "0x" else None


def get_logs(t, frm, to, step=50_000):
    out, cur = [], frm
    while cur <= to:
        e = min(cur + step - 1, to)
        r = rpc("eth_getLogs", [{"address": AM, "topics": [t],
                                 "fromBlock": hex(cur), "toBlock": hex(e)}])
        if r:
            out += r
        cur = e + 1
    return out


def prices(tokens):
    out, ks = {}, ["ethereum:" + t.lower() for t in tokens if t]
    for i in range(0, len(ks), 60):
        for a in range(3):
            try:
                r = requests.get("https://coins.llama.fi/prices/current/"
                                 + ",".join(ks[i:i + 60]), timeout=60)
                if r.status_code == 429:
                    time.sleep(3 + a * 3); continue
                out.update(r.json().get("coins") or {}); break
            except Exception:
                time.sleep(2)
        time.sleep(0.25)
    return out


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"last_block": DEPLOY - 1}


def main():
    st = load_state()
    head = int(rpc("eth_blockNumber", []), 16)
    frm = int(st.get("last_block", DEPLOY - 1)) + 1
    print("■ 증분 스캔 %d~%d (%d블록)" % (frm, head, max(head - frm + 1, 0)), flush=True)

    # ── 1. 슬래싱 이벤트 (신규분만)
    new = []
    if frm <= head:
        for lg in get_logs(t0(SIG_SLASH), frm, head):
            op, os_, strat, wads, desc = abi_decode(
                ["address", "(address,uint32)", "address[]", "uint256[]", "string"],
                bytes.fromhex(lg["data"][2:]))
            new.append(dict(block=int(lg["blockNumber"], 16), tx=lg["transactionHash"],
                            operator=op, avs=os_[0], opset_id=os_[1],
                            wad_max=max(int(w) for w in wads) / 1e18 if wads else 0.0,
                            n_strat=len(strat), description=desc))
    E = pd.DataFrame(new)
    if EVENTS.exists():
        old = pd.read_parquet(EVENTS)
        E = pd.concat([old, E], ignore_index=True).drop_duplicates(subset=["tx", "block"])
    if len(E):
        E.to_parquet(EVENTS)
    print("■ 슬래싱 이벤트 신규 %d · 누적 %d" % (len(new), len(E)), flush=True)

    # ── 2. 현재 배분 상태 (전수 재구성 — 이벤트 수가 적어 싸다)
    rows = []
    for lg in get_logs(t0(SIG_ALLOC), DEPLOY, head):
        op, os_, strat, mag, eff = abi_decode(
            ["address", "(address,uint32)", "address", "uint64", "uint32"],
            bytes.fromhex(lg["data"][2:]))
        rows.append(dict(block=int(lg["blockNumber"], 16), operator=op, avs=os_[0],
                         set_id=os_[1], strategy=strat, magnitude=float(mag)))
    A = pd.DataFrame(rows)
    if not len(A):
        print("배분 없음"); return
    cur = (A.sort_values("block")
             .groupby(["operator", "avs", "set_id", "strategy"], as_index=False).last())
    act = cur[cur.magnitude > 0].copy()

    # ── 3. 지분·maxMagnitude·가격
    recs = []
    for _, r in act[["operator", "strategy"]].drop_duplicates().iterrows():
        sh = call(DM, sel("operatorShares(address,address)")
                  + r.operator[2:].lower().rjust(64, "0") + r.strategy[2:].lower().rjust(64, "0"))
        mm = call(AM, sel("getMaxMagnitude(address,address)")
                  + r.operator[2:].lower().rjust(64, "0") + r.strategy[2:].lower().rjust(64, "0"))
        tok = call(r.strategy, sel("underlyingToken()"))
        cv = call(r.strategy, sel("sharesToUnderlyingView(uint256)") + hex(10**18)[2:].rjust(64, "0"))
        recs.append(dict(operator=r.operator, strategy=r.strategy,
                         shares=float(int(sh, 16)) / 1e18 if sh else 0.0,
                         max_mag=float(int(mm, 16)) if mm else 1e18,
                         token="0x" + tok[-40:] if tok else None,
                         ratio=int(cv, 16) / 1e18 if cv else 1.0))
        time.sleep(0.04)
    R = pd.DataFrame(recs)
    P = prices(R.token.dropna().unique().tolist())
    R["price"] = R.token.map(lambda t: (P.get("ethereum:" + t.lower()) or {}).get("price") if t else None)
    M = act.merge(R, on=["operator", "strategy"], how="left")
    M["max_mag"] = M.max_mag.fillna(1e18).replace(0, 1e18)
    M["frac"] = (M.magnitude / M.max_mag).clip(upper=1.0)     # ★ 계약 공식
    M["usd_slashable"] = M.shares * M.ratio.fillna(1) * M.price * M.frac

    today = pd.Timestamp.now().normalize()
    snap = pd.DataFrame([dict(
        date=today, block=head,
        n_slash_events=len(E), n_slash_operators=E.operator.nunique() if len(E) else 0,
        n_alloc=len(act), n_operators=act.operator.nunique(), n_avs=act.avs.nunique(),
        usd_slashable=float(M.usd_slashable.sum(skipna=True)))])
    if PANEL.exists():
        old = pd.read_parquet(PANEL)
        old = old[pd.to_datetime(old.date).dt.normalize() != today]
        snap = pd.concat([old, snap], ignore_index=True)
    snap.to_parquet(PANEL)
    M.to_parquet(OUT / "restake_allocations.parquet")
    STATE.write_text(json.dumps({"last_block": head}))
    print("■ 스냅샷 %s · 블록 %d" % (str(today)[:10], head))
    print("   배분 %d건 · 오퍼레이터 %d · AVS %d · 슬래싱가능 $%s"
          % (len(act), act.operator.nunique(), act.avs.nunique(),
             format(M.usd_slashable.sum(skipna=True), ",.0f")))


def check():
    for p, n in ((PANEL, "panel_restake"), (EVENTS, "slashing_events")):
        if not p.exists():
            print("   %-18s 없음" % n); continue
        d = pd.read_parquet(p)
        if "date" in d.columns:
            dt = pd.to_datetime(d.date)
            print("   %-18s %d행 · %s~%s · %d일치"
                  % (n, len(d), str(dt.min())[:10], str(dt.max())[:10], dt.nunique()))
        else:
            print("   %-18s %d행 · 블록 %d~%d" % (n, len(d), d.block.min(), d.block.max()))


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        main()
        check()
