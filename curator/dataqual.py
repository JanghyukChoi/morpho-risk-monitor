# -*- coding: utf-8 -*-
"""★★ 데이터 신뢰도 전수 검사 — 노출 지도를 지을 수 있는 땅인가.

발견: 담보 USD 환산이 이색 자산에서 깨진다(USR $0.096, xUSD priceUsd=NaN).
      노출 지도는 전부 USD 값 위에 서 있다. 땅이 꺼지면 지도도 꺼진다.
검사: 마켓별로 USD 값의 내적 정합성을 본다. 가격 결측/이상 비율을 잰다.
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
URL="https://blue-api.morpho.org/graphql"
Q="""query($s:Int!,$k:Int!){ markets(first:$s, skip:$k){ items{
  marketId lltv
  collateralAsset{symbol decimals priceUsd}
  loanAsset{symbol decimals priceUsd}
  state{ collateralAssets collateralAssetsUsd borrowAssets borrowAssetsUsd supplyAssetsUsd }
} pageInfo{countTotal} } }"""
S=requests.Session(); rows=[]; k=0; tot=None
while True:
    r=S.post(URL,json={"query":Q,"variables":{"s":200,"k":k}},timeout=120).json()
    if "errors" in r: print(str(r["errors"])[:300]); break
    m=r["data"]["markets"]; tot=m["pageInfo"]["countTotal"]
    for x in m["items"]:
        st=x.get("state") or {}; ca=x.get("collateralAsset") or {}
        dec=ca.get("decimals"); 
        nat=float(st.get("collateralAssets") or 0)/(10**(dec if dec else 18))
        rows.append(dict(mid=x["marketId"],coll=ca.get("symbol"),dec=dec,
            price=ca.get("priceUsd"),nat=nat,cusd=float(st.get("collateralAssetsUsd") or 0),
            busd=float(st.get("borrowAssetsUsd") or 0),susd=float(st.get("supplyAssetsUsd") or 0),
            lltv=float(x.get("lltv") or 0)/1e18))
    k+=200
    if k>=tot: break
D=pd.DataFrame(rows)
A=D[D.busd>1000].copy()          # 차입이 있는 마켓 = 리스크가 실재하는 곳
print("[ 차입 $1K 이상 마켓 %d개 (전체 %d) ]"%(len(A),len(D)))
print("\n[ ★ 담보 가격 결측·이상 ]")
A["nop"]=A.price.isna()
A["impl"]=A.cusd/A.nat.replace(0,np.nan)      # USD/수량 = 내재가격
print("   priceUsd 결측          **%d개 (%.1f%%)**"%(A.nop.sum(),A.nop.mean()*100))
print("   담보USD=0 인데 수량>0   **%d개 (%.1f%%)**"%(((A.cusd==0)&(A.nat>0)).sum(),((A.cusd==0)&(A.nat>0)).mean()*100))
cov=A.cusd/A.busd.replace(0,np.nan)
print("   담보USD < 차입USD      **%d개 (%.1f%%)**  ← LLTV<1 이면 구조적으로 불가능해야 한다"
      %((cov<1).sum(),(cov<1).mean()*100))
print("\n[ ★★ 가장 중요한 검사 — 담보가 차입을 못 덮는 %d개는 진짜인가 ]"%(cov<1).sum())
bad=A[cov<1]
print("   그 중 priceUsd 결측      %d개 (%.0f%%)"%(bad.price.isna().sum(),bad.price.isna().mean()*100))
print("   그 중 담보수량=0         %d개 (%.0f%%)  ← 이것만이 진짜 소진이다"%((bad.nat==0).sum(),(bad.nat==0).mean()*100))
print("\n[ 스테이블 담보의 내재가격 — $1 근처여야 한다 ]")
STB=("USR","RLP","wstUSR","deUSD","sdeUSD","xUSD","sNUSD","USDC","USDT","DAI","USDS","sUSDS")
for s in STB:
    t=A[A.coll==s]
    if not len(t): continue
    im=t.impl.replace([np.inf,-np.inf],np.nan).dropna()
    if not len(im): print("   %-8s 내재가격 계산 불가 (담보USD=0)"%s); continue
    print("   %-8s 내재가격 중앙 **$%.4f**  (n=%d)%s"%(s,im.median(),len(t),
          "  ← ⚠ $1 에서 크게 벗어남" if abs(im.median()-1)>0.3 and s not in("RLP",) else ""))
print("\n[ ★ 결론용 — USD 환산을 믿을 수 있는 구간 ]")
maj=A[A.coll.isin(["WETH","wstETH","cbBTC","WBTC","cbETH","weETH","USDC","USDT"])]
oth=A[~A.coll.isin(["WETH","wstETH","cbBTC","WBTC","cbETH","weETH","USDC","USDT"])]
for nm,t in (("주요자산 담보",maj),("그 외 담보",oth)):
    if not len(t): continue
    print("   %-12s n=%3d · priceUsd 결측 %5.1f%% · 담보USD=0 %5.1f%% · 담보<차입 %5.1f%%"
          %(nm,len(t),t.price.isna().mean()*100,((t.cusd==0)&(t.nat>0)).mean()*100,
            (t.cusd/t.busd.replace(0,np.nan)<1).mean()*100))
D.to_parquet(ROOT / "data"/"dataqual.parquet")
