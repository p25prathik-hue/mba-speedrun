"""Export the topic web (+ precomputed preset roadmaps) for the static GitHub Pages site.

The Pages planner runs the same heuristics in JavaScript (docs/planner.js) for any
custom selection; presets also carry the Python result so the two can be compared.
"""
from __future__ import annotations

import json
import os

from .data import Params, Web


def export(web: Web, params: Params, out: str, profiles_path: str = None, results_path: str = None,
           var: str = "SPEEDRUN_WEB"):
    data = {
        "generated_by": "speedrun.webexport",
        "params": {k: v for k, v in params.__dict__.items()},
        "topics": [
            {"id": t.id, "name": t.name, "course": t.course, "courses": t.courses, "domain": t.domain,
             "term": t.term, "order": t.order, "hours": t.hours, "value": t.value}
            for t in web.topics.values()
        ],
        "links": [{"src": l.src, "dst": l.dst, "type": l.type, "group": l.group, "source": l.source}
                  for l in web.links],
        "overlaps": [{"a": a, "b": b, "sim": s} for (a, b), s in web.overlaps.items() if a < b],
        "presets": [],
    }
    if profiles_path and os.path.exists(profiles_path):
        data["presets"] = json.load(open(profiles_path))
    if results_path and os.path.exists(results_path):
        res = {r["profile"]: r for r in json.load(open(results_path))}
        for p in data["presets"]:
            r = res.get(p["name"])
            if r:
                p["python_result"] = {"roadmap_ids": r["roadmap_ids"], "total": r["roadmap"]["total"],
                                      "B0": r["B0"]["total"], "B1": r["B1"]["total"],
                                      "days": r["days"]["n_days"]}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(data, f, indent=1)
    # same data as a script, so the site also works when opened from disk (file://)
    with open(os.path.splitext(out)[0] + ".js", "w") as f:
        f.write(f"window.{var} = " + json.dumps(data) + ";\n")
    print(f"wrote {out}: {len(data['topics'])} topics, {len(data['links'])} links, {len(data['presets'])} presets")
