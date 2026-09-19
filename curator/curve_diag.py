# -*- coding: utf-8 -*-
"""★ 곡선 직접 검사 — 38,928배 팽창이 이자로 설명되나. 안 되면 내 판정이 틀렸다."""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
URL="https://blue-api.morpho.org/graphql"
Q="""query($id:String!,$opt:TimeseriesOptions){ markets(first:1, where:{uniqueKey_in:[$id]}){ items{
  collateralAsset{symbol} loanAsset{symbol}
  historicalState{ supplyAssetsUsd(options:$opt){x y} borrowAssetsUsd(options:$opt){x y}
                   collateralAssetsUsd(options:$opt){x y} } } } }"""
I=pd.read_parquet("data/curator/principal2.parquet")
opt={"startTimestamp":1704067200,"endTimestamp":int(time.time()),"interval":"WEEK"}
S=requests.Session()
def ser(p):
    d={}
    for q in (p or []):
        if q.get("y") is None: continue
        d[pd.to_datetime(q["x"],unit="s")]=float(q["y"])
    return pd.Series(d).sort_index()
for sym_want in ("wstUSR/USDC","msY/USDC","PAXG/USDC","AVLT/USDC"):
    row=I[I.sym==sym_want]
    if not len(row): continue
    mid=row.iloc[0].mid
    r=S.post(URL,json={"query":Q,"variables":{"id":mid,"opt":opt}},timeout=120).json()
    if "errors" in r: print(r["errors"][:1]); continue
    it=r["data"]["markets"]["items"]
    if not it: continue
    h=it[0]["historicalState"]
    sp=ser(h.get("supplyAssetsUsd")); cu=ser(h.get("collateralAssetsUsd")); bw=ser(h.get("borrowAssetsUsd"))
    print("\n[ %s ]  주간 곡선 (공급 / 담보 / 차입, USD)"%sym_want)
    idx=sp.index
    show=list(idx[::max(len(idx)//16,1)])+[idx[-1]]
    for t in show:
        s=sp.get(t,np.nan); c=cu.get(t,np.nan); b=bw.get(t,np.nan)
        cov=c/b if (b==b and b>0) else np.nan
        print("   %s  공급 $%14s · 담보 $%14s · 차입 $%14s · 커버 %s"
              %(str(t)[:10],format(s,",.0f") if s==s else "-",
                format(c,",.0f") if c==c else "-",format(b,",.0f") if b==b else "-",
                ("%.3f"%cov) if cov==cov else "-"))
    print("   → 공급 최대 $%s (%s) · 현재 $%s"
          %(format(sp.max(),",.0f"),str(sp.idxmax())[:10],format(sp.iloc[-1],",.0f")))
    time.sleep(0.3)
