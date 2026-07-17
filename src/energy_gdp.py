#!/usr/bin/env python3
"""Build the "high-GDP, low-energy country" project page.

Offline analytics job (see CLAUDE.md "Python Analytics Pattern"): reads the
saved raw datasets in ``data/``, characterises the joint distribution of
GDP per capita and primary energy use per capita across the full 2000-2023
panel, and writes a fully static page to ``frontend/``. No network, no HTTP.

    uv run python src/energy_gdp.py

Inputs  (data/):
    owid-primary-energy-per-capita.csv                     OWID (Energy Institute
        Statistical Review; Ember) primary energy per capita, kWh/yr, all years.
    worldbank-gdp-per-capita-current-usd-2000-2023.json    World Bank
        NY.GDP.PCAP.CD, current US$, 2000-2023.

Outputs (frontend/):
    energy-gdp.html                       the rendered page (data baked in)
    files/energy-gdp-panel-2000-2023.csv  the merged country-year panel
"""
import json
import csv
import math
import html
from collections import defaultdict
from pathlib import Path

Y0YEAR, Y1YEAR = 2000, 2023
PUB_DATE = "17 July 2026"

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data"
FRONTEND = REPO / "frontend"

ENERGY_CSV = RAW / "owid-primary-energy-per-capita.csv"
GDP_JSON = RAW / "worldbank-gdp-per-capita-current-usd-2000-2023.json"
OUT_HTML = FRONTEND / "energy-gdp.html"
OUT_CSV = FRONTEND / "files" / "energy-gdp-panel-2000-2023.csv"

# Low-energy threshold for the "empty corner": no high-income (>= $30k)
# country-year falls below this many kWh of primary energy per capita.
LOW_KWH = 15000

# World Bank aggregate/region codes to exclude so only sovereign entities remain.
AGG = {"AFE", "AFW", "ARB", "CEB", "CSS", "EAP", "EAR", "EAS", "ECA", "ECS",
       "EMU", "EUU", "FCS", "HIC", "HPC", "IBD", "IBT", "IDA", "IDB", "IDX",
       "LAC", "LCN", "LDC", "LIC", "LMC", "LMY", "LTE", "MEA", "MIC", "MNA",
       "NAC", "OED", "OSS", "PRE", "PSS", "PST", "SAS", "SSA", "SSF", "SST",
       "TEA", "TEC", "TLA", "TMN", "TSA", "TSS", "UMC", "WLD", "INX"}


def esc(s):
    return html.escape(str(s))


def compact_years(years):
    """[2001,2002,2003,2005] -> '2001-2003, 2005'"""
    ys = sorted(years)
    runs, start, prev = [], ys[0], ys[0]
    for y in ys[1:]:
        if y == prev + 1:
            prev = y
            continue
        runs.append((start, prev))
        start = prev = y
    runs.append((start, prev))
    return ", ".join(f"{a}-{b}" if a != b else f"{a}" for a, b in runs)


