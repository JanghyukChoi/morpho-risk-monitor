# -*- coding: utf-8 -*-
"""Phase 1~2 — 기준선 + 모델 + 사전등록 게이트 판정.
사전등록 alpha/prereg/curator_risk.md §9 를 그대로 따른다.

★ 설명변수는 **생성 시 관측 가능한 것만**. 현재 상태(supply/borrow/util/apy)는 결과 오염이라 제외.
  단 b30(나이 30일 시점 차입)은 시점이 고정돼 있어 허용 — 사전등록 §9.2
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score
ROOT=Path(__file__).resolve().parent.parent
D=pd.read_parquet(ROOT / "data"/"markets.parquet")

# ── 대상집합 (사전등록 §9.2)
U=D[(D.bmax>1e4)&(D.created.notna())].copy()
U["y"]=(U.rbd>0).astype(int)
print("[ 대상집합 ] n=%d · 라벨 %d (%.2f%%)"%(len(U),U.y.sum(),U.y.mean()*100))

# ── 담보 성격: 손 분류 대신 **객관 파생**
loan_syms=set(D.loan.dropna())                       # 대출자산으로도 쓰이는가 = 확립된 자산
cnt=D.groupby("coll").size()                          # 몇 개 마켓이 이 담보를 쓰는가
U["coll_is_loanable"]=U.coll.isin(loan_syms).astype(int)
U["coll_nmkt"]=np.log1p(U.coll.map(cnt).fillna(0))
U["loan_nmkt"]=np.log1p(U.loan.map(D.groupby("loan").size()).fillna(0))
U["oracle_unknown"]=(U.otype.fillna("(none)").isin(["Unknown","(none)"])).astype(int)
U["oracle_none"]=U.otype.isna().astype(int)
U["log_b30"]=np.log1p(U.b30.fillna(0))
U["log_age"]=np.log1p(U.age_d)
U["w_oracle_bad"]=U.warn.fillna("").str.contains("oracle_unusable|oracle_price_derivation").astype(int)
U["w_lowliq"]=U.warn.fillna("").str.contains("sustained_low_liquidity").astype(int)
U["w_unrec_coll"]=U.warn.fillna("").str.contains("unrecognized_collateral_asset").astype(int)
FEATS=["lltv","coll_is_loanable","coll_nmkt","loan_nmkt","oracle_unknown","oracle_none",
       "log_b30","log_age","w_oracle_bad","w_lowliq","w_unrec_coll"]

# ── 기준선 (사전등록 §9.4)
def prauc(y,s): return average_precision_score(y,s)
base_rate=U.y.mean()
print("\n[ 기준선 — 전체 표본 ]")
print("   ① 상수                      PR-AUC %.4f  (= 라벨률)"%base_rate)
print("   ② LLTV 단독                 PR-AUC %.4f"%prauc(U.y,U.lltv))
b3=(1-U.coll_is_loanable)                             # '담보가 대출자산으로 안 쓰임' = 비확립
print("   ③ 담보 비확립 규칙           PR-AUC %.4f  ← 이겨야 할 기준선"%prauc(U.y,b3))
print("   ④ 오라클 경고 규칙           PR-AUC %.4f"%prauc(U.y,U.w_oracle_bad))

# ── 워크포워드 (생성시각 기준)
U=U.sort_values("created")
qs=[0.45,0.60,0.75]
print("\n[ ★ 워크포워드 — T 이전 생성으로 훈련 → 이후 생성으로 검정 ]")
print("   ⚠ 최근 마켓은 사고 기회가 적다. 검정셋은 **나이 90일 이상**으로 제한한다")
res=[]
for q in qs:
    T=U.created.quantile(q)
    tr=U[U.created<=T]
    te=U[(U.created>T)&(U.age_d>=90)]
    if te.y.sum()<5 or len(te)<40:
        print("   q=%.2f  검정 표본 부족 (n=%d, 라벨=%d) — 건너뜀"%(q,len(te),te.y.sum())); continue
    Xtr,Xte=tr[FEATS].fillna(0),te[FEATS].fillna(0)
    lr=LogisticRegression(max_iter=2000,class_weight="balanced").fit(
        (Xtr-Xtr.mean())/Xtr.std().replace(0,1), tr.y)
    plr=lr.predict_proba((Xte-Xtr.mean())/Xtr.std().replace(0,1))[:,1]
    gb=HistGradientBoostingClassifier(max_iter=250,max_depth=3,learning_rate=0.06,
        min_samples_leaf=15,random_state=0).fit(Xtr,tr.y)
    pgb=gb.predict_proba(Xte)[:,1]
    pavg=(pd.Series(plr).rank(pct=True).values+pd.Series(pgb).rank(pct=True).values)/2  # 격자 전면평균
    b3te=(1-te.coll_is_loanable)
    r=dict(q=q,n_te=len(te),lab=int(te.y.sum()),base=te.y.mean(),
           b_lltv=prauc(te.y,te.lltv), b_rule=prauc(te.y,b3te), b_orc=prauc(te.y,te.w_oracle_bad),
           lr=prauc(te.y,plr), gb=prauc(te.y,pgb), avg=prauc(te.y,pavg))
    k=max(int(len(te)*0.10),1)
    top=np.argsort(-pavg)[:k]
    r["cap10"]=te.y.values[top].sum()/te.y.sum()*100
    res.append(r)
    print("   q=%.2f  검정 n=%3d 라벨 %2d (기저 %.3f) │ LLTV %.3f · 규칙 %.3f · 오라클 %.3f │ **평균모델 %.3f** · 상위10%%포착 %.0f%%"
          %(q,len(te),te.y.sum(),te.y.mean(),r["b_lltv"],r["b_rule"],r["b_orc"],r["avg"],r["cap10"]))
R=pd.DataFrame(res)
print("\n[ ★ 게이트 판정 ]")
if len(R)==0:
    print("   G1~G2 판정 불가 — 워크포워드 검정셋이 모두 표본 부족")
else:
    g1=(R.avg>R.b_rule).all()
    g2=(R.cap10>=40).all()
    print("   G1 모든 구간에서 모델 > 담보규칙 기준선 : %s  (%s)"
          %("✅ 통과" if g1 else "❌ 미달", " / ".join("%.3f vs %.3f"%(a,b) for a,b in zip(R.avg,R.b_rule))))
    print("   G2 상위10%% 포착률 ≥ 40%%            : %s  (%s)"
          %("✅ 통과" if g2 else "❌ 미달", " / ".join("%.0f%%"%c for c in R.cap10)))
# ── G3 용량-반응 (전체 표본 인-샘플 아님: 워크포워드 마지막 폴드 사용)
print("\n[ G3 용량-반응 — 위험점수 decile 별 실제 사고율 ]")
if len(R):
    T=U.created.quantile(qs[-1]); tr=U[U.created<=T]; te=U[(U.created>T)&(U.age_d>=90)]
    Xtr,Xte=tr[FEATS].fillna(0),te[FEATS].fillna(0)
    gb=HistGradientBoostingClassifier(max_iter=250,max_depth=3,learning_rate=0.06,
        min_samples_leaf=15,random_state=0).fit(Xtr,tr.y)
    te=te.assign(p=gb.predict_proba(Xte)[:,1])
    te["dec"]=pd.qcut(te.p.rank(method="first"),5,labels=False)
    t=te.groupby("dec").agg(n=("y","size"),rate=("y","mean"))
    for d,row in t.iterrows(): print("   %d분위  n=%3d · 사고율 **%5.1f%%**"%(d+1,row.n,row.rate*100))
    mono=t.rate.is_monotonic_increasing
    print("   단조 증가: %s"%("✅" if mono else "❌ — 사전등록 G3 미달이면 기각"))
