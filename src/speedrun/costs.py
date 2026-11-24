"""Cost model and fast sequence evaluation.

Class links
-----------
* c_ij is the TSP "distance" (Session 1, slide 15). Here it is a sequence-dependent
  setup time (Session 6, slide 1): asymmetric, can be negative, and is not metric.
  That is why the worst-case bounds of Session 1 slide 25 and Session 3 slides 14
  and 28 do not apply, and we measure empirical gaps against exact solutions instead.
* Revision (forgetting) cost uses the professor's load-variable clock Q_i (Session 9,
  slide 22): the gap between finishing prerequisite k and starting topic j is
  Q_k - p_k - Q_j study hours. Interpretation from Session 1, slides 2-5: knowledge
  held too long before it is used is like inventory that goes obsolete.

Objective of a sequence pi (topics only; dummy start 0 and end n+1 implicit):
    z(pi) = sum_i p_i + c_0,pi1 + sum_k c_{pi_k pi_k+1}
            + sum_{links k->j} min(rho * max(0, gap_kj - L), kappa * p_k) + sum_{SOFT violated} pi_soft

with p_i = m_i t_i and
    c_ij = w [domain_i != domain_j] - s * sim(i,j) * p_j

IIMA context: w is the warm-up when you switch from, say, FRA to Marketing; the
synergy saving s*sim*p_j is the time saved when WACC follows CAPM directly.
All parameter values are estimates (see docs/assumptions.md).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence

import numpy as np

from .data import Instance

INF = float("inf")

try:  # optional: ~20x faster evaluation for the 266-topic web (same arithmetic as the numpy path)
    from numba import njit
except Exception:  # pragma: no cover
    njit = None


def _total_py(seq, n, p, C, c0, rho, L, kappa, pi, ak, aj, sk, sj, orj, orptr, ormem):
    pos = np.empty(n, np.int64)
    for k in range(len(seq)):
        pos[seq[k]] = k
    for e in range(len(ak)):
        if pos[ak[e]] >= pos[aj[e]]:
            return np.inf
    for g in range(len(orj)):
        ok = False
        for q in range(orptr[g], orptr[g + 1]):
            if pos[ormem[q]] < pos[orj[g]]:
                ok = True
                break
        if not ok:
            return np.inf
    end = np.empty(n)
    clock = 0.0
    tot = 0.0
    for k in range(len(seq)):
        clock += p[seq[k]]
        end[seq[k]] = clock
        tot += p[seq[k]]
    if len(seq) > 0:
        tot += c0
    for k in range(len(seq) - 1):
        tot += C[seq[k], seq[k + 1]]
    for e in range(len(ak)):
        g = end[aj[e]] - p[aj[e]] - end[ak[e]] - L
        if g > 0:
            tot += min(rho * g, kappa * p[ak[e]])
    for e in range(len(sk)):
        if pos[sk[e]] > pos[sj[e]]:
            tot += pi
        else:
            g = end[sj[e]] - p[sj[e]] - end[sk[e]] - L
            if g > 0:
                tot += min(rho * g, kappa * p[sk[e]])
    for g in range(len(orj)):
        best = np.inf
        j = orj[g]
        for q in range(orptr[g], orptr[g + 1]):
            k = ormem[q]
            if pos[k] < pos[j]:
                gap = end[j] - p[j] - end[k] - L
                r = min(rho * gap, kappa * p[k]) if gap > 0 else 0.0
                if r < best:
                    best = r
        tot += best
    return tot


def _total_np(seq, n, p, C, c0, rho, L, kappa, pi, ak, aj, sk, sj, orj, orptr, ormem):
    """Vectorised numpy version of _total_py (same terms; used when numba is missing).

    About 10-20x faster than the plain loops on the 266-topic web, so the tool stays
    usable on a laptop without numba. tests/test_core.py checks it against _total_py.
    """
    m = len(seq)
    pos = np.empty(n, np.int64)
    pos[seq] = np.arange(m)
    if len(ak) and bool((pos[ak] >= pos[aj]).any()):
        return np.inf
    if len(orj):
        sizes = np.diff(orptr)
        jrep = np.repeat(orj, sizes)
        before = pos[ormem] < pos[jrep]
        if not bool(np.logical_or.reduceat(before, orptr[:-1]).all()):
            return np.inf
    ps = p[seq]
    end = np.empty(n)
    end[seq] = np.cumsum(ps)
    tot = float(ps.sum())
    if m > 0:
        tot += c0
    if m > 1:
        tot += float(C[seq[:-1], seq[1:]].sum())
    if len(ak):
        g = end[aj] - p[aj] - end[ak] - L
        tot += float(np.minimum(rho * np.maximum(g, 0.0), kappa * p[ak]).sum())
    if len(sk):
        back = pos[sk] > pos[sj]
        g = end[sj] - p[sj] - end[sk] - L
        r = np.minimum(rho * np.maximum(g, 0.0), kappa * p[sk])
        tot += pi * float(back.sum()) + float(r[~back].sum())
    if len(orj):
        gap = end[jrep] - p[jrep] - end[ormem] - L
        r = np.where(before, np.minimum(rho * np.maximum(gap, 0.0), kappa * p[ormem]), np.inf)
        tot += float(np.minimum.reduceat(r, orptr[:-1]).sum())
    return tot


_total = njit(cache=True)(_total_py) if njit else _total_np


def similarity(inst: Instance, i: str, j: str) -> float:
    """sim(i, j) used when j is studied right after i (directional)."""
    web = inst.web
    ti, tj = web.topics[i], web.topics[j]
    best = 0.0
    if (i, j) in web.overlaps:
        best = max(best, web.overlaps[(i, j)])
    if ti.course and ti.course == tj.course:
        best = max(best, 0.5 if abs(ti.order - tj.order) <= 1 else 0.25)
    return best


class Evaluator:
    """Vectorised evaluation of z(pi) for one Instance (used by every heuristic)."""

    def __init__(self, inst: Instance):
        self.inst = inst
        P = inst.params
        self.ids: List[str] = list(inst.ids)
        self.idx: Dict[str, int] = {t: k for k, t in enumerate(self.ids)}
        n = self.n = len(self.ids)
        web = inst.web
        self.p = np.array([inst.p[t] for t in self.ids], dtype=float)
        dom = [web.topics[t].domain for t in self.ids]
        # link-based similarity
        linked = defaultdict(float)
        for l in web.links:
            if l.src in self.idx and l.dst in self.idx:
                linked[(l.src, l.dst)] = 1.0
                linked[(l.dst, l.src)] = max(linked[(l.dst, l.src)], 0.5)
        C = np.zeros((n, n))
        S = np.zeros((n, n))
        for a, i in enumerate(self.ids):
            for b, j in enumerate(self.ids):
                if a == b:
                    continue
                sim = max(linked.get((i, j), 0.0), similarity(inst, i, j))
                S[a, b] = sim
                C[a, b] = P.w_switch * (dom[a] != dom[b]) - P.s_synergy * sim * self.p[b]
        self.C = C
        self.S = S
        self.c0 = P.start_warmup
        self.rho, self.L, self.pi_soft = P.rho_revision, P.L_revision_free, P.soft_penalty
        self.kappa = P.revision_cap_share
        ak, aj, sk, sj = [], [], [], []
        orr = defaultdict(list)
        known = inst.known
        self.or_satisfied_by_known = set()
        for l in web.links:
            if l.dst not in self.idx:
                continue
            if l.type == "AND" and l.src in self.idx:
                ak.append(self.idx[l.src]); aj.append(self.idx[l.dst])
            elif l.type == "SOFT" and l.src in self.idx:
                sk.append(self.idx[l.src]); sj.append(self.idx[l.dst])
            elif l.type == "OR":
                key = (l.dst, l.group or f"OR_{l.dst}")
                if l.src in known:
                    self.or_satisfied_by_known.add(key)
                if l.src in self.idx:
                    orr[key].append(self.idx[l.src])
        self.ak, self.aj = np.array(ak, int), np.array(aj, int)
        self.sk, self.sj = np.array(sk, int), np.array(sj, int)
        self.orgroups = [
            (self.idx[j], np.array(m, int)) for (j, g), m in orr.items() if (j, g) not in self.or_satisfied_by_known
        ]
        # predecessor / successor lists for windows (AND + OR members are treated in feasibility)
        self.and_pred = [[] for _ in range(n)]
        self.and_succ = [[] for _ in range(n)]
        for k, j in zip(ak, aj):
            self.and_pred[j].append(k)
            self.and_succ[k].append(j)
        self.or_of = defaultdict(list)  # j -> list of member arrays
        for j, m in self.orgroups:
            self.or_of[j].append(m)
        self.sum_p = float(self.p.sum())
        # flat arrays for the compiled evaluator
        self._orj = np.array([j for j, m in self.orgroups], np.int64)
        self._orptr = np.cumsum([0] + [len(m) for _, m in self.orgroups]).astype(np.int64)
        self._ormem = (np.concatenate([m for _, m in self.orgroups]).astype(np.int64)
                       if self.orgroups else np.zeros(0, np.int64))
        self._args = (self.n, self.p, self.C, float(self.c0), float(self.rho), float(self.L), float(self.kappa),
                      float(self.pi_soft), self.ak.astype(np.int64), self.aj.astype(np.int64),
                      self.sk.astype(np.int64), self.sj.astype(np.int64), self._orj, self._orptr, self._ormem)

    def rev_link(self, gap: float, k: int) -> float:
        """Revision hours for one link: min(rho * (gap - L)^+, kappa * p_k)."""
        return min(self.rho * max(0.0, gap - self.L), self.kappa * float(self.p[k]))

    # ------------------------------------------------------------------
    def positions(self, seq: Sequence[int]) -> np.ndarray:
        pos = np.empty(self.n, int)
        pos[np.asarray(seq)] = np.arange(len(seq))
        return pos

    def feasible(self, seq: Sequence[int], pos: np.ndarray = None) -> bool:
        if pos is None:
            pos = self.positions(seq)
        if len(self.ak) and np.any(pos[self.ak] >= pos[self.aj]):
            return False
        for j, m in self.orgroups:
            if not np.any(pos[m] < pos[j]):
                return False
        return True

    def breakdown(self, seq: Sequence[int]) -> Dict[str, float]:
        seq = np.asarray(seq, int)
        pos = self.positions(seq)
        if not self.feasible(seq, pos):
            return {"total": INF, "feasible": False}
        cum = np.cumsum(self.p[seq])
        end = np.empty(self.n)
        end[seq] = cum
        start = end - self.p
        trans = float(self.C[seq[:-1], seq[1:]].sum()) + self.c0 if len(seq) else 0.0
        switch = float(sum(self.C[a, b] > 0 for a, b in zip(seq[:-1], seq[1:])))
        rev = 0.0
        cap = self.kappa * self.p
        if len(self.ak):
            gaps = start[self.aj] - end[self.ak]
            rev += float(np.minimum(self.rho * np.maximum(0.0, gaps - self.L), cap[self.ak]).sum())
        soft_pen = 0.0
        if len(self.sk):
            viol = pos[self.sk] > pos[self.sj]
            soft_pen = self.pi_soft * float(viol.sum())
            gaps = start[self.sj] - end[self.sk]
            rev += float(np.minimum(self.rho * np.maximum(0.0, gaps - self.L), cap[self.sk])[~viol].sum())
        for j, m in self.orgroups:
            before = m[pos[m] < pos[j]]
            g = start[j] - end[before]
            rev += float(np.minimum(self.rho * np.maximum(0.0, g - self.L), cap[before]).min())
        total = self.sum_p + trans + rev + soft_pen
        return {
            "total": total,
            "study": self.sum_p,
            "transitions": trans,
            "revision": rev,
            "soft_penalty": soft_pen,
            "domain_switches": switch,
            "feasible": True,
        }

    def cost(self, seq: Sequence[int]) -> float:
        if len(seq) != self.n:
            return INF
        return float(_total(np.asarray(seq, np.int64), *self._args))

    # helpers
    def to_ids(self, seq: Sequence[int]) -> List[str]:
        return [self.ids[k] for k in seq]

    def from_ids(self, ids: Sequence[str]) -> List[int]:
        return [self.idx[t] for t in ids]
