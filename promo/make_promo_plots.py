#!/usr/bin/env python3
"""
Brand-styled promo plots for "India · Built & Lit".

Emits 9:16 portrait story slides (1080x1920) ready to post on Instagram /
WhatsApp / X, each with an XKDR-coral chart, a headline, a takeaway caption,
and the XKDR logomark. Also writes bare PDF charts (no title/caption) sized for
the square carousel card-3 figure slot.

    python3 promo/make_promo_plots.py

Reads docs/data/{bv_annual,viirs_monthly}.csv. Outputs to promo/plots/.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.colors import (BoundaryNorm, LinearSegmentedColormap,
                                ListedColormap, Normalize)
from matplotlib.collections import PatchCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
from matplotlib.ticker import FuncFormatter

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
OUT = ROOT / "promo" / "plots"
OUT.mkdir(parents=True, exist_ok=True)
LOGOMARK = ROOT / "promo" / "XKDR_Logomark_RGB_Full_Colour.png"

# ---------------------------------------------------------------------------
# brand tokens
# ---------------------------------------------------------------------------
CORAL = "#F27A69"      # official XKDR SpOrange
CORAL_DK = "#E0654F"
INK = "#1A1A1A"
MUTED = "#6A6A6A"
PAPER = "#F2F1F0"      # warm off-white background
WHITE = "#FFFFFF"
BLUE = "#3B5C8F"       # for negative growth bars

_MONT = "/usr/share/texlive/texmf-dist/fonts/opentype/public/montserrat/"
for _f in ("Montserrat-Regular.otf", "Montserrat-SemiBold.otf",
           "Montserrat-Bold.otf", "Montserrat-ExtraBold.otf"):
    p = Path(_MONT + _f)
    if p.exists():
        fm.fontManager.addfont(str(p))
plt.rcParams.update({
    "font.family": "Montserrat" if Path(_MONT).exists() else "DejaVu Sans",
    "axes.edgecolor": INK,
    "axes.linewidth": 1.4,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "svg.fonttype": "none",
})

# ---------------------------------------------------------------------------
# PC11 state codes → names (for bar labels)
# ---------------------------------------------------------------------------
PC11 = {1: "J&K", 2: "HP", 3: "Punjab", 4: "Chandigarh", 5: "Uttarakhand",
        6: "Haryana", 7: "Delhi", 8: "Rajasthan", 9: "UP", 10: "Bihar",
        11: "Sikkim", 12: "Arunachal", 13: "Nagaland", 14: "Manipur",
        15: "Mizoram", 16: "Tripura", 17: "Meghalaya", 18: "Assam",
        19: "West Bengal", 20: "Jharkhand", 21: "Odisha", 22: "Chhattisgarh",
        23: "MP", 24: "Gujarat", 25: "Daman & Diu", 26: "DNH",
        27: "Maharashtra", 28: "AP", 29: "Karnataka", 30: "Goa",
        31: "Lakshadweep", 32: "Kerala", 33: "Tamil Nadu", 34: "Puducherry",
        35: "A&N Is."}


def clean_names(df):
    """Drop rows whose district name is missing/blank."""
    n = df["d_name"].astype("string").str.strip()
    return df[n.notna() & (n != "") & (n.str.lower() != "missing")].copy()


def shorten(name):
    """Compact common long district names so bar labels don't overflow."""
    return (name.replace("Twenty Four", "24")
                .replace("Twenty-four", "24")
                .replace("Twentyfour", "24"))


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------
bv = pd.read_csv(DATA / "bv_annual.csv")
viirs = pd.read_csv(DATA / "viirs_monthly.csv")

# annual NTL = sum of monthly sum_radiance per district-year
ntl_annual = (viirs.dropna(subset=["sum_radiance"])
              .groupby(["pc11_s_id", "pc11_d_id", "year"], as_index=False)
              .agg(sum_radiance=("sum_radiance", "sum"),
                   d_name=("d_name", "first")))


