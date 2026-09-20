# -*- coding: utf-8 -*-
"""슬래싱 주체 AVS 3곳의 정체 확인 — 실제 AVS 인가 시험용인가."""
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
# AVSMetadataURIUpdated(address indexed avs, string metadataURI) — avs 가 indexed
T=k("AVSMetadataURIUpdated(address,string)")
TARGETS={"0x26ddbf2a":"slash 10% 시험","0x90c68bf0":"AlephAVS","0x12b75d5e":"eigenyields 스팸"}
print("[ AVS 메타데이터 조회 — 전체 AVS 등록 현황 ]")
logs=[];cur=22218956
while cur<=26_017_000:
    end=min(cur+49999,26_017_000)
    r=rpc("eth_getLogs",[{"address":AM,"topics":[T],"fromBlock":hex(cur),"toBlock":hex(end)}])
    if r: logs+=r
    cur=end+1
print("  등록 이벤트 %d건"%len(logs))
seen={}
for lg in logs:
    avs="0x"+lg["topics"][1][-40:]
    try: uri=ad(["string"],bytes.fromhex(lg["data"][2:]))[0]
    except Exception: uri="(디코딩실패)"
    seen[avs.lower()]=uri
print("  고유 AVS **%d곳**"%len(seen))
print()
print("[ ★ 슬래싱을 실행한 AVS 3곳의 정체 ]")
for pre,lab in TARGETS.items():
    hit=[(a,u) for a,u in seen.items() if a.startswith(pre.lower())]
    if hit:
        a,u=hit[0]; print("  %s (%s)\n     메타데이터: %s"%(a,lab,str(u)[:110]))
    else:
        print("  %s (%s)\n     ⚠ 메타데이터 등록 없음 — 정식 AVS 로 등록조차 안 했다"%(pre,lab))
print()
print("[ 참고 — 등록된 AVS 중 일부 ]")
for a,u in list(seen.items())[:12]:
    print("  %s  %s"%(a,str(u)[:80]))
