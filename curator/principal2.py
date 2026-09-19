# -*- coding: utf-8 -*-
"""★★★ 원금 복원 v2 — 사망 판정을 '담보USD>0' 이 아니라 **커버리지<1** 로 바꾼다.

v1 결함: 담보USD가 $1,000 만 넘어도 '생존'으로 봐서 wstUSR·msY·RLP·USR 의
         팽창 보정이 안 됐다. 그 결과 wstUSR 원금이 $191.8M 로 나왔는데
         **이 규모 손실이면 업계 최대 뉴스여야 한다.** 믿기 전에 곡선을 본다.
v2:      커버리지 = 담보USD / 차입USD. 마지막으로 >=1 이었던 날이 건전했던 날이다.
         그 시점의 공급액이 실제 원금이다.
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"
URL="https://blue-api.morpho.org/graphql"
Q="""query($id:String!,$opt:TimeseriesOptions){ markets(first:1, where:{uniqueKey_in:[$id]}){ items{
  marketId collateralAsset{symbol decimals} loanAsset{symbol decimals}
  historicalState{
    supplyAssetsUsd(options:$opt){x y}
    borrowAssetsUsd(options:$opt){x y}
    collateralAssetsUsd(options:$opt){x y} } } } }"""
def ser(pts):
    if not pts: return pd.Series(dtype=float)
    d={}
    for p in pts:
        y=p.get("y")
        if y is None: continue
        d[pd.to_datetime(p["x"],unit="s")]=float(y)
    return pd.Series(d).sort_index()
I=pd.read_parquet(OUT/"impaired_final.parquet")
opt={"startTimestamp":1704067200,"endTimestamp":int(time.time()),"interval":"DAY"}
S=requests.Session(); rows=[]
for i,mid in enumerate(I.mid.tolist()):
    x=None
    for a in range(4):
        try:
            r=S.post(URL,json={"query":Q,"variables":{"id":mid,"opt":opt}},timeout=120).json()
            if "errors" in r: break
            it=r["data"]["markets"]["items"]; x=it[0] if it else None; break
        except Exception: time.sleep(2+a*2)
    if not x: continue
    h=x.get("historicalState") or {}
    sp=ser(h.get("supplyAssetsUsd")); bw=ser(h.get("borrowAssetsUsd")); cu=ser(h.get("collateralAssetsUsd"))
    if not len(sp): continue
    sym="%s/%s"%((x.get("collateralAsset") or {}).get("symbol"),(x.get("loanAsset") or {}).get("symbol"))
    idx=sp.index.intersection(bw.index).intersection(cu.index)
    cov=(cu.reindex(idx)/bw.reindex(idx).replace(0,np.nan))
    healthy=cov[cov>=1.0]
    dead = healthy.index[-1] if len(healthy) else (idx[0] if len(idx) else None)
    pre = sp.loc[:dead].iloc[-1] if (dead is not None and len(sp.loc[:dead])) else np.nan
    # 사망 이전 구간의 최대 공급 — 원금 상한
    pmax = sp.loc[:dead].max() if (dead is not None and len(sp.loc[:dead])) else np.nan
    rows.append(dict(mid=mid,sym=sym,n=len(sp),dead=dead,
        s_now=sp.iloc[-1], s_pre=pre, s_premax=pmax, s_allmax=sp.max(),
        b_now=bw.iloc[-1] if len(bw) else np.nan,
        infl=(sp.iloc[-1]/pre) if (pre==pre and pre>0) else np.nan,
        days_dead=(pd.Timestamp.now()-dead).days if dead is not None else np.nan))
    time.sleep(0.15)
D=pd.DataFrame(rows).sort_values("s_pre",ascending=False)
print("[ ★ 커버리지<1 기준 사망 판정 후 원금 ]")
print("   %-20s %11s %5s %15s %15s %9s"%("마켓","사망일","경과일","현재(명목)","사망직전 원금","팽창"))
for _,r in D.iterrows():
    print("   %-20s %11s %5s %15s %15s %9s"
          %(str(r.sym)[:20],str(r.dead)[:10] if r.dead is not None else "-",
            ("%.0f"%r.days_dead) if r.days_dead==r.days_dead else "-",
            format(r.s_now,",.0f"),
            format(r.s_pre,",.0f") if r.s_pre==r.s_pre else "-",
            ("%.1fx"%r.infl) if r.infl==r.infl else "-"))
v=D[D.s_pre.notna()]
print("\n[ ★★ 결론 ]")
print("   명목 공급 합       $%s"%format(D.s_now.sum(),",.0f"))
print("   사망직전 원금 합    $%s  ← **실제 위험 원금**"%format(v.s_pre.sum(),",.0f"))
print("   사망전 최대 공급 합  $%s  (상한)"%format(v.s_premax.sum(),",.0f"))
if v.s_pre.sum()>0: print("   → 명목값은 실제를 **%.0f배** 과대평가"%(D.s_now.sum()/v.s_pre.sum()))
print("\n[ ⚠ 타당성 검사 — 개별 손실이 업계 뉴스가 될 규모인가 ]")
for _,r in v.nlargest(5,"s_pre").iterrows():
    print("   %-20s 원금 $%14s · 사망 %s (%.0f일 전)"
          %(str(r.sym)[:20],format(r.s_pre,",.0f"),str(r.dead)[:10],r.days_dead))
D.to_parquet(OUT/"principal2.parquet")
