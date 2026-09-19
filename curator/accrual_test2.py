# -*- coding: utf-8 -*-
"""★★★ 메커니즘 검정 v2 — 보고 APY 가 못 쓰는 값이어서 설계를 바꾼다.

v1 실패 원인 (내 가설이 아니라 데이터)
    보고 supplyApy 가 297,995% 같은 값을 준다. PAXG 실제 성장은 90일 7.2배
    = 함의 연율 800%. **보고값이 실제보다 ~300배 높다.** APY 필드를 못 쓴다.

v2 설계 — 자유 파라미터 1개, 여전히 아웃오브샘플
    부실 구간 전반부의 log(supply) 기울기로 금리 r 을 **추정**
    → 후반부를 예측 → 실제와 대조
    귀무가설: 성장은 지수형이 아니다(= 이자 복리가 아니다) → 예측이 크게 빗나간다
    대립가설: 지수형이다 → 전반부 기울기로 후반부가 맞는다
비교 기준
    ① 무변화 가정  ② 선형 외삽  ③ 지수(이자) 모형  ← ③이 이겨야 주장이 선다
"""
from __future__ import annotations
import numpy as np, pandas as pd, requests, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"
URL="https://blue-api.morpho.org/graphql"
Q="""query($id:String!,$opt:TimeseriesOptions){ markets(first:1, where:{uniqueKey_in:[$id]}){ items{
  collateralAsset{symbol} loanAsset{symbol decimals}
  historicalState{ supplyAssets(options:$opt){x y} collateralAssetsUsd(options:$opt){x y} } } } }"""
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
    sp=ser(h.get("supplyAssets"),ld); cu=ser(h.get("collateralAssetsUsd"))
    if len(sp)<160: continue
    live=cu[cu>1000] if len(cu) else pd.Series(dtype=float)
    start=live.index[-1] if len(live) else sp.index[0]
    seg=sp[(sp.index>start)&(sp>0)]
    if len(seg)<120: continue
    half=len(seg)//2
    tr,te=seg.iloc[:half],seg.iloc[half:]
    d=np.array([(t-tr.index[0]).days for t in tr.index],dtype=float)
    y=np.log(tr.values)
    if np.std(d)==0: continue
    r_hat=np.polyfit(d,y,1)[0]*365.0                      # 연율 추정
    dd=np.array([(t-tr.index[0]).days for t in te.index],dtype=float)
    pred_exp=float(tr.iloc[0])*np.exp(r_hat*dd/365.0)
    slope=np.polyfit(np.array([(t-tr.index[0]).days for t in tr.index],dtype=float),tr.values,1)[0]
    pred_lin=tr.values[0]+slope*dd
    pred_flat=np.full(len(te),float(tr.iloc[-1]))
    act=te.values
    mape=lambda p: float(np.nanmedian(np.abs(p/np.where(act==0,np.nan,act)-1)))
    res.append(dict(sym="%s/%s"%((x.get("collateralAsset") or {}).get("symbol"),
                                 (x.get("loanAsset") or {}).get("symbol")),
        n=len(seg),days=int((seg.index[-1]-seg.index[0]).days),r_hat=r_hat,
        e_exp=mape(pred_exp),e_lin=mape(pred_lin),e_flat=mape(pred_flat),
        s0=float(tr.iloc[0]),s_end=float(te.iloc[-1])))
    time.sleep(0.15)
R=pd.DataFrame(res)
if not len(R): print("검정 가능 마켓 없음"); raise SystemExit
print("[ ★★★ 아웃오브샘플 — 전반부로 후반부 예측 · 마켓 %d개 ]"%len(R))
print("   %-20s %5s %10s %10s %10s %10s"%("마켓","일수","추정연율","지수오차","선형오차","무변화오차"))
for _,r in R.sort_values("s_end",ascending=False).iterrows():
    print("   %-20s %5d %9.0f%% %9.1f%% %9.1f%% %9.1f%%"
          %(str(r.sym)[:20],r.days,r.r_hat*100,r.e_exp*100,r.e_lin*100,r.e_flat*100))
print("\n[ 판정 ]")
print("   중앙 오차 — 지수(이자) **%.1f%%** · 선형 %.1f%% · 무변화 %.1f%%"
      %(R.e_exp.median()*100,R.e_lin.median()*100,R.e_flat.median()*100))
w=(R.e_exp<R.e_lin)&(R.e_exp<R.e_flat)
print("   지수모형이 둘 다 이긴 마켓 **%d/%d (%.0f%%)**"%(w.sum(),len(R),w.mean()*100))
ok=R.e_exp.median()<0.30 and w.mean()>=0.6
print("   → %s"%("**메커니즘 확증: 지수 성장 = 이자 복리와 정합**" if ok
                 else "⚠ 확증 불가 — 지수모형이 지배적이지 않다"))
R.to_parquet(OUT/"accrual_test2.parquet")
