"""An author `display:` on a `<dialog>` overrides the UA's closed-dialog hiding.

The user-agent stylesheet hides a closed dialog with `dialog:not([open]) { display: none }`,
and that rule loses to any author rule setting `display` on the same element — a class
selector outranks it. The dialog then paints while closed, and because these are
full-screen sheets and backdrops, "paints while closed" means *covering every screen on
the phone*. It was caught once by opening the capture diffs before approving them, which
is not a mechanism.

So: every `<dialog>` whose class is given a `display` anywhere in the stylesheet must
also restate `:not([open]) { display: none }` for that class. Three do today. This exists
for the fourth, which will be written by someone who has never read this comment.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"
STYLESHEET = WEB / "shell.css"

#: `<dialog ... className="a b" ...>`, across the newlines JSX puts attributes on.
_DIALOG = re.compile(r"<dialog\b[^>]*?className=\"([^\"]+)\"", re.DOTALL)
#: Comments out, so a `display:` quoted in prose is not read as a declaration.
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def dialog_classes() -> set[str]:
    """Every class name that lands on a `<dialog>` element."""

    found: set[str] = set()
    for path in WEB.rglob("*.tsx"):
        if path.name.endswith(".test.tsx"):
            continue
        for match in _DIALOG.finditer(path.read_text(encoding="utf-8")):
            found.update(match.group(1).split())
    return found


class DialogDisplayGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.css = _COMMENT.sub("", STYLESHEET.read_text(encoding="utf-8"))
        self.classes = dialog_classes()

    def test_the_dialogs_are_found_at_all(self) -> None:
        """A regex that matches nothing would pass every assertion below."""

        self.assertIn("tour-backdrop", self.classes)
        self.assertIn("sheet-dialog", self.classes)
        self.assertIn("day-stop-lightbox", self.classes)

    def test_every_dialog_given_a_display_restates_the_closed_rule(self) -> None:
        for name in sorted(self.classes):
            # Any rule whose selector names this class and whose body sets `display`.
            styled = [
                block
                for selector, block in re.findall(
                    r"([^{}]+)\{([^{}]*)\}", self.css
                )
                if re.search(rf"\.{re.escape(name)}\b", selector)
                and re.search(r"(?<![-\w])display\s*:", block)
                # The guard itself sets `display`, and requiring it to be guarded in
                # turn is circular.
                and ":not([open])" not in selector
            ]
            if not styled:
                continue
            guarded = re.search(
                rf"\.{re.escape(name)}[^{{}}]*:not\(\[open\]\)[^{{}}]*\{{[^{{}}]*"
                r"display\s*:\s*none",
                self.css,
            )
            with self.subTest(dialog=name):
                # `assertTrue` rather than `assertRegex`, whose failure message prints
                # the whole 10,000-line stylesheet it did not match.
                self.assertTrue(
                    guarded,
                    f".{name} is a <dialog> given a display, so it needs an explicit"
                    f" `.{name}:not([open]) {{ display: none }}` — an author rule beats"
                    " the user agent's, and the closed sheet paints over the page.",
                )


if __name__ == "__main__":
    unittest.main()
