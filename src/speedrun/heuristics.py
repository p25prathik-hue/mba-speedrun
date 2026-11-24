"""Construction and improvement heuristics, all precedence-feasible.

Class links (session, slides)
-----------------------------
* Construction vs improvement ............................ S1, 22
* Nearest neighbour (append the cheapest available topic) S1, 26-31
* Cheapest insertion, Delta_ijk = c_ik + c_kj - c_ij ..... S1, 32-39
* Farthest insertion (place the hardest topic first) ..... S1, 40-44
* Savings s_ij = c_i0 + c_0j - c_ij (Clarke-Wright) ...... S8, 20-27; S9, 2-3
  (the cycle test when merging chains is the same question Kruskal faces, S3 slide 6)
* 2-opt ................................................... S3, 31-36
* Or-opt with p = 3, 2, 1 ................................. S3, 39-41
* Neighbourhood search with random restart ................ S10, 36-38

Precedence handling: a topic is *available* once all its AND prerequisites and at
least one member of each OR group are done. Insertion and or-opt moves are limited to
the window between a topic's last prerequisite and its first dependent.

IIMA context: these are the methods the roadmap planner runs in the browser for a
student's own scope, because exact B&B is only practical for ~30 topics.
"""
from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from .costs import INF, Evaluator


# ---------------------------------------------------------------------------
# Availability bookkeeping
# ---------------------------------------------------------------------------
class _Avail:
    def __init__(self, ev: Evaluator):
        self.ev = ev
        n = ev.n
        self.need_and = [len(ev.and_pred[j]) for j in range(n)]
        self.need_or = [len(ev.or_of[j]) for j in range(n)]
        self.or_done = [[False] * len(ev.or_of[j]) for j in range(n)]
        # member -> list of (j, group index)
        self.member_of: Dict[int, List[Tuple[int, int]]] = {}
        for j in range(n):
            for gi, m in enumerate(ev.or_of[j]):
                for k in m:
                    self.member_of.setdefault(int(k), []).append((j, gi))
        self.done = [False] * n

    def available(self, j: int) -> bool:
        return not self.done[j] and self.need_and[j] == 0 and self.need_or[j] == 0

    def mark(self, k: int):
        self.done[k] = True
        for j in self.ev.and_succ[k]:
            self.need_and[j] -= 1
        for j, gi in self.member_of.get(k, []):
            if not self.or_done[j][gi]:
                self.or_done[j][gi] = True
                self.need_or[j] -= 1


# ---------------------------------------------------------------------------
# Construction heuristics
# ---------------------------------------------------------------------------
def nearest_neighbour(ev: Evaluator, start_rule: str = "curriculum") -> List[int]:
    """Append the available topic with the smallest *true* incremental cost.

    Increment = c_ij + revision on links into j given the current clock
              + SOFT penalties for dependents already placed.
    """
    av = _Avail(ev)
    T = ev.inst.web.topics
    seq: List[int] = []
    end = np.zeros(ev.n)
    clock = 0.0
    placed = np.zeros(ev.n, bool)
    soft_succ = [[] for _ in range(ev.n)]
    soft_pred = [[] for _ in range(ev.n)]
    for k, j in zip(ev.sk, ev.sj):
        soft_succ[k].append(j)
        soft_pred[j].append(k)
    cur_key = lambda j: (T[ev.ids[j]].term, T[ev.ids[j]].order)
    while len(seq) < ev.n:
        cand = [j for j in range(ev.n) if av.available(j)]
        if not seq:
            bj = min(cand, key=cur_key)  # first topic: earliest in the curriculum
        else:
            best, bj = INF, None
            for j in cand:
                inc = ev.C[seq[-1], j]
                # revision on links into j, given the current clock
                for k in ev.and_pred[j]:
                    inc += ev.rev_link(clock - end[k], k)
                for k in soft_pred[j]:
                    if placed[k]:
                        inc += ev.rev_link(clock - end[k], k)
                for k in soft_succ[j]:
                    if placed[k]:
                        inc += ev.pi_soft
                if inc < best - 1e-12 or (abs(inc - best) <= 1e-12 and cur_key(j) < cur_key(bj)):
                    best, bj = inc, j
        seq.append(bj)
        av.mark(bj)
        placed[bj] = True
        clock += ev.p[bj]
        end[bj] = clock
    return seq


