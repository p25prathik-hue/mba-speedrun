"""Data loading and instance building.

Class link: the instance is the node set N and cost matrix c_ij of the TSP
(Session 1, slide 15; Session 6, slide 3). Topics are "jobs", the student is the
single "machine" (Session 6, slide 1: machine scheduling with sequence-dependent
setup times).

IIMA context: topics.csv lists PGP core micro-topics; prereqs.csv lists the
prerequisite links between them (within and across courses).

The loader accepts several column spellings so the starter-kit CSVs and the
pilot CSVs both load without edits. Run `python -m speedrun.cli inspect --data DIR`
to see how columns were mapped.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Accepted spellings for each logical column (lower-case match).
TOPIC_COLS = {
    "id": ["id", "topic_id", "tid", "node", "code"],
    "name": ["name", "title", "topic", "label", "topic_name"],
    "course": ["course", "primary_course", "course_code", "course_name", "subject"],
    "domain": ["domain", "area", "discipline", "subject_area", "cluster", "group"],
    "term": ["term", "trimester", "semester", "t"],
    "order": ["order", "seq", "sequence", "session", "position", "week"],
    "hours": ["hours", "time", "t_i", "base_hours", "est_hours", "duration", "study_hours", "time_h"],
    "minutes": ["base_minutes", "minutes", "time_min", "mins"],
    "value": ["value", "value_1to5", "weight", "importance", "r_i", "priority", "exam_weight"],
    "all_courses": ["all_courses", "courses"],
}
LINK_COLS = {
    "src": ["src", "from_id", "from", "prereq", "pre", "source_id", "u", "parent"],
    "dst": ["dst", "to_id", "to", "topic", "target", "target_id", "v", "child"],
    "type": ["type", "kind", "link_type", "rel", "relation"],
    "group": ["group", "or_group", "grp", "g"],
    "source": ["source", "provenance", "origin", "evidence_source"],
}


def _pick(header: List[str], options: List[str]) -> Optional[str]:
    low = {h.lower().strip(): h for h in header}
    for o in options:
        if o in low:
            return low[o]
    return None


def _read_csv(path: str) -> Tuple[List[str], List[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        rows = list(r)
        return list(r.fieldnames or []), rows


@dataclass
class Topic:
    id: str
    name: str
    course: str
    domain: str
    term: float
    order: float
    hours: float
    value: float = 1.0
    courses: List[str] = field(default_factory=list)  # all courses that teach it (merged concepts have > 1)


@dataclass
class Link:
    src: str  # prerequisite k
    dst: str  # dependent j
    type: str  # AND | OR | SOFT
    group: str = ""
    source: str = "estimate"


@dataclass
class Params:
    """All cost parameters are estimates in hours (labelled as such in the report)."""

    w_switch: float = 0.5        # w: warm-up when the domain changes (setup time)
    s_synergy: float = 0.15      # s: share of t_j saved right after a related topic
    rho_revision: float = 0.02   # rho: revision hours per hour of gap beyond L
    L_revision_free: float = 12.0  # L: gap (study hours) before revision is needed
    revision_cap_share: float = 0.5  # kappa: a refresh never costs more than kappa * p_k
    soft_penalty: float = 1.0    # pi: cost of studying j before a SOFT prerequisite
    start_warmup: float = 0.5    # c_0j: warm-up for the very first topic
    day_hours: float = 5.0       # H (= bin size b in Session 8)
    day_warmup: float = 0.25     # warm-up at the start of every day (depot leg c_0i)

    @classmethod
    def load(cls, path: Optional[str]) -> "Params":
        p = cls()
        if path and os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
            for k, v in d.items():
                if hasattr(p, k) and not k.startswith("_"):
                    setattr(p, k, float(v))
        return p

    def copy(self, **kw) -> "Params":
        d = dict(self.__dict__)
        d.update(kw)
        return Params(**d)


@dataclass
class Web:
    topics: Dict[str, Topic]
    links: List[Link]
    overlaps: Dict[Tuple[str, str], float] = field(default_factory=dict)
    colmap: dict = field(default_factory=dict)

    # ---- convenience views -------------------------------------------------
    def and_preds(self, j: str) -> List[str]:
        return [l.src for l in self.links if l.dst == j and l.type == "AND"]

    def or_groups(self, j: str) -> Dict[str, List[str]]:
        g: Dict[str, List[str]] = {}
        for l in self.links:
            if l.dst == j and l.type == "OR":
                g.setdefault(l.group or f"OR_{j}", []).append(l.src)
        return g

    def soft_preds(self, j: str) -> List[str]:
        return [l.src for l in self.links if l.dst == j and l.type == "SOFT"]


def load_web(data_dir: str) -> Web:
    """Load topics.csv, prereqs.csv and (optional) overlaps.csv from data_dir."""
    th, trows = _read_csv(os.path.join(data_dir, "topics.csv"))
    cm = {k: _pick(th, v) for k, v in TOPIC_COLS.items()}
    if cm["id"] is None or (cm["hours"] is None and cm["minutes"] is None):
        raise ValueError(f"topics.csv needs an id and an hours (or minutes) column; found {th}")
    topics: Dict[str, Topic] = {}
    for i, r in enumerate(trows):
        tid = str(r[cm["id"]]).strip()
        if not tid:
            continue

        def g(key, default):
            c = cm[key]
            v = r.get(c) if c else None
            return default if v in (None, "") else v

        topics[tid] = Topic(
            id=tid,
            name=str(g("name", tid)),
            course=str(g("course", "")),
            domain=str(g("domain", g("course", ""))),
            term=float(g("term", 0) or 0),
            order=float(g("order", i) or i),
            hours=float(g("hours", 0) or 0) or float(g("minutes", 60)) / 60.0,
            value=float(g("value", 1.0)),
            courses=[c.strip() for c in str(g("all_courses", "")).split(";") if c.strip()] or [str(g("course", ""))],
        )
    lh, lrows = _read_csv(os.path.join(data_dir, "prereqs.csv"))
    lm = {k: _pick(lh, v) for k, v in LINK_COLS.items()}
    if lm["src"] is None or lm["dst"] is None:
        raise ValueError(f"prereqs.csv needs src/dst columns; found {lh}")
    links: List[Link] = []
    for r in lrows:
        s, d = str(r[lm["src"]]).strip(), str(r[lm["dst"]]).strip()
        if s not in topics or d not in topics:
            continue
        typ = (r.get(lm["type"]) if lm["type"] else "AND") or "AND"
        typ = typ.strip().upper()
        typ = {"HARD": "AND", "REQ": "AND", "REQUIRED": "AND", "ANY": "OR", "RECOMMENDED": "SOFT"}.get(typ, typ)
        links.append(
            Link(
                src=s,
                dst=d,
                type=typ,
                group=(r.get(lm["group"]) or "").strip() if lm["group"] else "",
                source=(r.get(lm["source"]) or "estimate").strip() if lm["source"] else "estimate",
            )
        )
    overlaps: Dict[Tuple[str, str], float] = {}
    op = os.path.join(data_dir, "overlaps.csv")
    if os.path.exists(op):
        _, orows = _read_csv(op)
        for r in orows:
            a, b = r.get("a", "").strip(), r.get("b", "").strip()
            if a in topics and b in topics:
                v = float(r.get("sim", 0.5) or 0.5)
                overlaps[(a, b)] = v
                overlaps[(b, a)] = v
    return Web(topics=topics, links=links, overlaps=overlaps, colmap={"topics": cm, "links": lm})


# --------------------------------------------------------------------------
# Profiles (personalisation) -> an Instance the solvers work on
# --------------------------------------------------------------------------
@dataclass
class Profile:
    """A student's scope.

    known: topics already known (treated as satisfied prerequisites, not studied).
    skip: topics the student does not want; dependents that *require* them trigger
          auto-inclusion (closure) unless allow_drop is True, in which case the
          dependents are dropped too.
    multipliers: m_i < 1 for partial prior knowledge (e.g. 0.5 = half the time).
    targets: if given, study only these plus their required prerequisites.
    """

    name: str = "fresh"
    known: List[str] = field(default_factory=list)
    skip: List[str] = field(default_factory=list)
    multipliers: Dict[str, float] = field(default_factory=dict)
    targets: List[str] = field(default_factory=list)
    domain_multipliers: Dict[str, float] = field(default_factory=dict)
    known_domains: List[str] = field(default_factory=list)
    skip_domains: List[str] = field(default_factory=list)
    target_domains: List[str] = field(default_factory=list)
    allow_drop: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        p = cls()
        for k, v in d.items():
            if hasattr(p, k):
                setattr(p, k, v)
        return p


@dataclass
class Instance:
    """The scoped problem: ordered list of topic ids plus effective times p_i = m_i t_i."""

    web: Web
    ids: List[str]
    p: Dict[str, float]           # effective processing time p_i = m_i * t_i
    known: set
    params: Params
    warnings: List[str] = field(default_factory=list)
    auto_added: List[str] = field(default_factory=list)
    profile_name: str = "fresh"

    @property
    def n(self) -> int:
        return len(self.ids)
