"""Exactness vs scale (Session 5 slides 17-18: combinatorial explosion; Session 7: complexity).

Random precedence-closed sub-instances of the pilot, solved by B&B (CBC) and by the
heuristics. Records time, nodes, proven optimality and heuristic gap.
Run:  python scripts/scale_experiment.py --data data/sample --out results/scale.json
"""
import argparse, json, os, random, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from speedrun.data import load_web, Params, Profile
from speedrun.graph import build_instance
from speedrun.costs import Evaluator
from speedrun import heuristics as H, milp
from speedrun.baselines import curriculum_order, subject_by_subject

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/sample"); ap.add_argument("--out", default="results/scale.json")
ap.add_argument("--per-size", type=int, default=4); ap.add_argument("--time-limit", type=float, default=180)
ap.add_argument("--sizes", default="8,12,16,20,24,28")
a = ap.parse_args()
web = load_web(a.data); P = Params.load(os.path.join(a.data, "params.json"))
rng = random.Random(42)
ids = list(web.topics)
rows = []
for size in [int(s) for s in a.sizes.split(",")]:
    got, tries = 0, 0
    seen = set()
    while got < a.per_size and tries < 500:
        tries += 1
        k = rng.randint(1, size)
        targets = rng.sample(ids, k)
        inst = build_instance(web, Profile(targets=targets), P)
        if inst.n != size or tuple(inst.ids) in seen:
            continue
        seen.add(tuple(inst.ids)); got += 1
        ev = Evaluator(inst)
        b0, _ = curriculum_order(ev); b1 = subject_by_subject(ev)
        log = []
        t = time.time(); hs, hc = H.solve_heuristic(ev, restarts=3, extra_starts={"B0": b0, "B1": b1}, log=log); ht = time.time() - t
        construct = {r["start"]: r["construct"] for r in log}
        r = milp.solve_exact(ev, time_limit=a.time_limit, warm_seq=hs, cuts=True)
        lp1 = milp.lp_bound(ev, True); lp0 = milp.lp_bound(ev, False); apb = milp.assignment_bound(ev)
        row = dict(n=size, ids=inst.ids, heur=hc, heur_secs=round(ht, 2), exact=r["objective_eval"],
                   proven=r["optimal"], secs=r["secs"], nodes=r["nodes"], bound=r["best_bound"],
                   lp_cuts=lp1, lp_plain=lp0, assign=apb, B0=ev.cost(b0), B1=ev.cost(b1),
                   construct=construct, sum_p=ev.sum_p)
        rows.append(row)
        print(size, round(hc, 3), round(r["objective_eval"], 3), r["optimal"], r["secs"], r["nodes"], flush=True)
        json.dump(rows, open(a.out, "w"), indent=1)
