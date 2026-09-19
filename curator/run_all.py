# -*- coding: utf-8 -*-
"""재현 1커맨드 — `python alpha/curator/run_all.py`

RESULT_CURATOR_RISK.md 의 모든 수치를 처음부터 다시 만든다.
각 단계는 독립 실행 가능하며, 실패해도 다음 단계가 이전 산출물을 쓴다.

단계
  1 fetch_markets   Morpho 마켓 전수 + 주간 차입 이력      (~205s)
  2 fetch_alloc     볼트→마켓 배분 전수                    (~40s)
  3 fetch_prices    독립 가격(DefiLlama coins) + 교차용     (~75s)
  4 crossval        가격·자릿수·소스간 교차 검증            (V0~V3)
  5 verify_tokens   토큰 주소 진위 (심볼 위장 탐지)         (W4)
  6 principal2      커버리지<1 기준 사망일 → 실제 원금 복원
  7 real_exposure   볼트 명목 노출 → 실제 노출 역산
  8 accrual_test2   메커니즘 1차 검정 (확증 실패 — 기록용)
  9 regime_test     ★ 사전등록 팽창국면 정의로 재검정 (통과)
 10 euler           외부 타당성 (Euler v2 대조)
 11 snapshot        일별 패널 적재 (멱등)

옵션  --quick  이미 받은 데이터로 6~9 만 다시 계산
"""
from __future__ import annotations
import subprocess, sys, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
PY=sys.executable
FULL=["fetch_markets.py","fetch_alloc.py","fetch_prices.py","crossval.py",
      "verify_tokens.py","principal2.py","real_exposure.py","accrual_test2.py",
      "regime_test.py","euler.py","euler2.py","snapshot.py","build_site.py"]
QUICK=["principal2.py","real_exposure.py","regime_test.py","euler2.py","snapshot.py","build_site.py"]
def main():
    steps=QUICK if "--quick" in sys.argv else FULL
    t0=time.time(); fail=[]
    for i,s in enumerate(steps,1):
        p=HERE/s
        if not p.exists(): print("   [%d/%d] %-22s 없음 — 건너뜀"%(i,len(steps),s)); continue
        print("\n[%d/%d] %s"%(i,len(steps),s),flush=True)
        r=subprocess.run([PY,str(p)],cwd=str(HERE.parent.parent))
        if r.returncode!=0: fail.append(s); print("   ⚠ 실패 (계속 진행)")
    print("\n■ 완료 %.0fs · 실패 %d개 %s"%(time.time()-t0,len(fail),fail if fail else ""))
if __name__=="__main__": main()
