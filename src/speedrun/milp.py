"""Exact model (pilot scale) and lower bounds.

Formulation in the professor's notation
---------------------------------------
Nodes: S (dummy start, Q_S = T), topics N = {1..n}, E (dummy end, Q_E = 0).
x_ij = 1 if topic j is studied immediately after i                (S6 slide 3)
Q_i  = study hours still to go just before starting topic i      (S9 slide 22)
       ("load on vehicle immediately before reaching customer i", with d_i = p_i, C = T)

min  sum_i p_i + sum_ij c_ij x_ij + sum r_kj + pi * sum v_kj
s.t. (I)   sum_j x_ij = 1            for all i in S u N
     (II)  sum_i x_ij = 1            for all j in N u E
     (Load) Q_i >= Q_j + p_i x_ij - T(1 - x_ij)      (S9 slide 22: kills subtours)
            Q_i <= Q_j + p_i + T(1 - x_ij)          (makes Q an exact clock)
     (AND)  Q_k >= Q_j + p_k                         k must precede j
     (OR)   sum_{k in G_j} y_kj >= 1,  Q_k >= Q_j + p_k - T(1 - y_kj)   (S5 slides 4, 7)
     (SOFT) Q_k >= Q_j + p_k - T v_kj,  v_kj in {0,1}  (penalised violation)
     (REV)  r_kj = min(rho (Q_k - p_k - Q_j - L)^+, kappa p_k)  (forgetting, capped; S1 slides 2-5)
            linearised with a binary b_kj when the cap can bind:
            r >= rho(gap - L) - M b,  r >= kappa p_k b,  r >= 0       (S5 slides 11-12: big-M logic)
     x, y, v binary; p_i <= Q_i <= T

Valid inequalities / arc fixing (S9 slides 23-25):
     x_jk = 0 if k is an AND-ancestor of j;  x_Sj = 0 if j has a prerequisite in scope;
     x_iE = 0 if i has a dependent in scope;  x_ij + x_ji <= 1 (subtour breaking, |S| = 2).

Bounds (S5 slide 16, S6 slide 3):
     assignment relaxation  <=  LP relaxation  <=  LP + cuts  <=  z*  <=  heuristic

IIMA context: exact B&B is practical for a ~30-topic pilot (e.g. the Finance +
Accounting core), which is how we measure how far the heuristics are from optimal.
"""
from __future__ import annotations

import os
import re
import tempfile
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pulp
from scipy.optimize import linear_sum_assignment

from .costs import Evaluator
from .graph import and_ancestors


def _solver(time_limit: float = 300, msg: bool = False, warm: bool = False, log_path: Optional[str] = None):
    avail = pulp.listSolvers(onlyAvailable=True)
    if "PULP_CBC_CMD" in avail:
        return pulp.PULP_CBC_CMD(msg=msg, timeLimit=time_limit, warmStart=warm, logPath=log_path)
    if "COIN_CMD" in avail:
        return pulp.COIN_CMD(msg=msg, timeLimit=time_limit, warmStart=warm, logPath=log_path)
    if "HiGHS" in avail:
        return pulp.HiGHS(msg=msg, timeLimit=time_limit)
    raise RuntimeError("No MILP solver found: pip install 'pulp[cbc]' or highspy")


