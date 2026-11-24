"""Apply reviewed Step 1 decisions to a web's prerequisite list (IDs never change).

Input : DATA/prereqs_with_source.csv (from integrate_external.py), data/external/step1_changes_<web>.csv
Output: DATA/prereqs.csv with columns from_id,to_id,type,or_group,source,external_evidence,step1
Run   : python scripts/apply_step1_changes.py --data data/iima --changes data/external/step1_changes_iima.csv
"""
import argparse, csv
ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/iima"); ap.add_argument("--changes", default="data/external/step1_changes_iima.csv")
a = ap.parse_args()
rows = list(csv.DictReader(open(f"{a.data}/prereqs_with_source.csv")))
ch = list(csv.DictReader(open(a.changes)))
key = lambda r: (r.get("from_id") or r.get("src"), r.get("to_id") or r.get("dst"))
idx = {key(r): r for r in rows}
for r in rows:
    r["step1"] = "kept"
n_down = n_add = 0
for c in ch:
    k = (c["from_id"], c["to_id"])
    if c["action"] == "downgrade":
        r = idx[k]; r["type"] = c["new_type"]; r["step1"] = "downgraded: " + c["reason"]
        r["source"] = ";".join(sorted(set(r["source"].split(";")) - {"estimate"} | set(c["source"].split(";"))))
        n_down += 1
    elif c["action"] == "add":
        assert k not in idx, k
        rows.append({"from_id": k[0], "to_id": k[1], "type": c["new_type"], "or_group": "", "source": c["source"],
                     "external_evidence": "", "step1": "added: " + c["reason"]})
        n_add += 1
    elif c["action"] == "keep" and k in idx:
        idx[k]["step1"] = "kept after review: " + c["reason"]
fields = ["from_id", "to_id", "type", "or_group", "source", "external_evidence", "step1"]
with open(f"{a.data}/prereqs.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
print(f"{len(rows)} links written ({n_down} downgraded, {n_add} added)")
