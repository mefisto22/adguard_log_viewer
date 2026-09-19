"""Tags and categories: the catalogue plus manual assignment to domains."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.categorization.engine import TAG_KINDS
from app.i18n import Message

MANUAL_SOURCE = "manual"


def list_tags(conn: sqlite3.Connection, *, kind: str | None = None) -> list[dict[str, Any]]:
    clauses = "WHERE kind = ?" if kind else ""
    params = (kind,) if kind else ()
    rows = conn.execute(
        "SELECT t.id, t.name, t.kind, t.color, t.description, t.builtin, "
        "       (SELECT COUNT(*) FROM domain_tags dt WHERE dt.tag_id = t.id) AS domain_count "
        f"FROM tags t {clauses} ORDER BY t.kind, t.name COLLATE NOCASE",
        params,
    ).fetchall()
    return [{**dict(row), "builtin": bool(row["builtin"])} for row in rows]


def create_tag(
    conn: sqlite3.Connection,
    *,
    name: str,
    kind: str = "tag",
    color: str = "",
    description: str = "",
) -> int:
    name = name.strip()
    kind = kind.strip().lower()
    if not name:
        raise ValueError(Message("A tag needs a name"))
    if kind not in TAG_KINDS:
        raise ValueError(Message("kind must be one of {kinds}", kinds=", ".join(TAG_KINDS)))

    existing = conn.execute(
        "SELECT id FROM tags WHERE name = ? AND kind = ?", (name, kind)
    ).fetchone()
    if existing:
        # A message per kind rather than one with a ``{kind}`` placeholder: the
        # word has to be translated too, and a language that inflects it needs
        # the whole sentence to itself.
        if kind == "category":
            raise ValueError(Message("A category named {name} already exists", name=repr(name)))
        raise ValueError(Message("A tag named {name} already exists", name=repr(name)))

    cursor = conn.execute(
        "INSERT INTO tags (name, kind, color, description, builtin) VALUES (?, ?, ?, ?, 0)",
        (name, kind, color.strip(), description.strip()),
    )
    return int(cursor.lastrowid or 0)


def update_tag(
    conn: sqlite3.Connection,
    tag_id: int,
    *,
    name: str | None = None,
    color: str | None = None,
    description: str | None = None,
) -> bool:
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        if not name.strip():
            raise ValueError(Message("A tag needs a name"))
        sets.append("name = ?")
        params.append(name.strip())
    if color is not None:
        sets.append("color = ?")
        params.append(color.strip())
    if description is not None:
        sets.append("description = ?")
        params.append(description.strip())
    if not sets:
        return False
    params.append(tag_id)
    cursor = conn.execute(f"UPDATE tags SET {', '.join(sets)} WHERE id = ?", tuple(params))
    return bool(cursor.rowcount)


def delete_tag(conn: sqlite3.Connection, tag_id: int) -> bool:
    row = conn.execute("SELECT builtin FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if row is None:
        return False
    if row["builtin"]:
        raise ValueError(
            Message("Built-in tags cannot be deleted. Disable the rule that applies it instead.")
        )
    cursor = conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    return bool(cursor.rowcount)


def set_domain_tags(
    conn: sqlite3.Connection, domain_id: int, tag_ids: list[int], *, replace: bool = True
) -> int:
    """Attach tags to a domain by hand.

    Manual links survive re-classification; automatic ones are replaced whenever
    the rule set changes.
    """
    if replace:
        conn.execute(
            "DELETE FROM domain_tags WHERE domain_id = ? AND source = ?",
            (domain_id, MANUAL_SOURCE),
        )
    if not tag_ids:
        return 0
    conn.executemany(
        "INSERT INTO domain_tags (domain_id, tag_id, source) VALUES (?, ?, ?) "
        "ON CONFLICT(domain_id, tag_id) DO UPDATE SET source = excluded.source",
        [(domain_id, tag_id, MANUAL_SOURCE) for tag_id in tag_ids],
    )
    return len(tag_ids)


def remove_domain_tag(conn: sqlite3.Connection, domain_id: int, tag_id: int) -> bool:
    cursor = conn.execute(
        "DELETE FROM domain_tags WHERE domain_id = ? AND tag_id = ?", (domain_id, tag_id)
    )
    return bool(cursor.rowcount)
