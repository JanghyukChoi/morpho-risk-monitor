# -*- coding: utf-8 -*-
"""★★★ 메커니즘 직접 검정 — 팽창이 정말 '이자 누적'인가. 자유 파라미터 0개.

주장(4부): 부실 마켓의 명목 공급 증가 = 순수 이자 복리
반증 가능한 형태:
    supply(t+k) = supply(t) × exp( ∫ supplyAPY dt )
    APY 는 **API 가 독립적으로 보고**하는 값이다. 내가 맞추는 게 아니다.
    → 예측이 실제와 맞으면 메커니즘이 확증된다. 어긋나면 내 해석이 틀린 것이다.

⚠ 기다릴 필요가 없다. 과거 시점 T 에서 예측해 T+k 실제와 대조하면 아웃오브샘플이다.
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"
URL="https://blue-api.morpho.org/graphql"
Q="""query($id:String!,$opt:TimeseriesOptions){ markets(first:1, where:{uniqueKey_in:[$id]}){ items{
  collateralAsset{symbol decimals} loanAsset{symbol decimals}
  historicalState{
    supplyAssets(options:$opt){x y}
    supplyApy(options:$opt){x y}
    collateralAssetsUsd(options:$opt){x y} } } } }"""
def ser(p,dec=0):
    d={}
    for q in (p or []):
        if q.get("y") is None: continue
        d[pd.to_datetime(q["x"],unit="s")]=float(q["y"])/(10**dec if dec else 1)
    return pd.Series(d).sort_index()
I=pd.read_parquet(OUT/"principal2.parquet")
opt={"startTimestamp":1704067200,"endTimestamp":int(time.time()),"interval":"DAY"}
S=requests.Session(); res=[]
for _,row in I.iterrows():
    x=None
    for a in range(3):
        try:
            r=S.post(URL,json={"query":Q,"variables":{"id":row.mid,"opt":opt}},timeout=120).json()
            if "errors" in r: break
            it=r["data"]["markets"]["items"]; x=it[0] if it else None; break
        except Exception: time.sleep(2)
    if not x: continue
    h=x.get("historicalState") or {}
    ld=(x.get("loanAsset") or {}).get("decimals") or 18
    sp=ser(h.get("supplyAssets"),ld); ap=ser(h.get("supplyApy")); cu=ser(h.get("collateralAssetsUsd"))
    idx=sp.index.intersection(ap.index)
    if len(idx)<120: continue
    sp=sp.reindex(idx); ap=ap.reindex(idx)
    # 부실 구간만 — 담보가 사실상 사라진 이후
    if len(cu):
        c=cu.reindex(idx).fillna(0)
        live=c[c>1000]
        start=live.index[-1] if len(live) else idx[0]
    else: start=idx[0]
    seg_i=idx[idx>start]
    if len(seg_i)<90: continue
    for K in (30,60,90):
        # T = 부실 시작 + 30일, 예측 구간 [T, T+K]
        t0=seg_i[min(30,len(seg_i)-K-1)]
        t1_cand=[t for t in seg_i if (t-t0).days>=K]
        if not t1_cand: continue
        t1=t1_cand[0]
        seg=ap.loc[t0:t1]
        if seg.isna().all() or sp.loc[t0]<=0: continue
        days=(t1-t0).days
        # ∫APY dt 를 일별 평균으로 근사 (APY 는 이미 연율 복리)
        rate=float(np.nanmean(seg.values))
        pred=float(sp.loc[t0])*np.exp(rate*days/365.0)
        act=float(sp.loc[t1])
        res.append(dict(sym="%s/%s"%((x.get("collateralAsset") or {}).get("symbol"),
                                     (x.get("loanAsset") or {}).get("symbol")),
            K=K,t0=t0,t1=t1,days=days,apy=rate,s0=float(sp.loc[t0]),pred=pred,act=act,
            err=(pred/act-1) if act>0 else np.nan, naive_err=(float(sp.loc[t0])/act-1) if act>0 else np.nan))
    time.sleep(0.15)
R=pd.DataFrame(res)
if not len(R): print("검정 가능한 구간 없음"); raise SystemExit
print("[ ★★★ 무수정 예측 — APY 만으로 공급 곡선을 맞힐 수 있는가 ]")
print("   검정 %d건 (마켓 %d · 기간 30/60/90일)"%(len(R),R.sym.nunique()))
for K,g in R.groupby("K"):
    ae=g.err.abs(); an=g.naive_err.abs()
    print("\n   [ %d일 예측 · n=%d ]"%(K,len(g)))
    print("      예측 오차  중앙 **%6.1f%%** · 25~75분위 %.1f%% ~ %.1f%%"%(ae.median()*100,ae.quantile(.25)*100,ae.quantile(.75)*100))
    print("      무예측(변화없음 가정) 오차 중앙 %6.1f%%"%(an.median()*100))
    better=(ae<an).mean()*100
    print("      이자모형이 더 정확한 비율 **%.0f%%**"%better)
    print("      ±20%% 이내 적중 **%.0f%%** · ±50%% 이내 %.0f%%"%((ae<0.2).mean()*100,(ae<0.5).mean()*100))
print("\n[ 개별 사례 — 90일 예측 ]")
for _,r in R[R.K==90].nlargest(8,"act").iterrows():
    print("   %-18s APY %8.1f%% · %s→%s · 시작 $%11s · 예측 $%13s · 실제 $%13s · 오차 %+7.1f%%"
          %(str(r.sym)[:18],r.apy*100,str(r.t0)[:10],str(r.t1)[:10],
            format(r.s0,",.0f"),format(r.pred,",.0f"),format(r.act,",.0f"),r.err*100))
R.to_parquet(OUT/"accrual_test.parquet")
print("\n[ 판정 ]")
a=R.err.abs()
print("   전체 예측 오차 중앙 **%.1f%%** · 무예측 대비 개선 %.0f%%"
      %(a.median()*100,(a<R.naive_err.abs()).mean()*100))
print("   → %s"%("**메커니즘 확증: 팽창은 보고된 이자율로 설명된다**" if a.median()<0.5
                 else "❌ 이자만으로 설명 안 된다 — 4부 해석 재검토 필요"))