def build_model(ev: Evaluator, relax: bool = False, cuts: bool = True, budget: Optional[float] = None):
    """Build the SOP model. If budget is given, build the crunch (prize-collecting) variant:
    max sum r_i z_i  s.t. total hours <= budget (S9 slides 17-21; S5 slide 7)."""
    inst = ev.inst
    n = ev.n
    N = list(range(n))
    S, E = "S", "E"
    p = ev.p
    T = float(p.sum())
    cat = pulp.LpContinuous if relax else pulp.LpBinary
    crunch = budget is not None
    prob = pulp.LpProblem("crunch" if crunch else "sop", pulp.LpMaximize if crunch else pulp.LpMinimize)

    anc = and_ancestors(inst.web) if cuts else {}
    has_pred = {j: bool(ev.and_pred[j]) or bool(ev.or_of[j]) for j in N}
    has_succ = {i: bool(ev.and_succ[i]) for i in N}

    arcs = []
    for j in N:
        if not (cuts and has_pred[j]) or crunch:
            arcs.append((S, j))
    for i in N:
        if not (cuts and has_succ[i]) or crunch:
            arcs.append((i, E))
    for i in N:
        for j in N:
            if i == j:
                continue
            if cuts and ev.ids[j] in anc.get(ev.ids[i], set()):
                continue  # j is an ancestor of i: j cannot come right after i
            arcs.append((i, j))
    if crunch:
        arcs.append((S, E))
    x = {a: pulp.LpVariable(f"x_{a[0]}_{a[1]}", lowBound=0, upBound=1, cat=cat) for a in arcs}
    Q = {i: pulp.LpVariable(f"Q_{i}", lowBound=0, upBound=T) for i in N}
    z = {i: (pulp.LpVariable(f"z_{i}", lowBound=0, upBound=1, cat=cat) if crunch else 1) for i in N}

    def cost(a):
        i, j = a
        if i == S:
            return ev.c0 if j != E else 0.0
        if j == E:
            return 0.0
        return float(ev.C[i, j])

    out_arcs = {v: [] for v in [S] + N}
    in_arcs = {v: [] for v in N + [E]}
    for a in arcs:
        out_arcs[a[0]].append(a)
        in_arcs[a[1]].append(a)
    # (I) and (II)
    prob += pulp.lpSum(x[a] for a in out_arcs[S]) == 1
    prob += pulp.lpSum(x[a] for a in in_arcs[E]) == 1
    for i in N:
        prob += pulp.lpSum(x[a] for a in out_arcs[i]) == z[i], f"out_{i}"
        prob += pulp.lpSum(x[a] for a in in_arcs[i]) == z[i], f"in_{i}"
    # Load (Q) constraints
    QS, QE = T, 0.0
    for (i, j) in arcs:
        if i == S and j == E:
            continue
        qi = QS if i == S else Q[i]
        qj = QE if j == E else Q[j]
        pi_ = 0.0 if i == S else float(p[i])
        prob += qi >= qj + pi_ * x[(i, j)] - T * (1 - x[(i, j)])
        if i != S:  # exact clock is anchored at E (Q_E = 0); Q_S only bounds from above
            prob += qi <= qj + pi_ + T * (1 - x[(i, j)])
    for i in N:
        prob += Q[i] >= float(p[i]) * (z[i] if crunch else 1)
    if cuts and not crunch:
        # every AND-descendant of i comes after i, every AND-ancestor before it:
        #   Q_i >= p_i + sum_{desc} p,   Q_i <= T - sum_{anc} p     (valid inequalities)
        idx = {t: k for k, t in enumerate(ev.ids)}
        for i in N:
            anc_i = [idx[a] for a in anc.get(ev.ids[i], set()) if a in idx]
            desc_i = [k for k in N if ev.ids[i] in anc.get(ev.ids[k], set())]
            prob += Q[i] >= float(p[i]) + float(sum(p[k] for k in desc_i))
            prob += Q[i] <= T - float(sum(p[k] for k in anc_i))
    if cuts and not crunch:
        seen = set()
        for (i, j) in arcs:
            if i in N and j in N and (j, i) in x and (j, i) not in seen:
                prob += x[(i, j)] + x[(j, i)] <= 1
                seen.add((i, j))
    rev_terms = []
    aux = {}
    rho, L, M = ev.rho, ev.L, T
    kappa = ev.kappa
    nb = [0]

    def capped(r, k, j, expr_gap, relax_terms):
        """Add r >= min(rho*(gap - L)^+, kappa*p_k) for one link (relax_terms switch it off)."""
        cap_k = kappa * float(p[k])
        thr = L + (cap_k / rho if rho > 0 else float("inf"))
        if T - float(p[k]) - float(p[j]) <= thr + 1e-9:  # the cap can never bind
            prob.__iadd__(r >= rho * (expr_gap - L) - relax_terms * rho * M)
            return
        nb[0] += 1
        b = pulp.LpVariable(f"b{nb[0]}_{k}_{j}", lowBound=0, upBound=1, cat=cat)
        prob.__iadd__(r >= rho * (expr_gap - L) - relax_terms * rho * M - rho * M * b)
        prob.__iadd__(r >= cap_k * b - relax_terms * cap_k)
    # AND precedence + revision
    for k, j in zip(ev.ak, ev.aj):
        k, j = int(k), int(j)
        if crunch:
            prob += z[j] <= z[k]  # S5 slide 7: x5 <= x4
            prob += Q[k] >= Q[j] + float(p[k]) - T * (1 - z[j])
        else:
            prob += Q[k] >= Q[j] + float(p[k])
        r = pulp.LpVariable(f"r_{k}_{j}", lowBound=0)
        capped(r, k, j, Q[k] - float(p[k]) - Q[j], (2 - z[k] - z[j]) if crunch else 0)
        rev_terms.append(r)
    # OR groups
    for gi, (j, mem) in enumerate(ev.orgroups):
        j = int(j)
        ys = []
        rG = pulp.LpVariable(f"rG_{gi}", lowBound=0)
        for k in mem:
            k = int(k)
            y = pulp.LpVariable(f"y_{k}_{j}", lowBound=0, upBound=1, cat=cat)
            ys.append(y)
            aux[("y", k, j)] = y
            prob += Q[k] >= Q[j] + float(p[k]) - T * (1 - y)
            if crunch:
                prob += y <= z[k]
            capped(rG, k, j, Q[k] - float(p[k]) - Q[j], (1 - y))
        prob += pulp.lpSum(ys) >= (z[j] if crunch else 1)
        rev_terms.append(rG)
    # SOFT
    soft_terms = []
    for k, j in zip(ev.sk, ev.sj):
        k, j = int(k), int(j)
        v = pulp.LpVariable(f"v_{k}_{j}", lowBound=0, upBound=1, cat=cat)
        aux[("v", k, j)] = v
        prob += Q[k] >= Q[j] + float(p[k]) - T * v - (T * (2 - z[k] - z[j]) if crunch else 0)
        r = pulp.LpVariable(f"rs_{k}_{j}", lowBound=0)
        capped(r, k, j, Q[k] - float(p[k]) - Q[j], v + ((2 - z[k] - z[j]) if crunch else 0))
        soft_terms.append(ev.pi_soft * v)
        rev_terms.append(r)
    hours = (pulp.lpSum(float(p[i]) * z[i] for i in N) if crunch else float(p.sum())) \
        + pulp.lpSum(cost(a) * x[a] for a in arcs) + pulp.lpSum(rev_terms) + pulp.lpSum(soft_terms)
    if crunch:
        val = {i: ev.inst.web.topics[ev.ids[i]].value for i in N}
        prob += pulp.lpSum(val[i] * z[i] for i in N) - 1e-3 * hours
        prob += hours <= budget, "budget"
    else:
        prob += hours
    prob._aux = aux
    return prob, x, Q, z, arcs


