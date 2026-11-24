"""Baseline orders.

B0 - curriculum (cohort) order: terms in sequence; inside a term the courses run in
     parallel, so sessions are interleaved round-robin across courses (this is how a
     PGP1 student actually meets the material). Then repaired to respect prerequisites
     with Kahn's algorithm (a dependent waits for a prerequisite that is taught later,
     e.g. EVA in CCS (T2) waits for WACC from CF (T3)).
B1 - subject by subject ("finish FRA, then start MA ..."). This is the cluster-first,
     route-second idea of the sweep heuristic (Session 9, slides 8-10): cluster by
     domain/course, then sequence within each cluster.

IIMA context: B0 is what a student who simply replays the timetable would do; B1 is
what most students do when catching up alone ("one subject at a time").
"""
from __future__ import annotations

from collections import defaultdict
from typing import List, Tuple

from .costs import Evaluator
from .graph import kahn_topological


def _arcs(ev: Evaluator) -> List[Tuple[str, str]]:
    ids = set(ev.ids)
    return [(l.src, l.dst) for l in ev.inst.web.links if l.type in ("AND", "OR") and l.src in ids and l.dst in ids]


def curriculum_order(ev: Evaluator) -> Tuple[List[int], int]:
    """B0: round-robin across parallel courses within each term, then Kahn repair.

    Returns (sequence, number of prerequisite inversions that had to be repaired).
    """
    web = ev.inst.web
    T = web.topics
    by_term_course = defaultdict(list)
    for t in ev.ids:
        by_term_course[(T[t].term, T[t].course)].append(t)
    rank = {}
    for (term, course), lst in by_term_course.items():
        lst.sort(key=lambda t: (T[t].order, t))
        n = len(lst)
        for r, t in enumerate(lst):
            # spread each course evenly over the term (parallel courses)
            rank[t] = (term, (r + 0.5) / n, course, t)
    raw = sorted(ev.ids, key=lambda t: rank[t])
    pos = {t: k for k, t in enumerate(raw)}
    inversions = sum(1 for a, b in _arcs(ev) if pos[a] > pos[b])
    order = kahn_topological(ev.ids, _arcs(ev), key=lambda t: rank[t])
    return ev.from_ids(order), inversions


def subject_by_subject(ev: Evaluator) -> List[int]:
    """B1: finish one course before the next (term, course, session), then Kahn repair."""
    T = ev.inst.web.topics
    key = lambda t: (T[t].term, T[t].course, T[t].order, t)
    order = kahn_topological(ev.ids, _arcs(ev), key=key)
    return ev.from_ids(order)
