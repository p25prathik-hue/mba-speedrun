"""Make the report figures (black-and-white friendly: greys + hatching + marker shapes).

Run: python scripts/make_figures.py --data data/sample --res results/sample --scale results/scale.json --out report/figures
"""
import argparse, json, math, os, sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from speedrun.data import load_web, Params, Profile
from speedrun.graph import build_instance
from speedrun.costs import Evaluator
from speedrun.heuristics import solve_heuristic
from speedrun.days import shortest_path_split, lower_bound_days

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/iima"); ap.add_argument("--res", default="results/iima")
ap.add_argument("--pilot-data", default="data/sample"); ap.add_argument("--pilot-res", default="results/sample")
ap.add_argument("--scale", default="results/scale.json"); ap.add_argument("--out", default="report/figures")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
plt.rcParams.update({"font.size": 9, "font.family": "serif", "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.bbox": "tight", "savefig.dpi": 200, "hatch.linewidth": 0.6})
GREYS = ["#ffffff", "#bdbdbd", "#737373", "#252525", "#e0e0e0", "#969696"]
HATCH = ["///", "...", "", "xx", "\\\\", "++"]
MARK = ["o", "s", "^", "D", "v", "P"]

web = load_web(a.pilot_data); P = Params.load(os.path.join(a.pilot_data, "params.json"))
domains = sorted({t.domain for t in web.topics.values()})
dstyle = {d: (GREYS[i % 6], HATCH[i % 6], MARK[i % 6]) for i, d in enumerate(domains)}

# 1. topic web --------------------------------------------------------------
pred = defaultdict(list)
for l in web.links:
    pred[l.dst].append(l)
depth = {}
def dep(v, st=()):
    if v in depth: return depth[v]
    d = 0
    for l in pred[v]:
        if l.type != "SOFT" and l.src not in st:
            d = max(d, dep(l.src, st + (v,)) + 1)
    depth[v] = d; return d
for t in web.topics: dep(t)
cols = defaultdict(list)
for t in web.topics.values(): cols[depth[t.id]].append(t)
pos = {}
for d, lst in cols.items():
    lst.sort(key=lambda t: (t.domain, t.term, t.order))
    for i, t in enumerate(lst):
        pos[t.id] = (d * 4.4, -i * 1.0)
fig, ax = plt.subplots(figsize=(7.4, 5.6))
for l in web.links:
    (x1, y1), (x2, y2) = pos[l.src], pos[l.dst]
    ls = {"AND": "-", "OR": "--", "SOFT": ":"}[l.type]
    ax.annotate("", xy=(x2 - 0.15, y2), xytext=(x1 + 0.15, y1),
                arrowprops=dict(arrowstyle="-|>", lw=0.6, ls=ls, color="#555", shrinkA=0, shrinkB=0, mutation_scale=6,
                                connectionstyle="arc3,rad=0.08"))
for t in web.topics.values():
    x, y = pos[t.id]; c, h, m = dstyle[t.domain]
    ax.scatter([x], [y], s=60, marker=m, facecolor=c, edgecolor="black", linewidth=0.7, hatch=h, zorder=3)
    ax.text(x + 0.25, y + 0.28, t.name if len(t.name) < 27 else t.name[:25] + "…", fontsize=5.2, va="center", zorder=4,
            bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.85))
for d in domains:
    c, h, m = dstyle[d]
    ax.scatter([], [], marker=m, facecolor=c, edgecolor="black", hatch=h, label=d, s=40)
ax.plot([], [], "-", color="#555", label="AND (required)"); ax.plot([], [], "--", color="#555", label="OR (one of group)")
ax.plot([], [], ":", color="#555", label="SOFT (recommended)")
ax.legend(fontsize=6.5, loc="lower right", frameon=False, ncol=2)
ax.set_axis_off(); ax.set_title("Pilot prerequisite web (columns = prerequisite depth)", fontsize=9)
fig.savefig(os.path.join(a.out, "fig_web.pdf")); plt.close(fig)

