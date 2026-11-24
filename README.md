# MBA Speedrun

**Personalised learning roadmaps for the IIMA PGP core, as a Sequential Ordering Problem.**
Group project for *Optimisation Methods in Logistics* (OML), IIM Ahmedabad. Group: Prathik, Nikita Naik Mood, Anureet Biswas, Mrinal Bhaskar.

**Roadmap planner (live):** https://p25prathik-hue.github.io/mba-speedrun/  
**Report (PDF):** [docs/report.pdf](docs/report.pdf)  
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/p25prathik-hue/mba-speedrun/blob/main/notebooks/00_run_in_colab.ipynb)

## Run it the easy way

| You want to | Do this |
|---|---|
| Make a study plan, nothing to install | Open the [roadmap planner](https://p25prathik-hue.github.io/mba-speedrun/). Offline: download the folder and open `docs/index.html` in your browser. |
| Run the Python tool without installing anything | Click **Open in Colab** above, then *Runtime → Run all*. Fill in the form; the plan downloads as a CSV. |
| Run it on your Windows laptop | *Code → Download ZIP*, unzip, double-click **`START_HERE_Windows.bat`**. |
| Run it on a Mac or Linux | In the unzipped folder run `bash start_mac_linux.sh`. |

The launchers need Python 3.9+ ([python.org](https://www.python.org/downloads/); on Windows tick *Add python.exe to PATH*). The first run sets up a private environment in `.venv` and installs the requirements, which takes 1-3 minutes and needs internet. After that they open this menu at once:

```
  1  Open the roadmap planner website (in your browser, nothing else needed)
  2  Make my study roadmap here (answer a few questions, get a day-by-day plan)
  3  Exam crunch: best topics for a fixed number of hours
  4  Reproduce every number and figure in the report
  5  Run the tests
```

Options 2 and 3 ask which subject areas you know, half know or want to skip, any single topics you know, and your hours per day. They print the first days and save the whole plan to `my_roadmaps/` as a CSV that opens in Excel. Already have Python set up? `python start.py` opens the same menu, and `python start.py roadmap` (or `crunch`, `planner`, `reproduce`, `test`) jumps straight to one option.

The full 266-topic roadmap takes about 20 seconds, or about a minute if `numba` could not be installed. All hours are **estimates**.

A student catching up alone (before end-terms or summer-placement prep) learns one topic at a time, but the core is taught as parallel courses for a cohort of ~400. This repo orders core micro-topics so that

* every prerequisite comes first (AND, OR and recommended links, within and across courses),
* subject switches, lost synergies and forgetting are kept low, and
* the order is split into days of *H* study hours,

using the class toolkit: the student is the **machine**, topics are **jobs**, and the switching cost *c<sub>ij</sub>* is a **sequence-dependent setup time** (a TSP application on Session 6, slide 1).

**Website (GitHub Pages):** live at https://p25prathik-hue.github.io/mba-speedrun/ once Pages is switched on. `docs/` has a roadmap planner, two topic-web explorers and the class-concept map. Enable it under *Settings → Pages → Branch: main, folder: /docs*.

> **Data.** `data/iima/` is the main web: 266 micro-topics across all 37 first-year courses, with 387 links after Step 1 (358 AND, 6 OR, 23 SOFT). 119 links are backed by textbook or syllabus order; 268 are our estimates. `data/sample/` is a 28-topic Finance + Accounting **pilot**, small enough for exact branch and bound. Topic hours, values and all cost parameters are **estimates** in both.

---

## Quick start

```bash
git clone https://github.com/p25prathik-hue/mba-speedrun.git && cd mba-speedrun
python -m pip install -r requirements.txt        # PuLP 2.9 bundles the CBC solver

python run.py audit    --data data/iima           # DAG check (Kahn + Bellman-Ford), stats
python run.py solve    --data data/iima --hours 6 --known QNT01,QNT02 --skip MKT24
python run.py exact    --data data/sample --targets F8,M6     # branch and bound + bounds (pilot scale)
python run.py profiles --data data/iima --out results/iima
python run.py sensitivity --data data/iima --draws 60 --restarts 0 --out results/iima/sensitivity.json
python run.py web      --data data/iima --out docs/data/web.json      # refresh the website data
python -m pytest -q                                # 19 tests incl. brute force and JS parity
```

On Windows use `python`, not `py`. Open `docs/planner.html` straight from disk: it also works without a server.

Optional: `python -m pip install numba` makes evaluation of a 266-topic order about 4x faster than the built-in numpy evaluator (same results). The launchers install it for you when they can.

Reproduce every number in the report:

```bash
# the 266-topic web: rebuild from the source list, then Step 1
python scripts/kit/audit.py                         # writes data/iima/topics.csv, prereqs.csv (kit version)
python scripts/integrate_external.py --data data/iima --out results/iima/external_agreement.json
python scripts/apply_step1_changes.py --data data/iima --changes data/external/step1_changes_iima.csv
python run.py profiles    --data data/iima --out results/iima
python run.py sensitivity --data data/iima --draws 60 --restarts 0 --out results/iima/sensitivity.json
# the pilot: exactness, bounds, crunch exact
python run.py profiles    --data data/sample --out results/sample
python run.py sensitivity --data data/sample --draws 200 --restarts 2 --out results/sample/sensitivity.json
python scripts/scale_experiment.py --data data/sample --out results/scale.json
# figures, website data, report
python scripts/make_figures.py
python run.py web --data data/iima --out docs/data/web.json && python run.py web --data data/sample --out docs/data/pilot.json
python scripts/kit/layout.py                        # the starter kit's detailed explorer -> docs/topic-web.html
cd report && latexmk -pdf main.tex
```

Note: `scripts/kit/audit.py` rebuilds the kit version of `prereqs.csv`. Run the two Step 1 scripts after it, as above.

---

## The model (professor's notation)

S = dummy start (Q<sub>S</sub> = T), E = dummy end (Q<sub>E</sub> = 0), p<sub>i</sub> = m<sub>i</sub> t<sub>i</sub> (effective hours).

```
min  Σ p_i + Σ c_ij x_ij + Σ r_kj + π Σ v_kj
(I)   Σ_j x_ij = 1   (II)  Σ_i x_ij = 1                               S6 slide 3
Load  Q_i ≥ Q_j + p_i x_ij − T(1 − x_ij);  Q_i ≤ Q_j + p_i + T(1 − x_ij)    S9 slide 22
AND   Q_k ≥ Q_j + p_k
OR    Σ_{k∈G_j} y_kj ≥ 1,  Q_k ≥ Q_j + p_k − T(1 − y_kj)                 S5 slides 4, 7
SOFT  Q_k ≥ Q_j + p_k − T v_kj   (penalised)
REV   r_kj = min(ρ (Q_k − p_k − Q_j − L)^+, κ p_k)   (capped; one binary per long link)  forgetting
c_ij = w·[domain_i ≠ domain_j] − s·sim(i,j)·p_j
```

Q<sub>i</sub> is "study hours still to go before topic i": the professor's "load on the vehicle just before customer i" with d<sub>i</sub> = p<sub>i</sub>. It removes subtours and is also an exact clock, so the forgetting cost stays linear.

## Class-concept map

Full table: [`docs/class_concept_map.csv`](docs/class_concept_map.csv) (56 rows: 33 core, 18 supporting, 5 not used). Main uses:

| Code | Class idea | Session, slides |
|---|---|---|
| `milp.py` | ATSP formulation (I), (II); load-variable compact form Q<sub>i</sub>; B&B, LP bound, incumbent; warm start | S6 sl.3; S9 sl.22; S5 sl.16–28; S8 sl.9 |
| `milp.py` | Assignment relaxation bound; arc fixing and subtour-breaking cuts | S6 sl.3; S9 sl.23–25 |
| `heuristics.py` | NN, cheapest/farthest insertion with Δ<sub>ijk</sub>; Clarke–Wright savings s<sub>ij</sub> (best start on the 266-topic web); 2-opt; or-opt; random restart | S1 sl.26–44; S8 sl.20–27; S3 sl.31–41; S10 sl.36–38 |
| `baselines.py` | Timetable order (B0); subject-by-subject = sweep / cluster-first (B1) | S9 sl.8–10 |
| `days.py` | Bin packing and ⌈Σa<sub>i</sub>/b⌉; exact split = shortest path (lot-sizing structure); hop-limited Bellman–Ford | S8 sl.10–16; S7 sl.1–16 |
| `crunch.py` | Profit-maximising tour heuristic; capital budgeting x<sub>j</sub> ≤ x<sub>k</sub>; knapsack; common carrier δ<sub>i</sub> | S9 sl.12–21; S5 sl.7; S8 sl.7–8 |
| `graph.py` | Cycle check as negative-cycle detection; closure as reachability labels; critical path | S7 sl.10–18 |
| `sensitivity.py` | *Extension*: null test, ±25% one-at-a-time, Monte Carlo | (not in decks) |

Not used, and why: convex hull, MST, Christofides and their worst-case bounds all need symmetric, metric, non-negative costs. Our c<sub>ij</sub> is asymmetric and can be negative, so we measure empirical gaps against exact solutions instead.

## Repository layout

```
data/iima/        266-topic web: topics.csv, prereqs.csv (after Step 1), prereqs_kit.csv, topics_source.txt,
                  overlaps.csv, topic_unit_map.csv (reviewed), params.json, profiles.json, kit_web.json
data/sample/      28-topic pilot web (exact-method checks)
data/external/    Step 1: sources.csv (register + licences), units.csv (chapter/session order), step1_changes_iima.csv
scripts/kit/      the starter kit's audit.py, layout.py and explorer template (paths now relative to the repo)
src/speedrun/     data, graph, costs, baselines, heuristics, milp, days, crunch, sensitivity, experiments, cli,
                  easy (plain-language front end used by start.py and the Colab notebook)
start.py          menu launcher (planner, roadmap, crunch, reproduce, tests); START_HERE_Windows.bat and
                  start_mac_linux.sh set up .venv on first run and then open it
scripts/          scale_experiment.py, integrate_external.py, make_figures.py
notebooks/        00_run_in_colab.ipynb (one-click roadmap in Colab); 01-06 one walkthrough per class concept
tests/            brute-force checks and the JS/Python parity test
docs/             GitHub Pages: index, planner (live JS heuristic), explorer, topic-web (kit explorer), concepts, proposal/
report/           LaTeX source (Overleaf-ready), figures, compiled PDF
results/          JSON/CSV outputs used in the report
```

## Data dictionary

See [`data/README.md`](data/README.md). In short: `topics.csv` (id, name, course, domain, term, order, hours, value) and `prereqs.csv` (src → dst, type AND/OR/SOFT, OR group, source). The loader also accepts common alternative column names (`python run.py inspect --data DIR` shows the mapping), so the starter-kit files load without edits.

## Headline results (estimates; see the report)

| 266-topic web, 6 h/day | Topics | Subject by subject (B1) | Roadmap | Saving |
|---|---|---|---|---|
| Fresh learner | 266 | 502.3 h | 415.4 h | 86.9 h (17%) |
| Engineer | 257 | 451.3 h | 385.8 h | 65.5 h (15%) |
| Commerce graduate | 252 | 443.3 h | 367.4 h | 75.9 h (17%) |
| Skip Marketing (closure keeps 14 of 25 MKT topics) | 255 | 484.2 h | 401.5 h | 82.7 h (17%) |

Personalisation saves another 28–79 h. Treating the 77 shared concepts once avoids about 142 h of re-learning. The roadmap clusters by **domain** (FRA+CCS, FM+CF), not by course.

## Extend it (ideas for the next group)

1. **Real hours:** a 10-minute PGP2 survey (hours per topic, by background) to replace the estimates. The sensitivity chapter shows which parameters matter most.
2. **Exam weights as values:** ask the Acads committee or course outlines for the session weights used in crunch mode.
3. **Group study:** several students = several machines. Assigning topics to study partners is a VRP (S7–S9), with Clarke–Wright as a first heuristic.
4. **Time windows:** exam dates per course turn the problem into a TSP with time windows.
5. **Where to teach shared concepts:** a UFLP (S10) to decide whether a concept used by several courses should be taught once or repeated.

## Licences

Code: MIT (`LICENSE`). Data in `data/`: CC BY 4.0 (`data/LICENSE-DATA.md`). External sources are cited in `data/external/sources.csv`. We store only chapter/session *order* facts and paraphrased unit names, never textbook text. MIT OCW material is CC BY-NC-SA 4.0.

## Acknowledgement

AI tools were used, as the course guidelines encourage: for code, data structuring and drafting. Every number in the report comes from running this code. The starter kit (topic web, audit and layout scripts, explorer, proposal) came from an earlier phase of the project and is included with its paths made relative.
