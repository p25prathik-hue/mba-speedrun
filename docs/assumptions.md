# Assumptions and estimates

Everything below is an **estimate**. The report's Section 8 tests how much each one matters.

| Item | Value (pilot) | Why this value | Most sensitive? |
|---|---|---|---|
| Topic hours t_i | 45 / 90 / 150 min (S/M/L) on the IIMA web; 2–3 h on the pilot | Roughly one class session plus practice | All hours ±25% moves the gain by under 0.5 points |
| Switch warm-up w | 0.5 h | Re-reading notes and getting back into a subject's notation | Moderate |
| Synergy s | 0.15 | Up to 15% of t_j saved when it directly follows a linked topic | **High** |
| Revision rate ρ | 0.02 h per h of gap | e.g. a 60-hour gap costs about 1 h of revision | **High** |
| Revision-free gap L | 12 study hours | About two study days | Moderate |
| Revision cap κ | 0.5 × p_k | A refresh never costs more than half the original learning time. Without it, a T1 topic used in T3 is charged 6 h of revision on every link | **High on the full web**, none on the pilot |
| SOFT penalty π | 1.0 h | Learning without a recommended prior | Low |
| Day warm-up | 0.25 h | Start-of-day ramp-up (the "depot leg") | Low |
| Hours per day H | 6 h | Catch-up during a break; the planner lets students change it | Changes days, not the order |
| Value r_i | 1–5 | Placement and interview relevance (crunch mode only) | Changes the crunch selection |

Modelling assumptions:

* The clock counts **study hours**, not calendar days. Sleep and spacing between days are not modelled.
* Costs are **linear**: one warm-up per switch, and synergy proportional to the next topic's time.
* Forgetting starts after L hours and grows linearly. This is a simple stand-in for a forgetting curve (Ebbinghaus 1885/1913).
* **Interleaving benefits** for long-term retention (Rohrer & Taylor 2007) are not modelled. If they were, optimal plans would mix subjects more.
* Topics are **indivisible** within a day.
* **One learner.** Group study would be a multi-machine problem, i.e. a VRP.

How to replace the estimates: run a 10-minute PGP2 survey (hours per topic by background), or ask the Acads Secretary for course outlines with session plans.
