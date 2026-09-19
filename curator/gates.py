# -*- coding: utf-8 -*-
"""G3~G5 정밀 판정 + 변수 기여. model.py 의 G3 가 라벨 2개짜리 폴드에서 돌아
   판정 불가였던 것을 유효 폴드로 다시 한다. **게이트 기준은 바꾸지 않는다.**"""
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score as ap
from sklearn.inspection import permutation_importance
ROOT=Path(__file__).resolve().parent.parent
D=pd.read_parquet(ROOT / "data"/"markets.parquet")
U=D[(D.bmax>1e4)&(D.created.notna())].copy(); U["y"]=(U.rbd>0).astype(int)
loan_syms=set(D.loan.dropna()); cnt=D.groupby("coll").size()
U["coll_is_loanable"]=U.coll.isin(loan_syms).astype(int)
U["coll_nmkt"]=np.log1p(U.coll.map(cnt).fillna(0))
U["loan_nmkt"]=np.log1p(U.loan.map(D.groupby("loan").size()).fillna(0))
U["oracle_unknown"]=(U.otype.fillna("(none)").isin(["Unknown","(none)"])).astype(int)
U["oracle_none"]=U.otype.isna().astype(int)
U["log_b30"]=np.log1p(U.b30.fillna(0)); U["log_age"]=np.log1p(U.age_d)
U["w_oracle_bad"]=U.warn.fillna("").str.contains("oracle_unusable|oracle_price_derivation").astype(int)
U["w_lowliq"]=U.warn.fillna("").str.contains("sustained_low_liquidity").astype(int)
U["w_unrec_coll"]=U.warn.fillna("").str.contains("unrecognized_collateral_asset").astype(int)
F=["lltv","coll_is_loanable","coll_nmkt","loan_nmkt","oracle_unknown","oracle_none",
   "log_b30","log_age","w_oracle_bad","w_lowliq","w_unrec_coll"]
U=U.sort_values("created")
def split(q):
    T=U.created.quantile(q); return U[U.created<=T], U[(U.created>T)&(U.age_d>=90)]
def fit(tr,te):
    gb=HistGradientBoostingClassifier(max_iter=250,max_depth=3,learning_rate=0.06,
        min_samples_leaf=15,random_state=0).fit(tr[F].fillna(0),tr.y)
    return gb, gb.predict_proba(te[F].fillna(0))[:,1]
print("[ ★ G3 용량-반응 — 유효 폴드(라벨 5개 이상)에서만 판정 ]")
for q in (0.45,0.60):
    tr,te=split(q)
    if te.y.sum()<5: continue
    gb,p=fit(tr,te); te2=te.assign(p=p)
    nb=3 if te.y.sum()<20 else 4
    te2["b"]=pd.qcut(te2.p.rank(method="first"),nb,labels=False)
    t=te2.groupby("b").agg(n=("y","size"),k=("y","sum"),rate=("y","mean"))
    print("   q=%.2f (검정 n=%d · 라벨 %d · %d분위)"%(q,len(te),te.y.sum(),nb))
    for b,r in t.iterrows(): print("      %d분위 n=%3d · 사고 %2d건 · **%5.1f%%**"%(b+1,r.n,r.k,r.rate*100))
    print("      단조 증가: %s"%("✅" if t.rate.is_monotonic_increasing else "❌"))
print("\n[ ★ G4 체인 분할 부호 일관성 ]")
tr,te=split(0.45); gb,p=fit(tr,te); te=te.assign(p=p)
for ch,s in te.groupby("chain"):
    if len(s)<30 or s.y.sum()<3: print("   chain %-6s n=%3d 라벨 %d — 표본부족"%(ch,len(s),s.y.sum())); continue
    print("   chain %-6s n=%3d 라벨 %2d · PR-AUC %.3f (기저 %.3f) · lift **%.1fx**"
          %(ch,len(s),s.y.sum(),ap(s.y,s.p),s.y.mean(),ap(s.y,s.p)/s.y.mean()))
print("\n[ ★ G5 누수 재검사 — 변수 하나씩 빼며 성능 변화 ]")
tr,te=split(0.45); base=ap(te.y,fit(tr,te)[1])
print("   전체 변수 PR-AUC %.4f"%base)
for f in F:
    F2=[x for x in F if x!=f]
    gb=HistGradientBoostingClassifier(max_iter=250,max_depth=3,learning_rate=0.06,
        min_samples_leaf=15,random_state=0).fit(tr[F2].fillna(0),tr.y)
    a=ap(te.y,gb.predict_proba(te[F2].fillna(0))[:,1])
    print("   −%-18s PR-AUC %.4f  (%+.4f)%s"%(f,a,a-base," ★지배" if base-a>base*0.4 else ""))
print("\n[ 참고 — 사고 마켓의 특징 (인-샘플 기술통계, 판정 아님) ]")
for c,l in (("coll_is_loanable","담보가 대출자산으로도 쓰임"),("oracle_unknown","오라클 Unknown"),
            ("w_oracle_bad","오라클 경고 RED"),("w_unrec_coll","미인식 담보")):
    a=U[U.y==1][c].mean()*100; b=U[U.y==0][c].mean()*100
    print("   %-22s 사고 %5.1f%% vs 무사고 %5.1f%%  (차 %+.1f%%p)"%(l,a,b,a-b))
print("   %-22s 사고 %5.3f vs 무사고 %5.3f"%("LLTV 평균",U[U.y==1].lltv.mean(),U[U.y==0].lltv.mean()))
