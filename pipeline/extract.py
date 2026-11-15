"""
Read one WhatsApp message and pull out what a CRM needs.

Default mode is rules: deterministic, explainable, and scored against the answer key.
An optional AI mode (extract_ai) handles phrasing the rules miss. Its output goes
through the same approval policy as the rules, so it can never write a stage, an
amount or a signer on its own.

Facts extracted per message:
  commitment  who owes what, by when (owner = rep or client)
  amount      a quoted contract value (rep) or a stated budget (client)
  signer      the person who signs, with their role
  contacts    contact cards shared in the chat
  signals     stage evidence: meeting agreed, meeting held, proposal sent, won, lost, no-show
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

from pipeline.timeparse import parse_due

TOPICS = ["revised quote", "proposal", "site visit", "pricing", "contract draft", "contract", "sla document",
          "invoice", "quote", "price list"]

# ---- commitments ----
CLIENT_ASKS_REP = re.compile(
    r"\b(call|reach out to|reach|talk to|talk|ring|contact|text|send|message)\b[^.?!]{0,25}\b(me|us)\b"
    r"|\blet'?s (talk|speak|meet|discuss)\b|\bworks for (me|us)\b|\bcall me\b|\bcome (by|over)\b"
    r"|\babeg (call|send|reach)\b", re.I)
CLIENT_SELF = re.compile(
    r"\b(i|we)\s*(will|'ll|go|shall)\s*(revert|get back|come back|confirm|review|let you know|reach out|respond)\b"
    r"|\bgive (me|us) (till|until)\b|\blet me (discuss|check|review|confirm|talk)\b.*\b(get back|revert)\b", re.I)
REP_SELF = re.compile(
    r"\b(i|i'll|we'll|we)\s*(will|'ll|go|shall)?\s*(send|call|get back|share|revert|forward|prepare|reach out)\b", re.I)
NEGATION = re.compile(r"\b(don'?t|do not|no (call|send)|never|stop)\b", re.I)
PAST = re.compile(r"\b(called|sent|said you|you promised|was supposed)\b", re.I)

# ---- amounts ----
AMOUNT = re.compile(
    r"(?:₦|\bNGN\s?|\bN(?=\d))\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(m|M|million|k|K)?\b"
    r"|\b(\d+(?:\.\d+)?)\s*(million|m)\s*naira\b", re.I)
QUOTE_CUE = re.compile(r"\b(comes to|total|quote|proposal|contract|per year|annual|for the year)\b", re.I)
BUDGET_CUE = re.compile(r"\b(budget|we can pay|we can do|our limit)\b", re.I)

# ---- signer ----
ROLES = r"(MD|CEO|CFO|COO|GM|Head of Admin|Head of Procurement|Director|Chairman|Oga)"
SIGNER_A = re.compile(r"\b(?:our|the)\s+" + ROLES + r",?\s+((?:Mr|Mrs|Dr|Engr|Chief)\.?\s+[A-Z][a-z]+)", re.I)
SIGNER_B = re.compile(r"((?:Mr|Mrs|Dr|Engr|Chief)\.?\s+[A-Z][a-z]+)\s*\(" + ROLES + r"\)", re.I)
SIGN_CUE = re.compile(r"\b(sign|approv|approval|final say|decid)", re.I)

# ---- stage signals ----
SIGNALS = [
    ("won", "in", re.compile(r"\b(good to go|send the invoice|po will come|purchase order|approved, let'?s start|management has approved|payment (has been )?made)\b", re.I)),
    ("lost", "in", re.compile(r"\b(went with another|another vendor|won'?t be proceeding|not proceeding|said no)\b", re.I)),
    ("no_show", "out", re.compile(r"\b(couldn'?t reach|could not reach|didn'?t pick|no answer|missed each other)\b", re.I)),
    ("meeting_held", "out", re.compile(r"\b(thank you for your time|thanks for the call|good speaking with you)\b", re.I)),
    ("proposal_sent", "out", re.compile(r"\b(comes to|our quote|proposal attached|find our proposal|total for the year)\b", re.I)),
]


def _topic(text: str, default: str) -> str:
    t = text.lower()
    for k in TOPICS:
        if k in t:
            return k
    return default


def parse_amount(text: str) -> int | None:
    m = AMOUNT.search(text)
    if not m:
        return None
    if m.group(3):
        return int(round(float(m.group(3)) * 1_000_000))
    num, unit = m.group(1).replace(",", ""), (m.group(2) or "").lower()
    v = float(num)
    if unit in ("m", "million"):
        v *= 1_000_000
    elif unit == "k":
        v *= 1_000
    return int(round(v))


def extract_rules(text: str, direction: str, sent: datetime) -> dict:
    out: dict = {"commitment": None, "amount": None, "signer": None, "signals": []}
    if not text:
        return out
    due = parse_due(text, sent)
    if due and not NEGATION.search(text) and not PAST.search(text):
        owner = None
        if direction == "in" and CLIENT_SELF.search(text):
            owner = "client"
        elif direction == "in" and CLIENT_ASKS_REP.search(text):
            owner = "rep"
        elif direction == "out" and REP_SELF.search(text):
            owner = "rep"
        if owner:
            default = "call" if re.search(r"\b(call|talk|ring|speak|reach|works for (me|us))\b", text, re.I) else "follow-up"
            out["commitment"] = {"owner": owner, "due": due, "topic": _topic(text, default)}
    amt = parse_amount(text)
    if amt and amt >= 50_000:
        if direction == "out" and QUOTE_CUE.search(text) and not re.search(r"\bstarts? from\b", text, re.I):
            out["amount"] = {"value": amt, "kind": "quote"}
        elif direction == "in" and BUDGET_CUE.search(text):
            out["amount"] = {"value": amt, "kind": "budget"}
    if direction == "in" and SIGN_CUE.search(text):
        m = SIGNER_A.search(text) or SIGNER_B.search(text)
        if m:
            role, name = (m.group(1), m.group(2)) if m.re is SIGNER_A else (m.group(2), m.group(1))
            out["signer"] = {"name": name.strip(), "role": role.strip()}
    for sig, d, rx in SIGNALS:
        if d == direction and rx.search(text):
            out["signals"].append(sig)
    if direction == "in" and out["commitment"] and out["commitment"]["owner"] == "rep" \
            and out["commitment"]["topic"] == "call":
        out["signals"].append("meeting_agreed")
    return out


# ---------------- optional AI mode ----------------
AI_SYSTEM = """You read one WhatsApp message between a B2B sales rep and a client in Nigeria (English or Pidgin).
Return JSON only:
{"commitment": null | {"owner": "rep"|"client", "due": "YYYY-MM-DDTHH:MM", "topic": "<2-4 words>"},
 "amount": null | {"value": <integer naira>, "kind": "quote"|"budget"},
 "signer": null | {"name": "<title surname>", "role": "<role>"}}
Rules: only a commitment with a stated or clearly implied date. A weekday means the next one after the sent date.
A day without a time is due 17:00. Ignore past events and negations ("don't call me Monday")."""


def extract_ai(text: str, direction: str, sent: datetime, cache_path) -> dict | None:
    """Live Claude call with a local cache. Returns None if no key and no cached answer."""
    key = json.dumps([text, direction, sent.isoformat()])
    cache = {}
    if cache_path.exists():
        for line in open(cache_path):
            row = json.loads(line)
            cache[row["key"]] = row["out"]
    if key in cache:
        return cache[key]
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic  # optional dependency
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=300, temperature=0, system=AI_SYSTEM,
        messages=[{"role": "user", "content": f"Sent: {sent.isoformat()} ({sent.strftime('%A')})\nFrom: {'client' if direction == 'in' else 'rep'}\nMessage: {text}"}])
    try:
        out = json.loads(msg.content[0].text)
    except (json.JSONDecodeError, IndexError, AttributeError):
        out = {"commitment": None, "amount": None, "signer": None, "needs_review": True}
    with open(cache_path, "a") as f:
        f.write(json.dumps({"key": key, "out": out}, ensure_ascii=False) + "\n")
    return out
