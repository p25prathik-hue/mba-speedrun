"""Correctness checks against brute force on small instances.

Run: python -m pytest -q
"""
import itertools, os, sys
import pytest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from speedrun.data import load_web, Params, Profile
from speedrun.graph import build_instance, audit, bellman_ford_has_cycle, kahn_topological
from speedrun.costs import Evaluator
from speedrun import heuristics as H, milp
from speedrun.days import shortest_path_split, _day_hours
from speedrun.sensitivity import null_test

DATA = os.path.join(ROOT, "data", "sample")
WEB = load_web(DATA)
P = Params.load(os.path.join(DATA, "params.json"))


def small(targets):
    inst = build_instance(WEB, Profile(targets=targets), P)
    return Evaluator(inst)


def brute(ev):
    best = (float("inf"), None)
    for perm in itertools.permutations(range(ev.n)):
        if ev.feasible(perm):
            c = ev.cost(perm)
            if c < best[0]:
                best = (c, perm)
    return best


def test_web_is_acyclic_both_ways():
    a = audit(WEB)
    assert a["acyclic_kahn"] and a["acyclic_bellman_ford"]


def test_bellman_ford_detects_a_cycle():
    assert bellman_ford_has_cycle(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    assert kahn_topological(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")]) is None


@pytest.mark.parametrize("targets", [["F5"], ["F8"], ["M6", "A4"]])
def test_milp_matches_brute_force(targets):
    ev = small(targets)
    assert ev.n <= 9
    zb, _ = brute(ev)
    r = milp.solve_exact(ev, time_limit=60)
    assert abs(r["objective_eval"] - zb) < 1e-6
    assert abs(r["objective_model"] - zb) < 1e-6, "MILP objective must equal the evaluator"
    # bound chain: assignment <= LP+cuts <= z*
    assert milp.assignment_bound(ev) <= zb + 1e-6
    assert milp.lp_bound(ev, True) <= zb + 1e-6
    assert milp.lp_bound(ev, False) <= milp.lp_bound(ev, True) + 1e-6


@pytest.mark.parametrize("targets", [["F5"], ["F8"], ["M6", "A4"]])
def test_heuristic_finds_brute_force_optimum_on_small(targets):
    ev = small(targets)
    zb, _ = brute(ev)
    _, c = H.solve_heuristic(ev, restarts=3)
    assert c <= zb + 1e-6


def test_constructors_feasible_on_full_pilot():
    ev = Evaluator(build_instance(WEB, Profile(), P))
    for name, f in H.CONSTRUCTORS.items():
        assert ev.feasible(f(ev)), name


def test_split_is_optimal_for_fixed_order():
    ev = small(["F8", "M6"])
    seq, _ = H.solve_heuristic(ev, restarts=1)
    H_ = 6.0
    sp = shortest_path_split(ev, seq, H_)
    n = len(seq)
    best = None
    for mask in range(1 << (n - 1)):  # every way to cut the sequence
        cuts = [0] + [k + 1 for k in range(n - 1) if mask >> k & 1] + [n]
        hrs = [_day_hours(ev, seq, a, b) for a, b in zip(cuts[:-1], cuts[1:])]
        if any(h > H_ + 1e-9 and b - a > 1 for h, (a, b) in zip(hrs, zip(cuts[:-1], cuts[1:]))):
            continue
        key = (len(hrs), sum(hrs))
        best = key if best is None or key < best else best
    assert sp["n_days"] == best[0] and abs(sp["total_hours"] - round(best[1], 2)) < 0.02


def test_closure_or_group_picks_cheapest_route():
    inst = build_instance(WEB, Profile(target_domains=["FIN"]), P)
    assert "M7" in inst.ids and "A7" not in inst.ids  # relevant-costing route is cheaper


def test_null_model_gives_zero_sequencing_gain():
    inst = build_instance(WEB, Profile(), P)
    assert null_test(inst)["passes"]


@pytest.mark.parametrize("targets", [["F8"], ["M6", "A4"]])
def test_milp_matches_brute_force_when_revision_cap_binds(targets):
    """Tight cap and fast forgetting, so min(rho*(gap-L), kappa*p_k) is active on several links."""
    P2 = P.copy(rho_revision=0.3, L_revision_free=0.0, revision_cap_share=0.1)
    ev = Evaluator(build_instance(WEB, Profile(targets=targets), P2))
    zb, perm = brute(ev)
    bd = ev.breakdown(perm)
    assert abs(bd["total"] - ev.cost(perm)) < 1e-9          # compiled == numpy evaluator
    r = milp.solve_exact(ev, time_limit=60)
    assert abs(r["objective_eval"] - zb) < 1e-6
    assert abs(r["objective_model"] - zb) < 1e-6


@pytest.mark.parametrize("data", ["sample", "iima"])
def test_numpy_kernel_matches_loop_kernel(data):
    """The numpy fallback (used when numba is missing) must give the loop kernel's cost."""
    import random
    import numpy as np
    from speedrun.costs import _total_np, _total_py
    d = os.path.join(ROOT, "data", data)
    ev = Evaluator(build_instance(load_web(d), Profile(), Params.load(os.path.join(d, "params.json"))))
    rng = random.Random(7)
    for t in range(60):
        s = H.random_topological(ev, rng)
        if t % 3 == 0:  # make some orders infeasible
            i, j = rng.randrange(ev.n), rng.randrange(ev.n)
            s[i], s[j] = s[j], s[i]
        a = np.asarray(s, np.int64)
        x, y = _total_py(a, *ev._args), _total_np(a, *ev._args)
        assert (np.isinf(x) and np.isinf(y)) or abs(x - y) < 1e-8


def test_easy_front_end_on_pilot():
    from speedrun.easy import make_crunch, make_roadmap, match_areas
    assert match_areas("2, fin", ["ACC", "FIN"]) == ["FIN"]
    r = make_roadmap("pilot", hours_per_day=6, root=ROOT)
    assert r["n_topics"] == len(r["rows"]) == 28
    assert r["total_hours_est"] <= r["subject_by_subject_hours_est"]
    assert [x["id"] for x in r["rows"]] and len({x["id"] for x in r["rows"]}) == 28
    c = make_crunch(20, "pilot", root=ROOT)
    assert c["hours_used_est"] <= 20 + 1e-9 and len(c["rows"]) + len(c["left_out"]) == 28
