# -*- coding: utf-8 -*-
"""★ 강한 주장 전 검증 — "진짜 슬래싱이 0건"이 맞는가.
V1 AllocationManager 배포 시점까지 거슬러 전수 스캔 (범위 누락 배제)
V2 스팸 AVS 의 정체 확인
V3 구버전 슬래싱 경로(DelegationManager 등) 존재 여부
"""
import requests, time
from Crypto.Hash import keccak
from eth_abi import decode as ad
RPCS=["https://gateway.tenderly.co/public/mainnet","https://rpc.mevblocker.io"]
AM="0x948a420b8CC1d6BFd0B6087C2E7c344a2CD0bc39"
def k(s):
    h=keccak.new(digest_bits=256); h.update(s.encode()); return "0x"+h.hexdigest()
def rpc(m,p,tries=3):
    for i in range(tries):
        for u in RPCS:
            try:
                d=requests.post(u,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=60).json()
                if "result" in d: return d["result"]
            except Exception: pass
        time.sleep(1)
    return None
T0=k("OperatorSlashed(address,(address,uint32),address[],uint256[],string)")
print("[ V1 AllocationManager 배포 시점 확인 ]")
code=rpc("eth_getCode",[AM,"latest"])
print("  컨트랙트 코드 %d바이트 (배포됨)"%((len(code)-2)//2 if code else 0))
# 이분탐색으로 배포 블록 찾기
lo,hi=20_000_000,26_017_000
while lo<hi:
    mid=(lo+hi)//2
    c=rpc("eth_getCode",[AM,hex(mid)])
    if c and c!="0x": hi=mid
    else: lo=mid+1
print("  ★ 배포 블록 ≈ %d"%lo)
print()
print("[ V1b 배포 블록부터 전수 재스캔 ]")
tot=[];cur=lo
t0=time.time()
while cur<=26_017_000:
    end=min(cur+9999,26_017_000)
    r=rpc("eth_getLogs",[{"address":AM,"topics":[T0],"fromBlock":hex(cur),"toBlock":hex(end)}])
    if r: tot+=r
    cur=end+1
print("  스캔 %d~26,017,000 (%d블록) · %.0fs"%(lo,26_017_000-lo,time.time()-t0))
print("  ★ OperatorSlashed 총 **%d건**"%len(tot))
rows=[]
for lg in tot:
    op,os_,st,wd,de=ad(["address","(address,uint32)","address[]","uint256[]","string"],bytes.fromhex(lg["data"][2:]))
    rows.append((int(lg["blockNumber"],16),op,os_[0],os_[1],max(int(x) for x in wd)/1e18,de))
print()
print("[ V2 사건 전수 ]")
print("  %-10s %-12s %-12s %6s %8s  %s"%("블록","오퍼레이터","AVS","setId","wad","description"))
for b,op,avs,sid,w,de in sorted(rows):
    print("  %-10d %-12s %-12s %6d %8.4f  %s"%(b,op[:10],avs[:10],sid,w,str(de)[:38]))
ops={r[1] for r in rows}; avss={r[2] for r in rows}
print()
print("  고유 오퍼레이터 %d · 고유 AVS %d · wad=1.0 인 건 %d/%d"
      %(len(ops),len(avss),sum(1 for r in rows if abs(r[4]-1.0)<1e-9),len(rows)))
print()
print("[ V3 구버전 슬래싱 경로 — 다른 이벤트로 슬래싱이 있었나 ]")
for sig in ["OperatorSlashed(address,address,uint32,address[],uint256[],string)",
            "Slashed(address,uint256)","OperatorFrozen(address,address)",
            "OperatorSlashed(address,(address,uint32),address[],uint256[])"]:
    r=rpc("eth_getLogs",[{"address":AM,"topics":[k(sig)],"fromBlock":hex(lo),"toBlock":hex(26_017_000)}])
    print("  %-60s %s건"%(sig[:58],len(r) if r is not None else "조회실패"))
