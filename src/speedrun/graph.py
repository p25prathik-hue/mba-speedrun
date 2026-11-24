"""Graph utilities: DAG checks, prerequisite closure, critical path, audit.

Class links
-----------
* Cycle check = negative-cycle detection with Bellman-Ford (Session 7, slides 17-18):
  give every arc weight -1; a prerequisite cycle is then a negative cycle, and it is
  detected when labels still improve at iteration n. We cross-check with Kahn's
  topological sort (polynomial, O(n + m); Session 7, slides 19-23 on complexity).
* Prerequisite closure = reachability labels of the Session 7 labelling algorithms
  (a node is in the closure iff its label becomes finite when we label backwards
  from the targets).
* Critical path = longest path in hours on the DAG, computed with the Bellman-Ford
  recursion u_j = max_k(u_k) + p_j over topological order (Session 7, slides 10-16).
  It is the minimum calendar time for a *cohort* learning in parallel; a solo
  learner needs the full sum of hours instead.

IIMA context: the closure tells a student who skips a course which topics they
cannot skip after all; the critical path shows why the curriculum is run as parallel
courses for a cohort of ~400.
"""
from __future__ import annotations

import heapq
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

from .data import Instance, Params, Profile, Web


# ---------------------------------------------------------------------------
# Basic adjacency
# ---------------------------------------------------------------------------
def required_arcs(web: Web, include_or: bool = True, include_soft: bool = False) -> List[Tuple[str, str]]:
    arcs = []
    for l in web.links:
        if l.type == "AND" or (include_or and l.type == "OR") or (include_soft and l.type == "SOFT"):
            arcs.append((l.src, l.dst))
    return arcs


