"""Parse the micro-topic web, audit it, and write clean data files + JSON for the explorer."""
import argparse, csv, json, os, re, itertools, collections
import networkx as nx

# Paths are relative to the repository root (run from anywhere):
#   python scripts/kit/audit.py [--src data/iima/topics_source.txt] [--out data/iima]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ap = argparse.ArgumentParser(description=__doc__)
_ap.add_argument("--src", default=os.path.join(ROOT, "data", "iima", "topics_source.txt"))
_ap.add_argument("--out", default=os.path.join(ROOT, "data", "iima"))
_args = _ap.parse_args()
SRC = _args.src
OUT = _args.out
SIZE_MIN = {"S": 45, "M": 90, "L": 150}
DOMAINS = {
    "QNT": "Quant & Analytics", "CMP": "Quant & Analytics", "ACC": "Accounting", "FIN": "Finance",
    "ECO": "Economics", "MKT": "Marketing", "OPS": "Operations", "OBH": "OB & HR", "STR": "Strategy",
    "RES": "Research Methods", "LAW": "Law", "ITD": "IT & Digital", "ENV": "Ethics, Society & Env",
    "COM": "Communication",
}
# Official IIMA first-year compulsory courses (iima.ac.in, tentative list)
OFFICIAL = {
    "FM": (1, "Financial Markets"), "FRA": (1, "Financial Reporting and Analysis"), "HRM-I": (1, "Human Resource Management-I"),
    "ID": (1, "Individual Dynamics"), "LAB": (1, "Legal Aspects of Business"), "MGRCMN": (1, "Managerial Communication"),
    "MGRCMP": (1, "Managerial Computing"), "MKT-I": (1, "Marketing-I"), "ME": (1, "Microeconomics"),
    "OM-I": (1, "Operations Management-I"), "QM-1a": (1, "Quantitative Methods-IA"), "QM-1b": (1, "Quantitative Methods-IB"),
    "CCS": (2, "Costing and Control Systems"), "HRM-II": (2, "Human Resource Management-II"),
    "IGP": (2, "Interpersonal and Group Processes"), "MEP": (2, "Macroeconomics and Policy"), "MKT-II": (2, "Marketing-II"),
    "OM-II": (2, "Operations Management-II"), "PCE": (2, "Personal and Corporate Ethics"), "QM-2": (2, "Quantitative Methods-2"),
    "SCEB": (2, "Social and Cultural Environment of Business"), "TBIT": (2, "Transforming Business through IT"),
    "WIP": (2, "Workshop on Interviews and Presentations"), "WAC-I": (2, "Written Analysis and Communication-I"),
    "BRM": (3, "Business Research Methods"), "BES": (3, "Business, Environment and Sustainability"),
    "CF": (3, "Corporate Finance"), "GSP": (3, "Government Systems and Policy Process"), "IEB": (3, "Internet-Enabled Businesses"),
    "MKT-III": (3, "Marketing-III"), "ODY": (3, "Organizational Dynamics"), "SM": (3, "Strategic Management"),
    "WAC-II": (3, "Written Analysis and Communication-II"), "OM-III": (3, "Operations Management-III"),
    "SOM": (3, "Service Operations Management"), "SHRM": (3, "Strategic HRM (flexi-core)"), "TCM": (3, "Talent and Competency Mgmt (flexi-core)"),
}

