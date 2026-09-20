# -*- coding: utf-8 -*-
"""무료 RPC 중 과거 로그(eth_getLogs) 가 되는 곳 찾기."""
import requests
AM="0x948a420b8CC1d6BFd0B6087C2E7c344a2CD0bc39"
T0="0x80969ad29428d6797ee7aad084f9e4a42a82fc506dcd2ca3b6fb431f85ccebe5"
RPCS=["https://ethereum-rpc.publicnode.com","https://eth.drpc.org","https://rpc.flashbots.net",
      "https://eth.merkle.io","https://1rpc.io/eth","https://eth.blockrazor.xyz",
      "https://eth-pokt.nodies.app","https://rpc.mevblocker.io","https://eth.rpc.blxrbdn.com",
      "https://gateway.tenderly.co/public/mainnet","https://api.securerpc.com/v1",
      "https://eth.api.onfinality.io/public","https://core.gashawk.io/rpc",
      "https://virginia.rpc.blxrbdn.com","https://singapore.rpc.blxrbdn.com"]
def t(u):
    try:
        h=requests.post(u,json={"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]},timeout=20).json()
        if "result" not in h: return u,"헤드실패",str(h.get("error"))[:50]
        head=int(h["result"],16)
        # 최근 2000블록 로그 (archive 아님)
        r1=requests.post(u,json={"jsonrpc":"2.0","id":1,"method":"eth_getLogs","params":[
            {"address":AM,"topics":[T0],"fromBlock":hex(head-2000),"toBlock":hex(head)}]},timeout=40).json()
        recent = "OK(%d)"%len(r1["result"]) if "result" in r1 else "X:"+str(r1.get("error",{}).get("message"))[:38]
        # 5개월 전 구간 (archive 필요)
        r2=requests.post(u,json={"jsonrpc":"2.0","id":1,"method":"eth_getLogs","params":[
            {"address":AM,"topics":[T0],"fromBlock":hex(24900000),"toBlock":hex(24902000)}]},timeout=40).json()
        old = "OK(%d)"%len(r2["result"]) if "result" in r2 else "X:"+str(r2.get("error",{}).get("message"))[:38]
        return u,recent,old
    except Exception as e: return u,"ERR",str(e)[:40]
print("  %-42s %-14s %s"%("RPC","최근로그","과거로그(archive)"))
ok=[]
for u in RPCS:
    a,b,c=t(u)
    mark="★" if c.startswith("OK") else " "
    print("%s %-42s %-14s %s"%(mark,a.split('//')[1][:42],b,c))
    if c.startswith("OK"): ok.append(u)
print("\n  archive 가능 RPC: %d개"%len(ok))
for u in ok: print("    "+u)
