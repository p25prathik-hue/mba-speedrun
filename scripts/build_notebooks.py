"""Generate and execute one walkthrough notebook per class concept.

Run: python scripts/build_notebooks.py   (writes notebooks/*.ipynb with outputs)
"""
import os, sys
import nbformat as nbf
from nbclient import NotebookClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NB = os.path.join(ROOT, "notebooks")
os.makedirs(NB, exist_ok=True)

SETUP = """import os, sys
ROOT = os.path.abspath('..'); sys.path.insert(0, os.path.join(ROOT, 'src'))
from speedrun.data import load_web, Params, Profile
from speedrun.graph import build_instance
from speedrun.costs import Evaluator
web = load_web(os.path.join(ROOT, 'data', 'sample'))
P = Params.load(os.path.join(ROOT, 'data', 'sample', 'params.json'))
inst = build_instance(web, Profile(), P); ev = Evaluator(inst)
name = lambda ids: ' -> '.join(ids)
print(ev.n, 'topics,', round(ev.sum_p, 1), 'study hours (estimates)')"""

books = {
"01_tsp_formulation_and_bounds": [
("md", """# 1. The roadmap as an asymmetric TSP / SOP, and its bounds
**Class:** Session 6 slide 3 (ATSP formulation, assignment relaxation), Session 9 slide 22 (load variables Q<sub>i</sub>), Session 5 slides 16–28 (LP bound, branch and bound), Session 9 slides 23–25 (valid inequalities).

**IIMA context:** a student who wants WACC (Corporate Finance) and variance analysis (Management Accounting) asks for the fastest prerequisite-respecting order. With ~13 topics, B&B proves the optimum in well under a second."""),
("code", SETUP),
("code", """from speedrun import milp, heuristics as H
ev13 = Evaluator(build_instance(web, Profile(targets=['F8', 'M6']), P))
print(ev13.n, 'topics in scope:', ev13.ids)
seq, zh = H.solve_heuristic(ev13, restarts=2)
r = milp.solve_exact(ev13, time_limit=60, warm_seq=seq)
print('heuristic z^H =', round(zh, 3), '| exact z* =', round(r['objective_eval'], 3), '| proven:', r['optimal'], '| nodes:', r['nodes'])"""),
("md", "The chain of lower bounds (minimisation, so Z<sub>LP</sub> ≤ Z<sub>IP</sub>, Session 5 slide 16). Relaxing constraint (III) leaves an assignment problem (Session 6 slide 3)."),
("code", """print('assignment relaxation (+ arc fixing):', round(milp.assignment_bound(ev13), 3))
print('LP relaxation, no cuts             :', round(milp.lp_bound(ev13, cuts=False), 3))
print('LP + arc fixing + 2-cycle cuts     :', round(milp.lp_bound(ev13, cuts=True), 3))
print('optimum z*                         :', round(r['objective_eval'], 3))
print(name(ev13.to_ids(r['seq'])))"""),
("md", "**Reading:** precedence-based arc fixing (x<sub>jk</sub> = 0 when k is an ancestor of j) does here what subtour and capacity inequalities do on Session 9 slide 25: it closes most of the LP gap."),
],
"02_construction_heuristics": [
("md", """# 2. Construction heuristics with precedence
**Class:** Session 1 slides 26–44 (nearest neighbour, nearest/cheapest insertion with Δ<sub>ijk</sub> = c<sub>ik</sub> + c<sub>kj</sub> − c<sub>ij</sub>, farthest insertion), Session 8 slides 20–27 (Clarke–Wright savings s<sub>ij</sub> = c<sub>i0</sub> + c<sub>0j</sub> − c<sub>ij</sub>).

**IIMA context:** the two baselines are what students actually do: replay the timetable (B0, parallel courses) or finish one subject before the next (B1, which is cluster-first like the sweep heuristic of Session 9)."""),
("code", SETUP),
("code", """from speedrun import heuristics as H
from speedrun.baselines import curriculum_order, subject_by_subject
b0, inv = curriculum_order(ev); b1 = subject_by_subject(ev)
rows = [('B0 timetable order', b0), ('B1 subject by subject', b1)] + [(k, f(ev)) for k, f in H.CONSTRUCTORS.items()]
for k, s in rows:
    bd = ev.breakdown(s)
    print(f"{k:<22} total {bd['total']:6.2f} h | switching {bd['transitions']:6.2f} | revision {bd['revision']:5.2f} | domain switches {int(bd['domain_switches'])}")"""),
("md", "Worst-case bounds such as z<sup>NI</sup>/z* ≤ 2 (Session 1 slide 37) need the triangle inequality. Our c<sub>ij</sub> is asymmetric and can be negative (synergy), so we compare against exact solutions instead (notebook 1 and `scripts/scale_experiment.py`)."),
],
"03_improvement_and_restarts": [
("md", """# 3. Improvement: or-opt, 2-opt, random restarts
**Class:** Session 3 slides 31–41 (2-opt, 3-opt, or-opt with p = 3, 2, 1), Session 10 slides 36–38 (neighbourhood search, neighbourhood size, random restart).

**IIMA context:** or-opt is "move this block of 1–3 topics earlier or later". It is the natural edit a student makes to a plan, limited to the window between the block's last prerequisite and first dependent."""),
("code", SETUP),
("code", """from speedrun import heuristics as H
s = H.nearest_neighbour(ev); c = ev.cost(s); print('NN start       ', round(c, 3))
s, c, _ = H.or_opt(ev, s, c); print('after or-opt   ', round(c, 3))
s, c, _ = H.two_opt(ev, s, c); print('after 2-opt    ', round(c, 3))
s, c = H.local_search(ev, s); print('local optimum  ', round(c, 3))
log = []; best_s, best = H.solve_heuristic(ev, restarts=8, log=log)
print('best of', len(log), 'starts:', round(best, 3))
for r in log: print(f"  {r['start']:<6} {r['construct']:7.2f} -> {r['improved']:7.2f}")"""),
("md", "In an asymmetric, precedence-constrained instance 2-opt rarely applies. Reversing a segment breaks any prerequisite chain inside it, so or-opt does most of the work."),
],
"04_days_bin_packing_shortest_path": [
("md", """# 4. Splitting the roadmap into days
**Class:** Session 8 slides 10–19 (bin packing, lower bound ⌈Σa<sub>i</sub>/b⌉, FFD), Session 7 slides 1–16 (shortest path, Dijkstra, Bellman–Ford with hop limit; the lot-sizing application), Session 8 slide 27 (TSP and bin packing are the two dimensions Clarke–Wright handles together).

**IIMA context:** H is what you can study around classes (3 h on a class day, 8 h on a weekend). Sorting topics by size (FFD) is not allowed because it would break prerequisites. For a fixed order, the shortest path over positions is the exact split."""),
("code", SETUP),
("code", """from speedrun import heuristics as H
from speedrun.days import shortest_path_split, greedy_split, lower_bound_days
seq, _ = H.solve_heuristic(ev, restarts=2)
for Hh in (4, 6, 8):
    sp = shortest_path_split(ev, seq, Hh); g = greedy_split(ev, seq, Hh)
    print(f"H={Hh}: shortest-path split {sp['n_days']} days / {sp['total_hours']} h | greedy {g['n_days']} days / {g['total_hours']} h | bound {lower_bound_days(ev, Hh)}")
sp = shortest_path_split(ev, seq, 6)
hop = shortest_path_split(ev, seq, 6, max_days=sp['n_days'] + 1)
print('one extra day (hop limit D+1) saves', round(sp['total_hours'] - sum(d['hours'] for d in hop['days']), 2), 'h: subject switches move to day breaks')"""),
],
"05_crunch_profit_max_tour": [
("md", """# 5. Crunch mode: the most value per hour
**Class:** Session 9 slides 17–21 (profit-maximising tour heuristic, bang-for-buck ratio), Session 5 slide 7 (capital budgeting with x<sub>5</sub> ≤ x<sub>4</sub>: *the professor's own prerequisite constraint*), Session 8 slides 7–8 (knapsack), Session 9 slides 12–16 (common carrier).

**IIMA context:** "Interviews in 25 hours." The heuristic grows the plan by the topic, plus its missing prerequisites, that adds the most value per hour. Topics left out go to the "common carrier": a senior's crash session or peer notes."""),
("code", SETUP),
("code", """from speedrun import crunch, milp
for B in (15, 25, 40):
    h = crunch.profit_max_tour(ev, B); k = crunch.knapsack_closure(ev, B)
    print(f"budget {B:>2} h: heuristic value {h['value']:.0f} in {h['hours']:.1f} h | knapsack (ignores sequencing) {k['value']:.0f}")
ex = milp.solve_crunch_exact(ev, 25, time_limit=60)
print('exact prize-collecting MILP at 25 h: value', ex['value'], ex['status'])
print('left out at 25 h:', crunch.profit_max_tour(ev, 25)['left_out'])"""),
],
"06_sensitivity": [
("md", """# 6. Are the results an artefact of estimated costs?
**Class:** not in the decks (our extension). Session 10 slide 6 mentions deterministic vs stochastic models; we stay deterministic and stress-test.

1. **Null test:** with w = s = ρ = π = 0 every order costs the same, so the gain must be 0.
2. **±25% one at a time** on each parameter.
3. **Monte Carlo:** see `python run.py sensitivity` (200 draws in the report)."""),
("code", SETUP),
("code", """from speedrun import sensitivity as S, heuristics as H
print('null test:', S.null_test(inst))
nominal = ev.to_ids(H.solve_heuristic(ev, restarts=1)[0])
for r in S.one_at_a_time(inst, nominal, restarts=1):
    print(f"{r['param']:<16} x{r['factor']:.2f}: gain vs B0 {r['gain_vs_B0_pct']:5.2f}%  vs B1 {r['gain_vs_B1_pct']:5.2f}%  regret of nominal plan {r['regret_nominal']:.2f} h")"""),
],
}

for nm, cells in books.items():
    nb = nbf.v4.new_notebook()
    nb.cells = [nbf.v4.new_markdown_cell(c) if t == "md" else nbf.v4.new_code_cell(c) for t, c in cells]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": NB}}).execute()
    nbf.write(nb, os.path.join(NB, nm + ".ipynb"))
    print("wrote", nm)