def growth(df, idcols, valcol, min_obs=3):
    """Annualised growth rate per district via OLS on log(value) ~ year.

    For each district, fits log(value) linearly against year and reports the
    slope as a compounded annual growth rate:  g_pct = (exp(slope) - 1) * 100.
    Uses every available year, so a single outlier year (e.g. raw BV 2022, a
    cloudy NTL year) cannot dominate the estimate — the standard fix for
    endpoint-differencing brittleness.

    Districts with non-positive values are dropped (log needs > 0) and any
    district with fewer than `min_obs` usable years is skipped.
    """
    out = []
    g = df.dropna(subset=[valcol])
    g = g[g[valcol] > 0].sort_values("year")
    for keys, sub in g.groupby(idcols, sort=False):
        if len(sub) < min_obs:
            continue
        years = sub["year"].to_numpy(dtype=float)
        logv = np.log(sub[valcol].to_numpy(dtype=float))
        slope, _ = np.polyfit(years, logv, 1)
        row = (dict(zip(idcols, keys)) if isinstance(keys, tuple)
               else {idcols[0]: keys})
        row.update({valcol: sub[valcol].iloc[0],   # first-year value, for the
                                                    # small-baseline filter below
                    "g_pct": (np.exp(slope) - 1) * 100,
                    "first_year": int(years.min()),
                    "last_year": int(years.max()),
                    "n_obs": len(sub)})
        out.append(row)
    return pd.DataFrame(out)


# ===========================================================================
# story-slide scaffold
# ===========================================================================
def story(title, subtitle, takeaway, left=0.155):
    """Create a 1080x1920 portrait figure; return (fig, ax) for the chart.

    `left` widens the chart's left margin for long y-tick labels (bar charts).
    """
    fig = plt.figure(figsize=(5.4, 9.6), dpi=200)
    fig.patch.set_facecolor(PAPER)

    # headline block
    fig.text(0.5, 0.945, title, ha="center", va="top",
             fontsize=26, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.5, 0.905, subtitle, ha="center", va="top",
                 fontsize=15, color=CORAL_DK, fontweight="semibold")

    # chart area; the headline block sits just above and the caption just
    # below. Caption y / chart bottom are tuned so a 2-line, fontsize-20 bold
    # caption clears the logomark with ~20px of breathing room.
    ax = fig.add_axes([left, 0.270, 0.945 - left, 0.590])
    ax.set_facecolor(WHITE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="both", color="#EAE6E2", lw=1, zorder=0)
    ax.tick_params(labelsize=12, length=4)

    # takeaway caption (coral, wraps on \n)
    fig.text(0.5, 0.200, takeaway, ha="center", va="top",
             fontsize=20, fontweight="bold", color=CORAL_DK,
             linespacing=1.35)

    # logomark, bottom-centre
    if LOGOMARK.exists():
        lax = fig.add_axes([0.42, 0.045, 0.16, 0.05])
        lax.imshow(plt.imread(str(LOGOMARK)))
        lax.axis("off")
        fig.text(0.5, 0.038, "XKDR FORUM", ha="center", va="top",
                 fontsize=10, color=MUTED, fontweight="semibold")
    return fig, ax


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    print("wrote", (OUT / f"{name}.png").relative_to(ROOT))


def barlabels(ax, bars, vals, fmt):
    xmax = max(v for v in vals)
    for b, v in zip(bars, vals):
        ax.text(b.get_width() + xmax * 0.015, b.get_y() + b.get_height() / 2,
                fmt(v), va="center", ha="left", fontsize=9.5,
                color=INK, fontweight="semibold")


# ===========================================================================
# 1 · National NTL trend
# ===========================================================================
def plot_ntl_trend():
    s = (viirs.dropna(subset=["sum_radiance"])
         .groupby("date", as_index=False)["sum_radiance"].sum())
    s["date"] = pd.to_datetime(s["date"])
    s = s.sort_values("date")
    fig, ax = story(
        "India is getting brighter",
        f"Total VIIRS nighttime lights · {s.date.dt.year.min()}–{s.date.dt.year.max()}",
        "Nationwide nighttime radiance has\nrisen steadily for a decade")
    ax.plot(s["date"], s["sum_radiance"], color=CORAL, lw=3, zorder=3)
    ax.fill_between(s["date"], s["sum_radiance"], color=CORAL, alpha=0.12, zorder=2)
    ax.set_ylabel("Sum radiance (nW/cm²/sr)", fontsize=12)
    ax.set_xlabel("")
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _: f"{v/1e6:.0f}M" if v >= 1e6 else f"{v/1e3:.0f}k"))
    ax.margins(x=0.02)
    save(fig, "story_ntl_trend")


