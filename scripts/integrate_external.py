"""Step 1: compare our prerequisite links with external ordering evidence.

Inputs : DATA/topics.csv, DATA/prereqs.csv, data/external/units.csv, data/external/sources.csv
Outputs: DATA/topic_unit_map_suggested.csv (review it, save as topic_unit_map.csv)
         DATA/prereqs_with_source.csv     (adds/extends the `source` column; IDs unchanged)
         results/external_agreement.json  (agreement rates per source + disagreements)

Evidence rule (stated honestly in the report): textbook chapter order and syllabus
session order are *ordering* evidence, not proof of a prerequisite. A link u -> v
"agrees" with a source if both topics map to units of that source and u's unit comes
no later than v's. It "disagrees" if u's unit comes later. Links whose endpoints do not
both map to one source get no external evidence and stay labelled `estimate`.

Run: python scripts/integrate_external.py --data data/sample
"""
import argparse, csv, json, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from speedrun.data import load_web

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/sample")
ap.add_argument("--units", default="data/external/units.csv")
ap.add_argument("--sources", default="data/external/sources.csv")
ap.add_argument("--out", default="results/external_agreement.json")
a = ap.parse_args()

web = load_web(a.data)
units = list(csv.DictReader(open(a.units)))
stype = {r["source_id"]: r["type"] for r in csv.DictReader(open(a.sources))}

def tokens(s):
    return set(re.findall(r"[a-z0-9/\-']+", s.lower()))

# 1) topic -> units mapping (confirmed file wins over the automatic suggestion)
confirmed = os.path.join(a.data, "topic_unit_map.csv")
mapping = defaultdict(dict)  # topic -> source -> position
if os.path.exists(confirmed):
    for r in csv.DictReader(open(confirmed)):
        if r.get("source_id") and r.get("position"):
            mapping[r["topic_id"]][r["source_id"]] = float(r["position"])
    mode = "confirmed"
else:
    mode = "suggested"
    rows = []
    for t in web.topics.values():
        name = t.name.lower()
        best_per_source = {}
        for u in units:
            kws = [k.strip() for k in u["keywords"].split(";") if k.strip()]
            score = sum(1 for k in kws if k in name)
            if score and score >= best_per_source.get(u["source_id"], (0,))[0]:
                best_per_source[u["source_id"]] = (score, float(u["position"]), u["unit"])
        for sid, (score, pos, unit) in best_per_source.items():
            mapping[t.id][sid] = pos
            rows.append([t.id, t.name, sid, pos, unit, score])
    with open(os.path.join(a.data, "topic_unit_map_suggested.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["topic_id", "topic", "source_id", "position", "unit", "keyword_hits"]); w.writerows(rows)

# 2) agreement per link
stats = defaultdict(lambda: {"agree": 0, "same_unit": 0, "disagree": 0})
disagreements, evidence = [], {}
for l in web.links:
    ev = []
    for sid in set(mapping[l.src]) & set(mapping[l.dst]):
        pu, pv = mapping[l.src][sid], mapping[l.dst][sid]
        if pu < pv:
            stats[sid]["agree"] += 1; ev.append(sid)
        elif pu == pv:
            stats[sid]["same_unit"] += 1; ev.append(sid + "(same unit)")
        else:
            stats[sid]["disagree"] += 1
            disagreements.append({"src": l.src, "dst": l.dst, "type": l.type, "source": sid, "pos_src": pu, "pos_dst": pv})
    evidence[(l.src, l.dst)] = ev

covered = sum(1 for v in evidence.values() if v) + sum(1 for d in disagreements if not evidence[(d["src"], d["dst"])])
tot = {k: sum(s[k] for s in stats.values()) for k in ("agree", "same_unit", "disagree")}
judged = tot["agree"] + tot["disagree"]
summary = {
    "mapping_mode": mode,
    "links": len(web.links),
    "links_with_external_evidence": covered,
    "per_source": stats,
    "overall_agreement_rate": round(tot["agree"] / judged, 3) if judged else None,
    "disagreements": disagreements,
    "note": "Ordering evidence only. Review topic_unit_map_suggested.csv before quoting these numbers.",
}
os.makedirs(os.path.dirname(a.out), exist_ok=True)
json.dump(summary, open(a.out, "w"), indent=1, default=dict)

# 3) prereqs_with_source.csv: keep every original column and ID, extend `source`
src_rows = list(csv.DictReader(open(os.path.join(a.data, "prereqs.csv"))))
fields = list(src_rows[0].keys())
for c in ("source", "external_evidence"):
    if c not in fields:
        fields.append(c)
cm = web.colmap["links"]
for r in src_rows:
    key = (r[cm["src"]].strip(), r[cm["dst"]].strip())
    ev = evidence.get(key, [])
    base = set((r.get("source") or "estimate").split(";"))
    for e in ev:
        base.add(stype.get(e.split("(")[0], "textbook"))
    if len(base) > 1:
        base.discard("estimate")
    r["source"] = ";".join(sorted(base))
    r["external_evidence"] = ";".join(ev)
with open(os.path.join(a.data, "prereqs_with_source.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(src_rows)
print(json.dumps({k: v for k, v in summary.items() if k != "disagreements"}, indent=1, default=dict))
print("disagreements:", disagreements)
