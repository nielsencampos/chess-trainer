"""One-time seed: wrote flat openings/<family>.json from the catalog. Those files are ours now.

They have since been reorganized into groups, subgroups and three languages, so running this
again with --force would not reproduce them. It stays for line_id_of and render.

Usage: uv run python -m catalog.generate_openings [--force]

Refuses to overwrite existing files, because they may have been edited since.
"""

import hashlib
import io
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import chess.pgn

from catalog.loader import CatalogEntry, load_catalog, source_commit

OPENINGS_DIR = Path(__file__).parent.parent / "openings"
LICENSE = "CC0-1.0"


def family_of(name: str) -> str:
    """The family part of a catalog name, before the colon.

    Args:
        name (str): A catalog name, such as `Caro-Kann Defense: Advance Variation`.

    Returns:
        str: The family, such as `Caro-Kann Defense`.
    """
    return name.split(":", 1)[0].strip()


def slugify(text: str) -> str:
    """A lowercase ASCII id made of letters, digits and hyphens.

    Args:
        text (str): Any text.

    Returns:
        str: The slug, such as `caro-kann-defense`.
    """
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def line_id_of(pgn: str) -> str:
    """A line id, for seeding only: the id is then stored and stays fixed, even if extended.

    Args:
        pgn (str): The line's catalog PGN.

    Returns:
        str: `line-` and 16 hex digits of its SHA-256.
    """
    return f"line-{hashlib.sha256(pgn.encode()).hexdigest()[:16]}"


def _moves(pgn: str) -> list[str]:
    """The SAN moves of a catalog PGN.

    Args:
        pgn (str): The PGN movetext.

    Returns:
        list[str]: The moves.

    Raises:
        ValueError: The PGN is invalid.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None or game.errors:
        raise ValueError(f"invalid catalog PGN: {pgn!r}")
    board = game.board()
    sans = []
    for move in game.mainline_moves():
        sans.append(board.san(move))
        board.push(move)
    return sans


def render(document: dict) -> str:
    """Indented JSON with each move list on one line, so diffs stay readable.

    Args:
        document (dict): An opening file's content.

    Returns:
        str: The JSON text.
    """
    text = json.dumps(document, ensure_ascii=False, indent=2)
    return re.sub(
        r'"moves": \[\s*(.*?)\s*\]',
        lambda match: '"moves": [' + re.sub(r",\s+", ", ", match.group(1)) + "]",
        text,
        flags=re.DOTALL,
    )


def build_documents(entries: list[CatalogEntry], commit: str) -> dict[str, dict]:
    """Groups the catalog's entries into one opening file per family.

    Args:
        entries (list[CatalogEntry]): The catalog.
        commit (str): The catalog commit, for `source`.

    Returns:
        dict[str, dict]: Family id -> file content.

    Raises:
        ValueError: Two families share an id.
    """
    families: dict[str, list[CatalogEntry]] = defaultdict(list)
    for entry in entries:
        families[family_of(entry.name)].append(entry)

    documents: dict[str, dict] = {}
    source = f"lichess-org/chess-openings@{commit[:7]} ({LICENSE})"
    for family, members in families.items():
        family_id = slugify(family)
        if family_id in documents:
            raise ValueError(f"two families share the id {family_id!r}")
        documents[family_id] = {
            "id": family_id,
            "names": {"en": family},
            "lines": [
                {
                    "id": line_id_of(entry.pgn),
                    "names": {
                        "en": entry.name.split(":", 1)[1].strip()
                        if ":" in entry.name
                        else entry.name
                    },
                    "eco": entry.eco,
                    "opening": entry.name,
                    "moves": _moves(entry.pgn),
                    "source": source,
                }
                for entry in sorted(members, key=lambda item: item.pgn)
            ],
        }
    return documents


def main(force: bool) -> int:
    """Writes the seed files, refusing to overwrite existing ones without `force`.

    Args:
        force (bool): Overwrite existing files.

    Returns:
        int: The exit code.
    """
    OPENINGS_DIR.mkdir(exist_ok=True)
    if not force and any(OPENINGS_DIR.glob("*.json")):
        print(f"{OPENINGS_DIR} already has files: use --force to overwrite them", file=sys.stderr)
        return 1
    documents = build_documents(load_catalog(), source_commit())
    for family_id, document in documents.items():
        (OPENINGS_DIR / f"{family_id}.json").write_text(render(document) + "\n", encoding="utf-8")
    print(f"wrote {len(documents)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main("--force" in sys.argv[1:]))
