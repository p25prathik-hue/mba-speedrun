# Data dictionary

All hours are **study hours for an average PGP1 student learning the topic for the first time**. They are estimates unless the `note`/`source` column says otherwise.

## topics.csv
| column | meaning | class symbol |
|---|---|---|
| id | stable identifier (never renumber) | i ∈ N |
| name | micro-topic | |
| course | IIMA course it is taught in (pilot: textbook-based course labels) | |
| domain | subject area used for the switching cost | domain<sub>i</sub> |
| term | term in which the course runs (1, 2, 3) | |
| order | session order within the course | |
| hours | base study time | t<sub>i</sub> |
| value | relevance for crunch mode (1 to 5, estimate) | r<sub>i</sub> |

## prereqs.csv
| column | meaning |
|---|---|
| src → dst | `src` must (AND), may (OR) or should (SOFT) come before `dst` |
| type | AND = required; OR = at least one link of the same `group` is required; SOFT = recommended (penalised if violated) |
| group | OR-group label |
| source | `estimate`, `textbook`, `syllabus`, `dataset` (several separated by `;`) |
| evidence | short note: which chapter/session order supports the link |

## overlaps.csv (optional)
Pairs of topics that reinforce each other when studied back to back (`sim` in [0, 1]), on top of the automatic similarity from links (1.0 forward, 0.5 backward) and same-course adjacency (0.5, or 0.25 if not adjacent).

## params.json (all estimates, in hours)
| key | meaning | symbol |
|---|---|---|
| w_switch | warm-up when the domain changes | w |
| s_synergy | share of t<sub>j</sub> saved right after a fully related topic | s |
| rho_revision | revision hours per study hour of gap beyond L | ρ |
| L_revision_free | gap (study hours) a prerequisite survives without revision | L |
| soft_penalty | cost of studying a topic before its recommended prerequisite | π |
| start_warmup | warm-up before the first topic | c<sub>0j</sub> |
| day_hours | study hours per day | H (= bin size b) |
| day_warmup | warm-up at the start of each day | depot leg |

## profiles.json
Student presets: `known` (treated as done), `skip` (excluded; closure may add them back), `multipliers` (m<sub>i</sub> < 1 = partly known), `targets` / `target_domains` (study only these plus required prerequisites), `budget` (crunch mode, hours).

## The 266-topic IIMA web
Put the starter-kit files in `data/iima/` (`topics.csv`, `prereqs.csv`, plus `params.json` and `profiles.json` copied from `data/sample` and adapted). Check the column mapping with `python run.py inspect --data data/iima`.