# 2. scale + bounds -----------------------------------------------------------
if os.path.exists(a.scale):
    S = json.load(open(a.scale))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 2.7))
    for r in S:
        ax1.scatter(r["n"], max(r["secs"], 0.01), marker="o" if r["proven"] else "x", color="black",
                    facecolor="none" if r["proven"] else "black", s=22)
    ns = sorted({r["n"] for r in S})
    med = [np.median([max(r["secs"], .01) for r in S if r["n"] == n]) for n in ns]
    ax1.plot(ns, med, "-", color="#777", lw=0.8)
    ax1.set_yscale("log"); ax1.set_xlabel("topics n"); ax1.set_ylabel("B&B time (s, log)")
    ax1.axhline(180, ls=":", color="black", lw=0.7); ax1.text(ns[-1], 230, "limit 180 s", fontsize=7, ha="right")
    ax1.scatter([], [], marker="o", facecolor="none", color="black", label="proven optimal")
    ax1.scatter([], [], marker="x", color="black", label="not proven")
    ax1.legend(fontsize=7, frameon=False, loc="lower right"); ax1.set_ylim(0.01, 900)
    ax1.set_title("Exactness vs scale (CBC)", fontsize=9)
    # bounds relative to the controllable part: (z - sum p)
    w = 0.25
    for k, (key, lab, hc) in enumerate([("lp_plain", "LP relaxation, no cuts", ""), ("assign", "assignment relaxation + arc fixing", "///"),
                                         ("lp_cuts", "LP + arc fixing + 2-cycle cuts", "xx")]):
        vals = []
        for n in ns:
            rr = [r for r in S if r["n"] == n]
            vals.append(np.mean([100 * (r["exact"] - r[key]) / r["exact"] for r in rr]))
        ax2.bar(np.arange(len(ns)) + (k - 1) * w, vals, w, color=["#ffffff", "#bdbdbd", "#737373"][k], edgecolor="black",
                hatch=hc, lw=0.6, label=lab)
    ax2.set_xticks(range(len(ns))); ax2.set_xticklabels(ns); ax2.set_xlabel("topics n")
    ax2.set_ylabel("gap below best known (%)"); ax2.set_ylim(0, 9.5); ax2.legend(fontsize=6, frameon=False, loc="upper left", ncol=1)
    ax2.set_title("Lower bounds: (z* - LB)/z*", fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(a.out, "fig_scale.pdf")); plt.close(fig)

# 3. profiles -----------------------------------------------------------------
web = load_web(a.data); P = Params.load(os.path.join(a.data, "params.json"))
R = json.load(open(os.path.join(a.res, "profiles.json")))
R = [r for r in R if not r["profile"].startswith(("crunch", "summers"))]
fig, ax = plt.subplots(figsize=(7.2, 2.8))
labs = [r["profile"].replace("_", " ") for r in R]
series = [("naive_B0", "whole curriculum, timetable order", "#ffffff", "..."),
          ("B0", "your scope, timetable order (B0)", "#d9d9d9", "///"),
          ("B1", "your scope, subject by subject (B1)", "#969696", ""),
          ("roadmap", "your scope, optimised roadmap", "#252525", "")]
w = 0.2
for k, (key, lab, c, h) in enumerate(series):
    vals = [r[key] if key == "naive_B0" else r[key]["total"] for r in R]
    bars = ax.bar(np.arange(len(R)) + (k - 1.5) * w, vals, w, color=c, edgecolor="black", hatch=h, lw=0.6, label=lab)
    if key == "roadmap":
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 6, f"{v:.0f}", ha="center", fontsize=6.5)
ax.set_xticks(range(len(R))); ax.set_xticklabels(labs); ax.set_ylabel("hours (study + switching + revision)")
ax.legend(fontsize=6.5, frameon=False, ncol=2, loc="upper right"); ax.set_ylim(0, max(r["naive_B0"] for r in R) * 1.25)
fig.tight_layout(); fig.savefig(os.path.join(a.out, "fig_profiles.pdf")); plt.close(fig)

# 4. sensitivity ----------------------------------------------------------------
sp = os.path.join(a.res, "sensitivity.json")
if os.path.exists(sp):
    Sx = json.load(open(sp))
    oat = Sx["oat"]
    names = ["w_switch", "s_synergy", "rho_revision", "L_revision_free", "revision_cap_share", "soft_penalty", "all_hours"]
    nice = {"w_switch": "switch warm-up w", "s_synergy": "synergy s", "rho_revision": "revision rate rho",
            "L_revision_free": "revision-free gap L", "revision_cap_share": "revision cap kappa", "soft_penalty": "SOFT penalty pi", "all_hours": "all topic hours"}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 2.6))
    for i, nm in enumerate(names):
        lo = [o for o in oat if o["param"] == nm and o["factor"] < 1][0]
        hi = [o for o in oat if o["param"] == nm and o["factor"] > 1][0]
        for o, c, h in ((lo, "#ffffff", "///"), (hi, "#737373", "")):
            ax1.barh(i + (0.18 if o is hi else -0.18), o["gain_vs_B1_pct"], 0.34, color=c, edgecolor="black", hatch=h, lw=0.6)
    ax1.set_yticks(range(len(names))); ax1.set_yticklabels([nice[n] for n in names], fontsize=7)
    ax1.set_xlabel("gain vs subject by subject B1 (%)")
    ax1.legend(handles=[Patch(facecolor="#ffffff", edgecolor="black", hatch="///", label="parameter -25%"),
                        Patch(facecolor="#737373", edgecolor="black", label="parameter +25%")],
               fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=2); ax1.set_title("One at a time, +-25%", fontsize=9)
    ax1.set_ylim(-0.6, len(names) + 0.5)  # head-room so the legend sits above the bars, clear of the x label
    mc = Sx["mc"]
    ax2.hist([m["gain_vs_B0_pct"] for m in mc], bins=18, color="#bdbdbd", edgecolor="black", lw=0.5, label="vs B0 (timetable)")
    ax2.hist([m["gain_vs_B1_pct"] for m in mc], bins=18, color="#ffffff", edgecolor="black", hatch="///", lw=0.5, label="vs B1 (subject by subject)")
    ax2.set_xlabel("gain of re-optimised roadmap (%)"); ax2.set_ylabel("draws")
    ax2.legend(fontsize=7, frameon=False); ax2.set_title(f"Monte Carlo, {len(mc)} draws, all inputs U[0.75,1.25]", fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(a.out, "fig_sensitivity.pdf")); plt.close(fig)