# --------------------------------------------------------------- data & stats
def load_panel():
    """Return list of (iso, name, year, gdp, energy) with both values present."""
    energy = {}
    with open(ENERGY_CSV) as f:
        for row in csv.DictReader(f):
            c = row["code"]
            if c and len(c) == 3:
                try:
                    energy[(c, int(row["year"]))] = float(row["primary_energy_consumption_per_capita__kwh"])
                except ValueError:
                    pass
    panel = []
    for r in json.load(open(GDP_JSON))[1]:
        iso = r["countryiso3code"]
        if r["value"] is None or iso in AGG:
            continue
        yr = int(r["date"])
        e = energy.get((iso, yr))
        g = float(r["value"])
        if e and g > 0 and e > 0:
            panel.append((iso, r["country"]["value"], yr, round(g, 1), round(e, 1)))
    panel.sort(key=lambda p: (p[0], p[2]))
    return panel


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    return cov / math.sqrt(va * vb)


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_vals[int(idx)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def analyse(panel):
    X = [math.log10(g) for _, _, _, g, _ in panel]
    Y = [math.log10(e) for _, _, _, _, e in panel]
    n = len(panel)
    mx, my = sum(X) / n, sum(Y) / n
    beta = sum((X[i] - mx) * (Y[i] - my) for i in range(n)) / sum((x - mx) ** 2 for x in X)
    alpha = my - beta * mx
    resid = [Y[i] - (alpha + beta * X[i]) for i in range(n)]
    sigma = math.sqrt(sum(e * e for e in resid) / (n - 2))
    r = pearson(X, Y)
    rho = pearson(ranks(X), ranks(Y))

    # within / between decomposition
    byc = defaultdict(list)
    for i, p in enumerate(panel):
        byc[p[0]].append(i)
    gbar = {c: sum(X[i] for i in idx) / len(idx) for c, idx in byc.items()}
    ebar = {c: sum(Y[i] for i in idx) / len(idx) for c, idx in byc.items()}
    rb = pearson([gbar[c] for c in byc], [ebar[c] for c in byc])
    wx, wy = [], []
    for c, idx in byc.items():
        if len(idx) >= 5:
            for i in idx:
                wx.append(X[i] - gbar[c])
                wy.append(Y[i] - ebar[c])
    rw = pearson(wx, wy)
    bw = sum(wx[i] * wy[i] for i in range(len(wx))) / sum(x * x for x in wx)

    # empty-corner support statement
    hi = [(p, e) for p, e in zip(panel, [10 ** y for y in Y]) if p[3] >= 30000]
    hi_min = min(hi, key=lambda t: t[0][4])[0]
    below = sum(1 for p, _ in hi if p[4] < LOW_KWH)

    return {
        "n": n, "beta": beta, "alpha": alpha, "sigma": sigma, "r": r, "rho": rho,
        "r2": r * r, "rb": rb, "rw": rw, "bw": bw, "ncountries": len(byc),
        "hi_n": len(hi), "hi_min": hi_min, "below": below,
        "X": X, "Y": Y,
    }


# --------------------------------------------------------------- density SVG
# sequential single-hue (blue) ramp, light -> dark, for log-count cells
RAMP = ["#e7edf4", "#c3d2e2", "#96afca", "#688cb0", "#436a92", "#274a6b"]


def build_density(panel, st):
    VW, VH = 760, 560
    PX0, PX1 = 92, 700          # plot area (leave room for density legend at right)
    PY0, PY1 = 30, 496
    X, Y = st["X"], st["Y"]
    XMIN, XMAX = min(X) - 0.06, max(X) + 0.06
    YMIN, YMAX = min(Y) - 0.10, max(Y) + 0.10
    NX, NY = 30, 26
    dx = (XMAX - XMIN) / NX
    dy = (YMAX - YMIN) / NY

    def sx(lg):   # lg = log10(gdp)
        return PX0 + (lg - XMIN) / (XMAX - XMIN) * (PX1 - PX0)

    def sy(le):   # le = log10(elec)
        return PY1 - (le - YMIN) / (YMAX - YMIN) * (PY1 - PY0)

    # 2-D histogram (track members per bin for hover tooltips)
    grid = defaultdict(int)
    members = defaultdict(list)
    for i in range(len(X)):
        ix = min(NX - 1, int((X[i] - XMIN) / dx))
        iy = min(NY - 1, int((Y[i] - YMIN) / dy))
        grid[(ix, iy)] += 1
        members[(ix, iy)].append((panel[i][1], panel[i][2]))  # (country, year)
    cmax = max(grid.values())

    def color(c):
        t = math.log(c) / math.log(cmax) if cmax > 1 else 1.0
        return RAMP[min(len(RAMP) - 1, int(t * (len(RAMP) - 1) + 1e-9))]

    s = [f'<svg viewBox="0 0 {VW} {VH}" role="img" aria-label="Density of {st["n"]} '
         f'country-year observations in the log GDP per capita by log energy use per '
         f'capita plane, {Y0YEAR}-{Y1YEAR}" xmlns="http://www.w3.org/2000/svg" class="scatter tex2jax_ignore">']
    s.append('<style>'
             '.scatter text{font-family:et-bembo,Palatino,Georgia,serif;fill:#111}'
             '.ax{font-size:15px;fill:rgba(17,17,17,.55)}'
             '.axtitle{font-size:16px;font-style:italic;fill:rgba(17,17,17,.75)}'
             '.cell{stroke:#fffdf6;stroke-width:.5}'
             '.pt{fill:#1d2b3a;fill-opacity:.9}'
             '.lbl{font-size:12.5px;fill:#2d2d2d}'
             '.lbl-guy{font-size:12.5px;fill:#a63d40;font-style:italic}'
             '.grid{stroke:rgba(17,17,17,.10);stroke-width:1}'
             '.ols{stroke:#8b2252;stroke-width:2;fill:none}'
             '.wall{stroke:#445c3c;stroke-width:2;fill:none;stroke-dasharray:6 3}'
             '.frame{stroke:rgba(17,17,17,.30);stroke-width:1;fill:none}'
             '.empty{fill:none;stroke:#a63d40;stroke-width:1.3;stroke-dasharray:5 4}'
             '.empty-lbl{font-size:13px;fill:#a63d40;font-style:italic}'
             '.leg{font-size:12px;fill:rgba(17,17,17,.6)}'
             '</style>')

    # cells
    for (ix, iy), c in sorted(grid.items()):
        x = sx(XMIN + ix * dx)
        y = sy(YMIN + (iy + 1) * dy)
        w = sx(XMIN + (ix + 1) * dx) - x
        h = sy(YMIN + iy * dy) - y
        bycountry = defaultdict(list)
        for cn, yr in members[(ix, iy)]:
            bycountry[cn].append(yr)
        tip = "\n".join(f"{cn}: {compact_years(yrs)}"
                        for cn, yrs in sorted(bycountry.items()))
        s.append(f'<rect class="cell" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                 f'height="{h:.1f}" fill="{color(c)}" data-tip="{esc(tip)}"/>')

    # gridlines + ticks
    for g, lab in [(1000, '$1k'), (10000, '$10k'), (100000, '$100k')]:
        x = sx(math.log10(g))
        s.append(f'<line class="grid" x1="{x:.1f}" y1="{PY0}" x2="{x:.1f}" y2="{PY1}"/>')
        s.append(f'<text class="ax" x="{x:.1f}" y="{PY1 + 22}" text-anchor="middle">{lab}</text>')
    for e, lab in [(100, '100'), (1000, '1,000'), (10000, '10,000'), (100000, '100,000')]:
        y = sy(math.log10(e))
        s.append(f'<line class="grid" x1="{PX0}" y1="{y:.1f}" x2="{PX1}" y2="{y:.1f}"/>')
        s.append(f'<text class="ax" x="{PX0 - 10}" y="{y + 5:.1f}" text-anchor="end">{lab}</text>')

    # 5th-percentile lower envelope ("the wall"): per GDP bin
    wall = []
    for ix in range(NX):
        lo, hiv = XMIN + ix * dx, XMIN + (ix + 1) * dx
        ys = sorted(10 ** Y[i] for i in range(len(X)) if lo <= X[i] < hiv)
        if len(ys) >= 12:
            wall.append((sx((lo + hiv) / 2), sy(math.log10(percentile(ys, 0.05)))))
    if wall:
        s.append('<polyline class="wall" points="' + ' '.join(f'{x:.1f},{y:.1f}' for x, y in wall) + '"/>')

    # OLS line
    gx0, gx1 = 10 ** XMIN, 10 ** XMAX
    ly0 = st["alpha"] + st["beta"] * math.log10(gx0)
    ly1 = st["alpha"] + st["beta"] * math.log10(gx1)
    s.append(f'<line class="ols" x1="{sx(XMIN):.1f}" y1="{sy(ly0):.1f}" x2="{sx(XMAX):.1f}" y2="{sy(ly1):.1f}"/>')

    # empty-corner outline: G >= $30k and E < LOW_KWH
    ex0, ey0 = sx(math.log10(30000)), sy(math.log10(LOW_KWH))
    s.append(f'<rect class="empty" x="{ex0:.1f}" y="{ey0:.1f}" width="{PX1 - ex0:.1f}" height="{PY1 - ey0:.1f}"/>')
    cx = (ex0 + PX1) / 2
    s.append(f'<text class="empty-lbl" x="{cx:.1f}" y="{(ey0 + PY1) / 2 - 5:.1f}" text-anchor="middle">no mass:</text>')
    s.append(f'<text class="empty-lbl" x="{cx:.1f}" y="{(ey0 + PY1) / 2 + 12:.1f}" text-anchor="middle">0 of {st["hi_n"]} country-years</text>')

    # a few labelled extreme points (2023 values). The petrostates (Turkmenistan,
    # Trinidad) sit high above the line: energy without the matching wealth.
    latest = {p[0]: p for p in panel if p[2] == Y1YEAR}
    marks = {'QAT': (-6, -7, 'end', 'Qatar'), 'NOR': (0, 16, 'middle', 'Norway'),
             'TTO': (0, -10, 'middle', 'Trinidad & Tobago'),
             'TKM': (-8, 4, 'end', 'Turkmenistan'),
             'MAC': (-8, 4, 'end', 'Macao'),
             'COD': (8, 4, 'start', 'DR Congo'),
             'SLE': (8, 4, 'start', 'Sierra Leone')}
    for iso, (dxp, dyp, anch, name) in marks.items():
        if iso not in latest:
            continue
        p = latest[iso]
        px, py = sx(math.log10(p[3])), sy(math.log10(p[4]))
        s.append(f'<circle class="pt" cx="{px:.1f}" cy="{py:.1f}" r="3.2"/>')
        s.append(f'<text class="lbl" x="{px + dxp:.1f}" y="{py + dyp:.1f}" text-anchor="{anch}">{esc(name)}</text>')

    # frame + axis titles
    s.append(f'<rect class="frame" x="{PX0}" y="{PY0}" width="{PX1 - PX0}" height="{PY1 - PY0}"/>')
    s.append(f'<text class="axtitle" x="{(PX0 + PX1) / 2:.1f}" y="{VH - 8}" text-anchor="middle">GDP per capita (US$, log scale)</text>')
    mid = (PY0 + PY1) / 2
    s.append(f'<text class="axtitle" x="22" y="{mid:.1f}" text-anchor="middle" transform="rotate(-90 22 {mid:.1f})">Primary energy use per capita (kWh/yr, log scale)</text>')

    # density legend (vertical ramp at right)
    lx, lw = 716, 14
    ly_top, lh = 120, 200
    seg = lh / len(RAMP)
    for k, col in enumerate(RAMP):
        s.append(f'<rect x="{lx}" y="{ly_top + (len(RAMP) - 1 - k) * seg:.1f}" width="{lw}" height="{seg:.1f}" fill="{col}"/>')
    s.append(f'<text class="leg" x="{lx + lw + 5}" y="{ly_top + 4}">{cmax}</text>')
    s.append(f'<text class="leg" x="{lx + lw + 5}" y="{ly_top + lh:.1f}">1</text>')
    s.append(f'<text class="leg" x="{lx + lw / 2:.0f}" y="{ly_top - 22}" text-anchor="middle">country-</text>')
    s.append(f'<text class="leg" x="{lx + lw / 2:.0f}" y="{ly_top - 22}" text-anchor="middle" dy="1.1em">years/cell</text>')
    s.append('</svg>')
    return '\n'.join(s)


# --------------------------------------------------------------- tables
def floor_rows(panel):
    out = []
    for thr in [1000, 5000, 10000, 20000, 30000, 50000]:
        grp = [p for p in panel if p[3] >= thr]
        fl = min(grp, key=lambda p: p[4])
        cy = len({p[0] for p in grp})
        out.append(f'<tr><td class="value">\\${thr:,}</td><td class="value">{cy}</td>'
                   f'<td class="value">{fl[4]:,.0f}</td><td>{esc(fl[1])} ({fl[2]})</td></tr>')
    return '\n'.join(out)


PAGE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
    <title>Jonathan Keogh | There are no rich, low-energy countries</title>
    <link rel="stylesheet" href="style.css" type="text/css" fetchpriority="high" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
    <meta name="author" content="Jonathan Keogh" />
    <meta name="description" content="Across the full 2000-2023 panel of 4,700+ country-years, the joint law of GDP per capita and primary energy use per capita puts no mass in the high-income, low-energy corner." />
    <script>
      MathJax = {{
        tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']], processEscapes: true }},
        options: {{ skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'], ignoreHtmlClass: 'tex2jax_ignore' }}
      }};
    </script>
    <script id="MathJax-script" async crossorigin="anonymous" src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
</head>
<body class="">
    <aside id="asidebar">
        <div id="logo">
            <a href="/">Jonathan<br>Keogh</a>
        </div>
        <nav class="main-menu">
<ul>
    <li><a href="writing.html">Blog</a></li>
    <li><a href="about.html">About</a></li>
    <li><a href="projects.html">Projects</a></li>
    <li><a href="links.html">Interesting Links</a></li>
</ul>        </nav>

<ul id="social">
    <li><a href="https://github.com/jonathankeogh/" title="GitHub" target=_blank rel="me noopener"><img alt="GitHub" src="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='%23000' aria-label='GitHub'><path d='M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12'/></svg>"></a></li>
    <li><a href="https://www.linkedin.com/in/jonathan-keogh-287235101/" title="LinkedIn" target=_blank rel="me noopener"><img alt="LinkedIn" src="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='%23000' aria-label='LinkedIn'><path d='M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z'/></svg>"></a></li>
</ul>    </aside>
    <main>            <article class="post">
                <header>
                    <h1>There are no rich, low-energy countries</h1>
                    <p><span class="newthought">Jonathan Keogh</span></p>
                    <div class="article-meta">
                        <p><span class="newthought">Filed under &ldquo;<a href="writing.html" rel="tag">Blog</a>&rdquo; &middot; {y1_month}</span></p>
                    </div>
                </header>
<section>
<p>Take every country with both figures reported, once per year from {y0} to {y1}: a panel of <strong>{n:,} country-year observations</strong> of GDP per capita $G$ and primary energy use per capita $E$&mdash;<em>all</em> energy a country consumes, not just the fifth or so delivered as electricity. The title is a statement about the <em>support</em> of their joint law&mdash;the region $\\{{G \\text{{ large}},\\, E \\text{{ small}}\\}}$ carries no mass&mdash;and it survives a close look. It is the sharper claim: a rich country must command a great deal of energy, which is why cheap and secure energy supply is not a luxury but a precondition for prosperity.</p>
</section>

<section>
<h2>The fit</h2>
<p>Both variables range over three orders of magnitude, so work in logs. Ordinary least squares on the pooled panel gives</p>
<div class="math">$$\\log_{{10}} E \\;=\\; \\alpha + \\beta\\,\\log_{{10}} G + \\varepsilon,\\qquad \\hat\\beta = {beta:.2f},\\quad \\hat\\alpha = {alpha:.2f}.$$</div>
<p>The relationship is tight and monotone: Pearson $r = {r:.2f}$ ($R^2 = {r2:.2f}$), Spearman $\\rho = {rho:.2f}$, residual scatter $\\hat\\sigma = {sigma:.2f}$ dex&mdash;a typical country sits within a factor of $10^{{{sigma:.2f}}} \\approx {sigfac:.1f}$ of the line. Since $\\hat\\beta \\approx 1$, energy use is very nearly proportional to income: energy intensity $E/G$ is roughly scale-invariant across the entire development range.</p>
</section>

<section>
<h2>All {nyears} years at once</h2>
<p>Rather than one map per year, bin the whole panel and shade each cell by how many country-years land in it. The mass concentrates on a straight diagonal band; the lower-right is blank.</p>
<figure class="fullwidth">
{density}
<figcaption>Empirical joint density of all {n:,} country-years, {y0}&ndash;{y1}, on log&ndash;log axes. Cell shade is the (log-scaled) count. Burgundy: the OLS line above. Green dashed: the 5th-percentile lower envelope&mdash;the &ldquo;wall.&rdquo; The red box marks GDP $\\ge$ \\${thr30}k and $E < $ {thr2c}&nbsp;kWh, which holds <strong>0 of {hi_n}</strong> qualifying country-years. The upper-left, by contrast, is populated: petrostates burn rich-world quantities of energy on modest incomes.</figcaption>
</figure>
</section>

<section>
<h2>The other corner: energy without wealth</h2>
<p>The empty region is the lower-right; the <em>upper</em>-left is not empty at all, and it says something important. The conspicuous outliers far above the line are petrostates: Turkmenistan (about \\$5,300 per head, yet roughly 59,500&nbsp;kWh of primary energy&mdash;some <strong>5&times; above</strong> the fit) and Trinidad&nbsp;&amp; Tobago (about \\$18,300 and 109,000&nbsp;kWh, roughly 3&times; above).<label for="sn-oc" class="margin-toggle sidenote-number"></label><input type="checkbox" id="sn-oc" class="margin-toggle"><span class="sidenote">Both sit on abundant domestic gas; consumption is inflated by subsidised prices, flaring, and energy-intensive export industry&mdash;LNG, ammonia, petrochemicals.</span> These economies have cheap, secure energy in abundance&mdash;and remain middle-income. So the implication runs strictly one way. A great deal of energy is <em>necessary</em> for wealth but not <em>sufficient</em>: energy that is merely extracted and burned, rather than converted into productive capital and diversified output, buys tonnes of oil-equivalent but not much GDP. The empty lower-right is the binding constraint; the populated upper-left is the reminder that clearing it is only the first step.</p>
</section>

<section>
<h2>Between countries vs. within one</h2>
<p>A pooled correlation conflates two questions. Split each series into a country mean and a deviation from it, $\\log_{{10}} X_{{it}} = \\bar X_i + \\tilde X_{{it}}$, and measure each piece separately:</p>
<ul>
<li><strong>Between</strong> the {ncountries} countries (their long-run means): $r_B = {rb:.2f}$. Richer nations use more&mdash;the cross-section.</li>
<li><strong>Within</strong> a country over time (deviations): $r_W = {rw:.2f}$, slope $\\beta_W = {bw:.2f}$. When a country&rsquo;s own income rises, its energy use rises too, but sub-proportionally&mdash;efficiency improves and the mix tilts toward less energy-intensive services.</li>
</ul>
<p>Both signs agree. The pattern is not an artifact of comparing nations frozen at one instant; it also holds along each country&rsquo;s own trajectory.</p>
</section>

<section>
<h2>The empty corner</h2>
<p>The claim concerns the lower edge of the cloud, not its center. Binning by income and taking the 5th percentile of $E$ (the green wall) yields a lower envelope that is monotone increasing: lift the income floor and the energy floor lifts with it. Sharpening to the corner, of the <strong>{hi_n} country-years</strong> with $G \\ge \\${thr30}{{,}}000$, none has $E$ below {thr2c}&nbsp;kWh&mdash;the lowest is {hi_min_e:,.0f}&nbsp;kWh ({hi_min_name}, {hi_min_year}). Empirically</p>
<div class="math">$$\\widehat{{\\Pr}}\\bigl(E < {thr2}\\ \\text{{kWh}} \\;\\big|\\; G \\ge \\${thr30}\\text{{k}}\\bigr) \\;=\\; \\frac{{0}}{{{hi_n}}} \\;=\\; 0.$$</div>
<div id="table-container">
<table>
<thead><tr><th>Countries with GDP/capita $\\ge$&hellip;</th><th style="text-align:right"># countries</th><th style="text-align:right">min $E$ (kWh)</th><th>attained by</th></tr></thead>
<tbody>
{floor}
</tbody>
</table>
</div>
</section>

<section>
<h2>Two caveats</h2>
<p>First, country-years are not independent: a country contributes up to {nyears} near-repeated points, so the effective sample is far below {n:,}. The honest content is <em>persistence across {nyears} annual cross-sections</em>, not {n:,} independent draws. Second, correlation fixes no direction&mdash;cheap energy enables output and output funds energy, with common drivers (industrialisation, institutions) behind both.<label for="sn-1" class="margin-toggle sidenote-number"></label><input type="checkbox" id="sn-1" class="margin-toggle"><span class="sidenote">The literature calls this the &ldquo;energy&ndash;growth nexus&rdquo;; the direction of causation genuinely varies by country.</span> Neither caveat touches the support statement, which is what the title asserts: no country has yet been wealthy without consuming a great deal of energy.</p>
</section>

                <footer class="de-emphasize">
                    <p>Sources: Our World in Data (Energy Institute Statistical Review of World Energy; U.S. EIA) &amp; World Bank, {y0}&ndash;{y1}. <a href="files/energy-gdp-panel-2000-2023.csv">Download the panel (CSV)</a>.</p>
                </footer>
            </article>

        <footer>
<p class="de-emphasize copyright">&copy;2026 Jonathan Keogh. All rights reserved.</p>        </footer>
    </main>
{tooltip_js}
</body>
</html>
'''


TIP_JS = r'''<script>
(function () {
  var svg = document.querySelector('svg.scatter');
  if (!svg) return;
  var tip = document.createElement('div');
  tip.className = 'cell-tip';
  tip.setAttribute('role', 'tooltip');
  document.body.appendChild(tip);
  var current = null;

  function render(text) {
    tip.textContent = '';
    text.split('\n').forEach(function (line) {
      var row = document.createElement('div');
      row.className = 'ct-row';
      var i = line.indexOf(': ');
      if (i < 0) {
        row.textContent = line;
      } else {
        var c = document.createElement('span');
        c.className = 'ct-country';
        c.textContent = line.slice(0, i);
        row.appendChild(c);
        row.appendChild(document.createTextNode(' ' + line.slice(i + 2)));
      }
      tip.appendChild(row);
    });
  }

  function place(e) {
    var pad = 16;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var x = e.clientX + pad, y = e.clientY + pad;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
    if (x < 8) x = 8;
    if (y < 8) y = 8;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }

  svg.addEventListener('mousemove', function (e) {
    var cell = e.target.closest('.cell');
    var data = cell && cell.getAttribute('data-tip');
    if (data) {
      if (cell !== current) { render(data); current = cell; }
      tip.classList.add('is-on');
      place(e);
    } else {
      tip.classList.remove('is-on');
      current = null;
    }
  });
  svg.addEventListener('mouseleave', function () {
    tip.classList.remove('is-on');
    current = null;
  });
})();
</script>'''


def main():
    panel = load_panel()
    st = analyse(panel)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["iso3", "country", "year", "gdp_per_capita_usd", "primary_energy_per_capita_kwh"])
        for iso, name, yr, g, e in panel:
            w.writerow([iso, name, yr, g, e])

    hm = st["hi_min"]
    page = PAGE.format(
        y0=Y0YEAR, y1=Y1YEAR, nyears=Y1YEAR - Y0YEAR + 1, n=st["n"],
        beta=st["beta"], alpha=st["alpha"], r=st["r"], r2=st["r2"], rho=st["rho"],
        sigma=st["sigma"], sigfac=10 ** st["sigma"],
        rb=st["rb"], rw=st["rw"], bw=st["bw"], ncountries=st["ncountries"],
        hi_n=st["hi_n"], hi_min_e=hm[4], hi_min_name=esc(hm[1]), hi_min_year=hm[2],
        thr30=30, thr2=LOW_KWH, thr2c=f"{LOW_KWH:,}", y1_month=PUB_DATE,
        density=build_density(panel, st), floor=floor_rows(panel),
        tooltip_js=TIP_JS,
    )
    OUT_HTML.write_text(page)
    print(f"wrote {OUT_HTML.relative_to(REPO)} ({len(page):,} bytes)")
    print(f"wrote {OUT_CSV.relative_to(REPO)} ({st['n']:,} rows)")
    print(f"n={st['n']}  beta={st['beta']:.3f}  r={st['r']:.3f}  rho={st['rho']:.3f}  "
          f"R2={st['r2']:.3f}  rB={st['rb']:.3f}  rW={st['rw']:.3f}  betaW={st['bw']:.3f}")
    print(f"empty corner: {st['below']} of {st['hi_n']} high-income country-years below {LOW_KWH:,} kWh")


if __name__ == "__main__":
    main()