def _extract(ev: Evaluator, x, arcs) -> List[int]:
    nxt = {}
    for a in arcs:
        if x[a].value() is not None and x[a].value() > 0.5:
            nxt[a[0]] = a[1]
    seq, cur = [], "S"
    while cur in nxt and nxt[cur] != "E":
        cur = nxt[cur]
        seq.append(cur)
        if len(seq) > ev.n + 1:
            break
    return seq


def solve_exact(ev: Evaluator, time_limit: float = 300, warm_seq: Optional[List[int]] = None,
                cuts: bool = True, msg: bool = False) -> Dict:
    """Branch and bound (CBC) on the SOP. warm_seq gives the first incumbent (S8 slide 9)."""
    prob, x, Q, z, arcs = build_model(ev, relax=False, cuts=cuts)
    if warm_seq is not None:
        seqx = ["S"] + list(warm_seq) + ["E"]
        on = set(zip(seqx[:-1], seqx[1:]))
        for a in arcs:
            x[a].setInitialValue(1 if a in on else 0)
        rem = float(ev.p.sum())
        pos = {v: k for k, v in enumerate(warm_seq)}
        for i in warm_seq:
            Q[i].setInitialValue(rem)
            rem -= float(ev.p[i])
        for key, var in prob._aux.items():
            kind, k, j = key
            if kind == "v":
                var.setInitialValue(1 if pos[k] > pos[j] else 0)
        for j, mem in ev.orgroups:  # y: the latest member placed before j
            before = [int(k) for k in mem if pos[int(k)] < pos[int(j)]]
            last = max(before, key=lambda k: pos[k])
            for k in mem:
                prob._aux[("y", int(k), int(j))].setInitialValue(1 if int(k) == last else 0)
    log = tempfile.NamedTemporaryFile(suffix=".log", delete=False).name
    t0 = time.time()
    status = prob.solve(_solver(time_limit, msg=msg, warm=warm_seq is not None, log_path=log))
    secs = time.time() - t0
    seq = _extract(ev, x, arcs)
    nodes, best_bound = None, None
    try:
        txt = open(log).read()
        m = re.findall(r"Enumerated nodes:\s+(\d+)", txt) or re.findall(r"after (\d+) nodes", txt)
        nodes = int(m[-1]) if m else None
        bb = re.findall(r"best possible ([\-\d\.e+]+)", txt)
        lb = re.findall(r"Lower bound:\s+([\-\d\.e+]+)", txt)
        best_bound = float(lb[-1]) if lb else (float(bb[-1]) if bb else None)
        solve_log_tail = txt[-1500:]
        os.unlink(log)
    except Exception:
        pass
    obj = ev.cost(seq) if len(seq) == ev.n else float("inf")
    return {
        "status": pulp.LpStatus[status],
        "optimal": pulp.LpStatus[status] == "Optimal" and secs < time_limit - 1,
        "objective_model": pulp.value(prob.objective),
        "objective_eval": obj,
        "seq": seq,
        "secs": round(secs, 2),
        "nodes": nodes,
        "best_bound": best_bound,
        "n_vars": len(prob.variables()),
        "n_cons": len(prob.constraints),
    }


