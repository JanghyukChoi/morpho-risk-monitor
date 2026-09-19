# -*- coding: utf-8 -*-
"""★★★ 실제 노출 — 볼트 포지션의 명목 팽창을 역산한다.

원리: 볼트의 청구권은 마켓 전체와 **같은 비율로** 팽창한다(지분 비례).
      볼트 실제원금 ≈ 볼트 명목공급 × (마켓 사망직전공급 / 마켓 현재명목공급)
      = 볼트 명목공급 / 팽창배율

검증된 전제 (3부·4부)
  · 가격·자릿수·토큰주소 정확 (V0~W4 통과)
  · 사망일이 실제 사건과 일치 (Stream 2025-11-06 · Resolv 2026-03-22)
  · 팽창은 100% 가동률 + 적응형 IRM 의 이자 복리로 설명된다
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"
P=pd.read_parquet(OUT/"principal2.parquet")[["mid","sym","dead","s_now","s_pre","infl","days_dead"]]
A=pd.read_parquet(OUT/"exposure.parquet")
B=A.merge(P,on="mid",how="inner").copy()
B["defl"]=np.where(B.infl.notna()&(B.infl>0), 1.0/B.infl, 1.0)
B["nominal"]=B.my_supply
B["real"]=B.my_supply*B.defl
print("[ 부실 마켓에 물린 볼트 배분 %d건 ]"%len(B))
print("   명목 합 $%s → **실제 합 $%s** (%.0f배 축소)"
      %(format(B.nominal.sum(),",.0f"),format(B.real.sum(),",.0f"),
        B.nominal.sum()/max(B.real.sum(),1)))
print("\n[ ★★★ 볼트별 실제 노출 (명목 대비) ]")
V=B.groupby(["vault","curator"],dropna=False).agg(
    tvl=("vault_tvl","first"),n=("mid","nunique"),
    nominal=("nominal","sum"),real=("real","sum")).reset_index()
V=V[V.real>100].sort_values("real",ascending=False)
print("   %-28s %-18s %13s %14s %13s"%("볼트","큐레이터","볼트TVL","명목노출","**실제노출**"))
for _,r in V.head(16).iterrows():
    print("   %-28s %-18s $%12s $%13s $%12s"
          %(str(r.vault)[:28],str(r.curator)[:18] if r.curator==r.curator else "(무명)",
            format(r.tvl,",.0f"),format(r.nominal,",.0f"),format(r.real,",.0f")))
print("\n[ ★ 이름 있는 큐레이터 — 최종 ]")
N=V[V.curator.notna()].groupby("curator").agg(
    tvl=("tvl","sum"),nominal=("nominal","sum"),real=("real","sum"),n=("n","sum"))
N["pct"]=N.real/N.tvl*100
for k,r in N.sort_values("real",ascending=False).iterrows():
    print("   %-24s 볼트TVL합 $%11s · 부실마켓 %d · 명목 $%11s → **실제 $%s (TVL의 %.2f%%)**"
          %(str(k)[:24],format(r.tvl,",.0f"),r.n,format(r.nominal,",.0f"),
            format(r.real,",.0f"),r.pct))
print("\n[ ★ 마켓별 — 어느 사고가 얼마를 남겼나 ]")
M=B.groupby("sym").agg(dead=("dead","first"),days=("days_dead","first"),
    nominal=("nominal","sum"),real=("real","sum"),nv=("vaddr","nunique")).sort_values("real",ascending=False)
for k,r in M.iterrows():
    print("   %-20s 사망 %s (%3.0f일) · 볼트 %2d · 명목 $%13s → **실제 $%11s**"
          %(str(k)[:20],str(r.dead)[:10],r.days,r.nv,format(r.nominal,",.0f"),format(r.real,",.0f")))
print("\n[ ⚠ 한계 — 이 숫자의 정직한 해석 ]")
print("   · '실제 노출'은 **사망 시점의 원금**이다. 일부는 이미 상각·회수됐을 수 있다")
print("   · 담보가 완전히 0 이 아닌 마켓(msY 커버 0.14)은 부분 회수가 가능하다")
print("   · 볼트 TVL 이 이미 상각됐다면 'TVL의 %' 분모가 줄어 비율이 과대해진다")
print("   · 팽창배율은 마켓 전체 기준이다. 볼트가 중간에 입출금했다면 오차가 생긴다")
V.to_parquet(OUT/"real_exposure.parquet")
