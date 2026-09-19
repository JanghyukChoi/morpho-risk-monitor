# -*- coding: utf-8 -*-
"""★★★ 토큰 진위 검증 — 무허가 프로토콜에서 심볼은 위장될 수 있다.
   주소로 대조한다. 심볼을 믿으면 안 된다."""
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
M=pd.read_parquet(ROOT / "data"/"markets_priced.parquet")
REAL={  # 공식 주소 (체인별)
 (1,"USDC"):"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
 (1,"USDT"):"0xdac17f958d2ee523a2206206994597c13d831ec7",
 (1,"DAI"): "0x6b175474e89094c44da98b954eedeac495271d0f",
 (1,"WETH"):"0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
 (8453,"USDC"):"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
 (8453,"WETH"):"0x4200000000000000000000000000000000000006",
}
A=M[M.m_busd>1000].copy()
print("[ ★ 대출자산 주소 검증 — 공식 주소와 대조 ]")
bad=[]
for (ch,sym),addr in REAL.items():
    t=A[(A.chain==ch)&(A.loan==sym)]
    if not len(t): continue
    mism=t[t.loan_addr!=addr]
    print("   chain %-6d %-6s 마켓 %3d · 주소 불일치 **%d개**"%(ch,sym,len(t),len(mism)))
    for _,r in mism.iterrows():
        bad.append(r); print("      ⚠ %-14s 차입 $%14s · 주소 %s"%(str(r.coll)[:14],format(r.m_busd,",.0f"),r.loan_addr))
print("\n[ ★★ 거대 차입 마켓의 실체 ]")
big=A.nlargest(8,"m_busd")
for _,r in big.iterrows():
    ok=""
    k=(r.chain,r.loan)
    if k in REAL: ok="✅공식" if r.loan_addr==REAL[k] else "❌**위장 토큰**"
    print("   %-14s/%-8s chain %-6s 차입 $%14s  대출주소 %s %s"
          %(str(r.coll)[:14],str(r.loan)[:8],r.chain,format(r.m_busd,",.0f"),str(r.loan_addr)[:20],ok))
print("\n[ ★ 정합성 — Morpho 전체와 대조 ]")
print("   차입 상위 8개 합 $%s · 전체 차입 합 $%s → 상위8 비중 **%.1f%%**"
      %(format(big.m_busd.sum(),",.0f"),format(A.m_busd.sum(),",.0f"),big.m_busd.sum()/A.m_busd.sum()*100))
print("   ※ Morpho 공시 TVL 은 약 $10B 규모다. 한 마켓이 $9.1B 차입은 물리적으로 불가능하다")
print("\n[ ★★★ 신뢰 가능 우주 정의 — 공식 주소 대출자산만 ]")
A["loan_ok"]=A.apply(lambda r: REAL.get((r.chain,r.loan))==r.loan_addr if (r.chain,r.loan) in REAL else np.nan,axis=1)
known=A[A.loan_ok.notna()]
print("   대출자산을 검증할 수 있는 마켓 %d개 · 그 중 공식 %d개 (%.1f%%) · **위장 %d개**"
      %(len(known),(known.loan_ok==True).sum(),(known.loan_ok==True).mean()*100,(known.loan_ok==False).sum()))
print("   위장 마켓의 표기 차입 합 $%s ← **전부 허수**"%format(known[known.loan_ok==False].m_busd.sum(),",.0f"))
print("   공식 마켓의 차입 합 $%s"%format(known[known.loan_ok==True].m_busd.sum(),",.0f"))
V=known[known.loan_ok==True].copy()
V["c_price"]=pd.to_numeric(V.c_price,errors="coerce")
V["cusd"]=V.coll_nat*V.c_price
V["cover"]=V.cusd/V.m_busd.replace(0,np.nan)
imp=V[(V.c_price>0)&(V.cover<1)].sort_values("m_busd",ascending=False)
print("\n[ ★★★ 최종 — 검증된 우주에서 진짜 부실 마켓 ]")
print("   대상 %d개 중 담보<차입 **%d개**"%(len(V[V.c_price>0]),len(imp)))
print("   %-14s %-8s %14s %14s %7s %6s"%("담보","대출","차입","담보","커버","LLTV"))
for _,r in imp.iterrows():
    print("   %-14s %-8s $%13s $%13s %6.3f %6.2f"
          %(str(r.coll)[:14],str(r.loan)[:8],format(r.m_busd,",.0f"),format(r.cusd,",.0f"),r.cover,r.lltv))
imp.to_parquet(ROOT / "data"/"impaired_final.parquet")
print("\n   부실 총 부족분 $%s"%format((imp.m_busd-imp.cusd).sum(),",.0f"))
