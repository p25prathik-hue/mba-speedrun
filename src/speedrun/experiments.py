"""Run the student profiles and write results (JSON/CSV) for the report and the website.

For every profile we report
  * naive baseline: replay the *whole* curriculum in timetable order (B0, full scope);
  * scoped baselines: B0 and B1 on the student's own scope (after closure);
  * our roadmap: best of NN / CI / FI / savings / baselines, improved by or-opt + 2-opt
    with random restarts (S1, S3, S8, S10); exact B&B when the scope is small;
  * the split into days (S7 shortest path, S8 lower bound);
  * crunch mode when the profile has a budget (S9 profit-maximising tour).

Gain decomposition (to answer "is this an artefact of estimated costs?"):
  scope gain      = naive B0 - scoped B0   (exclusions, prior knowledge; does NOT depend on c_ij)
  sequencing gain = scoped B0 - roadmap    (depends on c_ij: switching, synergy, forgetting)
"""
from __future__ import annotations

import csv
import json
import os
import time
from typing import Dict, List

from .baselines import curriculum_order, subject_by_subject
from .costs import Evaluator
from .crunch import knapsack_closure, profit_max_tour
from .data import Params, Profile, Web
from .days import shortest_path_split
from .graph import build_instance, critical_path
from .heuristics import solve_heuristic
from . import milp


def run_profile(web: Web, params: Params, prof: dict, naive_b0: float, exact_max_n: int = 16,
                restarts: int = 5, seed: int = 0) -> Dict:
    pr = Profile.from_dict(prof)
    P = params.copy(**{k: v for k, v in prof.get("params", {}).items()})
    inst = build_instance(web, pr, P)
    ev = Evaluator(inst)
    b0, inversions = curriculum_order(ev)
    b1 = subject_by_subject(ev)
    log: List[dict] = []
    t = time.time()
    seq, best = solve_heuristic(ev, restarts=restarts, seed=seed, extra_starts={"B0": b0, "B1": b1}, log=log)
    secs = time.time() - t
    out = {
        "profile": pr.name,
        "description": prof.get("description", ""),
        "n_topics": ev.n,
        "study_hours": round(ev.sum_p, 2),
        "auto_added": inst.auto_added,
        "warnings": inst.warnings,
        "naive_B0": round(naive_b0, 2),
        "B0": ev.breakdown(b0),
        "B1": ev.breakdown(b1),
        "roadmap": ev.breakdown(seq),
        "roadmap_ids": ev.to_ids(seq),
        "B0_ids": ev.to_ids(b0),
        "B1_ids": ev.to_ids(b1),
        "curriculum_inversions_repaired": inversions,
        "heuristic_secs": round(secs, 2),
        "starts": log,
        "critical_path_hours": round(critical_path(inst)[0], 2) if ev.n else 0,
    }
    out["scope_gain"] = round(naive_b0 - out["B0"]["total"], 2)
    out["sequencing_gain_vs_B0"] = round(out["B0"]["total"] - best, 2)
    out["sequencing_gain_vs_B1"] = round(out["B1"]["total"] - best, 2)
    if 0 < ev.n <= exact_max_n:
        r = milp.solve_exact(ev, time_limit=300, warm_seq=seq)
        out["exact"] = {k: r[k] for k in ("objective_eval", "optimal", "secs", "nodes")}
        out["exact"]["gap_heuristic"] = round(best - r["objective_eval"], 4)
    split = shortest_path_split(ev, seq, P.day_hours)
    out["days"] = split
    if prof.get("budget"):
        cr = profit_max_tour(ev, float(prof["budget"]))
        kn = knapsack_closure(ev, float(prof["budget"]))
        out["crunch"] = {"budget": prof["budget"], "value": cr["value"], "hours": round(cr["hours"], 2),
                         "ids": cr["ids"], "left_out": cr["left_out"], "knapsack_value": kn["value"],
                         "total_value": sum(web.topics[t].value for t in ev.ids)}
        sub = Evaluator(inst)
        out["crunch"]["days"] = shortest_path_split(sub, cr["seq"], P.day_hours)
    return out


def run_all(data_dir: str, out_dir: str, profiles_path: str, exact_max_n: int = 16, restarts: int = 5) -> List[Dict]:
    from .data import load_web

    web = load_web(data_dir)
    params = Params.load(os.path.join(data_dir, "params.json"))
    profiles = json.load(open(profiles_path))
    fresh = build_instance(web, Profile(), params)
    ev0 = Evaluator(fresh)
    naive = ev0.cost(curriculum_order(ev0)[0])
    os.makedirs(out_dir, exist_ok=True)
    res = []
    for prof in profiles:
        r = run_profile(web, params, prof, naive, exact_max_n=exact_max_n, restarts=restarts)
        res.append(r)
        print(f"{r['profile']:<18} n={r['n_topics']:<4} B0={r['B0']['total']:.2f} B1={r['B1']['total']:.2f} "
              f"roadmap={r['roadmap']['total']:.2f} days={r['days']['n_days']} (LB {r['days']['lb_days']})", flush=True)
        with open(os.path.join(out_dir, f"roadmap_{r['profile']}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["day", "topic_id", "topic", "course", "domain", "hours"])
            for d, day in enumerate(r["days"]["days"], 1):
                for t in day["topics"]:
                    T = web.topics[t]
                    w.writerow([d, t, T.name, T.course, T.domain, round(fresh.p.get(t, T.hours), 2)])
    json.dump(res, open(os.path.join(out_dir, "profiles.json"), "w"), indent=1, default=float)
    with open(os.path.join(out_dir, "profiles_summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["profile", "n_topics", "study_hours", "naive_B0", "B0", "B1", "roadmap", "scope_gain",
                    "seq_gain_vs_B0", "seq_gain_vs_B1", "days", "lb_days", "auto_added"])
        for r in res:
            w.writerow([r["profile"], r["n_topics"], r["study_hours"], r["naive_B0"], round(r["B0"]["total"], 2),
                        round(r["B1"]["total"], 2), round(r["roadmap"]["total"], 2), r["scope_gain"],
                        r["sequencing_gain_vs_B0"], r["sequencing_gain_vs_B1"], r["days"]["n_days"],
                        r["days"]["lb_days"], " ".join(r["auto_added"])])
    return res
