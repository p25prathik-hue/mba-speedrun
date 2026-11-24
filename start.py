"""MBA Speedrun: the easy way in.

Double-click START_HERE_Windows.bat (Windows) or run `bash start_mac_linux.sh`
(Mac/Linux); they set things up once and then open this menu. You can also run:

    python start.py              # menu
    python start.py planner      # open the roadmap planner website (no install needed)
    python start.py roadmap      # make a day-by-day roadmap (asks a few questions)
    python start.py crunch       # best topics for a fixed number of hours
    python start.py reproduce    # re-run every number and figure in the report
    python start.py test         # run the tests

All hours are estimates (see docs/assumptions.md), not measured study times.
"""
from __future__ import annotations

import datetime as _dt
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

SITE = "https://p25prathik-hue.github.io/mba-speedrun/"
OUT = ROOT / "my_roadmaps"


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        ans = input(f"{prompt}{hint}: ").strip()
    except EOFError:
        ans = ""
    return ans or default


def ask_float(prompt: str, default: float, lo: float, hi: float) -> float:
    while True:
        s = ask(prompt, f"{default:g}")
        try:
            v = float(s)
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(f"  Please type a number between {lo:g} and {hi:g}.")


def ask_areas(prompt: str, names, taken):
    from speedrun.easy import match_areas

    while True:
        s = ask(prompt + " (numbers or names, comma-separated; Enter for none)")
        try:
            got = match_areas(s, names)
        except ValueError as e:
            print("  " + str(e))
            continue
        clash = [a for a in got if a in taken]
        if clash:
            print("  Already chosen above: " + ", ".join(clash) + ". Pick each area once.")
            continue
        return got


def ask_topics(prompt: str, web: str):
    from speedrun.easy import match_topics, topic_list

    while True:
        s = ask(prompt + " (IDs like QNT01, FIN06; ? to list them; Enter for none)")
        if s.strip() == "?":
            cur = None
            for t in sorted(topic_list(web), key=lambda t: (t["area"], t["id"])):
                if t["area"] != cur:
                    cur = t["area"]
                    print(f"\n  {cur}")
                print(f"    {t['id']:<6} {t['topic']}")
            print()
            continue
        try:
            return match_topics(s, web)
        except ValueError as e:
            print("  " + str(e))


def has_numba() -> bool:
    try:
        import numba  # noqa: F401
        return True
    except Exception:
        return False


