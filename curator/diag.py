# -*- coding: utf-8 -*-
"""기각 진단 — 성능이 '나이 인공물'인가 진짜 신호인가.
★ 게이트를 완화하려는 게 아니다. 판정은 이미 기각이다. **원인을 특정**하려는 것이다."""
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score as ap
ROOT=Path(__file__).resolve().parent.parent
D=pd.read_parquet(ROOT / "data"/"markets.parquet")
U=D[(D.bmax>1e4)&(D.created.notna())].copy(); U["y"]=(U.rbd>0).astype(int)
loan_syms=set(D.loan.dropna())
U["coll_is_loanable"]=U.coll.isin(loan_syms).astype(int)
U["coll_nmkt"]=np.log1p(U.coll.map(D.groupby("coll").size()).fillna(0))
U["loan_nmkt"]=np.log1p(U.loan.map(D.groupby("loan").size()).fillna(0))
U["oracle_unknown"]=(U.otype.fillna("(none)").isin(["Unknown","(none)"])).astype(int)
U["log_b30"]=np.log1p(U.b30.fillna(0)); U["log_age"]=np.log1p(U.age_d)
U["w_unrec_coll"]=U.warn.fillna("").str.contains("unrecognized_collateral_asset").astype(int)
U=U.sort_values("created")
T=U.created.quantile(0.45); tr=U[U.created<=T]; te=U[(U.created>T)&(U.age_d>=90)]
def run(F,lab):
    gb=HistGradientBoostingClassifier(max_iter=250,max_depth=3,learning_rate=0.06,
        min_samples_leaf=15,random_state=0).fit(tr[F].fillna(0),tr.y)
    p=gb.predict_proba(te[F].fillna(0))[:,1]
    print("   %-34s PR-AUC %.4f · lift %.1fx"%(lab,ap(te.y,p),ap(te.y,p)/te.y.mean()))
    return p
print("[ 진단 1 — 나이를 빼면 신호가 남는가 ]  검정 n=%d · 라벨 %d · 기저 %.3f"%(len(te),te.y.sum(),te.y.mean()))
run(["log_age"],"나이 단독")
run(["lltv","coll_is_loanable","coll_nmkt","loan_nmkt","oracle_unknown","log_b30","w_unrec_coll"],"나이 제외 전체")
run(["loan_nmkt","coll_nmkt","log_b30"],"규모·인지도 3변수")
run(["lltv","coll_is_loanable","oracle_unknown"],"불변 파라미터만")
print("\n[ 진단 2 — 나이와 라벨의 관계 (인공물 확인) ]")
U["ab"]=pd.qcut(U.age_d,5,labels=False)
for b,s in U.groupby("ab"):
    print("   나이 %d분위 (중앙 %4.0f일)  n=%3d · 사고율 **%5.1f%%**"%(b+1,s.age_d.median(),len(s),s.y.mean()*100))
print("\n[ 진단 3 — 나이를 고정하면? 나이 180일 이상만, 나이 제외 모델 ]")
U2=U[U.age_d>=180]
T2=U2.created.quantile(0.5); tr2=U2[U2.created<=T2]; te2=U2[U2.created>T2]
F=["lltv","coll_is_loanable","coll_nmkt","loan_nmkt","oracle_unknown","log_b30","w_unrec_coll"]
if te2.y.sum()>=5:
    gb=HistGradientBoostingClassifier(max_iter=250,max_depth=3,learning_rate=0.06,
        min_samples_leaf=15,random_state=0).fit(tr2[F].fillna(0),tr2.y)
    p=gb.predict_proba(te2[F].fillna(0))[:,1]
    a=ap(te2.y,p)
    print("   검정 n=%d · 라벨 %d · 기저 %.3f → PR-AUC **%.4f** · lift **%.1fx**"
          %(len(te2),te2.y.sum(),te2.y.mean(),a,a/te2.y.mean()))
    k=max(int(len(te2)*.10),1); top=np.argsort(-p)[:k]
    print("   상위10%% 포착률 **%.0f%%**"%(te2.y.values[top].sum()/te2.y.sum()*100))
else: print("   표본 부족")
