# -*- coding: utf-8 -*-
"""사전등록 `alpha/prereg/accrual_regime.md` 대로 재검정. 정의는 이미 고정·커밋됨.

팽창 국면  C1 커버<0.5 · C2 가동률≥0.99 · C3 연속 30일+ · C4 시작 공급≥$1,000
게이트     G1 중앙오차<30% · G2 지수 승률≥70% · G3 길이 3분위 부호 일관
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"
URL="https://blue-api.morpho.org/graphql"
Q="""query($id:String!,$opt:TimeseriesOptions){ markets(first:1, where:{uniqueKey_in:[$id]}){ items{
  collateralAsset{symbol} loanAsset{symbol decimals}
  historicalState{ supplyAssets(options:$opt){x y} collateralAssetsUsd(options:$opt){x y}
                   borrowAssetsUsd(options:$opt){x y} utilization(options:$opt){x y} } } } }"""
def ser(p,dec=0):
    d={}
    for q in (p or []):
        if q.get("y") is None: continue
        d[pd.to_datetime(q["x"],unit="s")]=float(q["y"])/(10**dec if dec else 1)
    return pd.Series(d).sort_index()
# 후보 = 스냅샷 패널에서 커버<0.5 로 잡힌 적 있는 마켓 + 기존 부실 목록 (표본 확장)
cand=set(pd.read_parquet(OUT/"principal2.parquet").mid)
pm=pd.read_parquet(OUT/"panel_markets.parquet")
cand |= set(pm[(pm.cover<0.5)&(pm.util>=0.99)].mid.dropna())
mk=pd.read_parquet(OUT/"markets_priced.parquet")
cand |= set(mk[(mk.m_busd>1e4)&((mk.m_cusd/mk.m_busd.replace(0,np.nan))<0.5)].mid.dropna())
cand=sorted(cand)
print("■ 후보 마켓 %d개"%len(cand))
opt={"startTimestamp":1704067200,"endTimestamp":int(time.time()),"interval":"DAY"}
S=requests.Session(); segs=[]
for i,mid in enumerate(cand):
    x=None
    for a in range(3):
        try:
            r=S.post(URL,json={"query":Q,"variables":{"id":mid,"opt":opt}},timeout=120).json()
            if "errors" in r: break
            it=r["data"]["markets"]["items"]; x=it[0] if it else None; break
        except Exception: time.sleep(2)
    if not x: continue
    h=x.get("historicalState") or {}
    ld=(x.get("loanAsset") or {}).get("decimals") or 18
    sp=ser(h.get("supplyAssets"),ld); cu=ser(h.get("collateralAssetsUsd"))
    bw=ser(h.get("borrowAssetsUsd")); ut=ser(h.get("utilization"))
    idx=sp.index.intersection(cu.index).intersection(bw.index).intersection(ut.index)
    if len(idx)<60: continue
    sp,cu,bw,ut=[z.reindex(idx) for z in (sp,cu,bw,ut)]
    cov=cu/bw.replace(0,np.nan)
    ok=((cov<0.5)&(ut>=0.99)).fillna(False).values          # C1·C2
    # C3 연속 30일+ 구간 추출
    run=0
    for j in range(len(ok)+1):
        if j<len(ok) and ok[j]: run+=1; continue
        if run>=30:
            a,b=j-run,j-1
            if sp.iloc[a]>=1000:                            # C4
                segs.append(dict(mid=mid,
                    sym="%s/%s"%((x.get("collateralAsset") or {}).get("symbol"),
                                 (x.get("loanAsset") or {}).get("symbol")),
                    t0=idx[a],t1=idx[b],n=run,s=sp.iloc[a:b+1].copy()))
        run=0
    if (i+1)%10==0: print("   %d/%d · 구간 %d"%(i+1,len(cand),len(segs)),flush=True)
    time.sleep(0.12)
print("■ 정의 만족 구간 **%d개** (마켓 %d)"%(len(segs),len({s['mid'] for s in segs})))
old=set(pd.read_parquet(OUT/"principal2.parquet").mid)
new=[s for s in segs if s["mid"] not in old]
print("   6부 표본과 겹치지 않는 구간 **%d개**"%len(new))
if len(new)<5:
    print("\n[ 판정 ] 사전등록 §2 — 독립 구간 5개 미만. **검정 보류(표본 부족)**")
    print("   → 이것도 결과다. 표본이 없다는 사실을 공개한다.")
res=[]
for sg in segs:
    s=sg["s"]; half=len(s)//2
    tr,te=s.iloc[:half],s.iloc[half:]
    if len(tr)<10 or len(te)<10 or (tr<=0).any(): continue
    d=np.array([(t-tr.index[0]).days for t in tr.index],float)
    if np.std(d)==0: continue
    r_hat=np.polyfit(d,np.log(tr.values),1)[0]*365.0
    dd=np.array([(t-tr.index[0]).days for t in te.index],float)
    act=te.values
    m=lambda p: float(np.nanmedian(np.abs(p/np.where(act==0,np.nan,act)-1)))
    e_exp=m(float(tr.iloc[0])*np.exp(r_hat*dd/365.0))
    e_lin=m(tr.values[0]+np.polyfit(d,tr.values,1)[0]*dd)
    e_flat=m(np.full(len(te),float(tr.iloc[-1])))
    res.append(dict(sym=sg["sym"],n=sg["n"],r=r_hat,e_exp=e_exp,e_lin=e_lin,e_flat=e_flat,
                    win=(e_exp<e_lin)and(e_exp<e_flat)))
R=pd.DataFrame(res)
if not len(R): print("검정 가능 구간 0"); raise SystemExit
print("\n[ 검정 구간 %d개 ]"%len(R))
print("   %-22s %5s %9s %10s %10s %10s %s"%("마켓","일수","추정연율","지수","선형","무변화","승"))
for _,r in R.sort_values("n",ascending=False).iterrows():
    print("   %-22s %5d %8.0f%% %9.1f%% %9.1f%% %9.1f%%  %s"
          %(str(r.sym)[:22],r.n,r.r*100,r.e_exp*100,r.e_lin*100,r.e_flat*100,"✅" if r.win else "—"))
g1=R.e_exp.median()<0.30; g2=R.win.mean()>=0.70
R["b"]=pd.qcut(R.n.rank(method="first"),min(3,R.n.nunique()),labels=False)
g3=R.groupby("b").win.mean()
print("\n[ ★ 게이트 판정 (사전등록 §4) ]")
print("   G1 중앙오차 < 30%%      : %.1f%%  %s"%(R.e_exp.median()*100,"✅" if g1 else "❌"))
print("   G2 지수 승률 ≥ 70%%     : %.0f%%  %s"%(R.win.mean()*100,"✅" if g2 else "❌"))
print("   G3 길이 3분위 부호 일관 : "+" / ".join("%.0f%%"%(v*100) for v in g3))
print("\n   → %s"%("**메커니즘 확증**" if (g1 and g2) else "**확증 불가 — 확정. 재시도하지 않는다(사전등록 §4)**"))
R.to_parquet(OUT/"regime_test.parquet")
