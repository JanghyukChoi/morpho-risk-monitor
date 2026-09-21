# -*- coding: utf-8 -*-
"""큐레이터 리스크 일별 스냅샷 — **오늘 시작해야 나중에 이력이 생긴다.**

■ 왜 필요한가
  `RESULT_CURATOR_RISK` 4부의 탐지(커버리지<1 → 사망일 복원)는 과거를 재구성한 것이다.
  이 방법이 **앞으로도 맞는지**는 예측을 남겨두고 채점해야만 알 수 있다.
  남들이 안 하는 것이 정확히 이것이다 — 예측만 하고 채점을 안 한다.

■ 무엇을 남기나
  markets  차입 $1K 이상 마켓의 상태 + **오늘의 손상 판정**
  alloc    볼트→마켓 배분 (누가 무엇에 물려 있는가)
  두 패널 모두 date 열을 갖고, 같은 날짜는 덮어쓴다(멱등).

■ 채점 방법 (나중에)
  오늘 flag=1 로 찍은 마켓이 이후 실제로 realizedBadDebt 를 냈는가.
  flag=0 인데 사고가 난 마켓은 놓친 것이다. 둘 다 세야 정직한 성적표가 된다.

사용:
    python alpha/curator/snapshot.py            # 오늘치 수집·append
    python alpha/curator/snapshot.py --check    # 신선도만 확인
    python alpha/curator/snapshot.py --score    # 지금까지 쌓인 예측 채점
"""
from __future__ import annotations
import sys, time, requests, numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"; OUT.mkdir(parents=True, exist_ok=True)
PM, PA = OUT/"panel_markets.parquet", OUT/"panel_alloc.parquet"
URL = "https://blue-api.morpho.org/graphql"
BORROW_MIN = 1000.0

QM = """query($s:Int!,$k:Int!){ markets(first:$s, skip:$k){ items{
  marketId lltv chain{id}
  collateralAsset{symbol address decimals priceUsd}
  loanAsset{symbol address decimals priceUsd}
  oracle{ type }
  warnings{ type level }
  badDebt{usd} realizedBadDebt{usd}
  state{ collateralAssets collateralAssetsUsd borrowAssets borrowAssetsUsd
         supplyAssets supplyAssetsUsd utilization netSupplyApy }
} pageInfo{countTotal} } }"""

QV = """query($s:Int!,$k:Int!){ vaults(first:$s, skip:$k){ items{
  name address chain{id}
  state{ totalAssetsUsd curators{name}
    allocation{ supplyAssetsUsd market{ marketId } } } }
  pageInfo{countTotal} } }"""

def _f(v, d=0.0):
    try: return float(v)
    except (TypeError, ValueError): return d

def _page(q, page, key, S):
    """GraphQL 페이지 순회.

    ⚠ 응답 검사는 **재시도 루프 안에서** 한다.
      예전에는 errors 키만 보고 break 한 뒤 밖에서 r["data"] 를 깠다.
      레이트리밋 응답은 errors 없이 message 만 들고 오므로 재시도를 그냥
      빠져나가 KeyError: 'data' 로 죽었다(2026-09-21 러너 실행).
      실패하면 상태코드와 본문 앞부분을 남긴다 — 원인을 못 보면 또 헤맨다.
    """
    rows, k = [], 0
    while True:
        blk = None
        for a in range(5):
            try:
                resp = S.post(URL, json={"query": q, "variables": {"s": page, "k": k}}, timeout=120)
                r = resp.json()
                if "errors" in r:
                    raise RuntimeError(str(r["errors"])[:200])
                d = r.get("data")
                if not isinstance(d, dict) or key not in d:
                    raise RuntimeError("HTTP %d · 응답에 data.%s 가 없다: %s"
                                       % (resp.status_code, key, str(r)[:160]))
                blk = d[key]
                break
            except Exception:
                if a == 4:
                    raise
                time.sleep(3 + a * 5)
        tot = blk["pageInfo"]["countTotal"]
        rows += blk["items"]; k += page
        if k >= tot: break
    return rows

