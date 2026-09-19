# -*- coding: utf-8 -*-
"""★★★ 마지막 검증 — 명목 부채 vs 실제 노출.

가설: 담보가 0 이 된 죽은 마켓은 상환이 안 되고 **이자만 계속 붙는다.**
      borrowAssets 는 명목 누적 부채이지 경제적 손실이 아니다.
      공급자가 잃을 수 있는 최대 = **실제 공급액(supplyAssets)**.
검증: 부실 마켓의 supply 를 보고, borrow 와의 관계를 확인한다."""
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
M=pd.read_parquet(ROOT / "data"/"markets_priced.parquet")
I=pd.read_parquet(ROOT / "data"/"impaired_final.parquet")
S=M[M.mid.isin(I.mid)][["mid","coll","loan","m_busd","m_susd","sup_nat","loan_nat","lltv"]].copy()
S["b_over_s"]=S.m_busd/S.m_susd.replace(0,np.nan)
S=S.sort_values("m_busd",ascending=False)
print("[ ★ 부실 마켓의 차입 vs 공급 ]")
print("   %-14s %-8s %16s %16s %8s"%("담보","대출","표기차입","표기공급","차입/공급"))
for _,r in S.iterrows():
    print("   %-14s %-8s $%15s $%15s %7s"
          %(str(r.coll)[:14],str(r.loan)[:8],format(r.m_busd,",.0f"),format(r.m_susd,",.0f"),
            ("%.2f"%r.b_over_s) if r.b_over_s==r.b_over_s else "-"))
print("\n   → 차입 > 공급 인 마켓 %d개. **물리적으로 불가능하다**(공급된 것보다 더 빌릴 수 없다)"
      %(S.b_over_s>1.01).sum())
print("   → 이는 borrowAssets 가 **상환불가 부채에 이자가 누적된 명목값**임을 뜻한다")
print("\n[ ★★ 실제 노출 재계산 — 손실 상한 = 공급액 ]")
S["real_loss"]=S.m_susd            # 담보가 사실상 0 이면 공급액 전액이 상한
tot=S.real_loss.sum()
print("   부실 마켓 실제 노출 상한 합 = **$%s**  (명목 차입 합 $%s)"
      %(format(tot,",.0f"),format(S.m_busd.sum(),",.0f")))
print("   → 명목값을 쓰면 손실을 **%.0f배** 과대평가한다"%(S.m_busd.sum()/max(tot,1)))
print("\n[ ★★★ 볼트별 실제 노출 — 이제서야 신뢰 가능 ]")
A=pd.read_parquet(ROOT / "data"/"exposure.parquet")
B=A[A.mid.isin(I.mid)].copy()
B["share"]=(B.my_supply/B.mkt_supply.replace(0,np.nan)).clip(0,1).fillna(0)
B["loss"]=B.my_supply                # 공급액이 곧 상한
V=B.groupby(["vault","curator"],dropna=False).agg(
    tvl=("vault_tvl","first"),n=("mid","nunique"),loss=("loss","sum")).reset_index()
V["pct"]=(V.loss/V.tvl.replace(0,np.nan)*100).clip(upper=100)
V=V[V.loss>1000].sort_values("loss",ascending=False)
print("   %-28s %-20s %13s %5s %13s %7s"%("볼트","큐레이터","TVL","마켓","노출액","TVL대비"))
for _,r in V.head(14).iterrows():
    print("   %-28s %-20s $%12s %5d $%12s %6.1f%%"
          %(str(r.vault)[:28],str(r.curator)[:20],format(r.tvl,",.0f"),r.n,
            format(r.loss,",.0f"),r.pct if r.pct==r.pct else 0))
print("\n[ ★ 이름 있는 큐레이터만 ]")
N=V[V.curator.notna()].groupby("curator").agg(tvl=("tvl","sum"),loss=("loss","sum"),n=("n","sum"))
N["pct"]=(N.loss/N.tvl*100)
for k,r in N.sort_values("loss",ascending=False).iterrows():
    print("   %-24s TVL $%12s · 부실마켓 %d · 노출 $%12s · **TVL대비 %.2f%%**"
          %(str(k)[:24],format(r.tvl,",.0f"),r.n,format(r.loss,",.0f"),r.pct))
print("\n[ ⚠ 남은 불확실성 ]")
print("   · 담보가 완전히 0 이 아닌 마켓(msY 커버 0.14 등)은 부분 회수 가능 — 상한을 과대평가한다")
print("   · 볼트 TVL 이 이미 상각됐다면 'TVL대비'가 왜곡된다(분모가 이미 줄었다)")
print("   · 이 숫자는 **노출 상한**이지 확정 손실이 아니다")
