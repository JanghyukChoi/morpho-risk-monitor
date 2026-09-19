# -*- coding: utf-8 -*-
"""볼트 → 마켓 배분 전수 수집. 노출 지도의 입력.

★ 이건 예측이 아니라 **회계**다. "담보 X 가 무너지면 볼트 Y 가 얼마를 잃는가"는
   가정 없이 계산된다. 모델이 기각된 이유(노출 인공물)와 무관하게 성립한다.
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"; OUT.mkdir(parents=True,exist_ok=True)
URL="https://blue-api.morpho.org/graphql"
Q="""query($s:Int!,$k:Int!){ vaults(first:$s, skip:$k){ items{
  name address chain{id}
  state{ totalAssetsUsd fee curators{name}
    allocation{ supplyAssetsUsd supplyCapUsd
      market{ marketId lltv
        collateralAsset{symbol address} loanAsset{symbol}
        state{ collateralAssetsUsd borrowAssetsUsd supplyAssetsUsd } } } } }
  pageInfo{countTotal} } }"""
def _f(v):
    try: return float(v)
    except (TypeError,ValueError): return 0.0
def run(page=25):
    S=requests.Session(); rows=[]; k=0; tot=None; t0=time.time()
    while True:
        for a in range(4):
            try:
                r=S.post(URL,json={"query":Q,"variables":{"s":page,"k":k}},timeout=120).json()
                if "errors" in r: print(str(r["errors"])[:300]); return None
                break
            except Exception:
                if a==3: raise
                time.sleep(2+a*3)
        v=r["data"]["vaults"]; tot=v["pageInfo"]["countTotal"]
        for x in v["items"]:
            st=x.get("state") or {}
            curs=[c["name"] for c in (st.get("curators") or []) if c.get("name")]
            vt=_f(st.get("totalAssetsUsd"))
            for al in (st.get("allocation") or []):
                m=al.get("market") or {}; ms=m.get("state") or {}
                ca=m.get("collateralAsset") or {}
                rows.append(dict(
                    vault=x.get("name"), vaddr=x.get("address"), chain=(x.get("chain") or {}).get("id"),
                    curator=curs[0] if curs else None, vault_tvl=vt, vault_fee=_f(st.get("fee"))*100,
                    mid=m.get("marketId"), lltv=_f(m.get("lltv"))/1e18,
                    coll=ca.get("symbol"), coll_addr=ca.get("address"),
                    loan=(m.get("loanAsset") or {}).get("symbol"),
                    my_supply=_f(al.get("supplyAssetsUsd")), cap=_f(al.get("supplyCapUsd")),
                    mkt_coll=_f(ms.get("collateralAssetsUsd")), mkt_borrow=_f(ms.get("borrowAssetsUsd")),
                    mkt_supply=_f(ms.get("supplyAssetsUsd"))))
        k+=page
        if k%500==0: print("   %d/%d  %.0fs  행 %d"%(k,tot,time.time()-t0,len(rows)),flush=True)
        if k>=tot: break
    A=pd.DataFrame(rows); A.to_parquet(OUT/"alloc.parquet")
    print("■ 완료 %s → alloc.parquet (%.0fs)"%(A.shape,time.time()-t0))
    return A
if __name__=="__main__":
    A=run()
    print("\n볼트 %d · 마켓 %d · 담보종류 %d · 큐레이터 %d"
          %(A.vault.nunique(),A.mid.nunique(),A.coll.nunique(),A.curator.nunique()))
    print("배분 총액 $%s · 볼트 TVL 합 $%s"
          %(format(A.my_supply.sum(),",.0f"),format(A.groupby('vaddr').vault_tvl.first().sum(),",.0f")))
