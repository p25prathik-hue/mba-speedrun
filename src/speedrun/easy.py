"""Plain-language front end used by start.py (the menu launcher) and the Colab notebook.

It wraps the same code the report uses: build_instance (prerequisite closure)
-> heuristics (NN, CI, FI, savings + or-opt/2-opt) -> exact split into days.
Every hour figure is an ESTIMATE from data/*/topics.csv and params.json, not
measured study time.
"""
from __future__ import annotations

import csv
import os
from typing import Dict, Iterable, List, Optional, Sequence

from .baselines import curriculum_order, subject_by_subject
from .costs import Evaluator
from .crunch import profit_max_tour
from .data import Params, Profile, load_web
from .days import shortest_path_split
from .graph import build_instance
from .heuristics import solve_heuristic

WEBS = {
    "iima": ("data/iima", "Full IIMA core web (266 topics, all first-year courses)"),
    "pilot": ("data/sample", "Small Finance + Accounting pilot (28 topics)"),
}


def _root(root: Optional[str]) -> str:
    return root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def data_dir(web: str = "iima", root: Optional[str] = None) -> str:
    return os.path.join(_root(root), WEBS.get(web, (web,))[0])


def areas(web: str = "iima", root: Optional[str] = None) -> List[Dict]:
    """Subject areas (domains) with topic counts and estimated hours, in a fixed order."""
    w = load_web(data_dir(web, root))
    out: Dict[str, Dict] = {}
    for t in w.topics.values():
        a = out.setdefault(t.domain, {"area": t.domain, "topics": 0, "hours": 0.0})
        a["topics"] += 1
        a["hours"] += t.hours
    return sorted(out.values(), key=lambda a: (-a["topics"], a["area"]))


def topic_list(web: str = "iima", root: Optional[str] = None) -> List[Dict]:
    w = load_web(data_dir(web, root))
    return [{"id": t.id, "topic": t.name, "area": t.domain, "course": t.course} for t in w.topics.values()]


def match_areas(text: str, all_areas: Sequence[str]) -> List[str]:
    """Turn '1, quant, ob' into area names. Accepts list numbers, names, prefixes or unique parts."""
    found: List[str] = []
    for raw in (text or "").replace(";", ",").split(","):
        s = raw.strip()
        if not s:
            continue
        if s.isdigit() and 1 <= int(s) <= len(all_areas):
            hit = [all_areas[int(s) - 1]]
        else:
            low = s.lower()
            hit = [a for a in all_areas if a.lower() == low]
            hit = hit or [a for a in all_areas if a.lower().startswith(low)]
            hit = hit or [a for a in all_areas if low in a.lower()]
        if len(hit) != 1:
            why = "matches several areas" if hit else "matches no area"
            raise ValueError(f"'{s}' {why}. Choose from: " + "; ".join(f"{k+1} {a}" for k, a in enumerate(all_areas)))
        if hit[0] not in found:
            found.append(hit[0])
    return found


def match_topics(text: str, web: str = "iima", root: Optional[str] = None) -> List[str]:
    ids = {t["id"].upper(): t["id"] for t in topic_list(web, root)}
    out, bad = [], []
    for raw in (text or "").replace(";", ",").replace(" ", ",").split(","):
        s = raw.strip().upper()
        if s:
            (out.append(ids[s]) if s in ids else bad.append(raw.strip()))
    if bad:
        raise ValueError("Unknown topic ID(s): " + ", ".join(bad) + ". See the topic list (IDs like QNT01, FIN06).")
    return out


def _setup(web, hours_per_day, known_areas, half_known_areas, skip_areas, known_topics, skip_topics, root):
    w = load_web(data_dir(web, root))
    params = Params.load(os.path.join(data_dir(web, root), "params.json"))
    if hours_per_day:
        params = params.copy(day_hours=float(hours_per_day))
    prof = Profile(
        name="me",
        known=list(known_topics or []),
        skip=list(skip_topics or []),
        known_domains=list(known_areas or []),
        skip_domains=list(skip_areas or []),
        domain_multipliers={a: 0.5 for a in (half_known_areas or [])},
    )
    inst = build_instance(w, prof, params)
    return w, params, inst, Evaluator(inst)


def _rows(w, ev, split, values=False) -> List[Dict]:
    rows, step = [], 0
    for d, day in enumerate(split["days"] or [], 1):
        for t in day["topics"]:
            step += 1
            tp = w.topics[t]
            r = {"day": d, "step": step, "id": t, "topic": tp.name, "area": tp.domain, "course": tp.course,
                 "study_hours_est": round(float(ev.p[ev.idx[t]]), 2), "day_total_hours_est": day["hours"]}
            if values:
                r["value_1to5"] = tp.value
            rows.append(r)
    return rows