# 5. swimlanes (B1 vs roadmap) and days vs H, full web --------------------------
fr = [r for r in json.load(open(os.path.join(a.res, "profiles.json"))) if r["profile"] == "fresh"][0]
inst = build_instance(web, Profile(), P); ev = Evaluator(inst)
doms = sorted({t.domain for t in web.topics.values()})
fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.6), sharex=True)
for ax, key, title in ((axes[0], "B1_ids", "Subject by subject (B1)"), (axes[1], "roadmap_ids", "Optimised roadmap")):
    x = 0.0
    for t in fr[key]:
        d = doms.index(web.topics[t].domain); h = inst.p[t]
        ax.barh(d, h, left=x, height=0.7, color="black", lw=0)
        x += h
    bd = fr["B1"] if key == "B1_ids" else fr["roadmap"]
    ax.set_yticks(range(len(doms))); ax.set_yticklabels(doms, fontsize=5.8); ax.invert_yaxis()
    ax.set_title(f"{title}: {bd['total']:.0f} h total, {int(bd['domain_switches'])} subject switches, {bd['revision']:.0f} h revision", fontsize=8.5)
    ax.tick_params(axis="x", labelsize=7)
axes[1].set_xlabel("study hours elapsed (topic time only)")
fig.tight_layout(); fig.savefig(os.path.join(a.out, "fig_swimlanes.pdf")); plt.close(fig)

seq = ev.from_ids(fr["roadmap_ids"])
Hs = [3, 4, 5, 6, 8, 10, 12]
spd, lbd = [], []
for H in Hs:
    spd.append(shortest_path_split(ev, seq, H)["n_days"]); lbd.append(lower_bound_days(ev, H))
fig, ax2 = plt.subplots(figsize=(3.6, 2.4))
ax2.plot(Hs, spd, "-o", color="black", ms=3.5, label="days (exact split of the roadmap)")
ax2.plot(Hs, lbd, "--s", color="#777", ms=3.5, mfc="white", label="bin-packing bound ceil(sum p / H)")
ax2.set_xlabel("hours per day H"); ax2.set_ylabel("days"); ax2.legend(fontsize=6.5, frameon=False)
ax2.set_title("Days vs hours per day (266 topics)", fontsize=8.5)
fig.tight_layout(); fig.savefig(os.path.join(a.out, "fig_days.pdf")); plt.close(fig)
json.dump({"H": Hs, "days": spd, "lb": lbd}, open(os.path.join(a.res, "days_vs_H.json"), "w"))

# 6. cross-domain link matrix (full web) ------------------------------------------
import collections
ab = {d: "".join(w[0] for w in d.replace("&", " ").replace(",", " ").split())[:4] for d in doms}
M = np.zeros((len(doms), len(doms)))
for l in web.links:
    if l.type != "SOFT":
        M[doms.index(web.topics[l.src].domain), doms.index(web.topics[l.dst].domain)] += 1
fig, ax = plt.subplots(figsize=(4.6, 4.0))
im = ax.imshow(np.log1p(M), cmap="Greys")
for i in range(len(doms)):
    for j in range(len(doms)):
        if M[i, j]:
            ax.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=5.5, color="white" if np.log1p(M[i, j]) > 2.2 else "black")
ax.set_xticks(range(len(doms))); ax.set_xticklabels(doms, rotation=60, ha="right", fontsize=5.8)
ax.set_yticks(range(len(doms))); ax.set_yticklabels(doms, fontsize=5.8)
ax.set_xlabel("dependent topic's domain"); ax.set_ylabel("prerequisite's domain")
ax.set_title("Required links (AND/OR) between domains, 266-topic web", fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(a.out, "fig_domains.pdf")); plt.close(fig)
print("figures written to", a.out)
