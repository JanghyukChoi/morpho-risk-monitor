# -*- coding: utf-8 -*-
"""★ 노출 지도 — "담보 X 가 d% 무너지면 볼트 Y 가 얼마를 잃는가".

예측이 아니라 **회계**다. 가정은 딱 두 개이고 둘 다 명시한다:
  A1 갭다운 가정 — 청산이 개입하지 못하고 가격이 즉시 (1-d) 로 간다
     → 악성부채 = max(0, 차입 - 담보×(1-d))   [보수적 최악]
  A2 안분 가정 — 마켓의 악성부채는 공급자에게 **공급 비중대로** 배분된다
     → Morpho 의 손실 배분 규칙과 일치 (share 기반)
손실은 마켓 공급액으로 상한된다(더 잃을 수 없다).
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
A=pd.read_parquet(ROOT / "data"/"alloc.parquet")
A=A[A.mkt_supply>0].copy()
A["share"]=(A.my_supply/A.mkt_supply).clip(0,1)

def bad_debt(d):
    """담보 d% 하락 시 마켓별 악성부채 (A1)."""
    coll_after=A.mkt_coll*(1-d)
    return np.minimum(np.maximum(A.mkt_borrow-coll_after,0.0), A.mkt_supply)

SHOCKS=[0.25,0.50,0.75,1.00]
print("="*78)
print(" 노출 지도 — Morpho 볼트 855개 · 마켓 1,307개 · 담보 455종 · 배분 $2.00B")
print("="*78)
print("\n[ ★ 담보별 시스템 노출 — 그 담보가 100% 무너질 때 전체 볼트 손실 ]")
A["bd100"]=bad_debt(1.00); A["loss100"]=A.bd100*A.share
g=A.groupby("coll").agg(mkts=("mid","nunique"),vaults=("vaddr","nunique"),
    supplied=("my_supply","sum"),loss=("loss100","sum")).sort_values("loss",ascending=False)
print("   %-14s %5s %6s %14s %14s %7s"%("담보","마켓","볼트","배분액","최대손실","손실률"))
for k,r in g.head(15).iterrows():
    print("   %-14s %5d %6d $%13s $%13s %6.1f%%"
          %(str(k)[:14],r.mkts,r.vaults,format(r.supplied,",.0f"),format(r.loss,",.0f"),
            r.loss/max(r.supplied,1)*100))
tot=A.my_supply.sum()
print("\n   상위 5 담보가 전체 배분의 %.1f%% · 전체 최대손실의 %.1f%%"
      %(g.head(5).supplied.sum()/tot*100, g.head(5).loss.sum()/max(g.loss.sum(),1)*100))

print("\n[ ★ 충격 크기별 전체 손실 (전 담보 동시가 아니라 각각 독립) ]")
for d in SHOCKS:
    bd=bad_debt(d); l=(bd*A.share)
    n=(l>0).sum()
    print("   담보 -%3.0f%% → 손실 발생 배분 %4d건 · 총손실 $%13s (배분액의 %5.2f%%)"
          %(d*100,n,format(l.sum(),",.0f"),l.sum()/tot*100))

print("\n[ ★★ 큐레이터별 취약도 — 담보 1종이 100% 무너질 때 최대 단일 손실 ]")
rows=[]
for cur,s in A[A.curator.notna()].groupby("curator"):
    tvl=s.groupby("vaddr").vault_tvl.first().sum()
    by=s.groupby("coll").apply(lambda x:(x.bd100*x.share).sum(),include_groups=False)
    if not len(by): continue
    worst=by.idxmax(); wl=by.max()
    rows.append(dict(cur=cur,tvl=tvl,nv=s.vaddr.nunique(),worst=worst,wl=wl,
                     pct=wl/max(tvl,1)*100, total=(s.bd100*s.share).sum()))
C=pd.DataFrame(rows).sort_values("pct",ascending=False)
print("   %-24s %5s %13s %-12s %13s %7s"%("큐레이터","볼트","TVL","최악담보","최대손실","TVL대비"))
for _,r in C.iterrows():
    print("   %-24s %5d $%12s %-12s $%12s **%5.1f%%**"
          %(str(r.cur)[:24],r.nv,format(r.tvl,",.0f"),str(r.worst)[:12],format(r.wl,",.0f"),r.pct))

print("\n[ ★ 전염 지도 — 담보 하나를 여러 큐레이터가 공유하는가 ]")
sh=A[A.curator.notna()].groupby("coll").agg(curs=("curator","nunique"),loss=("loss100","sum"))
sh=sh[sh.curs>=2].sort_values("loss",ascending=False)
print("   2개 이상 큐레이터가 물린 담보 %d종"%len(sh))
for k,r in sh.head(10).iterrows():
    who=", ".join(sorted(A[(A.coll==k)&A.curator.notna()].curator.unique())[:5])
    print("   %-12s 큐레이터 %d명 · 공동손실 $%12s · %s"%(str(k)[:12],r.curs,format(r.loss,",.0f"),who[:60]))
print("\n[ 검산 ]")
print("   배분 총액 $%s · 담보 100%% 붕괴 가정 총손실 $%s (%.1f%%)"
      %(format(tot,",.0f"),format(A.loss100.sum(),",.0f"),A.loss100.sum()/tot*100))
print("   ※ 전 담보 동시 붕괴는 비현실적이다. 위 담보별 수치는 **각각 독립 시나리오**다")
A.to_parquet(ROOT / "data"/"exposure.parquet")
