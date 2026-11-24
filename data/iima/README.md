# The 266-topic IIMA web

| file | what it is |
|---|---|
| `topics_source.txt` | the hand-written source list (id, name, courses, term, size, value, prerequisites) |
| `topics.csv`, `prereqs_kit.csv`, `redundant_edges_removed.csv`, `kit_web.json` | starter-kit outputs of `scripts/kit/audit.py` |
| `prereqs.csv` | **the links used by every experiment**: the kit links after Step 1, with `source`, `external_evidence` and `step1` columns |
| `prereqs_with_source.csv` | intermediate output of `scripts/integrate_external.py` |
| `topic_unit_map.csv` | reviewed mapping of 129 topics to textbook chapters / syllabus sessions (order evidence) |
| `overlaps.csv` | 20 reviewed synergy pairs (from the kit's name-similarity screen; false positives dropped) |
| `params.json`, `profiles.json` | cost parameters (estimates) and the five student profiles |

Rebuild:

```bash
python scripts/kit/audit.py                    # topics.csv, prereqs.csv (kit version), kit_web.json
cp data/iima/prereqs.csv data/iima/prereqs_kit.csv
python scripts/integrate_external.py --data data/iima --out results/iima/external_agreement.json
python scripts/apply_step1_changes.py --data data/iima --changes data/external/step1_changes_iima.csv
python run.py audit --data data/iima
```

Units: `base_minutes` is read as hours / 60. IDs are stable: never renumber.
