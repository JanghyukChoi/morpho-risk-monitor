# -*- coding: utf-8 -*-
"""★ 외부 타당성 — 명목 누적 팽창이 Morpho 고유 현상인가, 일반 현상인가.

Morpho 에서 발견: 담보 0 → 상환 불가 → 가동률 100% 고정 → 이자 복리로
                  supply/borrow 가 동시 팽창 → 명목값이 589배 과대.
질문:            이게 Morpho 설계 탓인가, **모든 무허가 대출 프로토콜의 구조**인가.
검정 대상:        Euler v2(EVK). 공개 REST API 사용(v3.euler.finance/v3, 무인증 100req/min).

★ 팽창의 지문 = 가동률 ≈ 1.0 이 장기 고정 + 차입액이 계속 증가
  Euler 에 같은 지문이 있으면 일반 현상이다.
"""
from __future__ import annotations
import time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT / "data"; OUT.mkdir(parents=True,exist_ok=True)
B="https://v3.euler.finance/v3"
S=requests.Session()
def g(ep,**kw):
    for a in range(4):
        try:
            r=S.get(B+ep,params=kw,timeout=90)
            if r.status_code==429: time.sleep(3+a*3); continue
            if r.status_code!=200: return None
            return r.json()
        except Exception:
            if a==3: return None
            time.sleep(2)
def run():
    ch=g("/chains"); chains=[c["id"] for c in (ch.get("data") or []) if c.get("status")=="active"]
    print("■ 활성 체인 %d개: %s"%(len(chains),chains))
    # ⚠ API 가 limit 을 100 으로 자른다. 빈 응답이 올 때까지 계속 넘긴다(체인별로도 시도).
    rows=[]; seen=set()
    for c in chains:
        off=0
        while True:
            d=g("/evk/vaults",chainId=c,limit=100,offset=off)
            if not d: break
            it=d.get("data") or []
            if not it: break
            new_=[x for x in it if (x.get("chainId"),x.get("address")) not in seen]
            for x in new_: seen.add((x.get("chainId"),x.get("address")))
            rows+=new_; off+=len(it)
            if len(it)<100: break
        time.sleep(0.2)
    V=pd.json_normalize(rows)
    print("■ EVK 볼트 %d개 수집"%len(V))
    for c in ("totalSupplyUsd","totalBorrowsUsd","utilization","supplyApy","borrowApy"):
        if c in V: V[c]=pd.to_numeric(V[c],errors="coerce")
    V["created"]=pd.to_datetime(V.createdAt,errors="coerce",utc=True).dt.tz_localize(None)
    V["age_d"]=(pd.Timestamp.now()-V.created).dt.days
    bd=[]
    for c in chains:
        d=g("/evk/vaults/bad-debt",chainId=c)
        if not d: continue
        it=d.get("data") or []
        for x in it: x["chainId"]=c
        bd+=it
        time.sleep(0.3)
    BD=pd.json_normalize(bd) if bd else pd.DataFrame()
    print("■ 악성부채 레코드 %d건"%len(BD))
    if len(BD): print("   필드: "+", ".join(sorted(BD.columns))[:400])
    V.to_parquet(OUT/"euler_vaults.parquet")
    if len(BD): BD.to_parquet(OUT/"euler_baddebt.parquet")
    return V,BD
if __name__=="__main__":
    V,BD=run()
    A=V[V.totalBorrowsUsd>1000].copy()
    print("\n[ 차입 $1K+ 볼트 %d개 / 전체 %d ]"%(len(A),len(V)))
    print("   공급 합 $%s · 차입 합 $%s"%(format(A.totalSupplyUsd.sum(),",.0f"),format(A.totalBorrowsUsd.sum(),",.0f")))
    print("\n[ ★ 팽창 지문 — 가동률 ≈ 1.0 인 볼트 ]")
    hi=A[A.utilization>=0.995]
    print("   가동률 99.5%%+ **%d개 (%.1f%%)** · 차입 합 $%s"
          %(len(hi),len(hi)/len(A)*100,format(hi.totalBorrowsUsd.sum(),",.0f")))
    if len(hi):
        print("   %-34s %6s %14s %14s %7s"%("볼트","나이","공급USD","차입USD","차입/공급"))
        for _,r in hi.nlargest(12,"totalBorrowsUsd").iterrows():
            rr=r.totalBorrowsUsd/max(r.totalSupplyUsd,1)
            print("   %-34s %5.0f일 $%13s $%13s %7.3f"
                  %(str(r["name"])[:34],r.age_d if r.age_d==r.age_d else -1,
                    format(r.totalSupplyUsd,",.0f"),format(r.totalBorrowsUsd,",.0f"),rr))
    print("\n[ ★★ 대조 — Morpho 의 부실 마켓은 차입/공급 = 1.000 이었다 ]")
    A["bs"]=A.totalBorrowsUsd/A.totalSupplyUsd.replace(0,np.nan)
    print("   Euler 차입/공급 ≥0.999 인 볼트 **%d개 (%.1f%%)**"%((A.bs>=0.999).sum(),(A.bs>=0.999).mean()*100))
    print("   차입/공급 분포: 중앙 %.3f · 90분위 %.3f · 최대 %.3f"%(A.bs.median(),A.bs.quantile(.9),A.bs.max()))
    if len(BD):
        print("\n[ Euler 악성부채 ]")
        num=[c for c in BD.columns if BD[c].dtype.kind in "fi"]
        print("   숫자 필드: %s"%", ".join(num[:8]))
        for c in num:
            if "usd" in c.lower() or "Usd" in c:
                print("   %s 합 $%s"%(c,format(pd.to_numeric(BD[c],errors='coerce').sum(),",.0f")))
