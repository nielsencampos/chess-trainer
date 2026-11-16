"""What is left of the one-time seed of `openings/` from the catalog (2026-11-07).

The seed wrote flat `openings/<family>.json` files; they have since been reorganized into
groups, subgroups and languages, so it could not reproduce them, and it was removed in #59. Two
helpers stay: `line_id_of`, the id rule of the seeded lines, and `render`, the JSON layout every
opening file keeps.
"""

import hashlib
import json
import re


def line_id_of(pgn: str) -> str:
    """A line id, for seeding only: the id is then stored and stays fixed, even if extended.

    Args:
        pgn (str): The line's catalog PGN.

    Returns:
        str: `line-` and 16 hex digits of its SHA-256.
    """
    return f"line-{hashlib.sha256(pgn.encode()).hexdigest()[:16]}"


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
