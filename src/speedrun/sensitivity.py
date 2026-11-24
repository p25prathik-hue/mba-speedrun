"""Sensitivity analysis: are the results an artefact of estimated costs?

Not in the class decks; this is our extension. It is needed because every time and
cost parameter is an estimate (Session 10, slide 6 lists deterministic vs stochastic
as a modelling choice; we stay deterministic and stress-test instead).

Three tests
-----------
1. Null test: set w = s = rho = pi = 0. Every feasible order then costs the same, so
   the sequencing gain must be exactly 0. If it is not, the code is wrong.
2. One-at-a-time +-25% on each parameter and on all topic hours (tornado chart).
3. Monte Carlo: every t_i and every parameter drawn from U[0.75, 1.25] x nominal.
   For each draw we re-optimise and report
     * gain vs B0 / B1 (re-optimised plan vs baseline under the same draw),
     * regret of the nominal plan = cost(nominal plan under draw) - cost(re-optimised),
       i.e. how much a student loses by following our plan if the true costs differ.

IIMA context: the Acads committee should only act on findings that survive these tests.
"""
from __future__ import annotations

import random
from typing import Dict, List

import numpy as np

from .baselines import curriculum_order, subject_by_subject
from .costs import Evaluator
from .data import Instance, Params
from .heuristics import solve_heuristic

PARAMS = ["w_switch", "s_synergy", "rho_revision", "L_revision_free", "revision_cap_share", "soft_penalty"]


def _reinstance(inst: Instance, params: Params, hours_scale: Dict[str, float] = None) -> Instance:
    p = dict(inst.p)
    if hours_scale:
        p = {t: v * hours_scale.get(t, 1.0) for t, v in p.items()}
    return Instance(web=inst.web, ids=inst.ids, p=p, known=inst.known, params=params,
                    warnings=inst.warnings, auto_added=inst.auto_added, profile_name=inst.profile_name)


def _evaluate(inst: Instance, nominal_ids: List[str], restarts: int, seed: int) -> Dict:
    ev = Evaluator(inst)
    b0, _ = curriculum_order(ev)
    b1 = subject_by_subject(ev)
    seq, best = solve_heuristic(ev, restarts=restarts, seed=seed, extra_starts={"B0": b0, "B1": b1})
    nom = ev.cost(ev.from_ids(nominal_ids))
    c0, c1 = ev.cost(b0), ev.cost(b1)
    return {
        "B0": c0, "B1": c1, "opt": best, "nominal_plan": nom,
        "gain_vs_B0": c0 - best, "gain_vs_B1": c1 - best,
        "gain_vs_B0_pct": 100 * (c0 - best) / c0, "gain_vs_B1_pct": 100 * (c1 - best) / c1,
        "regret_nominal": nom - best,
    }


def null_test(inst: Instance, restarts: int = 2) -> Dict:
    P0 = inst.params.copy(w_switch=0.0, s_synergy=0.0, rho_revision=0.0, soft_penalty=0.0, start_warmup=0.0)
    i0 = _reinstance(inst, P0)
    ev = Evaluator(i0)
    b0, _ = curriculum_order(ev)
    r = _evaluate(i0, ev.to_ids(b0), restarts, 0)
    return {"B0": r["B0"], "opt": r["opt"], "gain": r["gain_vs_B0"], "passes": abs(r["gain_vs_B0"]) < 1e-9}


def one_at_a_time(inst: Instance, nominal_ids: List[str], delta: float = 0.25, restarts: int = 2) -> List[Dict]:
    rows = []
    for name in PARAMS + ["all_hours"]:
        for sgn in (-1, 1):
            f = 1 + sgn * delta
            if name == "all_hours":
                i2 = _reinstance(inst, inst.params, {t: f for t in inst.ids})
            else:
                i2 = _reinstance(inst, inst.params.copy(**{name: getattr(inst.params, name) * f}))
            r = _evaluate(i2, nominal_ids, restarts, 0)
            r.update({"param": name, "factor": f})
            rows.append(r)
    return rows


def monte_carlo(inst: Instance, nominal_ids: List[str], draws: int = 100, delta: float = 0.25,
                restarts: int = 1, seed: int = 7) -> List[Dict]:
    rng = random.Random(seed)
    rows = []
    for d in range(draws):
        kw = {k: getattr(inst.params, k) * rng.uniform(1 - delta, 1 + delta) for k in PARAMS}
        hs = {t: rng.uniform(1 - delta, 1 + delta) for t in inst.ids}
        i2 = _reinstance(inst, inst.params.copy(**kw), hs)
        r = _evaluate(i2, nominal_ids, restarts, d)
        r["draw"] = d
        rows.append(r)
    return rows


def summarise(rows: List[Dict], key: str) -> Dict:
    v = np.array([r[key] for r in rows])
    return {"mean": float(v.mean()), "p5": float(np.percentile(v, 5)), "p50": float(np.median(v)),
            "p95": float(np.percentile(v, 95)), "share_positive": float((v > 1e-9).mean())}
