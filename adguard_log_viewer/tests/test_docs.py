"""The links in the documentation, and where they actually point.

Two faults motivated this file, both of the same kind — a link that looked
perfectly fine and went somewhere else:

* ``config.yaml`` and ``build.yaml`` carried a different owner and repository
  name than the real remote, so the app card in Home Assistant offered an
  "open the … page" link into somebody else's account — that one is guarded in
  ``test_packaging.py``, next to the other checks that shell out to git;
* renaming "add-on" to "app" in the prose rewrote a URL as well, turning
  ``developers.home-assistant.io/docs/add-ons/configuration`` into a path that
  does not exist.

Nothing here reaches the network: a link check that needs the internet gets
switched off the first time it flakes. These are invariants of the text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ADDON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ADDON_ROOT.parent

#: The repo root is not part of the Docker build context, so inside the image
#: only the app's own documents exist.
DOCUMENTS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "ARCHITECTURE.md",
    ADDON_ROOT / "DOCS.md",
    ADDON_ROOT / "CHANGELOG.md",
]

INLINE_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
ANY_URL = re.compile(r"https?://[^\s)>\"'`]+")


def present() -> list[Path]:
    return [path for path in DOCUMENTS if path.is_file()]


def heading_slug(heading: str) -> str:
    """GitHub's anchor rules, as far as these documents exercise them."""
    text = re.sub(r"`([^`]*)`", r"\1", heading.strip())
    text = re.sub(r"\*+([^*]*)\*+", r"\1", text).lower()
    text = "".join(c for c in text if c.isalnum() or c in " -_")
    return text.strip().replace(" ", "-")


def anchors_of(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        base = heading_slug(line.lstrip("#"))
        index = seen.get(base, 0)
        seen[base] = index + 1
        # GitHub disambiguates a repeated heading with -1, -2, … which is what
        # keeps the two language halves of a bilingual document addressable.
        found.add(base if index == 0 else f"{base}-{index}")
    return found


class TestDocumentLinks:
    @pytest.mark.parametrize("document", present(), ids=lambda p: p.name)
    def test_relative_links_resolve(self, document: Path) -> None:
        broken = []
        for target in INLINE_LINK.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            file_part, _, anchor = target.partition("#")
            destination = (document.parent / file_part).resolve() if file_part else document
            if not destination.exists():
                broken.append(f"{target} (no such file)")
                continue
            if anchor and destination.suffix == ".md" and anchor not in anchors_of(destination):
                broken.append(f"{target} (no such heading)")
        assert not broken, f"{document.name}: {broken}"

    @pytest.mark.parametrize("document", present(), ids=lambda p: p.name)
    def test_urls_are_ascii(self, document: Path) -> None:
        """A URL with an accented character is a URL something rewrote.

        The documents are bilingual, so a blanket search-and-replace over the
        prose can reach inside a link without anyone noticing.
        """
        mangled = [
            url
            for url in ANY_URL.findall(document.read_text(encoding="utf-8"))
            if not url.isascii()
        ]
        assert not mangled, f"{document.name}: {mangled}"