# ===========================================================================
# 2 · Top districts by building volume
# ===========================================================================
def plot_top_districts():
    yr = int(bv["year"].max())
    d = clean_names(bv[(bv["year"] == yr)]).nlargest(20, "volume_m3")
    d = d.sort_values("volume_m3")
    labels = [f"{shorten(r.d_name)} · {PC11.get(int(r.pc11_s_id), '')}"
              for r in d.itertuples()]
    fig, ax = story(
        "Where India is built",
        f"Top 20 districts by building volume · {yr}",
        "Pune, Bangalore, Hyderabad —\nIndia's tech hubs take the top three",
        left=0.44)
    bars = ax.barh(labels, d["volume_m3"] / 1e9, color=CORAL, zorder=3)
    barlabels(ax, bars, list(d["volume_m3"] / 1e9), lambda v: f"{v:,.1f}")
    ax.set_xlabel("Building volume (billion m³)", fontsize=12)
    ax.tick_params(axis="y", labelsize=8.5)
    ax.margins(x=0.18)
    save(fig, "story_top_districts")


# ===========================================================================
# 3 · BV vs NTL scatter
# ===========================================================================
def plot_scatter():
    common = sorted(set(bv["year"]) & set(ntl_annual["year"]))
    yr = max(common)
    m = (bv[bv["year"] == yr][["pc11_d_id", "volume_m3"]]
         .merge(ntl_annual[ntl_annual["year"] == yr][["pc11_d_id", "sum_radiance"]],
                on="pc11_d_id"))
    m = m[(m["volume_m3"] > 0) & (m["sum_radiance"] > 0)]
    fig, ax = story(
        "Capital meets activity",
        f"Building volume vs nighttime lights · {yr}",
        "Districts with more built-up volume\nshine brighter at night")
    ax.scatter(m["volume_m3"], m["sum_radiance"], s=22, color=CORAL,
               alpha=0.5, edgecolor=CORAL_DK, linewidth=0.3, zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Building volume (m³)", fontsize=12, labelpad=8)
    ax.set_ylabel("NTL sum radiance (nW/cm²/sr)", fontsize=12, labelpad=8)
    # focus on the bulk of the distribution; outliers in the lower-left
    # corner waste vertical space without adding signal.
    ax.set_xlim(7e6, 4e9)
    ax.set_ylim(5e2, 5e6)
    save(fig, "story_scatter")


# ===========================================================================
# Choropleth helpers (no geopandas — direct GeoJSON → PathPatch)
# ===========================================================================
# One sequential palette for the whole map family, anchored on the brand:
#   theme off-white  →  pale coral  →  primary coral  →  deep coral  →  ink
CMAP_XKDR = LinearSegmentedColormap.from_list("xkdr", [
    PAPER,        # warm off-white background
    "#F8D4C9",    # pale coral
    "#F27A69",    # primary XKDR coral
    "#9E3F2F",    # deep coral
    INK,          # secondary ink
])


def _rings_path(rings):
    """Convert a list of GeoJSON linear rings to a matplotlib Path."""
    verts, codes = [], []
    for ring in rings:
        if len(ring) < 3:
            continue
        verts.extend(ring)
        codes.append(MplPath.MOVETO)
        codes.extend([MplPath.LINETO] * (len(ring) - 1))
    return MplPath(verts, codes)


def _feature_paths(feat):
    """Yield matplotlib Paths for a (Multi)Polygon feature."""
    g = feat["geometry"]
    if g["type"] == "Polygon":
        yield _rings_path(g["coordinates"])
    elif g["type"] == "MultiPolygon":
        for poly in g["coordinates"]:
            yield _rings_path(poly)


GREY_NEG = "#cfc8c1"   # warm-grey "no growth / shrinking" bin (matches theme)


def _pos_quintile_with_neg(cmap_base, val, n_pos=5):
    """Discrete colormap: 1 grey bin for negatives + n_pos quintile bins for
    positives. Gives finer resolution on the positive side, which is the
    interesting tail in most growth datasets (BV/NTL).
    """
    v = val.dropna().to_numpy()
    pos = v[v > 0]
    neg_lo = float(min(v.min() if v.min() < 0 else -1, -1))
    pos_breaks = np.quantile(pos, np.linspace(0, 1, n_pos + 1))
    breaks = np.array([neg_lo, 0.0, *pos_breaks[1:]])
    colors = [GREY_NEG] + [cmap_base(i / (n_pos - 1)) for i in range(n_pos)]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(breaks, ncolors=len(colors))
    # 1 decimal when any positive bin is < 20% (annualised rates) so adjacent
    # boundaries don't collapse to the same integer label.
    pos_max = float(max(breaks))
    fmt = (lambda x: f"{x:,.1f}%") if pos_max < 20 else (lambda x: f"{x:,.0f}%")
    tick_labels = [fmt(x) for x in breaks]
    return cmap, norm, breaks, tick_labels


def _draw_map(fig, ax, geo, val, cmap, norm, tick_labels, ticks=None):
    """Render the choropleth + bottom colorbar inside the story scaffold."""
    ax.set_position([0.04, 0.235, 0.92, 0.62])
    ax.set_aspect("equal"); ax.axis("off"); ax.set_facecolor(PAPER)
    patches, colors = [], []
    for f in geo["features"]:
        try:
            did = int(f["properties"]["pc11_d_id"])
        except (KeyError, TypeError, ValueError):
            continue
        v = val.get(did)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            c = "#e8e3de"
        else:
            c = cmap(norm(v))
        for p in _feature_paths(f):
            patches.append(PathPatch(p))
            colors.append(c)
    # Layer 1 (behind): every district stroked thick + dark, no fill. The
    # stroke spills half its width outside each polygon. On INTERNAL borders
    # the neighbouring district's fill (layer 2) covers the spillover; on the
    # COUNTRY boundary the spillover has no neighbour to cover it, leaving a
    # clean dark halo. No need to dissolve polygons.
    ax.add_collection(PatchCollection(
        patches, facecolors="none", edgecolors=INK, linewidths=2.2, zorder=1))
    # Layer 2 (on top): filled districts with thin white inner borders.
    ax.add_collection(PatchCollection(
        patches, facecolors=colors, edgecolors="#FFFFFF",
        linewidths=0.15, zorder=2))
    ax.set_xlim(67.5, 98.5)
    ax.set_ylim(7, 37.5)

    cax = fig.add_axes([0.18, 0.225, 0.64, 0.012])
    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    # spacing='uniform' so every bin (incl. the grey negatives bin) renders
    # at equal width regardless of the value range it covers.
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal",
                      spacing="uniform")
    if ticks is not None:
        cb.set_ticks(ticks)
    else:
        vmin, vmax = norm.vmin, norm.vmax
        cb.set_ticks([vmin, (vmin + vmax) / 2, vmax])
    cb.set_ticklabels(tick_labels)
    cb.ax.tick_params(labelsize=9, length=0, pad=2)
    cb.outline.set_visible(False)


