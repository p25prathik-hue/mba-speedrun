# Contributing

Future OML groups, IIMA committees and students are welcome to extend this.

## Ground rules
1. **Keep IDs stable.** Never renumber `topics.csv`; add new topics with new IDs. The planner, results and links all key on IDs.
2. **Label every number.** New hours, values or links need a `source` (`estimate`, `textbook`, `syllabus`, `survey`, `dataset`). Never present an estimate as measured.
3. **Link every change to class.** Each new module or method should say which session and slide it applies, in its docstring and in `docs/class_concept_map.csv`.
4. **Tests must pass:** `python -m pytest -q`. If you change a heuristic in `src/speedrun/heuristics.py`, port the change to `docs/planner-core.js` too. `tests/test_js_parity.py` checks the two give identical results.

## Common tasks
* **Add topics or links:** edit `data/<web>/topics.csv` and `prereqs.csv`, then run `python run.py audit --data data/<web>`. It must report `acyclic_kahn: true` and `acyclic_bellman_ford: true`.
* **Add external evidence:** add units to `data/external/units.csv` and the source to `sources.csv`, then run `python scripts/integrate_external.py --data data/<web>`. Review `topic_unit_map_suggested.csv` and save the reviewed version as `topic_unit_map.csv`.
* **Refresh the website:** `python run.py web --data data/<web> --out docs/data/web.json`.
* **Add a preset:** append to `data/<web>/profiles.json` (fields: name, description, known, skip, multipliers, targets, target_domains, budget).

## Ideas
See "Extend it" in the README: real hour estimates from a survey, exam weights, group study (VRP), time windows, and a UFLP for where shared concepts should be taught.
