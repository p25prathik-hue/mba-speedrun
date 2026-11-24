# Step 0: Guidelines audit, class concept map, and revised plan

*MBA Speedrun, OML group project. Built from the professor's guidelines and the 8 decks shared (Sessions 1, 3, 5, 6, 7, 8, 9, 10). The full map is `docs/class_concept_map.csv`: 56 rows, of which 33 are core, 18 supporting and 5 not used.*

## A. What the guidelines actually require

The guidelines document is 10 lines long. Every requirement in it:

| # | Requirement (paraphrased) | Our response |
|---|---|---|
| G1 | Groups of at most 4 | Cover lists the members (to be filled in) |
| G2 | AI tools are encouraged | An acknowledgement section says how AI was used |
| G3 | Groups **may be picked at random** in the last session to present | Every group must be ready, not just volunteers, so the presentation outline is a required deliverable |
| G4 | An important problem facing the IIMA student community | The catch-up and summer-prep crunch (Section 2 of the report) |
| G5 | The problem must benefit from optimisation ideas, tools and techniques **discussed in class** | Every module and section cites a session and slide |
| G6 | Why is it difficult? What are the trade-offs? | Report Section 3 |
| G7 | Random data, or real data you can obtain (Mess / Placement / **Acads Secretary**) | Estimates are labelled as estimates. Suggested real-data route: course outlines (session plans) via the Acads Secretary, plus a 10-minute PGP2 survey on hours per topic |
| G8 | A GitHub page is **encouraged** so later groups or IIMA departments can extend the work | Repo plus GitHub Pages site (explorer and planner) |
| G9 | **Evaluation:** relating class ideas and applying them in real-world contexts | A "Link to class" box in every chapter, the concept map table, and an IIMA interpretation of every result |

**Gaps and conflicts between the guidelines and our brief**

1. **No printed report, format, length or deadline appears in the guidelines.** The brief says the report is printed and submitted; that must have come from class or an email. *Action:* confirm the length, format and due date with the TA or the course page. The deck lists the final exam on **28 Nov**, and today is 24 Nov, so the last session is probably this week. I am planning for a compact report of about 20–25 pages of body text plus appendices, which is easy to trim.
2. **Random selection for presentations** (G3) means "may present" in the brief is too weak. We need a ready 5–7 minute talk.
3. **GitHub is "encouraged", not required.** It is still worth doing, because G8 explicitly rewards reuse by later groups and departments.
4. **Data (G7):** the guidelines prefer obtainable real data. Our times and values are estimates. The Acads Secretary route above is the cheapest way to replace them, and the report must label every estimate as one.
5. **Missing decks:** the course plan (S1 slide 8) includes a **Scheduling** module (2–3 sessions) and **Network Design**, but no decks for those were shared. If scheduling is taught before submission (setup times, single-machine sequencing), we should cite it, since our framing is single-machine scheduling.
6. The topics the guidelines give as examples (elective bidding, placement scheduling) are already taken by other groups. We don't overlap with either.

## B. Class concepts our plan already uses

ATSP formulation (S6 slide 3) · NP-hardness and complexity (S1 slide 11; S7 slides 19–23) · branch and bound, LP bound, incumbent (S5 slides 16–28) · nearest neighbour and cheapest insertion (S1 slides 26–39) · 2-opt and or-opt (S3 slides 31–41) · bin packing (S8 slides 10–16) · knapsack (S8 slides 7–8).

## C. Class concepts we can add naturally

| Add | Class source | Why it is natural here |
|---|---|---|
| **Load-variable compact formulation** `Q_i ≥ Q_j + d_i x_ij − C(1 − x_ij)` in place of positional MTZ | S9 slide 22 | This is the professor's own MTZ. With `d_i = t_i`, `Q_i` is the number of study hours still to go before topic i. Precedence becomes `Q_k ≥ Q_j + t_k`, and the forgetting penalty can be read directly from Q gaps, so the time-dependent cost stays linear. |
| **Assignment-relaxation lower bound** | S6 slide 3 | Drop (III) and solve an assignment problem. It is the correct bound for asymmetric costs. The MST bound is not, since it needs symmetric costs. |
| **Valid inequalities from precedence and the LP-bound table** | S9 slides 23–25 | Fixing the impossible arcs (j→k when k is a prerequisite of j) is like adding subtour cuts. We report the root LP bound before and after, as on S9 slide 25 (60.9% → 98.6%). |
| **Heuristic warm start for B&B** | S8 slide 9 | Pass the or-opt tour to CBC as its first incumbent. |
| **Savings (Clarke–Wright) construction** | S8 slides 20–27; S9 slide 2 | Start with every topic as its own chain. Merge chain-end i to chain-start j in decreasing order of `s_ij`, skipping merges that would break a prerequisite. |
| **"TSP + bin packing" decomposition** | S8 slide 27 | The roadmap is exactly these two dimensions. The special cases hold: `H ≥ Σt` gives a pure sequencing problem, and `c_ij = 0` gives pure bin packing. |
| **Sweep-style baseline** (cluster first, route second) | S9 slides 8–10 | "Finish one subject, then the next." This makes the clustering-vs-integration trade-off a measured result rather than a claim. |
| **Day split as a shortest path** | S7 slides 1–9 (lot sizing) | Positions 0…n are nodes, and an arc a→b is one day covering topics a+1…b. Dijkstra gives the exact split of a fixed order. |
| **Hop-constrained Bellman–Ford** | S7 slides 10–16 | "Can I finish by day D?" is a shortest path with at most D hops. |
| **Bin-packing lower bound** `⌈Σ a_i / b⌉` | S8 slide 16 | The minimum number of days, printed next to every plan. |
| **Profit-maximising tour heuristic** | S9 slides 17–21 | Crunch mode in the professor's notation: `max Σ r_i x_i − f(x)`, `Σ d_i x_i ≤ C`, choosing topics by bang-for-buck `(r_i − δ_i)/d_i`. |
| **Capital budgeting with logical constraints** | S5 slide 7 | The exact crunch IP: `x_j ≤ x_k` is the professor's own prerequisite constraint ("project 5 cannot be undertaken unless project 4"). |
| **Common-carrier removal saving** `δ_i` | S9 slides 12–16 | Decides which topics to "outsource" to a senior's session or peer notes. |
| **Neighbourhood search with random restarts** | S10 slides 36–38 | The design of our local search. |
| **Bellman–Ford negative-cycle check** | S7 slides 17–18 | Cross-checks that the web has no cycles. |
| *(optional)* **UFLP: where should a shared concept be taught?** | S10 slides 10–33 | A curriculum insight for the Acads committee: teach once (one facility) or repeat (several). Build it only if time permits. |