def _insertion(ev: Evaluator, farthest: bool = False) -> List[int]:
    """Cheapest (or farthest) insertion with Delta_ijk = c_ik + c_kj - c_ij (S1 slide 33).

    Topics are inserted only once they are available (precedence-closed insertion),
    at a position after their prerequisites already in the tour.
    """
    n = ev.n
    # extended matrix with START = n, END = n+1
    Cx = np.zeros((n + 2, n + 2))
    Cx[:n, :n] = ev.C
    Cx[n, :n] = ev.c0
    tour = [n, n + 1]
    av = _Avail(ev)
    pos = {n: 0, n + 1: 1}
    while len(tour) < n + 2:
        cand = [j for j in range(n) if av.available(j)]
        t = np.array(tour)
        best = None  # (score, k, insert_after_index)
        for k in cand:
            lo = 0
            for a in ev.and_pred[k]:
                lo = max(lo, pos[a])
            for m in ev.or_of[k]:
                placed = [pos[int(x)] for x in m if int(x) in pos]
                if placed:
                    lo = max(lo, min(placed))
            a_idx = t[lo:-1]
            b_idx = t[lo + 1:]
            d = Cx[a_idx, k] + Cx[k, b_idx] - Cx[a_idx, b_idx]
            r = int(np.argmin(d))
            score = d[r]
            if farthest:
                # farthest insertion: pick the topic whose best insertion is most expensive
                if best is None or score > best[0]:
                    best = (score, k, lo + r)
            else:
                if best is None or score < best[0]:
                    best = (score, k, lo + r)
        _, k, after = best
        tour.insert(after + 1, k)
        pos = {v: i for i, v in enumerate(tour)}
        av.mark(k)
    return tour[1:-1]


def cheapest_insertion(ev: Evaluator) -> List[int]:
    return _insertion(ev, farthest=False)


def farthest_insertion(ev: Evaluator) -> List[int]:
    return _insertion(ev, farthest=True)


