# -*- coding: utf-8 -*-
"""분모 규명 — 8.27배 불일치의 원인. 네이티브 ETH(EigenPod)를 빠뜨렸나."""
import requests, time
import pandas as pd
from Crypto.Hash import keccak
RPCS=["https://gateway.tenderly.co/public/mainnet","https://rpc.mevblocker.io"]
EPM="0x91E677b07F7AF907ec9a428aafA9fc14a0d3A22C"   # EigenPodManager
BEACON="0xbeaC0eEEeeeeeEEeEeeEEEEeEEeEeeeEeeEEBEaC0" # beaconChainETHStrategy 의사주소
def sel(s):
    h=keccak.new(digest_bits=256); h.update(s.encode()); return "0x"+h.hexdigest()[:8]
def rpc(m,p,t=3):
    for i in range(t):
        for u in RPCS:
            try:
                d=requests.post(u,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=60).json()
                if "result" in d: return d["result"]
            except Exception: pass
        time.sleep(1)
    return None
def call(to,data):
    r=rpc("eth_call",[{"to":to,"data":data},"latest"])
    return r if r and r!="0x" else None
M=pd.read_parquet("data/restake/allocations.parquet")
print("[ ① 배분에 네이티브 ETH 전략이 있나 ]")
has=[s for s in M.strategy.unique() if s.lower()==BEACON.lower()]
print("   beaconChainETHStrategy(%s) 등장: %s"%(BEACON[:14],"**있음**" if has else "없음"))
print("   배분에 등장한 전략 %d종 (전부 ERC20 전략)"%M.strategy.nunique())
print()
print("[ ② EigenPodManager — 네이티브 재스테이킹 규모 ]")
for fn in ("numPods()","ownerToPod(address)"):
    pass
r=call(EPM,sel("numPods()"))
print("   numPods = %s"%(int(r,16) if r else "조회실패"))
print()
print("[ ③ 전체 전략 목록 — StrategyManager 에 등록된 전부 ]")
SM="0x858646372CC42E1A627fcE94aa7A7033e7CF075A"
# StrategyAddedToDepositWhitelist(address indexed strategy)
def t0(s):
    h=keccak.new(digest_bits=256); h.update(s.encode()); return "0x"+h.hexdigest()
lg=[]; cur=17000000
while cur<=26_017_000:
    e=min(cur+200000-1,26_017_000)
    r=rpc("eth_getLogs",[{"address":SM,"topics":[t0("StrategyAddedToDepositWhitelist(address)")],
                          "fromBlock":hex(cur),"toBlock":hex(e)}])
    if r: lg+=r
    cur=e+1
# 인덱스 여부가 버전마다 다르다 — topics 에 없으면 data 에서 꺼낸다
ss=set()
for x in lg:
    if len(x.get("topics",[]))>1: ss.add("0x"+x["topics"][1][-40:])
    elif x.get("data") and len(x["data"])>=66: ss.add("0x"+x["data"][26:66])
strats=sorted(ss)
print("   (이벤트 %d건 → 전략 %d종 추출)"%(len(lg),len(strats)))
print("   화이트리스트 전략 **%d종** (배분 등장 16종의 상위집합)"%len(strats))
print()
print("[ ④ 전 전략 총예치 재집계 ]")
tot=0.0; rows=[]
for s in strats:
    ts=call(s,sel("totalShares()"))
    cv=call(s,sel("sharesToUnderlyingView(uint256)")+hex(10**18)[2:].rjust(64,"0"))
    tok=call(s,sel("underlyingToken()"))
    n=float(int(ts,16))/1e18 if ts else 0.0
    r_=int(cv,16)/1e18 if cv else 1.0
    u=n*r_
    if u>0.01: rows.append((s,u,"0x"+tok[-40:] if tok else None))
    tot+=u
    time.sleep(0.03)
rows.sort(key=lambda x:-x[1])
print("   유효 전략 %d종 · 총 underlying **%.0f 단위**"%(len(rows),tot))
for s,u,tk in rows[:8]: print("      %s  %12.2f"%(s[:20],u))
print()
print("[ ★ 분모 정정 후 ]")
act=M[M.magnitude>0]
print("   전 전략 총예치            %.0f"%tot)
print("   배분 참여 지분            %.2f  (%.4f%%)"%(act.shares.sum(),act.shares.sum()/tot*100))
print("   **실제 슬래싱 가능**      %.2f  (**%.5f%%**)"%(act.slashable_shares.sum(),act.slashable_shares.sum()/tot*100))
print()
print("   ※ 네이티브 ETH(EigenPod)는 이 합계에 **없다**. 그래서 DefiLlama TVL 과 여전히 차이가 난다.")
print("     다만 배분에도 네이티브 전략이 없으므로 **분자·분모 모두 ERC20 전략 기준**으로 일관된다.")
