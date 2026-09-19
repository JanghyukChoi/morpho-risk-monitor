# -*- coding: utf-8 -*-
"""Phase 0 — Morpho 마켓 전수 + 주간 차입 이력 수집.

사전등록 `alpha/prereg/curator_risk.md` §9 의 설계를 위한 데이터.
  · 불변 5개 파라미터(담보·대출자산·오라클·IRM·LLTV) — 생성 시 고정, 결과로 오염 불가
  · 주간 차입 이력 → **나이 30일 시점 차입규모**(대상집합 정의)와 최대 차입
  · 라벨: realizedBadDebt (누적 스칼라. 시점은 API 에 없다 — §9.1)

⚠ historicalState 에 badDebt 계열이 없어 시점 라벨은 구성 불가능하다.
   그래서 '언제'가 아니라 '터질 마켓인가'만 푼다.
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"; OUT.mkdir(parents=True,exist_ok=True)
URL="https://blue-api.morpho.org/graphql"
Q="""query($s:Int!,$k:Int!,$opt:TimeseriesOptions){ markets(first:$s, skip:$k){ items{
  marketId lltv creationTimestamp irmAddress
  chain{id}
  loanAsset{symbol address decimals}
  collateralAsset{symbol address decimals}
  oracle{ type address }
  warnings{ type level }
  badDebt{usd} realizedBadDebt{usd}
  state{ supplyAssetsUsd borrowAssetsUsd utilization netSupplyApy collateralAssetsUsd }
  historicalState{ borrowAssetsUsd(options:$opt){x y} }
} pageInfo{countTotal} } }"""

def _f(v):
    try: return float(v)
    except (TypeError, ValueError): return np.nan

def series_feats(pts, created_ts):
    """나이 30일 시점의 값 + 최대값. 결과 오염을 피하려 **시점을 고정**한다."""
    if not pts: return dict(b30=np.nan, bmax=np.nan, bfirst_ts=np.nan, nobs=0)
    xy=[(p["x"], _f(p.get("y"))) for p in pts]
    xy=[(x,y) for x,y in xy if y==y]
    if not xy: return dict(b30=np.nan, bmax=np.nan, bfirst_ts=np.nan, nobs=0)
    t30=(created_ts or xy[0][0])+30*86400
    le=[y for x,y in xy if x<=t30]
    nz=[x for x,y in xy if y>0]
    return dict(b30=(le[-1] if le else xy[0][1]), bmax=max(y for _,y in xy),
                bfirst_ts=(min(nz) if nz else np.nan), nobs=len(xy))

def run(page=35, start_ts=1690000000):
    opt={"startTimestamp":start_ts,"endTimestamp":int(time.time()),"interval":"WEEK"}
    S=requests.Session(); rows=[]; k=0; tot=None; t0=time.time()
    while True:
        for attempt in range(4):
            try:
                r=S.post(URL,json={"query":Q,"variables":{"s":page,"k":k,"opt":opt}},timeout=120).json()
                if "errors" in r: print(str(r["errors"])[:300]); return None
                break
            except Exception as e:
                if attempt==3: raise
                time.sleep(2+attempt*3)
        m=r["data"]["markets"]; tot=m["pageInfo"]["countTotal"]
        for x in m["items"]:
            st=x.get("state") or {}; o=x.get("oracle") or {}
            hs=x.get("historicalState") or {}
            ct=x.get("creationTimestamp")
            bf=series_feats(hs.get("borrowAssetsUsd"), ct)
            la=x.get("loanAsset") or {}; ca=x.get("collateralAsset") or {}
            rows.append(dict(
                mid=x["marketId"], chain=(x.get("chain") or {}).get("id"),
                created=ct, lltv=_f(x.get("lltv"))/1e18, irm=x.get("irmAddress"),
                loan=la.get("symbol"), loan_addr=la.get("address"),
                coll=ca.get("symbol"), coll_addr=ca.get("address"),
                otype=o.get("type"), oaddr=o.get("address"),
                warn=";".join("%s:%s"%(w.get("type"),w.get("level")) for w in (x.get("warnings") or [])),
                bd=_f((x.get("badDebt") or {}).get("usd")), rbd=_f((x.get("realizedBadDebt") or {}).get("usd")),
                supply=_f(st.get("supplyAssetsUsd")), borrow=_f(st.get("borrowAssetsUsd")),
                util=_f(st.get("utilization")), apy=_f(st.get("netSupplyApy")),
                b30=bf["b30"], bmax=bf["bmax"], bfirst=bf["bfirst_ts"], nobs=bf["nobs"],
                ))
        k+=page
        if k%1050==0: print("   %d/%d  %.0fs"%(k,tot,time.time()-t0),flush=True)
        if k>=tot: break
    D=pd.DataFrame(rows)
    D["age_d"]=(pd.Timestamp.now()-pd.to_datetime(D.created,unit="s",errors="coerce")).dt.days
    D.to_parquet(OUT/"markets.parquet")
    print("■ 완료 %s → %s (%.0fs)"%(D.shape,OUT/'markets.parquet',time.time()-t0))
    return D

if __name__=="__main__":
    D=run()
    print("\n[ 라벨 ] 실현 악성부채>0 = %d/%d (%.2f%%)"%((D.rbd>0).sum(),len(D),(D.rbd>0).mean()*100))
    print("[ 이력 ] 차입 시계열 있는 마켓 %d개 · 나이30일 차입 관측 %d개"%((D.nobs>0).sum(),D.b30.notna().sum()))
    print("[ 대상집합 후보 ] 최대차입 $10K+ = %d개 · 그 중 라벨 %d개 (%.2f%%)"
          %((D.bmax>1e4).sum(),((D.bmax>1e4)&(D.rbd>0)).sum(),
            ((D.bmax>1e4)&(D.rbd>0)).sum()/max((D.bmax>1e4).sum(),1)*100))
