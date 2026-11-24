"""Layered layout (columns = prerequisite depth) with barycentre ordering; embeds data into the explorer HTML."""
import argparse, json, os, collections

# Paths are relative to the repository root:
#   python scripts/kit/layout.py [--web data/iima/kit_web.json] [--out docs/topic-web.html]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ap = argparse.ArgumentParser(description=__doc__)
_ap.add_argument("--web", default=os.path.join(ROOT, "data", "iima", "kit_web.json"))
_ap.add_argument("--template", default=os.path.join(ROOT, "scripts", "kit", "explorer_template.html"))
_ap.add_argument("--out", default=os.path.join(ROOT, "docs", "topic-web.html"))
_args = _ap.parse_args()
D = json.load(open(_args.web, encoding="utf-8"))
T = {t["id"]: t for t in D["topics"]}
DOM_ORDER = ["Quant & Analytics", "Accounting", "Finance", "Economics", "Marketing", "Operations", "Strategy",
             "Research Methods", "OB & HR", "IT & Digital", "Law", "Ethics, Society & Env", "Communication"]
preds = collections.defaultdict(list); succs = collections.defaultdict(list)
for e in D["edges"]:
    if e["kind"] != "soft":
        preds[e["to_id"]].append(e["from_id"]); succs[e["from_id"]].append(e["to_id"])

cols = collections.defaultdict(list)
for t in D["topics"]:
    cols[t["depth"]].append(t["id"])
maxd = max(cols)
for d in cols:
    cols[d].sort(key=lambda i: (DOM_ORDER.index(T[i]["domain"]), i))
pos = {}
def index():
    for d in cols:
        for k, i in enumerate(cols[d]):
            pos[i] = k - (len(cols[d]) - 1) / 2   # centred
index()
for sweep in range(12):
    rng = range(1, maxd + 1) if sweep % 2 == 0 else range(maxd - 1, -1, -1)
    for d in rng:
        nb = preds if sweep % 2 == 0 else succs
        def key(i):
            ns = nb[i]
            return (sum(pos[n] for n in ns) / len(ns)) if ns else pos[i]
        cols[d].sort(key=lambda i: (key(i), DOM_ORDER.index(T[i]["domain"])))
        index()

COLW, ROWH = 214, 30
tallest = max(len(c) for c in cols.values())
for t in D["topics"]:
    t["x"] = 30 + t["depth"] * COLW
    t["y"] = 60 + (pos[t["id"]] + (tallest - 1) / 2) * ROWH
D["layout"] = dict(w=30 + (maxd + 1) * COLW + 20, h=60 + tallest * ROWH + 30, colw=COLW, levels=maxd + 1)
D["domains"] = DOM_ORDER
D["near_review"] = [
    ["ACC21", "FIN32", "Kept separate", "FRA measures the cycle; CF sets the policy. They are linked by a prerequisite, so the solver can place them together and earn an adjacency saving."],
    ["OPS01", "OPS03", "Kept separate", "Flow charts are a short sub-skill of process analysis. Merge them if you want a coarser graph."],
    ["QNT26", "QNT27, QNT30", "Kept as a chain", "Simple, multiple and logistic regression are successive steps, not duplicates."],
    ["ACC25", "ACC27", "Kept as a chain", "Absorption costing has to come before comparing it with variable costing."],
    ["FIN16", "FIN24", "Kept separate", "Financial options and real options share payoff logic but apply it differently; FIN16 is a prerequisite of FIN24."],
    ["MKT10", "STR04", "Kept separate", "Product life cycle and industry life cycle are the same idea at different levels; a high similarity score lowers their transition cost."],
    ["COM03", "STR16", "Kept separate", "Writing up a case and analysing one are different skills; COM03 is a prerequisite of STR16."],
    ["OPS14", "OBH14, ECO25", "False positive", "These only share words (‘planning’, ‘aggregate’)."],
]
D.pop("near")
html = open(_args.template, encoding="utf-8").read()
open(_args.out, "w", encoding="utf-8").write(html.replace("/*__DATA__*/null", json.dumps(D, separators=(",", ":"))))
print(D["layout"], {d: len(c) for d, c in sorted(cols.items())})
