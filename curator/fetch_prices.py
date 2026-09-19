# -*- coding: utf-8 -*-
"""★ 독립 가격 수집 — Morpho 의 USD 환산을 믿지 않는다.

2부에서 확인: Morpho API 의 priceUsd 는 이색 담보에서 결측/붕괴한다(17.7%).
그 위에 세운 손실 계산은 전부 무의미하다. 가격을 **독립 소스**에서 직접 받는다.

DefiLlama coins API 는 confidence 를 같이 준다 — 가격을 믿을지 말지가 데이터로 온다.
DefiLlama 도 못 매기는 자산은 **진짜로 가격을 못 매기는 자산**이고, 그 자체가 위험 신호다.
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"; OUT.mkdir(parents=True,exist_ok=True)
MURL="https://blue-api.morpho.org/graphql"
CHAIN={1:"ethereum",10:"optimism",56:"bsc",130:"unichain",137:"polygon",143:"monad",
       146:"sonic",480:"wc",747474:"katana",988:"movement",999:"hyperliquid",
       8453:"base",42161:"arbitrum",43114:"avax",4217:"unknown4217",
       4663:"unknown4663",5042:"unknown5042",1868:"soneium",57073:"ink"}
Q="""query($s:Int!,$k:Int!){ markets(first:$s, skip:$k){ items{
  marketId lltv chain{id}
  collateralAsset{symbol address decimals priceUsd}
  loanAsset{symbol address decimals priceUsd}
  state{ collateralAssets collateralAssetsUsd borrowAssets borrowAssetsUsd supplyAssets supplyAssetsUsd }
} pageInfo{countTotal} } }"""

def markets():
    S=requests.Session(); rows=[]; k=0; tot=None
    while True:
        r=S.post(MURL,json={"query":Q,"variables":{"s":200,"k":k}},timeout=120).json()
        if "errors" in r: print(str(r["errors"])[:300]); break
        m=r["data"]["markets"]; tot=m["pageInfo"]["countTotal"]
        for x in m["items"]:
            st=x.get("state") or {}; ca=x.get("collateralAsset") or {}; la=x.get("loanAsset") or {}
            cd=ca.get("decimals"); ld=la.get("decimals")
            rows.append(dict(mid=x["marketId"],chain=(x.get("chain") or {}).get("id"),
                lltv=float(x.get("lltv") or 0)/1e18,
                coll=ca.get("symbol"),coll_addr=(ca.get("address") or "").lower(),coll_dec=cd,
                coll_nat=float(st.get("collateralAssets") or 0)/(10**(cd if cd else 18)),
                m_cusd=float(st.get("collateralAssetsUsd") or 0), m_cprice=ca.get("priceUsd"),
                loan=la.get("symbol"),loan_addr=(la.get("address") or "").lower(),loan_dec=ld,
                loan_nat=float(st.get("borrowAssets") or 0)/(10**(ld if ld else 18)),
                m_busd=float(st.get("borrowAssetsUsd") or 0), m_lprice=la.get("priceUsd"),
                sup_nat=float(st.get("supplyAssets") or 0)/(10**(ld if ld else 18)),
                m_susd=float(st.get("supplyAssetsUsd") or 0)))
        k+=200
        if k>=tot: break
    return pd.DataFrame(rows)

def llama_prices(keys, batch=80):
    """DefiLlama coins — price + confidence. 429 회피를 위해 순차 + 지연."""
    out={}
    S=requests.Session()
    ks=[k for k in keys if k and ":" in k and len(k.split(":")[1])>10]
    for i in range(0,len(ks),batch):
        ch=ks[i:i+batch]
        for a in range(4):
            try:
                r=S.get("https://coins.llama.fi/prices/current/"+",".join(ch),timeout=60)
                if r.status_code==429: time.sleep(3+a*4); continue
                out.update(r.json().get("coins") or {}); break
            except Exception:
                if a==3: pass
                time.sleep(2)
        if i//batch%10==0: print("   가격 %d/%d"%(i,len(ks)),flush=True)
        time.sleep(0.25)
    return out

if __name__=="__main__":
    t0=time.time(); M=markets()
    print("■ 마켓 %d · 체인 %d"%(len(M),M.chain.nunique()))
    M["ckey"]=M.apply(lambda r: "%s:%s"%(CHAIN.get(r.chain,"x"),r.coll_addr) if r.coll_addr else None,axis=1)
    M["lkey"]=M.apply(lambda r: "%s:%s"%(CHAIN.get(r.chain,"x"),r.loan_addr) if r.loan_addr else None,axis=1)
    need=sorted(set(M.ckey.dropna())|set(M.lkey.dropna()))
    print("■ 고유 자산 %d개 가격 조회"%len(need))
    P=llama_prices(need)
    pr=pd.DataFrame([dict(key=k,ll_price=v.get("price"),ll_conf=v.get("confidence"),
                          ll_sym=v.get("symbol"),ll_ts=v.get("timestamp")) for k,v in P.items()])
    pr.to_parquet(OUT/"prices.parquet")
    print("■ 가격 확보 %d/%d (%.1f%%) · %.0fs"%(len(pr),len(need),len(pr)/len(need)*100,time.time()-t0))
    M=M.merge(pr.rename(columns={"key":"ckey","ll_price":"c_price","ll_conf":"c_conf","ll_sym":"c_sym"})
              [["ckey","c_price","c_conf","c_sym"]],on="ckey",how="left")
    M=M.merge(pr.rename(columns={"key":"lkey","ll_price":"l_price","ll_conf":"l_conf"})
              [["lkey","l_price","l_conf"]],on="lkey",how="left")
    M.to_parquet(OUT/"markets_priced.parquet")
    print("■ 저장 markets_priced.parquet %s"%(M.shape,))
    A=M[M.m_busd>1000]
    print("\n[ 차입 $1K+ 마켓 %d개 ]"%len(A))
    print("   Morpho 가격 결측 %5.1f%%  →  DefiLlama 가격 결측 **%5.1f%%**"
          %(A.m_cprice.isna().mean()*100, A.c_price.isna().mean()*100))
    print("   DefiLlama conf>=0.9 인 담보 %.1f%%"%((A.c_conf>=0.9).mean()*100))
