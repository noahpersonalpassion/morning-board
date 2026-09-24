"""Every module must import, including the ones nothing else imports.

This exists because of a real failure. `board/panels/deadlines.py` was
shipped with a duplicated keyword argument — a hard SyntaxError — and the
whole suite passed, because no test imported it. It is reached only through
`build.py`, which the tests do not run, so a broken module sat in a green
build until someone ran the real thing.

Two smaller lessons are baked in here as well:

  `ast.parse` is not a syntax check. It accepts duplicate keyword arguments,
  which are rejected later, at compile. Anything claiming to verify a file
  parses must use `compile()`.

  Python versions disagree about when they notice. The file that broke was
  accepted by 3.11 and refused by 3.14, so "it worked on my machine" was
  true and useless. Importing everything, everywhere, is the check that does
  not depend on which interpreter is asking.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PACKAGES = ("board", "notice")


def every_module() -> list[str]:
    """Every importable module, which is not quite every module.

    A package's `__main__` is excluded on purpose: importing it runs it,
    because running is the whole job of the file behind `python -m notice`.
    `notice/__main__.py` is three lines ending in `raise SystemExit(main())`
    and it is correct. The compile check below still covers it, so a syntax
    error there cannot hide — only its side effect is skipped.
    """
    names = []
    for pkg_name in PACKAGES:
        pkg = importlib.import_module(pkg_name)
        names.append(pkg_name)
        for mod in pkgutil.walk_packages(pkg.__path__, pkg_name + "."):
            if mod.name.rsplit(".", 1)[-1] == "__main__":
                continue
            names.append(mod.name)
    return sorted(names)


class TestEverythingImports(unittest.TestCase):
    def test_every_module_imports(self):
        failed = []
        for name in every_module():
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001 — report all, not the first
                failed.append(f"{name}: {type(exc).__name__}: {exc}")
        self.assertEqual(failed, [], "modules that would not import:\n  "
                                     + "\n  ".join(failed))

    def test_the_orchestrator_imports(self):
        """build.py is not in a package and is how the whole thing runs."""
        import build
        self.assertTrue(callable(build.main))

    def test_every_source_file_compiles(self):
        """compile(), not ast.parse() — the distinction that caused this."""
        bad = []
        for path in sorted(ROOT.glob("*.py")) + sorted(
                p for pkg in PACKAGES for p in (ROOT / pkg).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except SyntaxError as exc:
                bad.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
        self.assertEqual(bad, [], "files that will not compile:\n  "
                                  + "\n  ".join(bad))

    def test_the_walk_actually_found_the_modules(self):
        """A test that silently checks nothing is worse than no test."""
        names = every_module()
        self.assertIn("board.panels.deadlines", names)
        self.assertIn("board.render", names)
        self.assertIn("notice.delta", names)
        self.assertGreater(len(names), 15, names)


if __name__ == "__main__":
    unittest.main()