## D. Methods in our plan that were **not** taught, and what to do about each

| Plan item | Decision |
|---|---|
| Positional MTZ `u_i` | **Replace** with the S9 load-variable form (same idea, class notation, and it adds hour-accurate forgetting). |
| "Orienteering" | **Rename and re-ground** as the S9 profit-maximising tour heuristic, with the S5 capital-budgeting IP as the exact version. |
| "Next-fit" bin packing | **Re-ground**: it is the S8 slide 10 heuristic without its sort step (sorting would break precedence). Add the exact shortest-path split (S7) and the S8 lower bound. |
| Topological sort (Kahn) | **Keep** as a polynomial preprocessing step (S7 complexity) and cross-check it with the Bellman–Ford cycle test. |
| BFS/DFS prerequisite closure | **Keep**, but describe it as the reachability step of the S7 labelling algorithm (a label becomes finite once a node is reachable). |
| Transitive reduction | **Keep as an extension.** It removes implied precedence constraints, like dropping dominated constraints, and the feasible set doesn't change. |
| ±25% sensitivity / Monte Carlo | **Keep as an extension.** It isn't in the decks, but the inputs are estimates, so it is the honest test. |
| PuLP / CBC | Tools only. CBC is branch and cut (S1 slide 21). |

**Class methods we deliberately don't use:** convex hull, MST, Christofides, Concorde, and their worst-case bounds. All of them need symmetric, metric, non-negative costs. Our `c_ij` is asymmetric and can be negative (a saving), so the report says so and measures empirical gaps against exact solutions instead.

## E. Revised plan (short)

1. **Data:** keep the 266-topic web. Step 1 adds external evidence and a `source` column. Every estimate is labelled.
2. **Model (S6 + S9 + S5):** ATSP degree constraints (I) and (II), load variables `Q_i` in hours, AND precedence `Q_k ≥ Q_j + t_k`, OR precedence via S5 logic with `y_kj`, and a linear forgetting penalty from Q gaps. Arcs that would violate a prerequisite are fixed to zero.
3. **Bounds (S5, S6, S9):** assignment relaxation ≤ LP ≤ LP with cuts ≤ z*. Solved by B&B (CBC) with a heuristic warm start (S8 slide 9).
4. **Heuristics (S1, S3, S8, S9, S10):** baselines B0 (curriculum order) and B1 (subject by subject, sweep-style). Construction by NN, CI and savings, all precedence-feasible. Improvement by or-opt (p = 3, 2, 1) and 2-opt, with random restarts. Gaps are measured against exact solutions on pilot instances.
5. **Days (S7, S8):** exact shortest-path split of the chosen order, a hop-constrained "finish by day D" check, and the `⌈Σt/H⌉` lower bound.
6. **Crunch (S5, S8, S9):** profit-maximising tour heuristic with prerequisite closure, checked against the exact precedence-constrained knapsack IP.
7. **Honesty about estimates:** (i) split the gain into a *scope* part (exclusions, prior knowledge, merged concepts), which doesn't depend on `c_ij`, and a *sequencing* part, which does; (ii) a null test (`c_ij = 0` must give zero sequencing gain); (iii) ±25% one-at-a-time and Monte Carlo sensitivity; (iv) external evidence for the links.
8. **Curriculum insights:** critical path vs total hours (cohort vs solo learner), the three timing gaps, and an optional UFLP for where to teach shared concepts.
9. **Deliverables:** repo, Pages planner (the JS heuristic runs live), LaTeX report, presentation outline.
