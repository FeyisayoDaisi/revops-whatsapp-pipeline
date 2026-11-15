"""
From messages to a CRM the business owns.

For every conversation (one client number) this builds the deal record:
source, stage, amount, signer, contacts, every commitment and whether it was kept.
It then writes proposed CRM updates, each tagged with the approval tier from
config/approval_policy.yaml. Nothing in the "approve" tier changes until a person says yes.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import CONFIG, DATA, OUT, TODAY, company, load_yaml, reps  # noqa: E402
from pipeline.extract import extract_rules  # noqa: E402

STAGES = [s["name"] for s in load_yaml(CONFIG / "stage_rules.yaml")["stages"]]
QUIET = {s["name"]: s["max_quiet_days"] for s in load_yaml(CONFIG / "stage_rules.yaml")["stages"]}
POLICY = load_yaml(CONFIG / "approval_policy.yaml")
SIGNAL_TO_STAGE = {"meeting_agreed": "meeting_booked", "meeting_held": "meeting_held",
                   "proposal_sent": "proposal_sent", "won": "won", "lost": "lost"}
REFERRAL_RE = re.compile(r"(?:referred by|recommended you|gave me your number)", re.I)
REFERRER_RE = re.compile(r"((?:Mr|Mrs|Dr)\.? [A-Z][a-z]+(?: of [A-Z][\w ]+?)?)(?= gave| recommended|[.,]|$)")
AGENT_RE = re.compile(r"\bAGT-\d{2}\b")


def tier(update_type: str) -> str:
    if update_type in POLICY["approve"]["record_updates"]:
        return "approve"
    return "auto"


def detect_source(first_in: pd.Series, form_phones: set) -> dict:
    if first_in.ad_source_id:
        return {"channel": "ad", "detail": first_in.ad_source_id, "evidence": "Click-to-WhatsApp referral object"}
    text = first_in.text or ""
    m = AGENT_RE.search(text)
    if m:
        return {"channel": "field", "detail": m.group(0), "evidence": text}
    if REFERRAL_RE.search(text) or re.search(r"\b(referred|recommended)\b", text, re.I):
        r = REFERRER_RE.search(text)
        return {"channel": "referral", "detail": r.group(1) if r else "", "evidence": text}
    if first_in.client_phone in form_phones:
        return {"channel": "form", "detail": "website form", "evidence": "phone matches a form submission"}
    return {"channel": "organic", "detail": "", "evidence": "no source signal in the chat"}


def commitment_status(c: dict, conv: pd.DataFrame) -> str:
    """kept / overdue / pending (rep-owned); kept / lapsed / pending (client-owned)."""
    after = conv[conv.ts > c["made_at"]]
    timed = c["due"].hour != 17 or c["due"].minute != 0
    grace = timedelta(hours=3) if timed else timedelta(hours=7)
    if c["owner"] == "rep":
        hit = after[(after.direction == "out") & (after.ts <= c["due"] + grace)]
        hit = hit[~hit.text.str.fullmatch(r"Noted, I'll call you then\.", na=False)]
        if len(hit):
            return "kept"
        return "pending" if c["due"] + grace > TODAY else "overdue"
    hit = after[(after.direction == "in") & (after.ts <= c["due"] + timedelta(hours=24))]
    if len(hit):
        return "kept"
    return "pending" if c["due"] + timedelta(hours=24) > TODAY else "lapsed"


def build(msgs: pd.DataFrame):
    with open(DATA / "form_submissions.csv") as f:
        form_phones = {r["phone"] for r in csv.DictReader(f)}
    deals, commitments, updates = [], [], []
    for phone, conv in msgs.groupby("client_phone", sort=False):
        conv = conv.sort_values("ts")
        first_in = conv[conv.direction == "in"].iloc[0]
        rep = conv.rep.dropna().iloc[-1]
        deal = {"client_phone": phone, "client_name": first_in.client_name, "rep": rep,
                "created": conv.ts.iloc[0], "stage": "new", "amount": None, "budget": None,
                "signer": "", "signer_role": "", "contacts": [], "no_show": False,
                "honorific": "", "last_in": conv[conv.direction == "in"].ts.max(),
                "last_out": conv[conv.direction == "out"].ts.max(), "last_msg": conv.ts.max(),
                "last_text": conv.text.iloc[-1] if conv.text.iloc[-1] else "[" + conv.type.iloc[-1] + "]"}
        src = detect_source(first_in, form_phones)
        deal.update({"source": src["channel"], "source_detail": src["detail"]})
        updates.append({"client_phone": phone, "type": "source", "value": f"{src['channel']}:{src['detail']}",
                        "evidence": src["evidence"][:120], "msg_id": first_in.msg_id, "tier": tier("source")})
        hon = conv[(conv.direction == "out") & conv.text.str.contains(r"\b(?:sir|ma)\b", na=False)].text
        if len(hon):
            deal["honorific"] = "sir" if re.search(r"\bsir\b", hon.iloc[0]) else "ma"
        stage_idx = 0
        for r in conv.itertuples():
            if r.contacts:
                for c in json.loads(r.contacts):
                    deal["contacts"].append(c)
                    updates.append({"client_phone": phone, "type": "contact_added", "value": f"{c['name']} {c['phone']}",
                                    "evidence": "contact card shared in chat", "msg_id": r.msg_id, "tier": tier("contact_added")})
                continue
            if r.direction == "in" and stage_idx == 0 and re.search(r"\b\d+ staff\b", r.text or "") \
                    and re.search(r"\b(next month|this quarter|urgently|from january|as soon as possible|asap)\b", r.text or "", re.I):
                stage_idx = max(stage_idx, STAGES.index("qualified"))
            x = extract_rules(r.text, r.direction, r.ts)
            if x["commitment"]:
                c = {**x["commitment"], "client_phone": phone, "rep": rep, "msg_id": r.msg_id, "made_at": r.ts,
                     "said": r.text}
                commitments.append(c)
                updates.append({"client_phone": phone, "type": "commitment_logged",
                                "value": f"{c['owner']} owes {c['topic']} by {c['due']:%a %d %b %H:%M}",
                                "evidence": r.text[:120], "msg_id": r.msg_id, "tier": tier("commitment_logged")})
            if x["amount"]:
                key = "amount" if x["amount"]["kind"] == "quote" else "budget"
                deal[key] = x["amount"]["value"]
                updates.append({"client_phone": phone, "type": "amount" if key == "amount" else "activity_logged",
                                "value": x["amount"]["value"], "evidence": r.text[:120], "msg_id": r.msg_id,
                                "tier": tier("amount" if key == "amount" else "activity_logged")})
            if x["signer"]:
                deal["signer"], deal["signer_role"] = x["signer"]["name"], x["signer"]["role"]
                updates.append({"client_phone": phone, "type": "signer", "value": f"{x['signer']['name']} ({x['signer']['role']})",
                                "evidence": r.text[:120], "msg_id": r.msg_id, "tier": tier("signer")})
                stage_idx = max(stage_idx, STAGES.index("negotiation"))
            for s in x["signals"]:
                if s == "no_show":
                    deal["no_show"] = True
                elif s in SIGNAL_TO_STAGE:
                    new = STAGES.index(SIGNAL_TO_STAGE[s])
                    if s in ("won", "lost") or new > stage_idx:
                        stage_idx = new
                    if s == "meeting_held":
                        deal["no_show"] = False
        deal["stage"] = STAGES[stage_idx]
        updates.append({"client_phone": phone, "type": "stage_change", "value": deal["stage"],
                        "evidence": "latest stage signal in chat", "msg_id": conv.msg_id.iloc[-1], "tier": tier("stage_change")})
        deals.append(deal)

    cdf = pd.DataFrame(commitments)
    status = []
    by_phone = dict(tuple(msgs.groupby("client_phone")))
    for c in commitments:
        status.append(commitment_status(c, by_phone[c["client_phone"]]))
    cdf["status"] = status
    ddf = pd.DataFrame(deals)
    ddf["days_quiet"] = ((TODAY - ddf.last_msg).dt.total_seconds() / 86400).round(1)
    ddf["quiet_limit"] = ddf.stage.map(QUIET)
    ddf["going_cold"] = (~ddf.stage.isin(["won", "lost"])) & (ddf.days_quiet > ddf.quiet_limit)
    # every live deal gets a dated next action: the earliest open commitment, or the day the
    # stage's quiet limit runs out. Nobody has to remember to type "follow up".
    nxt = cdf[cdf.status.isin(["pending", "overdue"])].groupby("client_phone").due.min()
    ddf["next_action_date"] = ddf.client_phone.map(nxt)
    fallback = ddf.last_msg + pd.to_timedelta(ddf.quiet_limit.clip(upper=60), unit="D")
    ddf["next_action_date"] = ddf.next_action_date.fillna(fallback).where(~ddf.stage.isin(["won", "lost"]))
    ddf["contacts_on_record"] = ddf.contacts.apply(len) + 1
    ddf["contacts"] = ddf.contacts.apply(lambda c: json.dumps(c, ensure_ascii=False) if c else "")
    return ddf, cdf, pd.DataFrame(updates)


def main():
    msgs = pd.read_csv(OUT / "messages.csv", parse_dates=["ts"], keep_default_na=False,
                       dtype={"client_phone": str, "ad_source_id": str})
    deals, commits, updates = build(msgs)
    deals.to_csv(OUT / "deals_captured.csv", index=False)
    commits.to_csv(OUT / "commitments.csv", index=False)
    updates.to_csv(OUT / "crm_updates.csv", index=False)
    print(f"deals {len(deals)}, commitments {len(commits)} "
          f"({(commits.status == 'overdue').sum()} overdue rep promises, {(commits.status == 'lapsed').sum()} lapsed client promises), "
          f"CRM updates {len(updates)} ({(updates.tier == 'approve').sum()} need approval)")


if __name__ == "__main__":
    main()
