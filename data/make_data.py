"""
Seeded generator for the synthetic WhatsApp pipeline.

Creates one invented Lagos B2B services company with 6 reps, leads arriving
from Click-to-WhatsApp ads, a website form, referrals, field agents and organic
WhatsApp, and every conversation as it would arrive from the WhatsApp Cloud API
(Coexistence: inbound messages + echoes of what reps send from the app).

It also writes:
  - what the CRM looks like when reps update it by hand (the "before")
  - the truth for every planted fact (answer_key.json), so extraction is scored
  - meeting, show and win outcomes, so qualification is scored on real results

Everything is invented. No client data is used.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import CONFIG, DATA, TODAY, WAT, load_yaml  # noqa: E402

SEED = 20261116
N_LEADS = 320
rng = random.Random(SEED)

company = load_yaml(CONFIG / "company.yaml")
REPS = company["reps"]
ADS = company["ads"]
AGENTS = company["field_agents"]
START = datetime.fromisoformat(company["data_start"])
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

FIRST_M = ["Emeka", "Babatunde", "Yusuf", "Femi", "Obinna", "Kunle", "Ibrahim", "Uche", "Segun", "Musa", "Dapo", "Kelechi"]
FIRST_F = ["Ngozi", "Funke", "Aisha", "Chioma", "Yetunde", "Zainab", "Bisi", "Adaeze", "Hauwa", "Tolu", "Nneka", "Kemi"]
LAST = ["Okafor", "Adebayo", "Bello", "Nwachukwu", "Ogunleye", "Danjuma", "Eze", "Lawal", "Okonkwo", "Balogun",
        "Ibekwe", "Suleiman", "Ajayi", "Uzor", "Afolabi", "Oyelaran", "Abubakar", "Chukwu"]
AREAS = ["Lekki", "Ikeja", "Victoria Island", "Yaba", "Apapa", "Ikoyi", "Surulere", "Ajah", "Maryland", "Oregun"]
INDUSTRIES = ["bank", "fintech", "hospital", "school", "manufacturing", "logistics", "oil and gas", "telecoms",
              "insurance", "hotel"]
TOPICS = ["revised quote", "proposal", "site visit", "pricing", "contract draft", "SLA document"]
SIGNER_ROLES = ["MD", "CFO", "Head of Admin", "COO"]

# archetype mix differs by source; this is what makes "Source = Other" so expensive
ARCH_BY_SOURCE = {
    "ad":       {"serious": .30, "price_shopper": .32, "maybe_later": .20, "too_small": .18},
    "form":     {"serious": .45, "price_shopper": .15, "maybe_later": .25, "too_small": .15},
    "referral": {"serious": .70, "price_shopper": .05, "maybe_later": .20, "too_small": .05},
    "field":    {"serious": .40, "price_shopper": .15, "maybe_later": .30, "too_small": .15},
    "organic":  {"serious": .30, "price_shopper": .30, "maybe_later": .25, "too_small": .15},
}
SOURCE_MIX = {"ad": .45, "field": .20, "referral": .15, "form": .12, "organic": .08}
ACCEPT_MEETING = {"serious": .95, "maybe_later": .60, "price_shopper": .45, "too_small": .60}
SHOW = {"serious": .86, "maybe_later": .38, "price_shopper": .14, "too_small": .40}
WIN_IF_SHOWED = {"serious": .52, "maybe_later": .22, "price_shopper": .08, "too_small": .04}


def pick(d: dict) -> str:
    r, acc = rng.random(), 0.0
    for k, p in d.items():
        acc += p
        if r <= acc:
            return k
    return list(d)[-1]


# ---------- time phrases (conventions documented in docs/COMMITMENT_RULES.md) ----------

def hour_txt(h: int) -> str:
    style = rng.random()
    suffix = "am" if h < 12 else "pm"
    h12 = h if h <= 12 else h - 12
    if style < .55:
        return f"{h12}{suffix}"
    if style < .75:
        return f"{h12} {'a.m.' if h < 12 else 'p.m.'}"
    if style < .9:
        return f"{h12}:00{suffix}"
    return f"{h12} o'clock" if 8 <= h <= 11 or 13 <= h <= 17 else f"{h12}{suffix}"


def next_weekday(ts: datetime, wd: int) -> datetime:
    days = (wd - ts.weekday()) % 7 or 7
    return (ts + timedelta(days=days)).replace(minute=0, second=0, microsecond=0)


def due_phrase(ts: datetime) -> tuple[str, datetime]:
    """Return (phrase, due datetime) for a commitment made at ts."""
    kind = rng.choices(["wd_time", "wd_morning", "tomorrow_time", "tomorrow_morning", "by_wd", "eow", "next_week"],
                       [.32, .10, .16, .08, .16, .08, .10])[0]
    if kind in ("eow",) and ts.weekday() >= 3:
        kind = "by_wd"
    if kind == "wd_time":
        wd = rng.choice([0, 1, 2, 3, 4]); h = rng.choice([8, 9, 10, 11, 12, 14, 15, 16])
        d = next_weekday(ts, wd).replace(hour=h)
        fmt = rng.choice(["{wd} {t}", "{wd} by {t}", "on {wd} at {t}", "{wd} {t}"])
        return fmt.format(wd=WEEKDAYS[wd], t=hour_txt(h)), d
    if kind == "wd_morning":
        wd = rng.choice([0, 1, 2, 3, 4])
        d = next_weekday(ts, wd).replace(hour=9)
        return rng.choice([f"{WEEKDAYS[wd]} morning", f"first thing {WEEKDAYS[wd]}"]), d
    if kind == "tomorrow_time":
        h = rng.choice([9, 10, 11, 12, 14, 15, 16])
        d = (ts + timedelta(days=1)).replace(hour=h, minute=0, second=0)
        return rng.choice([f"tomorrow {hour_txt(h)}", f"tomorrow by {hour_txt(h)}", f"tomorrow at {hour_txt(h)}"]), d
    if kind == "tomorrow_morning":
        d = (ts + timedelta(days=1)).replace(hour=9, minute=0, second=0)
        return rng.choice(["tomorrow morning", "first thing tomorrow"]), d
    if kind == "by_wd":
        wd = rng.choice([0, 1, 2, 3, 4])
        d = next_weekday(ts, wd).replace(hour=17)
        return rng.choice([f"by {WEEKDAYS[wd]}", f"before {WEEKDAYS[wd]}", f"latest {WEEKDAYS[wd]}"]), d
    if kind == "eow":
        d = (ts + timedelta(days=4 - ts.weekday())).replace(hour=17, minute=0, second=0)
        return rng.choice(["before the end of the week", "before weekend", "by end of week"]), d
    d = next_weekday(ts, 0).replace(hour=10)
    return rng.choice(["next week", "early next week"]), d


def naira(v: int) -> str:
    m = v / 1_000_000
    m_txt = f"{m:.1f}".rstrip("0").rstrip(".")
    return rng.choice([f"₦{v:,}", f"N{m_txt}m", f"{m_txt} million naira", f"₦{m_txt}M", f"NGN {v:,}"])


# ---------- conversation builder ----------

class Convo:
    def __init__(self, lead: dict):
        self.lead, self.events, self.n = lead, [], 0
        self.facts = {"commitments": [], "amounts": [], "signer": None, "contacts": [], "stage_events": []}

    def add(self, ts: datetime, direction: str, body: str | None = None, kind: str = "text",
            extra: dict | None = None, voice: bool = False) -> str | None:
        if ts > TODAY:
            return None
        self.n += 1
        mid = f"wamid.{self.lead['lead_id']}.{self.n:02d}"
        if direction == "in" and voice and kind == "text":
            kind = "audio"
        self.events.append({"ts": ts, "dir": direction, "id": mid, "type": kind, "body": body, "extra": extra or {}})
        return mid

    def stage(self, ts: datetime, stage: str):
        if ts <= TODAY:
            self.facts["stage_events"].append((ts, stage))


def greet(lead) -> str:
    hr = "sir" if lead["gender"] == "m" else "ma"
    return rng.choice([f"Good day {hr}", f"Hello {hr}", f"Good morning {hr}", f"Thank you for reaching out {hr}"])


def opener(lead) -> str:
    s = lead["source"]
    if s == "ad":
        return rng.choice(["Hello, I saw your ad. I'd like to know more.", "Hi, is this facility management?",
                           "Good afternoon. Saw your advert on Instagram.", "Hello, I'm interested in your service."])
    if s == "referral":
        r = lead["referrer"]
        return rng.choice([f"Good afternoon. {r} gave me your number, said you handle their office.",
                           f"Hello, I was referred by {r}.",
                           f"Hi, {r} recommended you to us."])
    if s == "field":
        return rng.choice([f"Good morning, your agent visited our office yesterday. Code {lead['agent']}.",
                           f"Hello, your field officer ({lead['agent']}) left a flyer with us.",
                           f"Hi, I'm following up from the visit by {lead['agent']}."])
    if s == "form":
        return rng.choice(["Hello, I filled the form on your website.", "Good day, I submitted a request on your site."])
    return rng.choice(["Hello", "Good day, do you do office cleaning and maintenance?", "Hi, I got your number from a friend's status."])


def need_msg(lead) -> str:
    a = lead["arch"]
    if a == "too_small":
        return rng.choice([f"It's just a small shop in {lead['area']}, about {lead['staff']} of us.",
                           f"We're a small team, {lead['staff']} staff. Just need cleaning once a week."])
    if a == "price_shopper":
        return rng.choice(["How much is your service?", "Just send your price list please.", "How much for a month?"])
    timeline = rng.choice(["by next month", "this quarter", "urgently, our current vendor is leaving",
                           "from January", "as soon as possible"]) if a == "serious" else rng.choice(
        ["sometime next year maybe", "we're still thinking about it", "not sure yet"])
    return (f"We're a {lead['industry']} with about {lead['staff']} staff across {lead['sites']} "
            f"{'site' if lead['sites'] == 1 else 'sites'} in {lead['area']}. We need someone to start {timeline}.")


def build(lead: dict) -> Convo:
    c = Convo(lead)
    t = lead["created"]
    rep_first = lead["rep_name"].split()[0]
    c.add(t, "in", opener(lead), extra={"referral": lead.get("ad")} if lead["source"] == "ad" else None)
    c.stage(t, "new")
    t += timedelta(minutes=rng.randint(4, 90))
    c.add(t, "out", f"{greet(lead)}, this is {rep_first} from the team. Happy to help. What do you need and where is your office?")
    t += timedelta(minutes=rng.randint(10, 240))
    voice = rng.random() < .2
    c.add(t, "in", need_msg(lead), voice=voice)
    if lead["arch"] in ("serious", "maybe_later") or (lead["arch"] == "too_small" and rng.random() < .5):
        c.stage(t, "qualified") if lead["arch"] == "serious" else None
    if lead["arch"] == "price_shopper":
        t += timedelta(minutes=rng.randint(10, 120))
        c.add(t, "out", "It depends on your space and number of sites. For most offices it starts from N350k a month. Can we do a quick call so I give you an exact figure?")
    else:
        t += timedelta(minutes=rng.randint(10, 120))
        c.add(t, "out", "Thank you. Can we do a quick call so I understand your setup? What day and time works for you?")

    if not lead["accepted_meeting"]:
        t += timedelta(hours=rng.randint(2, 30))
        c.add(t, "in", rng.choice(["Okay, I will get back to you.", "Let me think about it.", "Thank you, noted.",
                                   "Alright. We will reach out."]))
        lead["stage_truth"] = "qualified" if lead["arch"] == "serious" else "new"
        return c

    # meeting booked: the CLIENT names the time, the rep owes a call at that time
    t += timedelta(minutes=rng.randint(15, 300))
    phrase, due = due_phrase(t)
    msg = rng.choice([f"Call me {phrase}.", f"Let's talk {phrase}.", f"Abeg call me {phrase}, I go dey office.",
                      f"{phrase[0].upper() + phrase[1:]} works for me."])
    mid = c.add(t, "in", msg, voice=rng.random() < .15)
    c.facts["commitments"].append({"msg_id": mid, "owner": "rep", "due": due, "topic": "call"})
    c.stage(t, "meeting_booked")
    lead["meeting_time"] = due
    t2 = t + timedelta(minutes=rng.randint(3, 40))
    c.add(t2, "out", "Noted, I'll call you then.")

    if due > TODAY:
        lead["stage_truth"] = "meeting_booked"
        return c
    if not lead["showed"]:
        tt = due + timedelta(minutes=rng.randint(5, 50))
        c.add(tt, "out", f"{greet(lead)}, I called at the time we agreed but couldn't reach you. When is a better time?")
        lead["stage_truth"] = "meeting_booked"
        lead["no_show"] = True
        return c
    t = due + timedelta(minutes=rng.randint(40, 180))
    c.add(t, "out", f"{greet(lead)}, thank you for your time on the call. I'll put the numbers together.")
    c.stage(t, "meeting_held")

    # proposal with amount
    t += timedelta(days=rng.randint(1, 4), minutes=rng.randint(0, 300))
    amt = lead["amount"]
    mid = c.add(t, "out", rng.choice([f"As discussed, the annual contract comes to {naira(amt)} for {lead['sites']} {'site' if lead['sites'] == 1 else 'sites'}.",
                                       f"Please find our proposal attached. Total for the year is {naira(amt)}.",
                                       f"Our quote for the full scope is {naira(amt)} per year."]))
    if mid:
        c.facts["amounts"].append({"msg_id": mid, "value": amt, "kind": "quote"})
    c.stage(t, "proposal_sent")

    # client names who signs, often shares a contact card
    t += timedelta(hours=rng.randint(3, 48))
    role, sname = lead["signer_role"], lead["signer_name"]
    smsg = rng.choice([f"Okay. Our {role}, {sname}, will sign off on this.",
                       f"Thanks. Final approval sits with our {role}, {sname}.",
                       f"Noted. {sname} ({role}) go approve am, I go show am."])
    mid = c.add(t, "in", smsg, voice=rng.random() < .2)
    if mid:
        c.facts["signer"] = {"msg_id": mid, "name": sname, "role": role}
        c.stage(t, "negotiation")
    if rng.random() < .6:
        t += timedelta(minutes=rng.randint(1, 20))
        cname = f"{rng.choice(FIRST_F + FIRST_M)} {rng.choice(LAST)}"
        cphone = f"23480{rng.randint(10000000, 99999999)}"
        c.add(t, "in", "Please also reach our admin manager for the site details.")
        mid = c.add(t + timedelta(seconds=30), "in", None, kind="contacts",
                    extra={"contacts": [{"name": {"formatted_name": cname}, "phones": [{"phone": f"+{cphone}", "wa_id": cphone}]}]})
        if mid:
            c.facts["contacts"].append({"msg_id": mid, "name": cname, "phone": cphone})

    # rep promises something, kept or missed
    t += timedelta(hours=rng.randint(1, 30))
    topic = rng.choice(TOPICS)
    phrase, due = due_phrase(t)
    mid = c.add(t, "out", rng.choice([f"Noted. I'll send the {topic} {phrase}.", f"I go send the {topic} {phrase}.",
                                       f"Okay, I'll get back to you with the {topic} {phrase}."]))
    if mid:
        kept = rng.random() < .68
        c.facts["commitments"].append({"msg_id": mid, "owner": "rep", "due": due, "topic": topic, "kept": kept})
        if kept:
            c.add(due - timedelta(minutes=rng.randint(10, 180)), "out", f"Here's the {topic} as promised.")
        else:
            late = due + timedelta(days=rng.randint(2, 6))
            if rng.random() < .5:
                c.add(late, "out", f"Sorry for the delay, here's the {topic}.")
        t = max(t, due)

    # client asks for the next touch, or promises to revert
    t += timedelta(hours=rng.randint(4, 60))
    topic2 = rng.choice(TOPICS)
    phrase, due = due_phrase(t)
    if rng.random() < .55:
        mid = c.add(t, "in", rng.choice([f"Reach out to me {phrase} about the {topic2}.",
                                          f"Please call me {phrase} so we close the {topic2}.",
                                          f"Talk to me {phrase} on the {topic2}."]), voice=rng.random() < .2)
        owner = "rep"
    else:
        mid = c.add(t, "in", rng.choice([f"Let me discuss the {topic2} with my {role} and get back to you {phrase}.",
                                          f"I will revert on the {topic2} {phrase}.",
                                          f"Give me till {phrase.replace('by ', '')} to review the {topic2}." if phrase.startswith("by ") else f"I will revert on the {topic2} {phrase}."]))
        owner = "client"
    if mid:
        rec = {"msg_id": mid, "owner": owner, "due": due, "topic": topic2}
        if due <= TODAY:
            rec["kept"] = rng.random() < (.65 if owner == "rep" else .4)
            if rec["kept"]:
                c.add(due + timedelta(minutes=rng.randint(0, 90)), "out" if owner == "rep" else "in",
                      f"Following up on the {topic2} as agreed." if owner == "rep" else f"Hello, we've reviewed the {topic2}.")
        c.facts["commitments"].append(rec)
        t = max(t, due)

    # outcome
    if lead["won"]:
        tw = t + timedelta(days=rng.randint(1, 8))
        if c.add(tw, "in", rng.choice(["We're good to go. Please send the invoice.", "Approved. PO will come from procurement today.",
                                       "Management has approved, let's start."])):
            c.stage(tw, "won")
            lead["closed"] = tw
    elif lead["lost"]:
        tl = t + timedelta(days=rng.randint(2, 12))
        if c.add(tl, "in", rng.choice(["Thank you but we went with another vendor.", "We won't be proceeding for now.",
                                       "Management said no for this year."])):
            c.stage(tl, "lost")
            lead["closed"] = tl
    lead["stage_truth"] = c.facts["stage_events"][-1][1] if c.facts["stage_events"] else "new"
    return c


# ---------- webhook payloads (WhatsApp Cloud API shape) ----------

def to_webhook(lead: dict, e: dict) -> dict:
    rep_num = lead["rep_number"]
    unix = str(int(e["ts"].replace(tzinfo=WAT).timestamp()))
    msg = {"id": e["id"], "timestamp": unix, "type": e["type"]}
    if e["type"] == "text":
        msg["text"] = {"body": e["body"]}
    elif e["type"] == "audio":
        msg["audio"] = {"id": f"media.{e['id']}", "mime_type": "audio/ogg; codecs=opus", "voice": True}
    elif e["type"] == "contacts":
        msg["contacts"] = e["extra"]["contacts"]
    if e["dir"] == "in":
        msg["from"] = lead["phone"]
        if e["extra"].get("referral"):
            ad = e["extra"]["referral"]
            msg["referral"] = {"source_url": "https://fb.me/ad", "source_id": ad["source_id"], "source_type": "ad",
                               "headline": ad["headline"], "media_type": "image",
                               "ctwa_clid": f"ARAk{rng.randint(10**9, 10**10)}"}
        value = {"messaging_product": "whatsapp",
                 "metadata": {"display_phone_number": rep_num, "phone_number_id": f"PNID_{lead['rep']}"},
                 "contacts": [{"profile": {"name": lead["name"]}, "wa_id": lead["phone"]}],
                 "messages": [msg]}
        field = "messages"
    else:
        msg["from"], msg["to"] = rep_num, lead["phone"]
        value = {"messaging_product": "whatsapp",
                 "metadata": {"display_phone_number": rep_num, "phone_number_id": f"PNID_{lead['rep']}"},
                 "message_echoes": [msg]}
        field = "smb_message_echoes"
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "WABA_DEMO", "changes": [{"field": field, "value": value}]}]}


WAT_OFFSET = timedelta(hours=1)


def iso(d):
    return d.isoformat(timespec="minutes") if d else ""


def main():
    span = (TODAY - timedelta(days=2) - START).days
    referrers = [f"{rng.choice(['Mr', 'Mrs', 'Dr'])} {rng.choice(LAST)} of {rng.choice(['Zenvale Bank', 'Corban Logistics', 'Halden Foods', 'Mirelle Hotels', 'Kestrel Energy'])}" for _ in range(8)]
    leads, convos = [], []
    for i in range(N_LEADS):
        g = rng.choice("mf")
        first = rng.choice(FIRST_M if g == "m" else FIRST_F)
        src = pick(SOURCE_MIX)
        arch = pick(ARCH_BY_SOURCE[src])
        created = START + timedelta(days=rng.randint(0, span), hours=rng.randint(8, 20), minutes=rng.randint(0, 59))
        rep = REPS[i % len(REPS)]
        if rep.get("left_on") and created.date() > datetime.fromisoformat(rep["left_on"]).date():
            rep = REPS[(i + 1) % len(REPS)]
        staff = rng.randint(2, 8) if arch == "too_small" else rng.randint(15, 400)
        sites = 1 if arch == "too_small" else rng.choice([1, 1, 2, 3, 4, 6])
        accepted = rng.random() < ACCEPT_MEETING[arch]
        showed = accepted and rng.random() < SHOW[arch]
        won = showed and rng.random() < WIN_IF_SHOWED[arch]
        lead = {
            "lead_id": f"L{i + 1:03d}", "name": f"{first} {rng.choice(LAST)}", "gender": g,
            "phone": f"23481{rng.randint(10000000, 99999999)}", "source": src, "arch": arch, "created": created,
            "rep": rep["id"], "rep_name": rep["name"], "rep_number": rep["number"],
            "industry": rng.choice(INDUSTRIES), "staff": staff, "sites": sites, "area": rng.choice(AREAS),
            "accepted_meeting": accepted, "showed": showed, "won": won,
            "lost": showed and not won and rng.random() < .55,
            "amount": int(round(rng.uniform(1.2, 3.0) * sites ** .6 * staff ** .3, 1) * 1_000_000),
            "signer_role": rng.choice(SIGNER_ROLES),
            "signer_name": f"{rng.choice(['Mr', 'Mrs', 'Dr'])} {rng.choice(LAST)}",
            "ad": rng.choice(ADS) if src == "ad" else None,
            "agent": rng.choice(AGENTS) if src == "field" else None,
            "referrer": rng.choice(referrers) if src == "referral" else None,
            "meeting_time": None, "no_show": False, "closed": None,
        }
        c = build(lead)
        leads.append(lead)
        convos.append(c)

    # webhook stream, in time order, the way it would hit the endpoint
    stream = []
    for lead, c in zip(leads, convos):
        for e in c.events:
            stream.append((e["ts"], to_webhook(lead, e), lead, e))
    stream.sort(key=lambda x: x[0])
    with open(DATA / "webhook_events.jsonl", "w") as f:
        for _, payload, _, _ in stream:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # speech-to-text output for voice notes (stands in for a transcription service)
    with open(DATA / "voice_transcripts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["media_id", "transcript"])
        for _, _, lead, e in stream:
            if e["type"] == "audio":
                w.writerow([f"media.{e['id']}", e["body"]])

    # website form submissions
    with open(DATA / "form_submissions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["submitted_at", "name", "phone", "company_type", "staff", "need"])
        for l in leads:
            if l["source"] == "form":
                w.writerow([iso(l["created"] - timedelta(minutes=rng.randint(5, 60))), l["name"], l["phone"],
                            l["industry"] if l["arch"] != "too_small" else "small business", l["staff"],
                            "facility management"])

    # the CRM as reps keep it by hand (the "before")
    with open(DATA / "crm_manual.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lead_id", "owner", "phone", "source", "stage", "amount", "signer", "next_step", "next_step_date", "contacts_on_record"])
        order = ["new", "qualified", "meeting_booked", "meeting_held", "proposal_sent", "negotiation", "won", "lost"]
        for l in leads:
            src = l["source"] if rng.random() < .33 else rng.choice(["Other", "Other", "", "WhatsApp"])
            st = l["stage_truth"]
            if st not in ("won", "lost") and rng.random() < .5:
                st = order[max(0, order.index(st) - 1)]
            w.writerow([l["lead_id"], l["rep"], l["phone"], src, st,
                        l["amount"] if l["showed"] and rng.random() < .45 else "",
                        l["signer_name"] if l["showed"] and rng.random() < .12 else "",
                        "follow up" if rng.random() < .3 else "",
                        iso(TODAY + timedelta(days=rng.randint(-20, 5))) if rng.random() < .15 else "", 1])

    # outcomes and the answer key
    with open(DATA / "outcomes.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lead_id", "created", "rep", "source", "accepted_meeting", "meeting_time", "showed", "won", "amount", "closed"])
        for l in leads:
            w.writerow([l["lead_id"], iso(l["created"]), l["rep"], l["source"], int(l["accepted_meeting"]),
                        iso(l["meeting_time"]), int(l["showed"]) if l["meeting_time"] and l["meeting_time"] <= TODAY else "",
                        int(l.get("stage_truth") == "won"), l["amount"], iso(l["closed"])])
    key = []
    for l, c in zip(leads, convos):
        key.append({
            "lead_id": l["lead_id"], "rep": l["rep"], "archetype": l["arch"], "stage": l["stage_truth"],
            "source": {"channel": l["source"], "ad_id": l["ad"]["source_id"] if l["ad"] else None,
                       "agent": l["agent"], "referrer": l["referrer"]},
            "commitments": [{**k, "due": iso(k["due"])} for k in c.facts["commitments"]],
            "amounts": c.facts["amounts"], "signer": c.facts["signer"], "contacts": c.facts["contacts"],
        })
    with open(DATA / "answer_key.json", "w") as f:
        json.dump(key, f, indent=1, ensure_ascii=False)
    n_msgs = sum(len(c.events) for c in convos)
    print(f"leads {len(leads)}, webhook events {n_msgs}, voice notes "
          f"{sum(e['type'] == 'audio' for c in convos for e in c.events)}")


if __name__ == "__main__":
    main()