def kahn_topological(nodes: List[str], arcs: List[Tuple[str, str]], key=None) -> Optional[List[str]]:
    """Kahn's algorithm with a priority key (curriculum order). None if a cycle exists."""
    indeg = {v: 0 for v in nodes}
    succ = defaultdict(list)
    ns = set(nodes)
    for u, v in arcs:
        if u in ns and v in ns:
            succ[u].append(v)
            indeg[v] += 1
    key = key or (lambda v: v)
    heap = [(key(v), v) for v in nodes if indeg[v] == 0]
    heapq.heapify(heap)
    out = []
    while heap:
        _, u = heapq.heappop(heap)
        out.append(u)
        for v in succ[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                heapq.heappush(heap, (key(v), v))
    return out if len(out) == len(nodes) else None


def bellman_ford_has_cycle(nodes: List[str], arcs: List[Tuple[str, str]]) -> bool:
    """Session 7 (slides 17-18): weights -1 on every arc; a cycle = a negative cycle.

    Run Bellman-Ford from a virtual source connected to all nodes with weight 0.
    If any label still improves at iteration n, a negative cycle (prerequisite loop) exists.
    """
    u = {v: 0.0 for v in nodes}
    n = len(nodes)
    for m in range(n):
        changed = False
        for a, b in arcs:
            if a in u and b in u and u[a] - 1 < u[b]:
                u[b] = u[a] - 1
                changed = True
        if not changed:
            return False  # early stop (slide 13, step 2)
    return True


def transitive_redundant(web: Web) -> List[Tuple[str, str]]:
    """AND links implied by a longer AND path (removing them leaves the feasible set unchanged)."""
    succ = defaultdict(set)
    for l in web.links:
        if l.type == "AND":
            succ[l.src].add(l.dst)
    red = []
    for l in web.links:
        if l.type != "AND":
            continue
        # is l.dst reachable from l.src without using the direct arc?
        stack = [x for x in succ[l.src] if x != l.dst]
        seen = set(stack)
        found = False
        while stack and not found:
            x = stack.pop()
            for y in succ[x]:
                if y == l.dst:
                    found = True
                    break
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        if found:
            red.append((l.src, l.dst))
    return red


def and_ancestors(web: Web) -> Dict[str, Set[str]]:
    """All AND-ancestors of each topic (used for arc fixing, Session 9 slides 23-25)."""
    preds = defaultdict(set)
    for l in web.links:
        if l.type == "AND":
            preds[l.dst].add(l.src)
    memo: Dict[str, Set[str]] = {}

    def anc(v, stack=()):
        if v in memo:
            return memo[v]
        out = set()
        for k in preds[v]:
            if k in stack:
                continue
            out.add(k)
            out |= anc(k, stack + (v,))
        memo[v] = out
        return out

    for v in web.topics:
        anc(v)
    return memo


# ---------------------------------------------------------------------------
# Closure and instance building (personalisation)
# ---------------------------------------------------------------------------
def build_instance(web: Web, profile: Optional[Profile] = None, params: Optional[Params] = None) -> Instance:
    """Apply a profile: exclusions, prior knowledge, targets, closure.

    Closure rule (BFS on reversed prerequisite arcs):
      * AND prerequisite missing  -> auto-include it (warning), or drop the dependent if allow_drop.
      * OR group with no member in scope or known -> add the member with the cheapest closure.
      * SOFT prerequisite missing -> ignored (no requirement).
    """
    profile = profile or Profile()
    params = params or Params()
    T = web.topics
    known = set(profile.known) | {t for t in T if T[t].domain in profile.known_domains}
    skip = set(profile.skip) | {t for t in T if T[t].domain in profile.skip_domains}
    if profile.targets or profile.target_domains:
        scope = set(profile.targets) | {t for t in T if T[t].domain in profile.target_domains}
    else:
        scope = set(T)
    scope -= known
    scope -= skip
    warnings: List[str] = []
    added: List[str] = []

    and_pred = defaultdict(list)
    or_grp = defaultdict(lambda: defaultdict(list))
    for l in web.links:
        if l.type == "AND":
            and_pred[l.dst].append(l.src)
        elif l.type == "OR":
            or_grp[l.dst][l.group or f"OR_{l.dst}"].append(l.src)

    def mult(t):
        m = profile.multipliers.get(t, profile.domain_multipliers.get(T[t].domain, 1.0))
        return float(m)

    def closure_cost(k: str, cur: Set[str], depth=0) -> Tuple[float, Set[str]]:
        """Hours needed to add k with its missing required ancestors (cheapest OR choice)."""
        if k in cur or k in known or depth > 60:
            return 0.0, set()
        need = {k}
        cost = T[k].hours * mult(k)
        for a in and_pred[k]:
            c, s = closure_cost(a, cur | need, depth + 1)
            cost += c
            need |= s
        for g, mem in or_grp[k].items():
            if any(m in cur or m in known or m in need for m in mem):
                continue
            best = min((closure_cost(m, cur | need, depth + 1) for m in mem), key=lambda x: x[0])
            cost += best[0]
            need |= best[1]
        return cost, need

    changed = True
    while changed:
        changed = False
        for j in sorted(scope):
            for k in and_pred[j]:
                if k in scope or k in known:
                    continue
                if profile.allow_drop:
                    scope.discard(j)
                    warnings.append(f"dropped {j} because required prerequisite {k} is excluded")
                else:
                    _, s = closure_cost(k, scope)
                    new = s - scope
                    scope |= new
                    added += sorted(new)
                    why = "skipped" if k in skip else "outside the chosen scope"
                    warnings.append(f"auto-included {', '.join(sorted(new))} (required for {j}; {k} was {why})")
                changed = True
                break
            if changed:
                break
            for g, mem in or_grp[j].items():
                if any(m in scope or m in known for m in mem):
                    continue
                if profile.allow_drop:
                    scope.discard(j)
                    warnings.append(f"dropped {j}: no member of OR-group {g} available")
                else:
                    best = min((closure_cost(m, scope) + (m,) for m in mem), key=lambda x: x[0])
                    new = best[1] - scope
                    scope |= new
                    added += sorted(new)
                    warnings.append(
                        f"OR-group {g} for {j}: added cheapest route via {best[2]} ({best[0]:.1f} h: {', '.join(sorted(new))})"
                    )
                changed = True
                break
            if changed:
                break

    ids = sorted(scope, key=lambda t: (T[t].term, T[t].course, T[t].order, t))
    p = {t: T[t].hours * mult(t) for t in ids}
    return Instance(web=web, ids=ids, p=p, known=known, params=params, warnings=warnings,
                    auto_added=sorted(set(added)), profile_name=profile.name)


def critical_path(inst: Instance) -> Tuple[float, List[str]]:
    """Longest prerequisite chain in hours (Bellman-Ford recursion on a DAG, Session 7)."""
    web = inst.web
    ids = set(inst.ids)
    arcs = [(l.src, l.dst) for l in web.links if l.type in ("AND", "OR") and l.src in ids and l.dst in ids]
    order = kahn_topological(list(inst.ids), arcs)
    if order is None:
        raise ValueError("cycle in prerequisites")
    and_pred = defaultdict(list)
    or_grp = defaultdict(lambda: defaultdict(list))
    for l in web.links:
        if l.src in ids and l.dst in ids:
            if l.type == "AND":
                and_pred[l.dst].append(l.src)
            elif l.type == "OR":
                or_grp[l.dst][l.group].append(l.src)
    u: Dict[str, float] = {}
    pred: Dict[str, Optional[str]] = {}
    for j in order:
        best, arg = 0.0, None
        for k in and_pred[j]:
            if u[k] > best:
                best, arg = u[k], k
        for g, mem in or_grp[j].items():
            # OR: the earliest member suffices
            m = min(mem, key=lambda k: u[k])
            if u[m] > best:
                best, arg = u[m], m
        u[j] = best + inst.p[j]
        pred[j] = arg
    end = max(u, key=u.get)
    path = [end]
    while pred[path[-1]] is not None:
        path.append(pred[path[-1]])
    return u[end], path[::-1]


def audit(web: Web) -> dict:
    nodes = list(web.topics)
    arcs = required_arcs(web, include_or=True, include_soft=True)
    topo = kahn_topological(nodes, arcs)
    cyc_bf = bellman_ford_has_cycle(nodes, arcs)
    doms = {t: web.topics[t].domain for t in nodes}
    cross = sum(1 for l in web.links if doms[l.src] != doms[l.dst])
    linked = {l.src for l in web.links} | {l.dst for l in web.links}
    by_type: Dict[str, int] = defaultdict(int)
    by_source: Dict[str, int] = defaultdict(int)
    for l in web.links:
        by_type[l.type] += 1
        for s in (l.source or "estimate").split(";"):
            by_source[s.strip()] += 1
    # longest chain in number of topics
    longest = 0
    if topo:
        dist = {v: 1 for v in nodes}
        succ = defaultdict(list)
        for a, b in required_arcs(web, include_or=True):
            succ[a].append(b)
        for v in topo:
            for w in succ[v]:
                dist[w] = max(dist[w], dist[v] + 1)
        longest = max(dist.values())
    return {
        "topics": len(nodes),
        "links": len(web.links),
        "links_by_type": dict(by_type),
        "links_by_source": dict(by_source),
        "acyclic_kahn": topo is not None,
        "acyclic_bellman_ford": not cyc_bf,
        "cross_domain_share": round(cross / max(1, len(web.links)), 3),
        "isolated_topics": sorted(set(nodes) - linked),
        "redundant_and_links": transitive_redundant(web),
        "longest_chain_topics": longest,
        "total_hours": round(sum(t.hours for t in web.topics.values()), 1),
        "domains": sorted({t.domain for t in web.topics.values()}),
    }
