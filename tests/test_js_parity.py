"""The browser planner (docs/planner-core.js) must reproduce the Python results."""
import json, os, shutil, subprocess, sys
import pytest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from speedrun.data import load_web, Params, Profile
from speedrun.graph import build_instance
from speedrun.costs import Evaluator
from speedrun.baselines import curriculum_order, subject_by_subject
from speedrun import heuristics as H
from speedrun.days import shortest_path_split
from speedrun.crunch import profit_max_tour


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("web_json,data_dir", [("pilot.json", "sample"), ("web.json", "iima")])
def test_parity(web_json, data_dir):
    web_json = os.path.join(ROOT, "docs", "data", web_json)
    if not os.path.exists(web_json):
        pytest.skip("export the web first: python run.py web")
    js = json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tests", "parity_node.js"), web_json]))
    data = os.path.join(ROOT, "data", data_dir)
    web = load_web(data); P = Params.load(os.path.join(data, "params.json"))
    for pr in json.load(open(os.path.join(data, "profiles.json"))):
        inst = build_instance(web, Profile.from_dict(pr), P.copy(**pr.get("params", {}))); ev = Evaluator(inst)
        r = js[pr["name"]]
        assert r["ids"] == inst.ids
        assert r["added"] == inst.auto_added
        b0, _ = curriculum_order(ev); b1 = subject_by_subject(ev)
        nn = H.nearest_neighbour(ev); ci = H.cheapest_insertion(ev)
        assert r["B0_ids"] == ev.to_ids(b0) and abs(r["B0"] - ev.cost(b0)) < 1e-6
        assert abs(r["B1"] - ev.cost(b1)) < 1e-6
        assert r["NN_ids"] == ev.to_ids(nn) and abs(r["NN"] - ev.cost(nn)) < 1e-6
        assert r["CI_ids"] == ev.to_ids(ci) and abs(r["CI"] - ev.cost(ci)) < 1e-6
        s, c = H.local_search(ev, list(nn))
        assert abs(r["NN_LS"] - c) < 1e-6
        assert r["days"] == shortest_path_split(ev, s)["n_days"]
        if pr.get("budget"):
            cr = profit_max_tour(ev, pr["budget"])
            assert r["crunch"]["value"] == cr["value"] and abs(r["crunch"]["hours"] - cr["hours"]) < 1e-6
