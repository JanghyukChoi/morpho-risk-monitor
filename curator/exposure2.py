# -*- coding: utf-8 -*-
"""노출 지도 v2 — 자명한 결과를 걷어내고 **이색 담보 집중도**를 잰다.

v1 의 문제: cbBTC·WETH 가 상위인 건 돈이 거기 많아서다. cbBTC 100% 붕괴는
            시나리오로 무의미하다. '큰 마켓은 노출이 크다'는 동어반복이다.
v2 의 축:   Stream 패턴 = **소수만 쓰는 이색 담보**. 이건 실제로 0 이 된다.
            확립도를 **손 분류가 아니라 객관 지표**로 잰다 — 몇 명의 독립 큐레이터가 쓰는가.
검증:       xUSD(Stream Finance 자산)가 데이터에 남아 있다. 지도가 이걸 잡는지 본다.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
A=pd.read_parquet(ROOT / "data"/"exposure.parquet")

# ── 담보 확립도: 몇 명의 독립 큐레이터가 담보로 채택했는가 (객관)
est=A[A.curator.notna()].groupby("coll").curator.nunique()
A["coll_ncur"]=A.coll.map(est).fillna(0)
A["exotic"]=(A.coll_ncur<=2).astype(int)      # 큐레이터 2명 이하가 쓰는 담보 = 이색
print("[ 담보 확립도 분포 — 독립 큐레이터 채택 수 ]")
d=A.groupby("coll").agg(ncur=("coll_ncur","first"),sup=("my_supply","sum"))
for lo,hi,l in ((0,0,"0명(큐레이터 없음)"),(1,1,"1명"),(2,2,"2명"),(3,5,"3~5명"),(6,99,"6명 이상")):
    m=(d.ncur>=lo)&(d.ncur<=hi)
    print("   %-18s 담보 %3d종 · 배분 $%13s (%5.1f%%)"%(l,m.sum(),format(d[m].sup.sum(),",.0f"),
          d[m].sup.sum()/d.sup.sum()*100))

print("\n[ ★★ 큐레이터별 '이색 담보' 노출 — Stream 패턴 직격 ]")
print("   이색 = 독립 큐레이터 2명 이하가 담보로 쓰는 자산")
rows=[]
for cur,s in A[A.curator.notna()].groupby("curator"):
    tvl=s.groupby("vaddr").vault_tvl.first().sum()
    ex=s[s.exotic==1].copy()
    ex["l"]=ex.bd100*ex.share
    exloss=float(ex.l.sum()) if len(ex) else 0.0
    top="-"
    if len(ex):
        byc=ex.groupby("coll",dropna=True)["l"].sum()
        if len(byc) and byc.max()>0: top=str(byc.idxmax())
    rows.append(dict(cur=cur,tvl=tvl,nex=ex.coll.nunique(),ex_sup=float(ex.my_supply.sum()),
                     exloss=exloss,pct=exloss/max(tvl,1)*100,top=top))
E=pd.DataFrame(rows).sort_values("pct",ascending=False)
print("   %-24s %13s %5s %13s %8s %-14s"%("큐레이터","TVL","이색종","이색손실","TVL대비","최대이색담보"))
for _,r in E.iterrows():
    if r.tvl<1000 and r.exloss<1000: continue
    print("   %-24s $%12s %5d $%12s **%6.1f%%** %-14s"
          %(str(r.cur)[:24],format(r.tvl,",.0f"),r.nex,format(r.exloss,",.0f"),r.pct,str(r.top)[:14]))

print("\n[ ★★★ 검증 — 실제로 터진 자산을 지도가 잡는가 ]")
for sym in ("xUSD","deUSD","sdeUSD","USDX","sUSDX"):
    s=A[A.coll.astype(str).str.contains(sym,case=False,na=False)]
    if not len(s): print("   %-8s 데이터에 없음"%sym); continue
    who=sorted(s[s.curator.notna()].curator.unique())
    print("   %-8s 마켓 %d · 볼트 %d · 배분 $%s · 최대손실 $%s · 큐레이터 %s"
          %(sym,s.mid.nunique(),s.vaddr.nunique(),format(s.my_supply.sum(),",.0f"),
            format((s.bd100*s.share).sum(),",.0f"), ", ".join(who) if who else "(무명)"))
print("\n   → Stream 사태 피해 큐레이터로 보도된 곳: MEV Capital · Re7 Labs · TelosC")
for c in ("MEV Capital","RE7 Labs"):
    s=A[A.curator==c]
    if not len(s): continue
    ex=s[s.exotic==1]
    print("   %-14s 현재 이색담보 %d종 · 이색배분 $%s (TVL 대비 %.1f%%)"
          %(c,ex.coll.nunique(),format(ex.my_supply.sum(),",.0f"),
            ex.my_supply.sum()/max(s.groupby('vaddr').vault_tvl.first().sum(),1)*100))

print("\n[ ★ 이색 담보 중 배분액 상위 — 지금 감시할 목록 ]")
x=A[A.exotic==1].groupby("coll").agg(cur=("curator","nunique"),v=("vaddr","nunique"),
    sup=("my_supply","sum"),loss=("loss100","sum")).sort_values("sup",ascending=False)
for k,r in x.head(15).iterrows():
    who=A[(A.coll==k)&A.curator.notna()].curator.unique()
    print("   %-18s 볼트%3d · 배분 $%11s · 최대손실 $%11s · %s"
          %(str(k)[:18],r.v,format(r.sup,",.0f"),format(r.loss,",.0f"),
            ", ".join(sorted(who))[:38] if len(who) else "(무명 큐레이터)"))