topics, raw_edges = {}, []   # raw edge: (from, to, kind, group)
for line in open(SRC, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = [x.strip() for x in re.split(r"\s\|\s?", line + " ")]
    tid, name, courses, term, size, value, pre = parts
    courses = courses.split(";")
    topics[tid] = dict(id=tid, name=name, courses=courses, primary=courses[0], domain=DOMAINS[tid[:3]],
                       term=min([int(term)] + [OFFICIAL[c][0] for c in courses if c != "FM"]), size=size, minutes=SIZE_MIN[size], value=int(value))
    for k, tok in enumerate([t.strip() for t in pre.split(",") if t.strip()]):
        if tok.startswith("("):
            gid = f"{tid}-OR{k}"
            for m in tok.strip("()").split("|"):
                raw_edges.append((m.strip(), tid, "or", gid))
        elif tok.startswith("~"):
            raw_edges.append((tok[1:], tid, "soft", ""))
        else:
            raw_edges.append((tok, tid, "and", ""))

# ---------- integrity ----------
missing = [(u, v) for u, v, *_ in raw_edges if u not in topics]
assert not missing, f"unknown prerequisite ids: {missing}"
unknown_courses = sorted({c for t in topics.values() for c in t["courses"] if c not in OFFICIAL})
assert not unknown_courses, unknown_courses

G = nx.DiGraph()
G.add_nodes_from(topics)
for u, v, kind, gid in raw_edges:
    G.add_edge(u, v, kind=kind, group=gid)
cycles = list(nx.simple_cycles(G))
assert not cycles, f"cycles: {cycles[:5]}"

# ---------- redundancy: transitive reduction ----------
# An AND/soft edge u->v is redundant if v is still reachable from u through the other AND edges.
H = nx.DiGraph([(u, v) for u, v, k, _ in raw_edges if k == "and"])
H.add_nodes_from(topics)
redundant = []
for u, v, kind, gid in raw_edges:
    if kind == "or":
        continue
    had = H.has_edge(u, v)
    if had:
        H.remove_edge(u, v)
    if nx.has_path(H, u, v):
        path = nx.shortest_path(H, u, v)
        redundant.append(dict(from_id=u, to_id=v, kind=kind, implied_via=" > ".join(path)))
    elif had:
        H.add_edge(u, v)
red_set = {(r["from_id"], r["to_id"]) for r in redundant}
edges = [dict(from_id=u, to_id=v, kind=k, or_group=g) for u, v, k, g in raw_edges if (u, v) not in red_set]

# Clean graph (all kept edges) for structural metrics
C = nx.DiGraph(); C.add_nodes_from(topics)
for e in edges:
    C.add_edge(e["from_id"], e["to_id"], kind=e["kind"])
assert nx.is_directed_acyclic_graph(C)

# ---------- depth / layering (hard + OR edges) ----------
hard = nx.DiGraph([(e["from_id"], e["to_id"]) for e in edges if e["kind"] != "soft"]); hard.add_nodes_from(topics)
depth = {}
for n in nx.topological_sort(hard):
    preds = list(hard.predecessors(n))
    depth[n] = 0 if not preds else 1 + max(depth[p] for p in preds)

# Prerequisite closure (all ancestors via AND edges; OR groups take the cheaper branch's closure)
def closure(n, memo={}):
    if n in memo:
        return memo[n]
    anc = set()
    groups = collections.defaultdict(list)
    for e in edges:
        if e["to_id"] != n or e["kind"] == "soft":
            continue
        if e["kind"] == "and":
            anc |= {e["from_id"]} | closure(e["from_id"])
        else:
            groups[e["or_group"]].append(e["from_id"])
    for g, members in groups.items():
        best = min((({m} | closure(m)) for m in members), key=lambda s: sum(topics[x]["minutes"] for x in s))
        anc |= best
    memo[n] = anc
    return anc

for t in topics.values():
    anc = closure(t["id"])
    t["depth"] = depth[t["id"]]
    t["n_prereq_closure"] = len(anc)
    t["closure_minutes"] = sum(topics[a]["minutes"] for a in anc) + t["minutes"]
    t["n_unlocks"] = len(nx.descendants(hard, t["id"]))

# ---------- curriculum timing gaps ----------
for t in topics.values():
    t["first_course"] = min(t["courses"], key=lambda c: t["term"] if c == "FM" else OFFICIAL[c][0])
    if "FM" in t["courses"] and t["term"] == t["term"]:
        t["first_course"] = next((c for c in t["courses"] if (t["term"] if c == "FM" else OFFICIAL[c][0]) == t["term"]), t["primary"])
or_min = collections.defaultdict(lambda: 9)
for e in edges:
    if e["kind"] == "or":
        or_min[e["or_group"]] = min(or_min[e["or_group"]], topics[e["from_id"]]["term"])
gaps = []
for e in edges:
    u, v = topics[e["from_id"]], topics[e["to_id"]]
    if e["kind"] == "or" and or_min[e["or_group"]] <= v["term"]:
        continue  # another OR branch is available in time
    if u["term"] > v["term"]:
        gaps.append(dict(prereq=u["id"], prereq_name=u["name"], prereq_course=u["first_course"], prereq_term=u["term"],
                         topic=v["id"], topic_name=v["name"], topic_course=v["first_course"], topic_term=v["term"], kind=e["kind"]))

# ---------- overlaps (merged concepts taught in >1 course) ----------
overlaps = [dict(id=t["id"], name=t["name"], courses=", ".join(t["courses"])) for t in topics.values() if len(t["courses"]) > 1]

# ---------- near-duplicate name screen ----------
STOP = set("and the of a an in for to vs with its basics model models theory theories analysis management".split())
def toks(s):
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) > 2}
near = []
for a, b in itertools.combinations(topics.values(), 2):
    ta, tb = toks(a["name"]), toks(b["name"])
    if ta and tb:
        j = len(ta & tb) / len(ta | tb)
        if j >= 0.25:
            near.append((round(j, 2), a["id"], a["name"], b["id"], b["name"]))