def open_file(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        print(f"  Could not open it automatically ({e}). It is at {path}")


# ---------------------------------------------------------------- actions
def planner() -> None:
    page = ROOT / "docs" / "index.html"
    print("Opening the roadmap planner in your browser (it runs offline from this folder).")
    print(f"Online version, once GitHub Pages is on: {SITE}")
    webbrowser.open(page.as_uri())


def _profile_questions():
    from speedrun.easy import WEBS, areas

    print("\nWhich topic web?")
    keys = list(WEBS)
    for k, key in enumerate(keys, 1):
        print(f"  {k}  {WEBS[key][1]}")
    web = keys[int(ask_float("Choose", 1, 1, len(keys))) - 1]
    ar = areas(web)
    names = [a["area"] for a in ar]
    print("\nSubject areas (topics, estimated hours):")
    for k, a in enumerate(ar, 1):
        print(f"  {k:>2}  {a['area']:<26} {a['topics']:>3} topics  {a['hours']:6.1f} h")
    print()
    known = ask_areas("Areas you already know well, to leave out", names, [])
    half = ask_areas("Areas you half know, counted at half time", names, known)
    skip = ask_areas("Areas you want to skip", names, known + half)
    ktop = ask_topics("Single topics you already know", web)
    hours = ask_float("Study hours per day", 6, 0.5, 16)
    return dict(web=web, hours_per_day=hours, known_areas=known, half_known_areas=half,
                skip_areas=skip, known_topics=ktop)


def _speed_note(web: str) -> None:
    if web == "iima":
        if has_numba():
            print("Working... (about 20-40 seconds for the full web)")
        else:
            print("Working... (about 1-2 minutes for the full web; install numba to make it faster)")
    else:
        print("Working...")


def _finish(res, stem: str) -> None:
    from speedrun.easy import day_plan_text, save_csv, summary

    print("\n" + summary(res))
    if not res["rows"]:
        return
    print("\n" + day_plan_text(res, max_days=7))
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
    path = save_csv(res, str(OUT / f"{stem}_{stamp}.csv"))
    print(f"\nSaved the full day-by-day plan to {path}")
    if ask("Open it now? (y/n)", "y").lower().startswith("y"):
        open_file(Path(path))


def roadmap() -> None:
    from speedrun.easy import make_roadmap

    print("\nMAKE MY ROADMAP: every topic you need, in the best order found, split into days.")
    q = _profile_questions()
    _speed_note(q["web"])
    t0 = time.time()
    res = make_roadmap(**q)
    print(f"Done in {time.time() - t0:.0f} s.")
    _finish(res, "roadmap")


def crunch() -> None:
    from speedrun.easy import make_crunch

    print("\nEXAM CRUNCH: the most valuable topics (with their prerequisites) that fit your hours.")
    q = _profile_questions()
    budget = ask_float("Total hours you have", 40, 1, 2000)
    print("Working... (usually under a minute)")
    t0 = time.time()
    res = make_crunch(budget, **q)
    print(f"Done in {time.time() - t0:.0f} s.")
    _finish(res, "crunch")


REPRODUCE = [
    ["scripts/kit/audit.py"],
    ["scripts/integrate_external.py", "--data", "data/iima", "--out", "results/iima/external_agreement.json"],
    ["scripts/apply_step1_changes.py", "--data", "data/iima", "--changes", "data/external/step1_changes_iima.csv"],
    ["run.py", "profiles", "--data", "data/iima", "--out", "results/iima"],
    ["run.py", "sensitivity", "--data", "data/iima", "--draws", "60", "--restarts", "0",
     "--out", "results/iima/sensitivity.json"],
    ["run.py", "profiles", "--data", "data/sample", "--out", "results/sample"],
    ["run.py", "sensitivity", "--data", "data/sample", "--draws", "200", "--restarts", "2",
     "--out", "results/sample/sensitivity.json"],
    ["scripts/scale_experiment.py", "--data", "data/sample", "--out", "results/scale.json"],
    ["scripts/make_figures.py"],
    ["run.py", "web", "--data", "data/iima", "--out", "docs/data/web.json"],
    ["run.py", "web", "--data", "data/sample", "--out", "docs/data/pilot.json"],
    ["scripts/kit/layout.py"],
]


def reproduce() -> None:
    print("\nREPRODUCE THE REPORT: re-runs every experiment, figure and the website data.")
    print("This overwrites results/, report/figures/ and docs/data/ with fresh copies.")
    if not has_numba():
        print("numba is not installed, so this will be slow. Install it with: python -m pip install numba")
    if not ask("Go ahead? (y/n)", "n").lower().startswith("y"):
        return
    t0 = time.time()
    for k, cmd in enumerate(REPRODUCE, 1):
        print(f"\n[{k}/{len(REPRODUCE)}] python {' '.join(cmd)}")
        r = subprocess.run([sys.executable] + cmd)
        if r.returncode:
            print(f"Step failed (exit code {r.returncode}). Stopping here.")
            return
    if shutil.which("latexmk"):
        print("\n[report] latexmk -pdf main.tex")
        subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "main.tex"], cwd=ROOT / "report")
    else:
        print("\nLaTeX is not installed, so the PDF was not rebuilt. Upload report/ to Overleaf to compile it.")
    print(f"\nAll done in {(time.time() - t0) / 60:.1f} minutes.")


def test() -> None:
    print("\nRUNNING THE TESTS")
    subprocess.run([sys.executable, "-m", "pytest", "-q"])


ACTIONS = {"planner": planner, "roadmap": roadmap, "crunch": crunch, "reproduce": reproduce, "test": test}
MENU = [
    ("planner", "Open the roadmap planner website (in your browser, nothing else needed)"),
    ("roadmap", "Make my study roadmap here (answer a few questions, get a day-by-day plan)"),
    ("crunch", "Exam crunch: best topics for a fixed number of hours"),
    ("reproduce", "Reproduce every number and figure in the report"),
    ("test", "Run the tests"),
]


def menu() -> None:
    while True:
        print("\n" + "=" * 64)
        print(" MBA Speedrun: personalised study roadmaps for the IIMA PGP core")
        print(" (all hours are estimates)")
        print("=" * 64)
        for k, (_, label) in enumerate(MENU, 1):
            print(f"  {k}  {label}")
        print("  0  Quit")
        c = ask("\nChoose", "1")
        if c in ("0", "q", "quit", "exit"):
            return
        if c.isdigit() and 1 <= int(c) <= len(MENU):
            run(MENU[int(c) - 1][0])
        else:
            print("  Please type a number from the list.")


def run(name: str) -> None:
    try:
        ACTIONS[name]()
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:  # keep the window open with a readable message
        print(f"\nSomething went wrong: {type(e).__name__}: {e}")
        print("Please report it with this message (see CONTRIBUTING.md).")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] not in ACTIONS:
            print("Usage: python start.py [" + "|".join(ACTIONS) + "]")
            sys.exit(2)
        run(sys.argv[1])
    else:
        try:
            menu()
        except KeyboardInterrupt:
            print()
