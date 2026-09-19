# -*- coding: utf-8 -*-
"""공개 모니터 페이지 생성 — data/ 의 패널을 정적 HTML 로 굽는다.

왜 정적인가
  GitHub Pages 는 정적만 호스팅한다(무료). 서버 비용 0원.
  매일 Actions 가 snapshot.py → build_site.py 를 돌려 index.html 을 갱신한다.

무엇을 보여주나 (남들이 안 하는 것만)
  1 명목 누적을 **교정한** 노출 — 이 교정이 이 사이트의 존재 이유다
  2 가격을 못 매기는 담보 — 판정 불가를 부실로 오인하지 않게
  3 커버리지 붕괴 마켓 — 현재 상태
  4 관측 이력 — 며칠째 재고 있는지 (채점 가능성의 근거)

사용  python curator/build_site.py     → index.html
"""
from __future__ import annotations
import html as _h
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "index.html"


def fnum(v, p=0):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:,.{p}f}"


def load(name):
    p = DATA / name
    return pd.read_parquet(p) if p.exists() else None


def section_impaired():
    """커버리지 붕괴 마켓 — 명목과 교정치를 나란히."""
    pm = load("panel_markets.parquet")
    pr = load("principal2.parquet")
    if pm is None:
        return "", 0
    pm["date"] = pd.to_datetime(pm.date)
    cur = pm[pm.date == pm.date.max()]
    imp = cur[(cur.flag_impaired == 1)].copy()
    defl = {}
    if pr is not None:
        for _, r in pr.iterrows():
            if r.get("infl") and np.isfinite(r["infl"]) and r["infl"] > 0:
                defl[r["mid"]] = 1.0 / r["infl"]
    rows = []
    for _, r in imp.sort_values("borrow_usd", ascending=False).head(25).iterrows():
        d = defl.get(r["mid"])
        real = r["supply_usd"] * d if d else None
        rows.append(
            "<tr><td>%s</td><td>%s</td><td class=n>%.2f</td><td class=n>%s</td>"
            "<td class=n>%s</td><td class=n %s>%s</td></tr>" % (
                _h.escape(str(r["coll"])[:22]), _h.escape(str(r["loan"])[:12]),
                r["lltv"], fnum(r["coll_usd"]), fnum(r["supply_usd"]),
                'class="n hi"' if real is not None else "class=n",
                fnum(real) if real is not None else "<span class=dim>not reconstructed</span>"))
    body = "".join(rows) or "<tr><td colspan=6 class=dim>none</td></tr>"
    return ("""<h2>Impaired markets <span class=sub>collateral no longer covers borrow</span></h2>
<p class=note><b>Nominal supply</b> keeps compounding once a position cannot be repaid.
<b>Corrected exposure</b> is the supply on the last day coverage was &ge; 1 &mdash; the principal
actually at risk. The gap between the two columns is why this page exists.</p>
<table><thead><tr><th>Collateral</th><th>Loan</th><th>LLTV</th><th>Collateral USD</th>
<th>Nominal supply</th><th>Corrected</th></tr></thead><tbody>%s</tbody></table>""" % body,
            len(imp))


def section_unpriced():
    pm = load("panel_markets.parquet")
    if pm is None:
        return "", 0
    pm["date"] = pd.to_datetime(pm.date)
    cur = pm[pm.date == pm.date.max()]
    up = cur[cur.flag_nopriced == 1].copy()
    g = (up.groupby("coll")
           .agg(n=("mid", "nunique"), borrow=("borrow_usd", "sum"))
           .sort_values("borrow", ascending=False).head(15))
    rows = "".join("<tr><td>%s</td><td class=n>%d</td><td class=n>%s</td></tr>"
                   % (_h.escape(str(k)[:26]), r["n"], fnum(r["borrow"]))
                   for k, r in g.iterrows())
    return ("""<h2>Unpriceable collateral <span class=sub>cannot be judged either way</span></h2>
<p class=note>With no price feed the collateral shows as $0. Reading that as impairment is a
<b>false positive</b> &mdash; 19 of our own first 34 flags were exactly this. Listed separately
rather than mixed into the table above.</p>
<table><thead><tr><th>Collateral</th><th>Markets</th><th>Reported borrow</th></tr></thead>
<tbody>%s</tbody></table>""" % (rows or "<tr><td colspan=3 class=dim>none</td></tr>"),
            len(up))


def section_vaults():
    re_ = load("real_exposure.parquet")
    if re_ is None or not len(re_):
        return ""
    rows = "".join(
        "<tr><td>%s</td><td>%s</td><td class=n>%s</td><td class=n>%s</td>"
        "<td class='n hi'>%s</td></tr>" % (
            _h.escape(str(r["vault"])[:30]),
            _h.escape(str(r["curator"])) if pd.notna(r["curator"]) else "<span class=dim>unregistered</span>",
            fnum(r["tvl"]), fnum(r["nominal"]), fnum(r["real"]))
        for _, r in re_.sort_values("real", ascending=False).head(15).iterrows())
    return """<h2>Vault exposure <span class=sub>nominal &rarr; corrected</span></h2>
<p class=note>Nominal total $482,404,560 &rarr; corrected <b>$819,198</b>, a ~589&times; difference.
Without this correction curators get flagged as impaired when they are not.
These are <b>exposure ceilings</b>, not realised losses.</p>
<table><thead><tr><th>Vault</th><th>Curator</th><th>Vault TVL</th>
<th>Nominal</th><th>Corrected</th></tr></thead><tbody>%s</tbody></table>""" % rows