# ===========================================================================
# 4 · Choropleth — NTL by district, latest year
# ===========================================================================
def plot_choropleth():
    geo = json.loads((DATA / "districts_simplified.geojson").read_text())
    yr = int(ntl_annual["year"].max())
    val = (ntl_annual[ntl_annual["year"] == yr]
           .groupby("pc11_d_id")["sum_radiance"].sum())
    logv = np.log10(val.clip(lower=1))
    vmin, vmax = float(np.percentile(logv, 5)), float(np.percentile(logv, 99))
    norm = Normalize(vmin=vmin, vmax=vmax)

    fig, ax = story(
        "India after dark",
        f"VIIRS nighttime lights by district · {yr}",
        "Megacities and the Ganga plain\nare India's brightest belt",
        left=0.04)
    _draw_map(fig, ax, geo, logv, CMAP_XKDR, norm,
              ["low", "", "high"])
    save(fig, "story_choropleth")


def _growth_for_map(df, valcol):
    """Per-district full-period growth, with a small-baseline filter.

    Districts whose first-year value falls in the bottom decile are dropped —
    they produce wildly volatile % growth that dominates and speckles the map.
    Returns (series indexed by pc11_d_id, first_year, last_year).
    """
    grow = growth(df, ["pc11_d_id"], valcol)
    floor = grow[valcol].quantile(0.10)
    grow = grow[grow[valcol] > floor]
    g = grow.set_index("pc11_d_id")["g_pct"]
    fy = int(grow["first_year"].min())
    ly = int(grow["last_year"].max())
    return g, fy, ly