def savings(ev: Evaluator) -> List[int]:
    """Clarke-Wright savings adapted to sequencing (S8 slides 20-27).

    Each topic starts as its own chain ("one truck per customer"). Merging the chain
    ending in i with the chain starting at j saves s_ij = c_i0 + c_0j - c_ij, where the
    depot legs are c_i0 = 0 and c_0j = w (a fresh warm-up). Merges are implemented in
    decreasing s_ij order, skipping a merge if (S8 slide 24):
      1. i and j are on the same chain,
      2. i is not the end of its chain or j is not the start of its chain,
      3. (new) the merge would make the chain-precedence graph cyclic
         (the Kruskal cycle test of S3 slide 6, here on directed chains).
    Remaining chains are concatenated in a precedence-feasible order.
    OR prerequisites are treated conservatively as AND inside this heuristic.
    """
    n = ev.n
    w = ev.inst.params.w_switch
    chain_of = list(range(n))
    chains: Dict[int, List[int]] = {i: [i] for i in range(n)}
    req = [(int(k), int(j)) for k, j in zip(ev.ak, ev.aj)]
    for j, m in ev.orgroups:
        req += [(int(k), int(j)) for k in m]

    def chain_graph():
        g: Dict[int, set] = {c: set() for c in chains}
        for k, j in req:
            a, b = chain_of[k], chain_of[j]
            if a != b:
                g[a].add(b)
        return g

    def reachable(g, src, dst) -> bool:
        stack, seen = [src], {src}
        while stack:
            x = stack.pop()
            if x == dst:
                return True
            for y in g[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return False

    S = w - ev.C  # s_ij
    np.fill_diagonal(S, -INF)
    order = np.dstack(np.unravel_index(np.argsort(-S, axis=None), S.shape))[0]
    g = chain_graph()
    for i, j in order:
        i, j = int(i), int(j)
        if S[i, j] == -INF:
            break
        A, B = chain_of[i], chain_of[j]
        if A == B or chains[A][-1] != i or chains[B][0] != j:
            continue
        # merging makes A and B one contiguous block (A then B). Invalid if
        #   (a) B must come before A (B reaches A), or
        #   (b) some other chain must sit between them (A reaches B via another chain Y).
        if reachable(g, B, A) or any(reachable(g, y, B) for y in g[A] if y != B):
            continue
        chains[A] = chains[A] + chains[B]
        for v in chains[B]:
            chain_of[v] = A
        del chains[B]
        # update graph: merge node B into A
        for c in g:
            if B in g[c]:
                g[c].discard(B)
                if c != A:
                    g[c].add(A)
        g[A] |= {x for x in g[B] if x != A}
        del g[B]
        if len(chains) == 1:
            break
    # concatenate chains in topological order of the chain graph
    T = ev.inst.web.topics
    key = {c: min((T[ev.ids[v]].term, T[ev.ids[v]].order) for v in chains[c]) for c in chains}
    indeg = {c: 0 for c in chains}
    for c in g:
        for d in g[c]:
            indeg[d] += 1
    ready = sorted([c for c in chains if indeg[c] == 0], key=lambda c: key[c])
    out = []
    while ready:
        c = ready.pop(0)
        out += chains[c]
        for d in g[c]:
            indeg[d] -= 1
            if indeg[d] == 0:
                ready.append(d)
                ready.sort(key=lambda x: key[x])
    assert len(out) == n, "savings: chain graph not acyclic"
    return out


def random_topological(ev: Evaluator, rng: random.Random) -> List[int]:
    """Random feasible order (used for random restarts, S10 slide 37)."""
    av = _Avail(ev)
    seq = []
    while len(seq) < ev.n:
        cand = [j for j in range(ev.n) if av.available(j)]
        j = rng.choice(cand)
        seq.append(j)
        av.mark(j)
    return seq


# ---------------------------------------------------------------------------
# Improvement heuristics
# ---------------------------------------------------------------------------
def _window(ev: Evaluator, seq: List[int], s: int, e: int) -> Tuple[int, int]:
    """Positions (in seq without the segment) where segment seq[s:e] may be re-inserted."""
    seg = set(seq[s:e])
    pos = {v: k for k, v in enumerate(seq)}
    lo, hi = 0, len(seq)
    for v in seg:
        for a in ev.and_pred[v]:
            if a not in seg:
                lo = max(lo, pos[a] + 1)
        for b in ev.and_succ[v]:
            if b not in seg:
                hi = min(hi, pos[b])
    return lo, hi


def or_opt(ev: Evaluator, seq: List[int], cur: float = None) -> Tuple[List[int], float, bool]:
    """One pass of or-opt: move p consecutive topics (p = 3, 2, 1) to their best feasible spot."""
    if cur is None:
        cur = ev.cost(seq)
    improved_any = False
    n = len(seq)
    for p in (3, 2, 1):
        s = 0
        while s + p <= n:
            lo, hi = _window(ev, seq, s, s + p)
            seg = seq[s:s + p]
            rest = seq[:s] + seq[s + p:]
            # translate window to indices in `rest`
            lo_r = lo if lo <= s else lo - p
            hi_r = hi if hi <= s else hi - p
            best, bseq = cur, None
            for ins in range(max(0, lo_r), min(len(rest), hi_r) + 1):
                if ins == s:
                    continue
                cand = rest[:ins] + seg + rest[ins:]
                c = ev.cost(cand)
                if c < best - 1e-9:
                    best, bseq = c, cand
            if bseq is not None:
                seq, cur, improved_any = bseq, best, True
            s += 1
    return seq, cur, improved_any


def two_opt(ev: Evaluator, seq: List[int], cur: float = None) -> Tuple[List[int], float, bool]:
    """2-opt (S3 slide 33): reverse seq[i:j]. In an asymmetric, precedence-constrained
    instance a reversal is only feasible if the segment has no internal prerequisite
    arc, and the reversed arcs are re-costed (c_ij != c_ji)."""
    if cur is None:
        cur = ev.cost(seq)
    improved = False
    n = len(seq)
    i = 0
    while i < n - 1:
        inside = {seq[i]}
        j = i + 1
        while j < n:
            v = seq[j]
            if any(a in inside for a in ev.and_pred[v]):
                break  # reversal would put v before its prerequisite
            inside.add(v)
            cand = seq[:i] + seq[i:j + 1][::-1] + seq[j + 1:]
            c = ev.cost(cand)
            if c < cur - 1e-9:
                seq, cur, improved = cand, c, True
                inside = set(seq[i:j + 1])
            j += 1
        i += 1
    return seq, cur, improved


def local_search(ev: Evaluator, seq: List[int], max_rounds: int = 50, time_limit: float = None) -> Tuple[List[int], float]:
    t0 = time.time()
    cur = ev.cost(seq)
    for _ in range(max_rounds):
        seq, cur, a = or_opt(ev, seq, cur)
        seq, cur, b = two_opt(ev, seq, cur)
        if not (a or b):
            break
        if time_limit and time.time() - t0 > time_limit:
            break
    return seq, cur


CONSTRUCTORS = {
    "NN": nearest_neighbour,
    "CI": cheapest_insertion,
    "FI": farthest_insertion,
    "SAV": savings,
}


def solve_heuristic(ev: Evaluator, restarts: int = 5, seed: int = 0, time_limit: float = 60.0,
                    extra_starts: Optional[Dict[str, List[int]]] = None, log: Optional[list] = None):
    """Multi-start neighbourhood search (S10 slides 36-38).

    Every constructor (NN, CI, FI, savings and any baselines passed in) is improved by
    or-opt + 2-opt; then `restarts` random feasible orders are improved too.
    Returns the best sequence, its cost and a per-start log.
    """
    rng = random.Random(seed)
    t0 = time.time()
    starts: Dict[str, List[int]] = {}
    for name, f in CONSTRUCTORS.items():
        starts[name] = f(ev)
    if extra_starts:
        starts.update(extra_starts)
    best, bseq, rows = INF, None, []
    for name, s in starts.items():
        c0 = ev.cost(s)
        t1 = time.time()
        s2, c2 = local_search(ev, list(s))
        rows.append({"start": name, "construct": c0, "improved": c2, "secs": round(time.time() - t1, 2)})
        if c2 < best:
            best, bseq = c2, s2
    for r in range(restarts):
        if time.time() - t0 > time_limit:
            break
        s = random_topological(ev, rng)
        c0 = ev.cost(s)
        s2, c2 = local_search(ev, s)
        rows.append({"start": f"rand{r}", "construct": c0, "improved": c2})
        if c2 < best:
            best, bseq = c2, s2
    if log is not None:
        log.extend(rows)
    return bseq, best
