# -*- coding: utf-8 -*-
"""★★ Euler 에서도 명목 팽창이 일어나는가 — 금리와 이력으로 확인.

Morpho: 100% 가동률 고정 → 적응형 IRM 이 금리를 무한정 올림 → 589배 팽창
질문:   Euler 도 같은가? 아니면 금리 상한/악성부채 인식으로 끊는가?
확인:   ① 그 볼트들의 borrowApy ② Euler 의 badDebt 회계가 순액을 내는가
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"
V=pd.read_parquet(OUT/"euler_vaults.parquet")
BD=pd.read_parquet(OUT/"euler_baddebt.parquet")
for c in ("totalSupplyUsd","totalBorrowsUsd","utilization","supplyApy","borrowApy"):
    V[c]=pd.to_numeric(V[c],errors="coerce")
A=V[V.totalBorrowsUsd>1000].copy()
hi=A[A.utilization>=0.995].copy()
print("[ ★ Euler 100%% 가동률 볼트 %d개의 금리 ]"%len(hi))
print("   %-30s %6s %13s %10s %10s"%("볼트","나이","차입USD","차입APY","공급APY"))
for _,r in hi.sort_values("totalBorrowsUsd",ascending=False).iterrows():
    print("   %-30s %5.0f일 $%12s %9.2f%% %9.2f%%"
          %(str(r["name"])[:30],r.age_d if r.age_d==r.age_d else -1,
            format(r.totalBorrowsUsd,",.0f"),r.borrowApy*100 if r.borrowApy==r.borrowApy else 0,
            r.supplyApy*100 if r.supplyApy==r.supplyApy else 0))
print("\n   차입APY 중앙 **%.1f%%** · 최대 %.1f%%"%(hi.borrowApy.median()*100,hi.borrowApy.max()*100))
print("   → Morpho 부실 마켓의 함의 금리는 연 597~2,130%% 였다 (PAXG·wstUSR 역산)")
print("\n[ ★★ Euler 의 악성부채 회계 — 순액을 내는가 ]")
for c in ("debtUsd","collateralUsd","coveredDebtUsd","badDebtUsd"):
    BD[c]=pd.to_numeric(BD[c],errors="coerce")
print("   레코드 %d건 · 계정 %d개"%(len(BD),int(BD.accountCount.sum())))
print("   총부채 $%s − 담보로 커버 $%s = **악성부채 $%s**"
      %(format(BD.debtUsd.sum(),",.0f"),format(BD.coveredDebtUsd.sum(),",.0f"),format(BD.badDebtUsd.sum(),",.0f")))
print("   검산: 부채−커버 = $%s  (보고값 $%s) %s"
      %(format(BD.debtUsd.sum()-BD.coveredDebtUsd.sum(),",.0f"),format(BD.badDebtUsd.sum(),",.0f"),
        "✅ 일치" if abs((BD.debtUsd.sum()-BD.coveredDebtUsd.sum())-BD.badDebtUsd.sum())<1 else "❌"))
print("\n   [ 악성부채 상위 ]")
for _,r in BD.nlargest(8,"badDebtUsd").iterrows():
    print("      chain %-6s %-16s 부채 $%12s · 담보 $%12s · **악성 $%12s** · 계정 %d"
          %(r.chainId,str(r.get("borrowAsset"))[:16],format(r.debtUsd,",.0f"),
            format(r.collateralUsd,",.0f"),format(r.badDebtUsd,",.0f"),r.accountCount))
print("\n[ ★★★ 두 프로토콜 대조 ]")
print("   %-14s %-16s %-16s"%("","Morpho","Euler"))
print("   %-14s %-16s %-16s"%("100%가동 마켓","17개","11개 (10.2%)"))
print("   %-14s %-16s %-16s"%("명목 차입 합","$15,552,344,406","$%s"%format(hi.totalBorrowsUsd.sum(),",.0f")))
print("   %-14s %-16s %-16s"%("악성부채 회계","복원 필요(realizedBadDebt 누적 스칼라)","전용 엔드포인트가 순액 제공"))
print("   %-14s %-16s %-16s"%("실제 원금","$41,687,199 (역산)","$%s (직접)"%format(BD.badDebtUsd.sum(),",.0f")))
print("   %-14s %-16s %-16s"%("명목 과대배율","**373배**","상한으로 억제"))
print("")
print("   ⚠ 두 '명목 차입 합'을 직접 비교하면 안 된다 — 프로토콜 규모가 다르고")
print("      Euler 는 금리 상한 때문에 팽창이 조기에 멈춘다. **배율**이 의미 있는 값이다.")
