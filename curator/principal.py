# -*- coding: utf-8 -*-
"""★★ 실제 원금 복원 — 명목 누적을 시계열로 벗겨낸다.

3부 발견: 담보가 0 이 되면 가동률 100% 고정 + 이자 누적으로 supply/borrow 가
          **동시에 팽창**한다. 현재값으로는 손실을 못 잰다.
해법:     네이티브 단위 시계열(MarketHistory.supplyAssets)을 본다.
          팽창이 시작되기 **직전의 공급액**이 실제 원금이다.
          이벤트 로그 파싱보다 싸고, 데이터가 이미 있다.

⚠ 쿼리 복잡도 한도(1e6) 때문에 **마켓 1개씩** 조회한다.
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"
URL="https://blue-api.morpho.org/graphql"
Q="""query($id:String!,$opt:TimeseriesOptions){ markets(first:1, where:{uniqueKey_in:[$id]}){ items{
  marketId chain{id}
  collateralAsset{symbol decimals} loanAsset{symbol decimals}
  historicalState{
    supplyAssets(options:$opt){x y}
    borrowAssets(options:$opt){x y}
    collateralAssetsUsd(options:$opt){x y} } } } }"""

def ser(pts, dec=0):
    if not pts: return pd.Series(dtype=float)
    d={}
    for p in pts:
        y=p.get("y")
        if y is None: continue
        d[pd.to_datetime(p["x"],unit="s")]=float(y)/(10**dec if dec else 1)
    return pd.Series(d).sort_index()

def one(mid, opt, S):
    for a in range(4):
        try:
            r=S.post(URL,json={"query":Q,"variables":{"id":mid,"opt":opt}},timeout=120).json()
            if "errors" in r:
                print("   ERR %s %s"%(mid[:10],str(r["errors"])[:120])); return None
            it=r["data"]["markets"]["items"]
            return it[0] if it else None
        except Exception:
            if a==3: return None
            time.sleep(2+a*2)

def run():
    I=pd.read_parquet(OUT/"impaired_final.parquet")
    opt={"startTimestamp":1704067200,"endTimestamp":int(time.time()),"interval":"DAY"}
    S=requests.Session(); rows=[]; curves={}
    for i,mid in enumerate(I.mid.tolist()):
        x=one(mid,opt,S)
        if not x: continue
        h=x.get("historicalState") or {}
        ld=(x.get("loanAsset") or {}).get("decimals") or 18
        sp=ser(h.get("supplyAssets"),ld); bw=ser(h.get("borrowAssets"),ld)
        cu=ser(h.get("collateralAssetsUsd"))
        if not len(sp): continue
        sym="%s/%s"%((x.get("collateralAsset") or {}).get("symbol"),(x.get("loanAsset") or {}).get("symbol"))
        # 사망 시점 = 담보USD 가 마지막으로 $1,000 을 넘었던 날
        dead=None
        if len(cu):
            alive=cu[cu>1000]
            dead=alive.index[-1] if len(alive) else cu.index[0]
        pre=np.nan
        if dead is not None and len(sp.loc[:dead]): pre=sp.loc[:dead].iloc[-1]
        rows.append(dict(mid=mid,sym=sym,chain=(x.get("chain") or {}).get("id"),
            n=len(sp),first=sp.index[0],last=sp.index[-1],dead=dead,
            s_now=sp.iloc[-1],s_max=sp.max(),s_pre=pre,
            b_now=bw.iloc[-1] if len(bw) else np.nan,
            infl=(sp.iloc[-1]/pre) if (pre==pre and pre>0) else np.nan))
        curves[mid]=sp
        print("   %2d/%d %-20s 관측 %d일"%(i+1,len(I),sym[:20],len(sp)),flush=True)
        time.sleep(0.2)
    D=pd.DataFrame(rows).sort_values("s_now",ascending=False)
    D.to_parquet(OUT/"principal.parquet")
    return D,curves

if __name__=="__main__":
    D,curves=run()
    print("\n[ ★ 부실 마켓의 공급액 — 현재(명목) vs 사망 직전(실제 원금) ]")
    print("   %-20s %6s %16s %16s %9s %11s"%("마켓","관측일","현재공급(명목)","사망직전 공급","팽창배율","사망일"))
    for _,r in D.iterrows():
        print("   %-20s %6d %16s %16s %9s %11s"
              %(str(r.sym)[:20],r.n,format(r.s_now,",.0f"),
                format(r.s_pre,",.0f") if r.s_pre==r.s_pre else "-",
                ("%.1fx"%r.infl) if r.infl==r.infl else "-",
                str(r.dead)[:10] if r.dead is not None else "-"))
    v=D[D.s_pre.notna()]
    print("\n[ ★★ 결론 ]")
    print("   명목 공급 합       $%s"%format(D.s_now.sum(),",.0f"))
    print("   사망직전 공급 합    $%s  ← **실제 위험 원금**"%format(v.s_pre.sum(),",.0f"))
    if v.s_pre.sum()>0:
        print("   → 명목값은 실제를 **%.0f배** 과대평가한다"%(D.s_now.sum()/v.s_pre.sum()))