def make_roadmap(web: str = "iima", hours_per_day: Optional[float] = None,
                 known_areas: Iterable[str] = (), half_known_areas: Iterable[str] = (),
                 skip_areas: Iterable[str] = (), known_topics: Iterable[str] = (),
                 skip_topics: Iterable[str] = (), restarts: int = 0, root: Optional[str] = None) -> Dict:
    """Full roadmap: every topic in scope, best order found, split into days of H hours."""
    w, params, inst, ev = _setup(web, hours_per_day, known_areas, half_known_areas, skip_areas,
                                 known_topics, skip_topics, root)
    res = {"mode": "roadmap", "web": web, "hours_per_day": params.day_hours, "n_topics": ev.n,
           "notes": list(inst.warnings), "rows": []}
    if ev.n == 0:
        return res
    b0, _ = curriculum_order(ev)
    b1 = subject_by_subject(ev)
    seq, cost = solve_heuristic(ev, restarts=restarts, extra_starts={"B0": b0, "B1": b1})
    split = shortest_path_split(ev, seq)
    res.update({
        "total_hours_est": round(cost, 1),
        "timetable_order_hours_est": round(ev.cost(b0), 1),
        "subject_by_subject_hours_est": round(ev.cost(b1), 1),
        "days": split["n_days"],
        "days_lower_bound": split["lb_days"],
        "rows": _rows(w, ev, split),
    })
    return res


def make_crunch(budget_hours: float, web: str = "iima", hours_per_day: Optional[float] = None,
                known_areas: Iterable[str] = (), half_known_areas: Iterable[str] = (),
                skip_areas: Iterable[str] = (), known_topics: Iterable[str] = (),
                skip_topics: Iterable[str] = (), root: Optional[str] = None) -> Dict:
    """Crunch: the most valuable topics (with their prerequisites) that fit in budget_hours."""
    w, params, inst, ev = _setup(web, hours_per_day, known_areas, half_known_areas, skip_areas,
                                 known_topics, skip_topics, root)
    res = {"mode": "crunch", "web": web, "hours_per_day": params.day_hours, "budget_hours": float(budget_hours),
           "notes": list(inst.warnings), "rows": [], "left_out": []}
    if ev.n == 0:
        return res
    cr = profit_max_tour(ev, float(budget_hours))
    split = shortest_path_split(ev, cr["seq"]) if cr["seq"] else {"days": [], "n_days": 0}
    res.update({
        "n_topics": len(cr["seq"]),
        "n_in_scope": ev.n,
        "hours_used_est": round(cr["hours"], 1),
        "value": cr["value"],
        "value_in_scope": sum(w.topics[t].value for t in ev.ids),
        "days": split["n_days"],
        "rows": _rows(w, ev, split, values=True),
        "left_out": [{"id": t, "topic": w.topics[t].name, "area": w.topics[t].domain,
                      "value_1to5": w.topics[t].value} for t in cr["left_out"]],
    })
    return res


def summary(res: Dict) -> str:
    """A short plain-text summary (hours are estimates)."""
    if not res["rows"]:
        return "Nothing to study: every topic is known or skipped."
    if res["mode"] == "roadmap":
        saved = res["subject_by_subject_hours_est"] - res["total_hours_est"]
        lines = [
            f"{res['n_topics']} topics, about {res['total_hours_est']:.0f} study hours (estimate) "
            f"in {res['days']} days at {res['hours_per_day']:g} h/day.",
            f"Studying subject by subject would take about {res['subject_by_subject_hours_est']:.0f} h, "
            f"and the timetable order about {res['timetable_order_hours_est']:.0f} h; "
            f"this order saves about {saved:.0f} h.",
        ]
    else:
        lines = [
            f"Crunch for {res['budget_hours']:g} h: {res['n_topics']} of {res['n_in_scope']} topics, "
            f"{res['hours_used_est']:.0f} h used, value {res['value']:g} of {res['value_in_scope']:g} "
            f"({100 * res['value'] / max(1, res['value_in_scope']):.0f}%), {res['days']} days at {res['hours_per_day']:g} h/day.",
            f"{len(res['left_out'])} topics left out (see the saved file).",
        ]
    for n in res["notes"]:
        lines.append("Note: " + n)
    return "\n".join(lines)


def day_plan_text(res: Dict, max_days: Optional[int] = None) -> str:
    out, cur = [], None
    for r in res["rows"]:
        if max_days and r["day"] > max_days:
            out.append(f"... and {res['days'] - max_days} more days in the saved file")
            break
        if r["day"] != cur:
            cur = r["day"]
            out.append(f"Day {cur} ({r['day_total_hours_est']:.1f} h)")
        out.append(f"   {r['id']:<6} {r['topic']}  [{r['area']}, {r['study_hours_est']:.1f} h]")
    return "\n".join(out)


def save_csv(res: Dict, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    rows = res["rows"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel shows names correctly
        if rows:
            wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            wr.writeheader()
            wr.writerows(rows)
        if res.get("left_out"):
            f.write("\nLeft out of the crunch plan\n")
            wr = csv.DictWriter(f, fieldnames=list(res["left_out"][0].keys()))
            wr.writeheader()
            wr.writerows(res["left_out"])
        f.write("\nAll hours are estimates (data/*/topics.csv and params.json), not measured study times.\n")
    return path
