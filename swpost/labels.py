"""Label parsing for person/timecode cross-checks."""

from __future__ import annotations

import re

# Uppercase tokens in select labels → canonical person names from brief.
LABEL_PERSON_ALIASES: dict[str, str] = {
    "MORGAN": "Morgan Sibbald",
    "FORREST": "Forrest Blackburn",
    "FOREST": "Forrest Blackburn",
    "JIM": "Jim Leonard",
    "STACY": "Stacy Conté",
    "STACEY": "Stacy Conté",
    "STEPHANIE": "Stephanie Castro",
    "TONY": "Tony Rook",
    "TONI": "Tony Rook",
    "KIKI": "Kiki Redhead",
    "CHI": "Chi Lee",
    "LEE": "Chi Lee",
    "DESTINY": "Destiny Thomas",
    "CAITLIN": "Caitlin Colleary",
    "CATILIN": "Caitlin Colleary",
    "NIKKI": "Nikki Burt",
    "NICOLE": "Nikki Burt",
    "MIRANDA": "Miranda Sinnott-Armstrong",
    "EMMA": "Emma Finestone",
}

_LABEL_RE = re.compile(
    r"^([A-Z][A-Z\s]+?)\s+(\d{1,2}):(\d{2}):(\d{2}):(\d{2})\b"
)


def label_timecode_frame(h: int, m: int, s: int, fr: int) -> int:
    return h * 86400 + m * 1440 + s * 24 + fr


def parse_select_label(label: str) -> tuple[str, int] | None:
    """Return (canonical person, stringout frame) if label matches NAME HH:MM:SS:FF."""
    if not label:
        return None
    m = _LABEL_RE.match(label.strip())
    if not m:
        return None
    raw_name = m.group(1).strip()
    token = raw_name.split()[0]
    person = LABEL_PERSON_ALIASES.get(token)
    if person is None:
        return None
    frame = label_timecode_frame(
        int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
    )
    return person, frame
