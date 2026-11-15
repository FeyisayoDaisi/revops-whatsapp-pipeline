"""
The 7:30am WhatsApp brief: each rep gets up to five things to do today, from the coaching
agent's own number, with a ready draft and a one-tap link that opens the client's chat
with the message already typed.

Rules that shape it:
  - WhatsApp's 24-hour window. The brief itself goes out as a pre-approved utility template
    ("your plan for today is ready"); once the rep replies, everything else is free-form.
    For each client, the brief says whether the agent could send inside the window or the
    rep should send from their own app.
  - Approval tiers from config/approval_policy.yaml. Anything that mentions price goes out
    only when the rep writes or edits it. Nothing in this file sends a message.
  - Five items, ranked. A brief that turns into a feed gets muted.
Managers get one email-style summary instead.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import CONFIG, OUT, TODAY, load_yaml, reps, write_json  # noqa: E402

PLAY = load_yaml(CONFIG / "playbook.yaml")["situations"]
POLICY = load_yaml(CONFIG / "approval_policy.yaml")
PRICE_WORDS = [w.lower() for w in POLICY["never_auto"]["send_if_text_mentions"]] + ["quote", "pricing"]
WEIGHT = {"scheduled_call_due": 6, "rep_promise_overdue": 5, "no_show_recovery": 4,
          "client_promise_lapsed": 3, "proposal_quiet": 2, "going_cold": 1}
LABEL = {"scheduled_call_due": "Due today", "rep_promise_overdue": "Overdue: you promised",
         "no_show_recovery": "Missed meeting", "client_promise_lapsed": "They went quiet on a promise",
         "proposal_quiet": "Proposal gone quiet", "going_cold": "Going cold"}


def draft(situation: str, honorific: str, topic: str) -> str:
    hr = f" {honorific}" if honorific else ""
    tpl = PLAY[situation].get("template_call") if topic == "call" else None
    return (tpl or PLAY[situation]["template"]).format(greeting=f"Good morning{hr}", topic=topic)


def route(text: str, topic: str, last_in) -> tuple[str, str]:
    t = (text + " " + topic).lower()
    in_window = pd.notna(last_in) and (TODAY - last_in) <= timedelta(hours=POLICY["whatsapp_rules"]["service_window_hours"])
    if any(w in t for w in PRICE_WORDS):
        return "never_auto", "mentions price: you write or edit it and send from your app"
    if in_window:
        return "approve", "inside the 24-hour window: tap approve and the agent sends it"
    return "approve", "outside the 24-hour window: tap the link and send from your app"


def items_for(deals: pd.DataFrame, commits: pd.DataFrame) -> list[dict]:
    items = []
    live = deals[~deals.stage.isin(["won", "lost"])].set_index("client_phone")
    recent = TODAY - timedelta(days=21)
    for c in commits.itertuples():
        if c.client_phone not in live.index:
            continue
        d = live.loc[c.client_phone]
        if c.owner == "rep" and c.status == "overdue" and c.due >= recent and d.last_out <= c.due:
            items.append((c.client_phone, "rep_promise_overdue", c.topic, f"due {c.due:%a %d %b %H:%M}", c.rep))
        elif c.owner == "rep" and c.status == "pending" and c.due.date() == TODAY.date():
            items.append((c.client_phone, "scheduled_call_due", c.topic, f"today {c.due:%H:%M}", c.rep))
        elif c.owner == "client" and c.status == "lapsed" and c.due >= recent and d.last_in <= c.due:
            items.append((c.client_phone, "client_promise_lapsed", c.topic, f"they promised by {c.due:%a %d %b}", c.rep))
    flagged = {i[0] for i in items}
    for phone, d in live.iterrows():
        if phone in flagged:
            continue
        if d.no_show and d.days_quiet <= 14 and d.last_in < d.last_out:
            items.append((phone, "no_show_recovery", "call", f"no-show, {d.days_quiet:.0f} days ago", d.rep))
        elif d.going_cold and d.stage not in ("new",) and d.days_quiet <= 30:
            sit = "proposal_quiet" if d.stage in ("proposal_sent", "negotiation") else "going_cold"
            items.append((phone, sit, "proposal" if sit == "proposal_quiet" else "facility setup",
                          f"{d.days_quiet:.0f} days with no reply (this stage should move within {d.quiet_limit})", d.rep))
    out = []
    for phone, sit, topic, when, rep in items:
        d = live.loc[phone]
        amt = float(d.amount) if str(d.amount) not in ("", "nan") else 0
        text = draft(sit, d.honorific, topic)
        tier, how = route(text, topic, d.last_in)
        out.append({"client_phone": phone, "client": d.client_name, "rep": rep, "situation": sit, "label": LABEL[sit],
                    "topic": topic, "when": when, "stage": d.stage, "amount": amt, "draft": text, "tier": tier,
                    "how_to_send": how, "link": f"https://wa.me/{phone}?text={quote(text)}",
                    "priority": WEIGHT[sit] * 10 + amt / 1e6})
    return out


def main():
    R = reps()
    deals = pd.read_csv(OUT / "deals_captured.csv", dtype={"client_phone": str}, keep_default_na=False,
                        parse_dates=["last_msg", "last_in", "last_out"])
    commits = pd.read_csv(OUT / "commitments.csv", dtype={"client_phone": str}, parse_dates=["due", "made_at"])
    handover = pd.read_csv(OUT / "handover.csv", dtype={"client_phone": str})
    moved = dict(zip(handover.client_phone, handover.to_rep))
    deals["rep"] = deals.apply(lambda d: moved.get(d.client_phone, d.rep), axis=1)
    commits["rep"] = commits.apply(lambda c: moved.get(c.client_phone, c.rep), axis=1)
    items = pd.DataFrame(items_for(deals, commits))
    items["inherited"] = items.client_phone.isin(moved)
    cap = POLICY["whatsapp_rules"]["max_brief_items"]
    gone = ", ".join(r["name"].split()[0] for r in R.values() if r.get("left_on"))
    (OUT / "briefs").mkdir(exist_ok=True)
    briefs = {}
    for rid, r in R.items():
        if r.get("left_on"):
            continue
        mine = items[items.rep == rid].sort_values("priority", ascending=False)
        top, rest = mine.head(cap), len(mine) - cap
        first = r["name"].split()[0]
        lines = [f"Good morning {first}. Here's today ({TODAY:%a %d %b}):", ""]
        for n, it in enumerate(top.itertuples(), 1):
            amt = f" · ₦{it.amount / 1e6:.1f}m" if it.amount else ""
            inh = f" · inherited from {gone}" if it.inherited else ""
            what = "the call they booked" if it.topic == "call" else it.topic
            lines += [f"*{n}. {it.label}*: {it.client}{amt}{inh}",
                      f"   {what}, {it.when}",
                      f"   Draft: \"{it.draft}\"",
                      f"   {it.how_to_send}", f"   {it.link}", ""]
        if rest > 0:
            lines.append(f"+{rest} more on your list. Reply *more* to see them.")
        lines += ["", "Reply *done 1*, *move 2 to Thursday*, or send a voice note with any update. I'll log it."]
        txt = "\n".join(lines)
        (OUT / "briefs" / f"{rid}.txt").write_text(txt)
        briefs[rid] = {"rep": r["name"], "items": top.to_dict("records"), "more": max(0, rest), "text": txt}
    write_json(OUT / "briefs.json", briefs)
    items.to_csv(OUT / "brief_items_all.csv", index=False)

    # manager summary
    by_rep = items.groupby("rep").situation.value_counts().unstack(fill_value=0)
    by_rep.index = [R[i]["name"] for i in by_rep.index]
    html = ["<h2>Pipeline commitments, Monday 7:30am</h2>",
            f"<p>{len(items)} actions across the team. {int((items.situation == 'rep_promise_overdue').sum())} promises to clients are overdue; "
            f"{int((items.situation == 'scheduled_call_due').sum())} calls are booked for today.</p>",
            by_rep.rename(columns=LABEL).to_html(border=0)]
    (OUT / "manager_summary.html").write_text("\n".join(html))
    print(f"briefs for {len(briefs)} reps, {len(items)} actions found, "
          f"{sum(len(b['items']) for b in briefs.values())} in today's briefs")


if __name__ == "__main__":
    main()