def lp_bound(ev: Evaluator, cuts: bool) -> float:
    prob, *_ = build_model(ev, relax=True, cuts=cuts)
    prob.solve(_solver(120))
    return float(pulp.value(prob.objective))


def assignment_bound(ev: Evaluator, cuts: bool = True) -> float:
    """Relax (III) / the load constraints: an assignment problem (S6 slide 3).

    Rows: S, 1..n ; columns: 1..n, E. Arc E->S closes the tour at cost 0.
    Revision and soft penalties are >= 0, so dropping them keeps a valid bound.
    """
    n = ev.n
    BIG = 1e6
    M = np.full((n + 1, n + 1), BIG)
    anc = and_ancestors(ev.inst.web) if cuts else {}
    for j in range(n):
        if not (cuts and (ev.and_pred[j] or ev.or_of[j])):
            M[0, j] = ev.c0
    for i in range(n):
        if not (cuts and ev.and_succ[i]):
            M[i + 1, n] = 0.0
        for j in range(n):
            if i != j and not (cuts and ev.ids[j] in anc.get(ev.ids[i], set())):
                M[i + 1, j] = ev.C[i, j]
    r, c = linear_sum_assignment(M)
    return float(ev.p.sum() + M[r, c].sum())


def solve_crunch_exact(ev: Evaluator, budget: float, time_limit: float = 300) -> Dict:
    prob, x, Q, z, arcs = build_model(ev, relax=False, cuts=False, budget=budget)
    t0 = time.time()
    status = prob.solve(_solver(time_limit))
    seq = _extract(ev, x, arcs)
    val = sum(ev.inst.web.topics[ev.ids[i]].value for i in seq)
    return {"status": pulp.LpStatus[status], "seq": seq, "value": val, "secs": round(time.time() - t0, 2)}
