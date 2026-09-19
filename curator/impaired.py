# -*- coding: utf-8 -*-
"""★★ 손상 마켓 탐지 — 예측이 아니라 **현재 사실**.

발견: 담보 USD 가치가 0 인데 차입이 남은 마켓이 존재한다.
      담보가 가격 피드에서 사라졌거나(상폐·디페그) 실제로 소진된 상태다.
      **어느 쪽이든 그 마켓에 공급한 볼트는 지금 회수 불가 위험을 안고 있다.**
      xUSD(Stream)·deUSD(Elixir) 가 정확히 이 형태로 잡힌다.

데이터 주의 (검증 완료)
  · 담보 심볼 NULL = 유휴 마켓. 차입 0. 손실 대상 아님 → 제외
  · 마켓 지표는 배분 행마다 반복된다 → **마켓 단위로 집계**해야 한다
  · 차입액에 이상치가 있다(sdeUSD $6.0B) → 별도 표시
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
A=pd.read_parquet(ROOT / "data"/"exposure.parquet")
A=A[A.coll.notna()].copy()                      # 유휴 마켓 제외
A["share"]=(A.my_supply/A.mkt_supply.replace(0,np.nan)).clip(0,1).fillna(0)

M=A.groupby("mid").agg(coll=("coll","first"),loan=("loan","first"),lltv=("lltv","first"),
    mcoll=("mkt_coll","first"),mborrow=("mkt_borrow","first"),msupply=("mkt_supply","first"),
    nv=("vaddr","nunique")).reset_index()
print("[ 마켓 단위 집계 — %d개 (배분 행 %d개에서 중복 제거) ]"%(len(M),len(A)))
print("   총 차입 $%s · 총 공급 $%s · 총 담보 $%s"
      %(format(M.mborrow.sum(),",.0f"),format(M.msupply.sum(),",.0f"),format(M.mcoll.sum(),",.0f")))

# ── 손상 정의: 담보가 차입을 못 덮는다
M["cover"]=M.mcoll/M.mborrow.replace(0,np.nan)
IMP=M[(M.mborrow>1000)&((M.mcoll==0)|(M.cover<1.0))].copy()
IMP["shortfall"]=(IMP.mborrow-IMP.mcoll).clip(lower=0)
IMP=IMP.sort_values("shortfall",ascending=False)
print("\n[ ★ 손상 마켓 — 담보가 차입을 못 덮는 마켓 ]")
print("   해당 %d개 / 차입있는 마켓 %d개 (%.1f%%)"
      %(len(IMP),(M.mborrow>1000).sum(),len(IMP)/max((M.mborrow>1000).sum(),1)*100))
print("   %-14s %-10s %6s %14s %14s %8s %4s"%("담보","대출","LLTV","차입","담보가치","부족분","볼트"))
for _,r in IMP.head(18).iterrows():
    print("   %-14s %-10s %6.2f $%13s $%13s $%7s %4d"
          %(str(r.coll)[:14],str(r.loan)[:10],r.lltv,format(r.mborrow,",.0f"),
            format(r.mcoll,",.0f"),format(r.shortfall,",.0f"),r.nv))

print("\n[ ★★ 볼트별 손상 노출 — 지금 물려 있는 금액 ]")
B=A.merge(IMP[["mid","shortfall","cover"]],on="mid",how="inner")
B["at_risk"]=B.shortfall*B.share
V=B.groupby(["vault","curator"],dropna=False).agg(
    tvl=("vault_tvl","first"),n=("mid","nunique"),
    supplied=("my_supply","sum"),risk=("at_risk","sum")).reset_index()
V["pct"]=V.risk/V.tvl.replace(0,np.nan)*100
V=V[V.risk>1000].sort_values("risk",ascending=False)
print("   손상 마켓에 물린 볼트 %d개"%len(V))
print("   %-28s %-18s %13s %5s %13s %7s"%("볼트","큐레이터","TVL","마켓","위험액","TVL대비"))
for _,r in V.head(18).iterrows():
    print("   %-28s %-18s $%12s %5d $%12s %6.1f%%"
          %(str(r.vault)[:28],str(r.curator)[:18],format(r.tvl,",.0f"),r.n,
            format(r.risk,",.0f"),r.pct if r.pct==r.pct else 0))

print("\n[ ★ 이름 있는 큐레이터의 손상 노출 ]")
N=V[V.curator.notna()].groupby("curator").agg(tvl=("tvl","sum"),risk=("risk","sum"),n=("n","sum"))
N["pct"]=N.risk/N.tvl*100; N=N.sort_values("risk",ascending=False)
if len(N):
    for k,r in N.iterrows():
        print("   %-24s TVL $%12s · 손상마켓 %d · 위험액 $%12s · **TVL대비 %.2f%%**"
              %(str(k)[:24],format(r.tvl,",.0f"),r.n,format(r.risk,",.0f"),r.pct))
else: print("   없음")
print("\n[ ⚠ 이상치 — 신뢰하기 전에 확인할 것 ]")
o=IMP[IMP.mborrow>1e9]
for _,r in o.iterrows():
    print("   %-14s 차입 $%s 는 비현실적이다. 가격피드 오류 가능. **별도 검증 필요**"
          %(str(r.coll)[:14],format(r.mborrow,",.0f")))
print("\n[ 검산 ] 손상 부족분 합 $%s (이상치 제외 $%s)"
      %(format(IMP.shortfall.sum(),",.0f"),format(IMP[IMP.mborrow<=1e9].shortfall.sum(),",.0f")))
IMP.to_parquet(ROOT / "data"/"impaired.parquet")
V.to_parquet(ROOT / "data"/"vault_risk.parquet")
