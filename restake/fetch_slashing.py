# -*- coding: utf-8 -*-
"""EigenLayer 슬래싱 이벤트 전수 수집 — 온체인 직접.

■ 왜 온체인인가
  EigenExplorer API 는 토큰이 필요하고, 그 집계가 맞는지 우리가 검증할 수 없다.
  슬래싱은 컨트랙트가 이벤트로 남긴다. **원천을 직접 읽는 것이 가장 견고하다.**
  (Morpho 때 API 의 supplyApy 가 실제보다 ~300배 틀렸던 교훈)

■ 대상
  AllocationManager  0x948a420b8CC1d6BFd0B6087C2E7c344a2CD0bc39
  event OperatorSlashed(address operator, OperatorSet(address avs,uint32 id),
                        IStrategy[] strategies, uint256[] wadSlashed, string description)
  topic0 = keccak("OperatorSlashed(address,(address,uint32),address[],uint256[],string)")
         = 0x80969ad29428d6797ee7aad084f9e4a42a82fc506dcd2ca3b6fb431f85ccebe5
  ※ keccak 구현은 Transfer 해시로 검산했다(알려진 값과 일치).

■ 주의
  · 인덱스 파라미터가 없다 → 전부 data 에 있다. ABI 디코딩 필요
  · wadSlashed 는 **비율**(1e18 = 100%)이지 금액이 아니다
  · 공개 RPC 는 블록 범위를 제한한다 → 청크로 나눠 받고 실패 시 반으로 쪼갠다
"""
from __future__ import annotations
import json, time, sys
from pathlib import Path
import requests
import pandas as pd
from Crypto.Hash import keccak
from eth_abi import decode as abi_decode

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_restake"
OUT.mkdir(parents=True, exist_ok=True)

# ★ 무료 RPC 중 **과거 로그(archive)** 가 되는 곳만 쓴다. 실측으로 걸렀다:
#   publicnode  → "Archive requests require a personal token"
#   drpc/1rpc/blockrazor/pokt → 블록 범위 제한(10~50블록)
#   아래 둘만 24,900,000 구간 eth_getLogs 가 통과했다.
RPCS = ["https://gateway.tenderly.co/public/mainnet",
        "https://rpc.mevblocker.io"]
ALLOC_MGR = "0x948a420b8CC1d6BFd0B6087C2E7c344a2CD0bc39"
SIG = "OperatorSlashed(address,(address,uint32),address[],uint256[],string)"


def topic0(sig: str) -> str:
    h = keccak.new(digest_bits=256)
    h.update(sig.encode())
    return "0x" + h.hexdigest()


def _rpc(method, params, tries=3):
    """공개 RPC 여러 곳을 돌아가며 쓴다. 하나 죽어도 계속 간다."""
    last = None
    for i in range(tries):
        for u in RPCS:
            try:
                r = requests.post(u, json={"jsonrpc": "2.0", "id": 1,
                                           "method": method, "params": params}, timeout=45)
                d = r.json()
                if "result" in d:
                    return d["result"]
                last = d.get("error")
            except Exception as e:
                last = str(e)[:80]
        time.sleep(1 + i)
    return {"__error__": last}


def get_logs(addr, t0, frm, to, depth=0):
    """범위 초과로 실패하면 **반으로 쪼개** 재귀한다. 노드마다 한계가 달라서다."""
    res = _rpc("eth_getLogs", [{"address": addr, "topics": [t0],
                                "fromBlock": hex(frm), "toBlock": hex(to)}])
    if isinstance(res, list):
        return res
    if depth > 12 or frm >= to:
        print("      범위 %d~%d 포기: %s" % (frm, to, str(res)[:90]), flush=True)
        return []
    mid = (frm + to) // 2
    return get_logs(addr, t0, frm, mid, depth + 1) + get_logs(addr, t0, mid + 1, to, depth + 1)


def decode(log):
    """인덱스가 없으므로 data 를 통째로 디코딩한다."""
    raw = bytes.fromhex(log["data"][2:])
    types = ["address", "(address,uint32)", "address[]", "uint256[]", "string"]
    try:
        op, opset, strats, wads, desc = abi_decode(types, raw)
    except Exception as e:
        return None
    return dict(block=int(log["blockNumber"], 16), tx=log["transactionHash"],
                operator=op, avs=opset[0], opset_id=opset[1],
                strategies=list(strats), wads=[int(w) for w in wads],
                wad_max=max([int(w) for w in wads]) if wads else 0,
                n_strat=len(strats), description=desc)


def run(start_block=24_400_000):
    t0 = topic0(SIG)
    # ── keccak 검산: 알려진 해시와 대조. 틀리면 전부 무의미하므로 여기서 멈춘다.
    assert topic0("Transfer(address,address,uint256)") == \
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef", "keccak 구현 오류"
    head = _rpc("eth_blockNumber", [])
    if not isinstance(head, str):
        print("RPC 실패:", head); return None
    head = int(head, 16)
    print("■ 체인 헤드 %d · 스캔 시작 %d (%d블록)" % (head, start_block, head - start_block), flush=True)
    print("  topic0 %s" % t0, flush=True)
    logs, step, cur = [], 10_000, start_block
    t_start = time.time()
    while cur <= head:
        end = min(cur + step - 1, head)
        got = get_logs(ALLOC_MGR, t0, cur, end)
        logs += got
        if got:
            print("   %d~%d  +%d건 (누적 %d)" % (cur, end, len(got), len(logs)), flush=True)
        cur = end + 1
    print("■ 로그 %d건 · %.0fs" % (len(logs), time.time() - t_start), flush=True)
    rows = [d for d in (decode(x) for x in logs) if d]
    D = pd.DataFrame(rows)
    if len(D):
        D.to_parquet(OUT / "slashing_events.parquet")
    return D


if __name__ == "__main__":
    sb = int(sys.argv[1]) if len(sys.argv) > 1 else 24_400_000
    D = run(sb)
    if D is None or not len(D):
        print("\n[ 결과 ] 슬래싱 이벤트 0건 — 시작 블록을 더 앞으로 당겨야 할 수 있다")
        sys.exit()
    print("\n[ ★ 슬래싱 이벤트 %d건 ]" % len(D))
    print("   고유 오퍼레이터 %d · 고유 AVS %d · 블록 %d~%d"
          % (D.operator.nunique(), D.avs.nunique(), D.block.min(), D.block.max()))
    print("\n   [ wadSlashed 분포 — 1e18 = 지분 100% ]")
    w = D.wad_max / 1e18
    for q in (0, 25, 50, 75, 100):
        print("      %3d분위  %.6f  (%.4f%%)" % (q, w.quantile(q / 100), w.quantile(q / 100) * 100))
    print("\n   [ AVS 별 건수 ]")
    for a, n in D.avs.value_counts().head(10).items():
        print("      %s  %d건" % (a, n))
    print("\n   [ 최근 사례 ]")
    for _, r in D.nlargest(8, "block").iterrows():
        print("      블록 %d · op %s · wad %.6f · %s"
              % (r.block, r.operator[:10], r.wad_max / 1e18, str(r.description)[:44]))
