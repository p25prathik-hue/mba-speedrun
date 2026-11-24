"""Splitting a roadmap into days.

Class links
-----------
* Bin packing (Session 8, slides 10-16): days are bins of size b = H hours; topics are
  objects of size a_i = p_i. Lower bound on days: ceil(sum a_i / b) (slide 16).
* The class bin-packing heuristic (slide 10-11) *sorts* objects first. We cannot sort:
  the order is fixed by the roadmap (sorting would break prerequisites). Without the
  sort it becomes "fill today, then start a new day" = greedy_split().
* Exact split of a fixed order = shortest path (Session 7, slides 1-9): nodes are
  positions 0..n, an arc a -> b means "one day covers topics a+1..b" and is allowed if
  the day's hours fit in H. Same structure as the production lot-sizing application
  on Session 7 slide 1. The arc cost is lexicographic (1 day, then hours), so the
  shortest path gives the fewest days and, among those, the fewest hours.
* "Can I finish by day D?" = shortest path with at most D hops: Bellman-Ford with a
  hop limit (Session 7, slides 10-13).
* Clarke-Wright's key observation (S8 slide 27): routing has two dimensions, TSP and
  bin packing. Here the TSP part is the sequence and the bin-packing part is the days.
  Special cases: H >= total hours -> pure sequencing; c_ij = 0 -> pure bin packing.

A day's hours = day warm-up (the "depot leg" c_0i) + its topics' p_i + transitions
*inside* the day. A transition across a day boundary is replaced by the next day's
warm-up, so placing subject switches at day breaks saves time.

IIMA context: H is the hours a student can give per day around classes, CP and
committee work (e.g. 3 h on a class day, 8 h on a weekend).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

from .costs import Evaluator

BIG = 1e6


def _day_hours(ev: Evaluator, seq: Sequence[int], a: int, b: int) -> float:
    """Hours of a day covering seq[a:b] (topics a..b-1)."""
    P = ev.inst.params
    h = P.day_warmup + float(ev.p[list(seq[a:b])].sum())
    for k in range(a, b - 1):
        h += float(ev.C[seq[k], seq[k + 1]])
    return h


def lower_bound_days(ev: Evaluator, H: float) -> int:
    """Session 8 slide 16: ceil(sum a_i / b)."""
    return int(math.ceil(float(ev.p.sum()) / H - 1e-9))


def shortest_path_split(ev: Evaluator, seq: Sequence[int], H: Optional[float] = None,
                        max_days: Optional[int] = None) -> Dict:
    """Exact split of a fixed order into days (DAG shortest path; Dijkstra = DP here).

    If max_days is given, the hop-constrained version (Bellman-Ford with hop limit h)
    answers whether the order fits in that many days.
    """
    H = H or ev.inst.params.day_hours
    n = len(seq)
    # arc (a -> b) allowed if the day fits, or if it holds a single topic longer than H
    hours = {}
    for a in range(n):
        for b in range(a + 1, n + 1):
            h = _day_hours(ev, seq, a, b)
            if h <= H + 1e-9 or b == a + 1:
                hours[(a, b)] = h
            else:
                break
    if max_days is None:
        u = [math.inf] * (n + 1)
        pred = [-1] * (n + 1)
        u[0] = 0.0
        for a in range(n):  # positions are already in topological order
            if u[a] == math.inf:
                continue
            for b in range(a + 1, n + 1):
                if (a, b) not in hours:
                    break
                days = max(1, math.ceil(hours[(a, b)] / H - 1e-9))  # a long topic spans days
                c = u[a] + BIG * days + hours[(a, b)]
                if c < u[b] - 1e-9:
                    u[b], pred[b] = c, a
        cuts = []
        b = n
        while b > 0:
            cuts.append((pred[b], b))
            b = pred[b]
        cuts = cuts[::-1]
    else:
        # Bellman-Ford with hop limit: u_b^m = min(u_b^{m-1}, min_a u_a^{m-1} + cost(a,b))
        u = [math.inf] * (n + 1)
        u[0] = 0.0
        preds = []
        for m in range(max_days):
            nu = list(u)
            pr = {}
            for (a, b), h in hours.items():
                if u[a] + h < nu[b] - 1e-9:
                    nu[b], pr[b] = u[a] + h, a
            preds.append(pr)
            u = nu
        if u[n] == math.inf:
            return {"feasible": False, "days": None}
        # rebuild: walk back through hop layers
        cuts, b, m = [], n, max_days - 1
        while b > 0 and m >= 0:
            if b in preds[m]:
                a = preds[m][b]
                cuts.append((a, b))
                b = a
            m -= 1
        cuts = cuts[::-1]
    days = []
    for a, b in cuts:
        days.append({"topics": [ev.ids[k] for k in seq[a:b]], "hours": round(_day_hours(ev, seq, a, b), 2)})
    total_days = sum(max(1, math.ceil(d["hours"] / H - 1e-9)) for d in days)
    return {
        "feasible": True,
        "days": days,
        "n_days": total_days,
        "lb_days": lower_bound_days(ev, H),
        "total_hours": round(sum(d["hours"] for d in days), 2),
        "H": H,
    }


def greedy_split(ev: Evaluator, seq: Sequence[int], H: Optional[float] = None) -> Dict:
    """Class bin-packing heuristic (S8 slides 10-11) without the sort step."""
    H = H or ev.inst.params.day_hours
    days, a = [], 0
    n = len(seq)
    while a < n:
        b = a + 1
        while b < n and _day_hours(ev, seq, a, b + 1) <= H + 1e-9:
            b += 1
        days.append({"topics": [ev.ids[k] for k in seq[a:b]], "hours": round(_day_hours(ev, seq, a, b), 2)})
        a = b
    total_days = sum(max(1, math.ceil(d["hours"] / H - 1e-9)) for d in days)
    return {"days": days, "n_days": total_days, "lb_days": lower_bound_days(ev, H),
            "total_hours": round(sum(d["hours"] for d in days), 2), "H": H}