def section_history():
    pm = load("panel_markets.parquet")
    if pm is None:
        return ""
    pm["date"] = pd.to_datetime(pm.date)
    g = (pm.groupby(pm.date.dt.date)
           .agg(markets=("mid", "nunique"), impaired=("flag_impaired", "sum"),
                nopriced=("flag_nopriced", "sum")).tail(30))
    rows = "".join("<tr><td>%s</td><td class=n>%d</td><td class=n>%d</td><td class=n>%d</td></tr>"
                   % (d, r["markets"], r["impaired"], r["nopriced"]) for d, r in g.iterrows())
    return """<h2>Observation log <span class=sub>each day's calls are recorded</span></h2>
<p class=note>Most tools make calls and never score them. Every day's flags are written down here.
Once enough incidents accumulate, precision and recall get published. While the record is short,
that is stated plainly rather than hidden.</p>
<table><thead><tr><th>Date</th><th>Markets</th><th>Impaired</th><th>Unpriceable</th></tr></thead>
<tbody>%s</tbody></table>""" % rows


CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a18;--dim:#71716c;--line:#e4e4e0;--hi:#b4461f;--card:#fff}
:root:not([data-theme=light]){}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){
 --bg:#16161a;--fg:#e8e8e4;--dim:#8f8f89;--line:#2c2c31;--hi:#e08a5f;--card:#1d1d22}}
:root[data-theme=dark]{--bg:#16161a;--fg:#e8e8e4;--dim:#8f8f89;--line:#2c2c31;--hi:#e08a5f;--card:#1d1d22}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:40px 16px 80px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:17px;margin:44px 0 6px;letter-spacing:-.01em}
.sub{font-weight:400;color:var(--dim);font-size:13px}
.lead{color:var(--dim);margin:0 0 28px;font-size:14px}
.note{color:var(--dim);font-size:13px;margin:0 0 14px;max-width:72ch}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:24px 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px}
.card .k{color:var(--dim);font-size:12px}
.card .v{font-size:22px;font-weight:600;letter-spacing:-.02em;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:4px}
th{text-align:left;font-weight:500;color:var(--dim);border-bottom:1px solid var(--line);padding:7px 8px;font-size:12px}
td{padding:7px 8px;border-bottom:1px solid var(--line)}
.n{text-align:right;font-variant-numeric:tabular-nums}
.hi{color:var(--hi);font-weight:600}
.dim{color:var(--dim)}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);font-size:12.5px}
a{color:inherit}
@media(max-width:640px){.wrap{padding:28px 16px 60px}table{font-size:12px}h1{font-size:22px}}
"""

TPL = """<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Morpho Risk Monitor</title>
<meta name=description content="Impaired exposure in Morpho lending markets, with nominal interest accrual stripped out.">
<style>%(css)s</style>
<div class=wrap>
<h1>Morpho Risk Monitor</h1>
<p class=lead>Impaired exposure in Morpho lending markets, with <b>nominal interest accrual
stripped out</b>. Rebuilt daily &middot; last update %(ts)s UTC</p>

<div class=cards>
 <div class=card><div class=k>Markets observed</div><div class=v>%(nmkt)s</div></div>
 <div class=card><div class=k>Impaired</div><div class=v>%(nimp)d</div></div>
 <div class=card><div class=k>Unpriceable</div><div class=v>%(nunp)d</div></div>
 <div class=card><div class=k>Days of record</div><div class=v>%(ndays)d</div></div>
</div>

%(impaired)s
%(vaults)s
%(unpriced)s
%(history)s

<footer>
<p><b>Method.</b> Principal is read as the supply on the last day coverage (collateral &divide;
borrow) was &ge; 1. Everything after that is interest accruing on debt that cannot be repaid.
On a preregistered test across 21 segments, median error was 4.8%% and an exponential model beat
both no-change and linear in 20 of 21.</p>
<p><b>Limits.</b> These are <b>exposure ceilings</b>, not realised losses. Some markets retain
recovery value, and mid-life vault deposits or withdrawals introduce error. The reported
<code>supplyApy</code> is off by roughly 300&times; for these markets and is not used.</p>
<p><b>Reproduce.</b> <code>python curator/run_all.py</code> &mdash; code, data and preregistrations
are all in <a href="https://github.com/JanghyukChoi/morpho-risk-monitor">this repository</a>,
including four approaches that were tested and rejected.</p>
</footer>
</div>
"""


def main():
    pm = load("panel_markets.parquet")
    nmkt = nimp = nunp = ndays = 0
    if pm is not None:
        pm["date"] = pd.to_datetime(pm.date)
        cur = pm[pm.date == pm.date.max()]
        nmkt, nimp = len(cur), int(cur.flag_impaired.sum())
        nunp, ndays = int(cur.flag_nopriced.sum()), pm.date.nunique()
    imp_html, _ = section_impaired()
    unp_html, _ = section_unpriced()
    OUT.write_text(TPL % dict(
        css=CSS, ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        nmkt=fnum(nmkt), nimp=nimp, nunp=nunp, ndays=ndays,
        impaired=imp_html, vaults=section_vaults(),
        unpriced=unp_html, history=section_history()), encoding="utf-8")
    print("index.html 생성 — 마켓 %s · 부실 %d · 가격불가 %d · 관측 %d일"
          % (fnum(nmkt), nimp, nunp, ndays))


if __name__ == "__main__":
    main()
