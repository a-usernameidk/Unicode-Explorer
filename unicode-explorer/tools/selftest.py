"""Headless check of the search engine. Run: python tools/selftest.py

Needs no Qt and no network -- handy for verifying the core works before
worrying about the GUI.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.index import UCD_VERSION, shared_index

CASES = [
    ("check mark", "\u2713"), ("tick", "\u2713"), ("U+2713", "\u2713"),
    ("1f600", "\U0001F600"), ("\u2192", "\u2192"), ("shrug", "\U0001F937"),
    ("->", "\u2192"), ("euro", "\u20AC"), ("pi", "\u03C0"), ("nbsp", "\u00A0"),
    ("zwj", "\u200D"), ("...", "\u2026"), ("black star", "\u2605"),
    ("infinity", "\u221E"), ("degree sign", "\u00B0"), ("bullet", "\u2022"),
]

def main() -> int:
    t0 = time.time()
    ix = shared_index()
    print(f"Indexed {len(ix):,} characters in {time.time()-t0:.2f}s (UCD {UCD_VERSION})")
    print(f"{len(ix.blocks)} blocks\n")

    failures, slowest = 0, 0.0
    for query, expected in CASES:
        t = time.time()
        results = ix.search(query, limit=5)
        ms = (time.time() - t) * 1000
        slowest = max(slowest, ms)
        chars = [c.char for c in results]
        ok = expected in chars
        rank = chars.index(expected) + 1 if ok else "-"
        failures += not ok
        print(f"  {'ok ' if ok else 'FAIL'} {query!r:14} -> {expected} at rank {rank:<3} ({ms:.1f}ms)")

    assert ix.search("qqzzxxyy") == [], "nonsense query should return nothing"
    print(f"\nslowest query: {slowest:.1f}ms")
    failures += check_packaging()
    print("\nFAILURES: %d" % failures if failures else "\nAll checks passed.")
    return 1 if failures else 0



def check_packaging() -> int:
    """Confirm the exporter never ships a virtual environment."""
    import tempfile, shutil
    from core.packager import collect_files

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with tempfile.TemporaryDirectory() as tmp:
        clone = os.path.join(tmp, "proj")
        shutil.copytree(root, clone, ignore=shutil.ignore_patterns(
            "venv", ".venv", "__pycache__", ".git", "dist"))
        # Plant the artefacts a real checkout would have.
        os.makedirs(os.path.join(clone, "venv", "Scripts"), exist_ok=True)
        os.makedirs(os.path.join(clone, "__pycache__"), exist_ok=True)
        open(os.path.join(clone, "venv", "pyvenv.cfg"), "w").close()
        open(os.path.join(clone, "venv", "Scripts", "python.exe"), "w").close()
        open(os.path.join(clone, "__pycache__", "x.cpython-312.pyc"), "w").close()

        included, skipped = collect_files(clone)
        leaked = [f for f in included
                  if "venv" in f or "__pycache__" in f or f.endswith(".zip")]
        print(f"\nPackaging: {len(included)} included, {len(skipped)} excluded")
        if leaked:
            print("  FAIL leaked into package:", leaked)
            return 1
        print("  ok  no venv / cache / archive artefacts included")
        return 0

if __name__ == "__main__":
    sys.exit(main())
