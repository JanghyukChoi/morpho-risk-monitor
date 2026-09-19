# -*- coding: utf-8 -*-
"""★★★ 최종 검증 — 부분담보 마켓이 진짜인가. 실존 큐레이터를 거론하기 전 마지막 관문.

교훈(내 오판): "스테이블이니 $1 이어야 한다"고 가정하고 데이터를 의심했다.
               USR 은 실제로 2026-03-22 익스플로잇으로 무너졌다(CMC $0.1251).
               **가정이 아니라 대조로 판단한다.**

검증 항목
  W1 네이티브 수량 × 독립가격 = USD 가 맞는가 (내적 정합)
  W2 차입 USD 가 네이티브 수량으로 재현되는가 (대출자산은 대개 USDC — 가격 신뢰 가능)
  W3 가격 시각(staleness) — 죽은 가격을 쓰고 있지 않은가
  W4 LLTV 대비 담보비율이 물리적으로 가능한 값인가
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
M=pd.read_parquet(ROOT / "data"/"markets_priced.parquet")
P=pd.read_parquet(ROOT / "data"/"prices.parquet")
A=M[M.m_busd>1000].copy()
A["c_price"]=pd.to_numeric(A.c_price,errors="coerce")
A["l_price"]=pd.to_numeric(A.l_price,errors="coerce")
A["cusd_calc"]=A.coll_nat*A.c_price            # 독립가격으로 재계산
A["busd_calc"]=A.loan_nat*A.l_price
print("[ W1 담보 USD 내적 정합 — Morpho 표기 vs 독립 재계산 ]")
w=A[(A.c_price>0)&(A.m_cusd>0)].copy(); w["r"]=w.cusd_calc/w.m_cusd
print("   대상 %d · ±5%% 일치 %.1f%% · 중앙 배율 %.4f"%(len(w),((w.r>0.95)&(w.r<1.05)).mean()*100,w.r.median()))
print("\n[ W2 ★ 차입 USD 검증 — 여기가 핵심이다 ]")
b=A[(A.l_price>0)&(A.m_busd>0)].copy(); b["r"]=b.busd_calc/b.m_busd
print("   대상 %d · ±5%% 일치 **%.1f%%** · 중앙 배율 %.4f"%(len(b),((b.r>0.95)&(b.r<1.05)).mean()*100,b.r.median()))
bad=b[(b.r<0.5)|(b.r>2)]
print("   ⚠ 2배 이상 어긋난 마켓 **%d개** — Morpho 의 차입 USD 를 못 믿는다는 뜻"%len(bad))
for _,r in bad.nlargest(10,"m_busd").iterrows():
    print("      %-14s/%-8s Morpho차입 $%14s · 재계산 $%14s (%.4fx)"
          %(str(r.coll)[:14],str(r.loan)[:8],format(r.m_busd,",.0f"),format(r.busd_calc,",.0f"),r.r))
print("\n[ W3 ★★ 부분담보 후보를 독립 재계산으로 다시 판정 ]")
V=A[(A.c_price>0)&(A.l_price>0)].copy()
V["cover"]=V.cusd_calc/V.busd_calc.replace(0,np.nan)
imp=V[(V.busd_calc>1e4)&(V.cover<1.0)].sort_values("busd_calc",ascending=False)
print("   독립 재계산 기준 담보<차입 마켓 **%d개** / 검증가능 마켓 %d개"%(len(imp),len(V[V.busd_calc>1e4])))
print("   %-14s %-8s %14s %14s %7s %6s"%("담보","대출","차입(재계산)","담보(재계산)","커버","LLTV"))
for _,r in imp.head(14).iterrows():
    print("   %-14s %-8s $%13s $%13s %6.3f %6.2f"
          %(str(r.coll)[:14],str(r.loan)[:8],format(r.busd_calc,",.0f"),
            format(r.cusd_calc,",.0f"),r.cover,r.lltv))
print("\n[ W4 가격 신선도 ]")
P["ts"]=pd.to_datetime(pd.to_numeric(P.ll_ts,errors="coerce"),unit="s",errors="coerce")
age=(pd.Timestamp.now()-P.ts).dt.days
print("   DefiLlama 가격 %d개 · 7일 초과 %d개 (%.1f%%) · 30일 초과 %d개"
      %(len(P),(age>7).sum(),(age>7).mean()*100,(age>30).sum()))
st=P[age>7].merge(A[["ckey","coll","m_busd"]].rename(columns={"ckey":"key"}),on="key",how="inner")
if len(st):
    print("   [ 오래된 가격을 쓰는 담보 ]")
    for _,r in st.nlargest(8,"m_busd").iterrows():
        print("      %-16s 가격 %s · 차입 $%s"%(str(r.coll)[:16],str(r.ll_price)[:10],format(r.m_busd,",.0f")))
imp.to_parquet(ROOT / "data"/"impaired_verified.parquet")
print("\n저장 impaired_verified.parquet (%d행)"%len(imp))
