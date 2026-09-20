# -*- coding: utf-8 -*-
"""노출 데이터는 실제로 있는가 — 손실 데이터가 없다고 전부 없는 게 아니다."""
import requests, time, collections
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
def scan(t0,frm=22218956,to=26_017_000,step=50000):
    out=[];cur=frm
    while cur<=to:
        e=min(cur+step-1,to)
        r=rpc("eth_getLogs",[{"address":AM,"topics":[t0],"fromBlock":hex(cur),"toBlock":hex(e)}])
        if r: out+=r
        cur=e+1
    return out
EV={
 "AllocationUpdated":"AllocationUpdated(address,(address,uint32),address,uint64,uint32)",
 "MaxMagnitudeUpdated":"MaxMagnitudeUpdated(address,address,uint64)",
 "OperatorAddedToOperatorSet":"OperatorAddedToOperatorSet(address,(address,uint32))",
 "OperatorRemovedFromOperatorSet":"OperatorRemovedFromOperatorSet(address,(address,uint32))",
 "OperatorSetCreated":"OperatorSetCreated((address,uint32))",
 "StrategyAddedToOperatorSet":"StrategyAddedToOperatorSet((address,uint32),address)",
 "SlasherUpdated":"SlasherUpdated((address,uint32),address,uint32)",
 "RedistributionAddressSet":"RedistributionAddressSet((address,uint32),address)",
}
print("[ ★ 노출·구조 데이터 가용성 — AllocationManager 이벤트 전수 ]")
res={}
for name,sig in EV.items():
    lg=scan(k(sig))
    res[name]=lg
    print("  %-32s **%5d건**"%(name,len(lg)))
print()
# 오퍼레이터-오퍼레이터셋 관계 복원
add=res["OperatorAddedToOperatorSet"]; rem=res["OperatorRemovedFromOperatorSet"]
pairs=collections.Counter()
for lg in add:
    try:
        op=ad(["address","(address,uint32)"],bytes.fromhex(lg["data"][2:])) if not lg["topics"][1:] else None
    except Exception: op=None
    # operator 가 indexed 다 → topics[1]
    o="0x"+lg["topics"][1][-40:]
    pairs[o]+=1
print("[ 복원 가능한 것 ]")
print("  · 오퍼레이터 → 오퍼레이터셋 등록/해제 이력  (등록 %d · 해제 %d)"%(len(add),len(rem)))
print("  · 고유 오퍼레이터 **%d명**"%len(pairs))
print("  · 오퍼레이터셋(=AVS×id) 생성 **%d개**"%len(res["OperatorSetCreated"]))
print("  · 전략 배정 **%d건** → 어떤 담보가 어느 AVS 에 걸려 있나"%len(res["StrategyAddedToOperatorSet"]))
print("  · 배분(AllocationUpdated) **%d건** → 오퍼레이터가 각 AVS 에 **얼마를 슬래싱 가능하게** 걸었나"%len(res["AllocationUpdated"]))
print("  · 최대 매그니튜드 %d건 → 슬래싱 상한"%len(res["MaxMagnitudeUpdated"]))
print("  · 슬래셔 지정 %d건 · 재분배 주소 %d건"%(len(res["SlasherUpdated"]),len(res["RedistributionAddressSet"])))
print()
print("[ ★★ 결론 ]")
print("  손실(빈도·심도) 데이터만 없다. **노출·구조·상한은 전부 온체인에 있다.**")
print("  → '확률'은 못 재지만 '만약 터지면 누가 얼마를 잃나'는 **계산**할 수 있다")
print("     Morpho 때 예측→회계로 전환한 것과 정확히 같은 구조다")
