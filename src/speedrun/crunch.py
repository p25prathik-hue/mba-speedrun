"""Crunch mode: the most value within a fixed number of hours.

Class links
-----------
* Profit-maximising tour heuristic (Session 9, slides 17-21):
      max sum r_i x_i - f(x)   s.t.  sum d_i x_i <= C
  with a "bang-for-buck" ratio (r_i - delta_i) / d_i and insertion cost delta_i
  (= Delta_ijk of cheapest insertion, S1 slide 33). In our problem value r_i
  (exam / placement relevance) and hours are different units, so the budget C is in
  hours and the ratio becomes  r(K_i) / (hours added by K_i),  where K_i is topic i
  plus its missing prerequisites (closure), inserted at the cheapest feasible spots.
  As on slide 20 we try several initial tours and keep the best.
* Exact references:
  - prize-collecting SOP MILP (milp.solve_crunch_exact), pilot scale only;
  - capital-budgeting knapsack with logical constraints (Session 5 slide 7;
    Session 8 slides 7-8):  max sum r_i z_i,  sum p_i z_i <= C,  z_j <= z_k for each
    AND prerequisite, z_j <= sum_{k in G} z_k for each OR group. It ignores sequence
    effects (switching, synergy, forgetting).
* Common carrier (Session 9, slides 12-16): topics left out of the crunch plan are
  the ones to "outsource" to a senior's session or peer notes; the removal saving
  delta_i tells you how many hours each one would cost to keep.

IIMA context: "summers in 3 weeks" or "end-terms in 4 days": the student cannot do
everything, so the question becomes which topics give the most marks or interview
readiness per hour.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

import numpy as np

from .costs import INF, Evaluator
from .heuristics import local_search


def _closure(ev: Evaluator, i: int, have: Set[int]) -> List[int]:
    """Topic i plus missing required prerequisites, in a feasible order (cheapest OR route)."""
    out: List[int] = []
    seen = set(have)

    def add(v, depth=0):
        if v in seen or depth > 60:
            return
        for a in ev.and_pred[v]:
            add(a, depth + 1)
        for m in ev.or_of[v]:
            if any(int(k) in seen for k in m):
                continue
            # cheapest member by its own closure hours
            best = min((int(k) for k in m), key=lambda k: _closure_hours(ev, k, seen))
            add(best, depth + 1)
        seen.add(v)
        out.append(v)

    add(i)
    return out


def _closure_hours(ev: Evaluator, k: int, have: Set[int]) -> float:
    tot, stack, seen = 0.0, [k], set(have)
    while stack:
        v = stack.pop()
        if v in seen:
            continue
        seen.add(v)
        tot += ev.p[v]
        stack.extend(ev.and_pred[v])
    return tot


def _insert_cheapest(ev: Evaluator, tour: List[int], v: int) -> List[int]:
    """Insert v where Delta_ijk = c_iv + c_vj - c_ij is smallest (S1 sl.33; delta_i of S9 sl.18),
    after its prerequisites already in the tour. Depot legs: c_S,first = c0, c_last,E = 0."""
    pos = {t: k for k, t in enumerate(tour)}
    lo = 0
    for a in ev.and_pred[v]:
        if a in pos:
            lo = max(lo, pos[a] + 1)
    for m in ev.or_of[v]:
        placed = [pos[int(k)] for k in m if int(k) in pos]
        if placed:
            lo = max(lo, min(placed) + 1)

    def cx(a, b):
        if a is None:
            return ev.c0 if b is not None else 0.0
        if b is None:
            return 0.0
        return float(ev.C[a, b])

    best, bins = INF, lo
    for ins in range(lo, len(tour) + 1):
        a = tour[ins - 1] if ins > 0 else None
        b = tour[ins] if ins < len(tour) else None
        d = cx(a, v) + cx(v, b) - cx(a, b)
        if d < best - 1e-12:
            best, bins = d, ins
    return tour[:bins] + [v] + tour[bins:]


def _partial_cost(ev: Evaluator, seq: List[int]) -> float:
    """Exact hours of a partial roadmap (only the selected topics, in this order)."""
    if not seq:
        return 0.0
    s = np.asarray(seq)
    inn = np.zeros(ev.n, bool)
    inn[s] = True
    pos = np.full(ev.n, -1)
    pos[s] = np.arange(len(s))
    end = np.zeros(ev.n)
    end[s] = np.cumsum(ev.p[s])
    h = ev.c0 + float(ev.p[s].sum()) + float(ev.C[s[:-1], s[1:]].sum())
    rl = lambda g, k: np.minimum(ev.rho * np.maximum(0.0, g - ev.L), ev.kappa * ev.p[k])
    if len(ev.ak):
        m = inn[ev.ak] & inn[ev.aj]
        k, j = ev.ak[m], ev.aj[m]
        h += float(rl(end[j] - ev.p[j] - end[k], k).sum())
    if len(ev.sk):
        m = inn[ev.sk] & inn[ev.sj]
        k, j = ev.sk[m], ev.sj[m]
        viol = pos[k] > pos[j]
        h += ev.pi_soft * float(viol.sum())
        h += float(rl(end[j] - ev.p[j] - end[k], k)[~viol].sum())
    return h


def profit_max_tour(ev: Evaluator, budget: float, values: Optional[Dict[int, float]] = None,
                    n_starts: int = 5) -> Dict:
    """S9 slide 20, adapted: grow the roadmap by the best value-per-hour closure."""
    values = values or {i: ev.inst.web.topics[ev.ids[i]].value for i in range(ev.n)}
    roots = [i for i in range(ev.n) if not ev.and_pred[i] and not ev.or_of[i]]
    roots.sort(key=lambda i: -values[i] / ev.p[i])
    best_res = None
    for k in [None] + roots[: max(0, n_starts - 1)]:
        tour: List[int] = []
        if k is not None and ev.p[k] + ev.c0 <= budget:
            tour = [k]
        while True:
            have = set(tour)
            cur = _partial_cost(ev, tour)
            best = None
            for i in range(ev.n):
                if i in have:
                    continue
                K = _closure(ev, i, have)
                t2 = list(tour)
                for v in K:
                    t2 = _insert_cheapest(ev, t2, v)
                h2 = _partial_cost(ev, t2)
                if h2 > budget + 1e-9:
                    continue
                ratio = sum(values[v] for v in K) / max(1e-6, h2 - cur)  # value per hour consumed
                if best is None or ratio > best[0]:
                    best = (ratio, t2)
            if best is None:
                break
            tour = best[1]
        val = sum(values[v] for v in tour)
        res = {"seq": tour, "value": val, "hours": _partial_cost(ev, tour), "start": None if k is None else ev.ids[k]}
        if best_res is None or val > best_res["value"] or (val == best_res["value"] and res["hours"] < best_res["hours"]):
            best_res = res
    best_res["ids"] = [ev.ids[v] for v in best_res["seq"]]
    left_out = [ev.ids[i] for i in range(ev.n) if i not in set(best_res["seq"])]
    best_res["left_out"] = left_out
    return best_res


def knapsack_closure(ev: Evaluator, budget: float) -> Dict:
    """Session 5 slide 7 (capital budgeting with logical constraints) as a 0-1 IP."""
    import pulp  # imported here so the crunch heuristic works without PuLP installed

    prob = pulp.LpProblem("knap", pulp.LpMaximize)
    z = {i: pulp.LpVariable(f"z{i}", cat=pulp.LpBinary) for i in range(ev.n)}
    vals = {i: ev.inst.web.topics[ev.ids[i]].value for i in range(ev.n)}
    prob += pulp.lpSum(vals[i] * z[i] for i in z) - 1e-4 * pulp.lpSum(float(ev.p[i]) * z[i] for i in z)
    prob += pulp.lpSum(float(ev.p[i]) * z[i] for i in z) <= budget
    for k, j in zip(ev.ak, ev.aj):
        prob += z[int(j)] <= z[int(k)]  # "project j cannot be undertaken unless project k is"
    for j, m in ev.orgroups:
        prob += z[int(j)] <= pulp.lpSum(z[int(k)] for k in m)  # either-or
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=60))
    chosen = [i for i in z if z[i].value() > 0.5]
    return {"chosen": [ev.ids[i] for i in chosen], "value": sum(vals[i] for i in chosen),
            "study_hours": float(sum(ev.p[i] for i in chosen))}