def collect():
    S = requests.Session(); today = pd.Timestamp.now().normalize()
    M = []
    for x in _page(QM, 200, "markets", S):
        st = x.get("state") or {}; ca = x.get("collateralAsset") or {}; la = x.get("loanAsset") or {}
        b = _f(st.get("borrowAssetsUsd"))
        if b < BORROW_MIN: continue
        cd = ca.get("decimals") or 18; ld = la.get("decimals") or 18
        cusd = _f(st.get("collateralAssetsUsd"))
        M.append(dict(date=today, mid=x["marketId"], chain=(x.get("chain") or {}).get("id"),
            lltv=_f(x.get("lltv"))/1e18, coll=ca.get("symbol"), loan=la.get("symbol"),
            coll_price=_f(ca.get("priceUsd"), np.nan),
            coll_nat=_f(st.get("collateralAssets"))/(10**cd),
            coll_usd=cusd, borrow_usd=b, supply_usd=_f(st.get("supplyAssetsUsd")),
            util=_f(st.get("utilization")), apy=_f(st.get("netSupplyApy")),
            otype=(x.get("oracle") or {}).get("type"),
            bd=_f((x.get("badDebt") or {}).get("usd")),
            rbd=_f((x.get("realizedBadDebt") or {}).get("usd")),
            warn=";".join("%s:%s" % (w.get("type"), w.get("level")) for w in (x.get("warnings") or []))))
    M = pd.DataFrame(M)
    # ★ 오늘의 판정 — 나중에 채점하려면 지금 남겨야 한다
    M["cover"] = M.coll_usd / M.borrow_usd.replace(0, np.nan)
    M["price_ok"] = M.coll_price.notna() & (M.coll_price > 0)
    M["flag_impaired"] = ((M.cover < 1.0) & M.price_ok).astype(int)   # 가격 있는 것만 — 3부 교훈
    M["flag_nopriced"] = (~M.price_ok).astype(int)                     # 가격 없음 = 판정 불가
    A = []
    for v in _page(QV, 25, "vaults", S):
        st = v.get("state") or {}
        curs = [c["name"] for c in (st.get("curators") or []) if c.get("name")]
        for al in (st.get("allocation") or []):
            s = _f(al.get("supplyAssetsUsd"))
            if s <= 0: continue
            A.append(dict(date=today, vault=v.get("name"), vaddr=v.get("address"),
                curator=curs[0] if curs else None, vault_tvl=_f(st.get("totalAssetsUsd")),
                mid=((al.get("market") or {}).get("marketId")), my_supply=s))
    return M, pd.DataFrame(A)

def append(df, path, today):
    if path.exists():
        old = pd.read_parquet(path)
        old = old[pd.to_datetime(old.date).dt.normalize() != today]   # 멱등
        df = pd.concat([old, df], ignore_index=True)
    df.to_parquet(path)
    return df

def check():
    for p, n in ((PM, "markets"), (PA, "alloc")):
        if not p.exists(): print("   %-8s 없음" % n); continue
        d = pd.read_parquet(p); dt = pd.to_datetime(d.date)
        print("   %-8s %6d행 · %s ~ %s · %d일치 · 최신 %d일 전"
              % (n, len(d), str(dt.min())[:10], str(dt.max())[:10], dt.nunique(),
                 (pd.Timestamp.now().normalize()-dt.max().normalize()).days))

def score():
    """쌓인 예측 채점 — flag 이후 실제로 악성부채가 났는가."""
    if not PM.exists(): print("패널 없음"); return
    d = pd.read_parquet(PM); d["date"] = pd.to_datetime(d.date)
    days = sorted(d.date.unique())
    if len(days) < 2:
        print("[ 채점 ] 관측일 %d일 — **최소 2일 필요.** 내일 다시" % len(days)); return
    first, last = d[d.date == days[0]], d[d.date == days[-1]]
    m = first[["mid", "flag_impaired", "rbd"]].merge(
        last[["mid", "rbd"]], on="mid", suffixes=("_0", "_1"), how="inner")
    m["new_bd"] = (m.rbd_1 > m.rbd_0 + 1).astype(int)
    print("[ 채점 ] %s → %s (%d일) · 마켓 %d개"
          % (str(days[0])[:10], str(days[-1])[:10], (days[-1]-days[0]).astype("timedelta64[D]").astype(int), len(m)))
    tp = ((m.flag_impaired == 1) & (m.new_bd == 1)).sum(); fp = ((m.flag_impaired == 1) & (m.new_bd == 0)).sum()
    fn = ((m.flag_impaired == 0) & (m.new_bd == 1)).sum(); tn = ((m.flag_impaired == 0) & (m.new_bd == 0)).sum()
    print("   flag=1 & 사고발생 %3d · flag=1 & 무사고 %3d" % (tp, fp))
    print("   flag=0 & 사고발생 %3d · flag=0 & 무사고 %3d" % (fn, tn))
    if tp+fp: print("   정밀도 %.1f%%" % (tp/(tp+fp)*100))
    if tp+fn: print("   재현율 %.1f%%" % (tp/(tp+fn)*100))
    else: print("   ※ 기간 내 신규 사고 0건 — 채점 불가. 더 쌓아야 한다")

if __name__ == "__main__":
    if "--check" in sys.argv: check(); sys.exit()
    if "--score" in sys.argv: score(); sys.exit()
    t0 = time.time(); today = pd.Timestamp.now().normalize()
    M, A = collect()
    M = append(M, PM, today); A = append(A, PA, today)
    print("■ 스냅샷 %s · %.0fs" % (str(today)[:10], time.time()-t0))
    print("   markets %d행 (오늘 %d) · alloc %d행 (오늘 %d)"
          % (len(M), (pd.to_datetime(M.date).dt.normalize() == today).sum(),
             len(A), (pd.to_datetime(A.date).dt.normalize() == today).sum()))
    t = M[pd.to_datetime(M.date).dt.normalize() == today]
    print("   오늘 판정 — 손상 flag **%d개** · 가격불가 %d개 · 정상 %d개"
          % (t.flag_impaired.sum(), t.flag_nopriced.sum(),
             len(t)-t.flag_impaired.sum()-t.flag_nopriced.sum()))
    check()
