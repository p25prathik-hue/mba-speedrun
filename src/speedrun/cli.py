"""Command line entry point.

    python run.py audit       --data data/sample
    python run.py solve       --data data/sample [--skip A1,A2] [--known Q1] [--hours 6]
    python run.py exact       --data data/sample --targets F8,M6
    python run.py profiles    --data data/sample --profiles data/sample/profiles.json
    python run.py sensitivity --data data/sample --draws 100
    python run.py web         --data data/sample --out docs/data/web.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .baselines import curriculum_order, subject_by_subject
from .costs import Evaluator
from .data import Params, Profile, load_web
from .days import shortest_path_split
from .graph import audit, build_instance
from .heuristics import solve_heuristic


def _csv(s):
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def main(argv=None):
    ap = argparse.ArgumentParser(prog="speedrun")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("audit", "solve", "exact", "profiles", "sensitivity", "web", "inspect"):
        p = sub.add_parser(name)
        p.add_argument("--data", default="data/sample")
        p.add_argument("--out", default=None)
        p.add_argument("--skip", default="")
        p.add_argument("--known", default="")
        p.add_argument("--targets", default="")
        p.add_argument("--hours", type=float, default=None, help="study hours per day (H)")
        p.add_argument("--profiles", default=None)
        p.add_argument("--draws", type=int, default=100)
        p.add_argument("--time-limit", type=float, default=300)
        p.add_argument("--restarts", type=int, default=5)
    a = ap.parse_args(argv)
    web = load_web(a.data)
    params = Params.load(os.path.join(a.data, "params.json"))
    if a.hours:
        params = params.copy(day_hours=a.hours)

    if a.cmd == "inspect":
        print(json.dumps(web.colmap, indent=1))
        return
    if a.cmd == "audit":
        print(json.dumps(audit(web), indent=1))
        return
    prof = Profile(name="cli", skip=_csv(a.skip), known=_csv(a.known), targets=_csv(a.targets))
    inst = build_instance(web, prof, params)
    ev = Evaluator(inst)
    for w in inst.warnings:
        print("NOTE:", w)
    if a.cmd == "solve":
        b0, _ = curriculum_order(ev)
        b1 = subject_by_subject(ev)
        seq, c = solve_heuristic(ev, restarts=a.restarts, extra_starts={"B0": b0, "B1": b1})
        print(f"topics={ev.n}  B0={ev.cost(b0):.2f} h  B1={ev.cost(b1):.2f} h  roadmap={c:.2f} h")
        sp = shortest_path_split(ev, seq)
        print(f"days={sp['n_days']} (lower bound {sp['lb_days']}) at {sp['H']} h/day")
        for d, day in enumerate(sp["days"], 1):
            print(f"Day {d:>2} ({day['hours']:.1f} h): " + " | ".join(web.topics[t].name for t in day["topics"]))
    elif a.cmd == "exact":
        from . import milp
        seq, c = solve_heuristic(ev, restarts=2)
        r = milp.solve_exact(ev, time_limit=a.time_limit, warm_seq=seq)
        print(f"n={ev.n} heuristic={c:.4f} exact={r['objective_eval']:.4f} proven={r['optimal']} "
              f"secs={r['secs']} nodes={r['nodes']}")
        print(f"bounds: assignment={milp.assignment_bound(ev):.3f} LP={milp.lp_bound(ev, False):.3f} "
              f"LP+cuts={milp.lp_bound(ev, True):.3f}")
        print(" -> ".join(ev.to_ids(r["seq"])))
    elif a.cmd == "profiles":
        from .experiments import run_all
        run_all(a.data, a.out or "results", a.profiles or os.path.join(a.data, "profiles.json"), restarts=a.restarts)
    elif a.cmd == "sensitivity":
        from . import sensitivity as S
        seq, _ = solve_heuristic(ev, restarts=a.restarts)
        nominal = ev.to_ids(seq)
        res = {"null": S.null_test(inst), "oat": S.one_at_a_time(inst, nominal),
               "mc": S.monte_carlo(inst, nominal, draws=a.draws)}
        res["summary"] = {k: S.summarise(res["mc"], k) for k in
                          ("gain_vs_B0_pct", "gain_vs_B1_pct", "regret_nominal")}
        out = a.out or "results/sensitivity.json"
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        json.dump(res, open(out, "w"), indent=1)
        print(json.dumps(res["summary"], indent=1))
    elif a.cmd == "web":
        from .webexport import export
        export(web, params, a.out or "docs/data/web.json", a.profiles or os.path.join(a.data, "profiles.json"),
               os.path.join("results", os.path.basename(os.path.normpath(a.data)), "profiles.json"),
               var=("SPEEDRUN_PILOT" if os.path.basename(os.path.normpath(a.data)) == "sample" else "SPEEDRUN_WEB"))


if __name__ == "__main__":
    main(sys.argv[1:])