near.sort(reverse=True)

# ---------- structure ----------
sources = [n for n in topics if hard.in_degree(n) == 0]
sinks = [n for n in topics if C.out_degree(n) == 0]
isolated = [n for n in topics if C.degree(n) == 0]
crit = nx.dag_longest_path(hard, weight=None)
cross = sum(1 for e in edges if topics[e["from_id"]]["domain"] != topics[e["to_id"]]["domain"])
cov = collections.Counter(c for t in topics.values() for c in t["courses"])
prim = collections.Counter(t["primary"] for t in topics.values())
course_rows = [dict(code=c, name=n, term=tm, primary_topics=prim.get(c, 0), tagged_topics=cov.get(c, 0)) for c, (tm, n) in OFFICIAL.items()]

summary = dict(
    n_topics=len(topics), n_edges=len(edges), n_and=sum(e["kind"] == "and" for e in edges),
    n_or_edges=sum(e["kind"] == "or" for e in edges), n_or_groups=len({e["or_group"] for e in edges if e["or_group"]}),
    n_soft=sum(e["kind"] == "soft" for e in edges), n_redundant_removed=len(redundant), n_gaps=len(gaps),
    n_overlaps=len(overlaps), n_sources=len(sources), n_sinks=len(sinks), n_isolated=len(isolated),
    cross_domain_edges=cross, max_depth=max(depth.values()), critical_chain=crit,
    total_hours=round(sum(t["minutes"] for t in topics.values()) / 60, 1),
)

# ---------- write files ----------
os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/topics.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "name", "domain", "primary_course", "all_courses", "term", "size", "base_minutes", "value_1to5", "depth", "n_prereqs_total", "path_minutes_incl_prereqs"])
    for t in topics.values():
        w.writerow([t["id"], t["name"], t["domain"], t["primary"], ";".join(t["courses"]), t["term"], t["size"], t["minutes"], t["value"], t["depth"], t["n_prereq_closure"], t["closure_minutes"]])
with open(f"{OUT}/prereqs.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["from_id", "to_id", "type", "or_group"])
    for e in edges:
        w.writerow([e["from_id"], e["to_id"], {"and": "AND", "or": "OR", "soft": "SOFT"}[e["kind"]], e["or_group"]])
with open(f"{OUT}/redundant_edges_removed.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["from_id", "to_id", "kind", "implied_via"]); w.writeheader(); w.writerows(redundant)

json.dump(dict(topics=list(topics.values()), edges=edges, redundant=redundant, gaps=gaps, overlaps=overlaps,
               near=near, sources=sources, sinks=sinks, isolated=isolated, courses=course_rows, summary=summary),
          open(f"{OUT}/kit_web.json", "w"), indent=0)

print(json.dumps(summary, indent=1))
print("\nREDUNDANT:"); [print(" ", r) for r in redundant]
print("\nGAPS:"); [print(f"  {g['prereq']} ({g['prereq_course']} T{g['prereq_term']}) -> {g['topic']} {g['topic_name']} ({g['topic_course']} T{g['topic_term']}) [{g['kind']}]") for g in gaps]
print("\nNEAR-DUPLICATE NAMES:"); [print(" ", n) for n in near]
print("\nISOLATED:", isolated)
print("\nSOURCES:", sources)
print("\nCOURSES with 0 primary topics:", [c["code"] for c in course_rows if c["primary_topics"] == 0])
print("\nTop closures:", sorted(((t["n_prereq_closure"], t["id"], t["name"]) for t in topics.values()), reverse=True)[:8])
