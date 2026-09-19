"""Static validation of the import graph.

Catches the class of bug that broke v1: importing a name from a module that
does not define it (ClipboardEngine was imported from `core.` while living in
`ui/`). Pure AST work -- no Qt, no imports executed.

Run: python tools/checkmodules.py
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_PACKAGES = ("core", "ui", "tools")


def module_path(dotted: str) -> str | None:
    candidate = os.path.join(ROOT, *dotted.split(".")) + ".py"
    if os.path.isfile(candidate):
        return candidate
    pkg = os.path.join(ROOT, *dotted.split("."), "__init__.py")
    return pkg if os.path.isfile(pkg) else None


def top_level_names(tree: ast.Module) -> set:
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def python_files() -> list:
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in {"venv", ".venv", "__pycache__", ".git", "dist"}]
        out += [os.path.join(dirpath, f) for f in filenames if f.endswith(".py")]
    return sorted(out)


def main() -> int:
    trees, errors, edges = {}, [], {}

    for path in python_files():
        rel = os.path.relpath(path, ROOT)
        try:
            trees[rel] = ast.parse(open(path, encoding="utf-8").read(), rel)
        except SyntaxError as exc:
            errors.append(f"{rel}: syntax error line {exc.lineno}: {exc.msg}")

    exports = {}
    for rel, tree in trees.items():
        dotted = rel[:-3].replace(os.sep, ".").removesuffix(".__init__")
        exports[dotted] = top_level_names(tree)

    for rel, tree in trees.items():
        dotted = rel[:-3].replace(os.sep, ".").removesuffix(".__init__")
        edges[dotted] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith(LOCAL_PACKAGES):
                continue
            edges[dotted].add(node.module)
            if module_path(node.module) is None:
                errors.append(f"{rel}:{node.lineno}: no such module '{node.module}'")
                continue
            available = exports.get(node.module, set())
            for alias in node.names:
                if alias.name != "*" and alias.name not in available:
                    errors.append(
                        f"{rel}:{node.lineno}: '{node.module}' does not define "
                        f"'{alias.name}'"
                    )

    # Cycle detection
    state = {}

    def visit(node: str, stack: list) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            errors.append("import cycle: " + " -> ".join(stack + [node]))
            return
        state[node] = 1
        for dep in sorted(edges.get(node, ())):
            visit(dep, stack + [node])
        state[node] = 2

    for node in sorted(edges):
        visit(node, [])

    print(f"Checked {len(trees)} modules.")
    if errors:
        for e in errors:
            print("  FAIL", e)
        return 1
    print("Import graph is consistent: no missing names, no cycles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