# ===========================================================================
# 4b · Building-volume growth choropleth (full period)
# ===========================================================================
def plot_bv_growth_map():
    geo = json.loads((DATA / "districts_simplified.geojson").read_text())
    g, fy, ly = _growth_for_map(bv, "volume_m3")
    cmap, norm, breaks, labels = _pos_quintile_with_neg(CMAP_XKDR, g)
    fig, ax = story(
        "Where India is building",
        f"Annualised building-volume growth · {fy}–{ly}",
        "Build-out is fastest beyond the\nbig metros — the urban edge",
        left=0.04)
    _draw_map(fig, ax, geo, g, cmap, norm, labels, ticks=list(breaks))
    save(fig, "story_bv_growth_map")


# ===========================================================================
# 4c · NTL growth choropleth (full period, diverging)
# ===========================================================================
def plot_ntl_growth_map():
    geo = json.loads((DATA / "districts_simplified.geojson").read_text())
    g, fy, ly = _growth_for_map(ntl_annual, "sum_radiance")
    cmap, norm, breaks, labels = _pos_quintile_with_neg(CMAP_XKDR, g)
    fig, ax = story(
        "Lighting up, dimming down",
        f"Annualised nighttime-lights growth · {fy}–{ly}",
        "Most of India is brightening —\na few belts are losing light",
        left=0.04)
    _draw_map(fig, ax, geo, g, cmap, norm, labels, ticks=list(breaks))
    save(fig, "story_ntl_growth_map")


# ===========================================================================
# 5 · Growth leaders (building volume, full period)
# ===========================================================================
def plot_growth_leaders():
    g = growth(clean_names(bv), ["pc11_s_id", "pc11_d_id", "d_name"], "volume_m3")
    fy, ly = int(g["first_year"].min()), int(g["last_year"].max())
    # drop the single extreme outlier so the field is readable
    top = g.nlargest(21, "g_pct").iloc[1:].sort_values("g_pct")
    labels = [f"{shorten(r.d_name)} · {PC11.get(int(r.pc11_s_id), '')}"
              for r in top.itertuples()]
    fig, ax = story(
        "Fastest-building districts",
        f"Annualised building-volume growth · {fy}–{ly}",
        "Smaller districts are catching up\nfastest on the built-up stock",
        left=0.40)
    bars = ax.barh(labels, top["g_pct"], color=CORAL, zorder=3)
    barlabels(ax, bars, list(top["g_pct"]), lambda v: f"{v:,.1f}%")
    ax.set_xlabel("Annualised growth (% per year)", fontsize=12)
    ax.tick_params(axis="y", labelsize=9)
    ax.margins(x=0.18)
    save(fig, "story_growth_leaders")


if __name__ == "__main__":
    plot_ntl_trend()
    plot_top_districts()
    plot_scatter()
    plot_choropleth()
    plot_bv_growth_map()
    plot_ntl_growth_map()
    plot_growth_leaders()
    print("done →", OUT.relative_to(ROOT))
