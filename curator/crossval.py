# -*- coding: utf-8 -*-
"""★★ 교차 검증 — 두 독립 소스를 대조한다. 어느 한쪽도 믿지 않는다.

검증 순서 (아래가 위에 의존하므로 순서가 중요하다)
  V0 소수점 자릿수  — 틀리면 네이티브 수량이 틀리고 전부 무너진다
  V1 소스 간 일치도 — Morpho priceUsd vs DefiLlama price
  V2 스테이블 기준점 — $1 여야 하는 것이 $1 인가
  V3 커버리지      — 어느 쪽도 가격이 없는 자산은 얼마나 되나
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
M=pd.read_parquet(ROOT / "data"/"markets_priced.parquet")
A=M[M.m_busd>1000].copy()
print("="*76); print(" 교차 검증 — 차입 $1K+ 마켓 %d개"%len(A)); print("="*76)

print("\n[ V0 소수점 자릿수 검증 — 알려진 자산으로 확인 ]")
KNOWN={"USDC":6,"USDT":6,"WETH":18,"WBTC":8,"cbBTC":8,"DAI":18,"wstETH":18}
ok=bad=0
for s,d in KNOWN.items():
    t=M[M.coll==s].coll_dec.dropna()
    if not len(t): t=M[M.loan==s].loan_dec.dropna()
    if not len(t): print("   %-8s 데이터 없음"%s); continue
    got=int(t.mode().iloc[0]); m="✅" if got==d else "❌"
    ok+= got==d; bad+= got!=d
    print("   %-8s 기대 %2d · 실제 %2d  %s"%(s,d,got,m))
print("   → %d/%d 일치. %s"%(ok,ok+bad,"자릿수 신뢰 가능" if bad==0 else "**자릿수 오류 존재 — 하류 전부 의심**"))

print("\n[ V1 소스 간 일치도 — 둘 다 가격이 있는 담보 ]")
B=A[(A.m_cprice.notna())&(A.c_price.notna())&(A.c_price>0)].copy()
B["ratio"]=B.m_cprice.astype(float)/B.c_price
print("   대상 %d개 (차입있는 마켓의 %.0f%%)"%(len(B),len(B)/len(A)*100))
for lo,hi,l in ((0.95,1.05,"±5% 이내 일치"),(0.8,1.25,"±25% 이내"),(0.5,2.0,"2배 이내"),(0,1e9,"전체")):
    m=(B.ratio>=lo)&(B.ratio<=hi); print("   %-16s %3d개 (%5.1f%%)"%(l,m.sum(),m.mean()*100))
print("\n   [ 불일치 상위 — 어느 쪽이 틀렸나 ]")
D=B[(B.ratio<0.8)|(B.ratio>1.25)].copy()
D["gap"]=(D.ratio-1).abs()
for _,r in D.nlargest(12,"gap").iterrows():
    print("      %-16s Morpho $%-12s vs Llama $%-12s (%.2fx · conf %.2f)"
          %(str(r.coll)[:16],("%.4f"%float(r.m_cprice))[:12],("%.4f"%r.c_price)[:12],r.ratio,
            r.c_conf if r.c_conf==r.c_conf else 0))

print("\n[ V2 스테이블 기준점 — $1 여야 하는 것 ]")
STB=("USDC","USDT","DAI","USDS","USR","RLP","wstUSR","deUSD","sdeUSD","xUSD","sNUSD","sUSDS","USD0")
print("   %-10s %14s %14s %8s"%("심볼","Morpho","DefiLlama","conf"))
for s in STB:
    t=M[M.coll==s]
    if not len(t): t=M[M.loan==s].rename(columns={"m_lprice":"m_cprice","l_price":"c_price","l_conf":"c_conf"})
    if not len(t): continue
    mp=pd.to_numeric(t.m_cprice,errors="coerce").median()
    lp=pd.to_numeric(t.c_price,errors="coerce").median()
    cf=pd.to_numeric(t.c_conf,errors="coerce").median()
    f=lambda v: "결측" if v!=v else "$%.4f"%v
    mk=""
    if lp==lp and abs(lp-1)<0.1 and mp==mp and abs(mp-1)>0.3: mk="  ← ★Morpho 가 틀렸다"
    elif lp==lp and abs(lp-1)>0.3: mk="  ← 실제 디페그 가능"
    print("   %-10s %14s %14s %8s%s"%(s,f(mp),f(lp),("%.2f"%cf) if cf==cf else "-",mk))

print("\n[ V3 커버리지 — 어느 쪽도 가격이 없는 담보 ]")
A["has_m"]=A.m_cprice.notna(); A["has_l"]=A.c_price.notna()&(A.c_price>0)
print("   Morpho만 %3d · Llama만 %3d · 둘다 %3d · **둘다 없음 %3d (%.1f%%)**"
      %((A.has_m&~A.has_l).sum(),(~A.has_m&A.has_l).sum(),(A.has_m&A.has_l).sum(),
        (~A.has_m&~A.has_l).sum(),(~A.has_m&~A.has_l).mean()*100))
print("   합집합 커버리지 **%.1f%%** (Morpho 단독 %.1f%% · Llama 단독 %.1f%%)"
      %((A.has_m|A.has_l).mean()*100,A.has_m.mean()*100,A.has_l.mean()*100))
n=A[~A.has_m&~A.has_l]
print("\n   [ 가격 불가 담보 — 그 자체가 위험 신호 ]")
for k,g in n.groupby("coll"):
    if g.m_busd.sum()<1e5: continue
    print("      %-24s 마켓 %2d · Morpho표기 차입 $%s"%(str(k)[:24],len(g),format(g.m_busd.sum(),",.0f")))
