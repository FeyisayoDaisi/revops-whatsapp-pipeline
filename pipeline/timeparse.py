"""
Turn the way people write deadlines in a chat into a datetime.

Conventions (also in docs/COMMITMENT_RULES.md):
  - a weekday means the NEXT one after the message date ("Monday" said on a Monday = next Monday)
  - a day with no time is due 17:00 that day
  - morning = 09:00, afternoon = 14:00, evening = 17:00, "first thing" = 09:00
  - "next week" = next Monday 10:00; "end of the week" / "weekend" = this Friday 17:00
  - a bare hour with no am/pm: 7 to 11 is morning, 12 is noon, 1 to 6 is afternoon
Returns None when there is no usable time reference. That is deliberate: a commitment
without a date is logged as an activity, not turned into a task with a guessed date.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

DAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6}
DAY_RE = re.compile(r"\b(" + "|".join(sorted(DAYS, key=len, reverse=True)) + r")\b", re.I)
TIME_RE = re.compile(
    r"\b(?:at|by|for|around|latest)?\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|o'?clock)?(?=[\s,.!?)]|$)", re.I)


def _hour(m: re.Match) -> tuple[int, int] | None:
    h, mins, suf = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower().replace(".", "")
    if h > 23 or mins > 59:
        return None
    if suf.startswith("p") and h < 12:
        h += 12
    elif suf.startswith("a") and h == 12:
        h = 0
    elif not suf.startswith(("a", "p")):
        if h > 12:
            pass
        elif 1 <= h <= 6:
            h += 12
        elif h == 0:
            return None
    return h, mins


def _find_time(text: str, exclude: list[tuple[int, int]]) -> tuple[int, int] | None:
    for m in TIME_RE.finditer(text):
        # ignore numbers that are clearly not times: money, staff counts, list numbers
        tail = text[m.end():m.end() + 12].lower()
        head = text[max(0, m.start() - 3):m.start()]
        if not m.group(3) and re.match(r"\s*(staff|sites?|people|employees|%|million|k\b|m\b|days|weeks|of us)", tail):
            continue
        if "₦" in head or head.strip().endswith(("N", "NGN")):
            continue
        has_suffix = bool(m.group(3))
        pre = text[max(0, m.start() - 8):m.start() + 4].lower()
        if not has_suffix and not re.search(r"\b(at|by|for|around|latest)\b", pre + m.group(0).lower()):
            # a bare number only counts as a time when introduced by at/by/for/around
            if not re.search(r"(morning|day|tomorrow|today)\s*$", text[:m.start()].lower().rstrip()):
                continue
        hm = _hour(m)
        if hm:
            return hm
    return None


def parse_due(text: str, sent: datetime) -> datetime | None:
    t = text.lower()
    base: datetime | None = None
    day_level = True

    if re.search(r"\bnext week\b", t):
        days = (0 - sent.weekday()) % 7 or 7
        return (sent + timedelta(days=days)).replace(hour=10, minute=0, second=0, microsecond=0)
    if re.search(r"\b(end of (the )?week|before (the )?weekend|end of week)\b", t):
        days = max(0, 4 - sent.weekday())
        return (sent + timedelta(days=days)).replace(hour=17, minute=0, second=0, microsecond=0)
    if re.search(r"\btomorrow\b|\btmrw\b|\btmr\b|\bnext tomorrow\b", t):
        extra = 2 if "next tomorrow" in t else 1
        base = (sent + timedelta(days=extra)).replace(second=0, microsecond=0)
    elif re.search(r"\btoday\b|\bthis (morning|afternoon|evening)\b|\blater today\b", t):
        base = sent.replace(second=0, microsecond=0)
    else:
        m = DAY_RE.search(text)
        if m:
            wd = DAYS[m.group(1).lower()]
            days = (wd - sent.weekday()) % 7 or 7
            base = (sent + timedelta(days=days)).replace(second=0, microsecond=0)
    if base is None:
        return None

    hm = _find_time(text, [])
    if hm:
        return base.replace(hour=hm[0], minute=hm[1])
    if re.search(r"\b(morning|first thing)\b", t):
        return base.replace(hour=9, minute=0)
    if re.search(r"\bafternoon\b", t):
        return base.replace(hour=14, minute=0)
    if re.search(r"\b(evening|tonight)\b", t):
        return base.replace(hour=17, minute=0)
    return base.replace(hour=17, minute=0) if day_level else base


def has_clock_time(text: str) -> bool:
    return _find_time(text, []) is not None
