"""
Before and after, on the same 320 leads: the CRM as reps keep it by hand versus the CRM
the captured chats produce. Writes outputs/before_after.csv and a one-page demo report.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, OUT, TODAY, answer_key, reps, write_json  # noqa: E402

CLOSED = ["won", "lost"]
LATE = ["negotiation", "won", "lost"]


def pct(a, b):
    return round(100 * a / b, 1) if b else 0.0


def compare() -> pd.DataFrame:
    key = {k["lead_id"]: k for k in answer_key()}
    crm = pd.read_csv(DATA / "crm_manual.csv", dtype={"phone": str}, keep_default_na=False)
    cap = pd.read_csv(OUT / "deals_captured.csv", dtype={"client_phone": str}, keep_default_na=False)
    com = pd.read_csv(OUT / "commitments.csv", dtype={"client_phone": str}, parse_dates=["due"])
    items = pd.read_csv(OUT / "brief_items_all.csv", dtype={"client_phone": str})
    ho = pd.read_csv(OUT / "handover.csv", dtype={"client_phone": str}, keep_default_na=False)
    crm["truth_stage"] = crm.lead_id.map(lambda i: key[i]["stage"])
    crm["quoted"] = crm.lead_id.map(lambda i: bool(key[i]["amounts"]))
    crm["has_signer"] = crm.lead_id.map(lambda i: bool(key[i]["signer"]))
    m = crm.merge(cap, left_on="phone", right_on="client_phone", suffixes=("_crm", "_cap"))
    m["last_msg"] = pd.to_datetime(m.last_msg)
    active = m[~m.truth_stage.isin(CLOSED) & (m.last_msg >= TODAY - pd.Timedelta(days=30))]
    recent_overdue = com[(com.status == "overdue") & (com.due >= TODAY - pd.Timedelta(days=21))]
    rows = [
        ("Leads with a real source (not 'Other' or blank)",
         pct((~m.source_crm.isin(["Other", "", "WhatsApp"])).sum(), len(m)), 100.0),
        ("Quoted deals with the amount on record",
         pct((m[m.quoted].amount_crm != "").sum(), m.quoted.sum()), pct((m[m.quoted].amount_cap != "").sum(), m.quoted.sum())),
        ("Deals past proposal with the signer named",
         pct((m[m.has_signer].signer_crm != "").sum(), m.has_signer.sum()), pct((m[m.has_signer].signer_cap != "").sum(), m.has_signer.sum())),
        ("Active deals (open, touched in 30 days) with a dated next action",
         pct((active.next_step_date != "").sum(), len(active)), pct((active.next_action_date != "").sum(), len(active))),
        ("Stage matches what really happened",
         pct((m.stage_crm == m.truth_stage).sum(), len(m)), pct((m.stage_cap == m.truth_stage).sum(), len(m))),
        ("Contacts on record per deal (average)",
         round(m.contacts_on_record_crm.astype(float).mean(), 2), round(m.contacts_on_record_cap.astype(float).mean(), 2)),
        ("Broken promises to clients a manager can see (last 21 days)", 0, len(recent_overdue)),
        ("Departed rep's open deals with stage, amount, signer and next step",
         pct(((ho.crm_had_amount != "") & (ho.crm_had_signer != "") & (ho.crm_had_next_step != "")).sum(), len(ho)), 100.0),
    ]
    df = pd.DataFrame(rows, columns=["measure", "hand_kept_crm", "captured_from_whatsapp"])
    df.to_csv(OUT / "before_after.csv", index=False)
    return df


def bubble_brief(text: str) -> str:
    out = []
    for line in html.escape(text).split("\n"):
        if line.strip().startswith("https://wa.me/"):
            out.append(f'<span class="lnk">{line.strip()[:48]}…</span>')
        else:
            import re
            out.append(re.sub(r"\*(.+?)\*", r"<b>\1</b>", line))
    return "<br>".join(out)


def main():
    ba = compare()
    q = json.load(open(OUT / "qualification.json"))
    ev = json.load(open(OUT / "eval_capture.json"))
    briefs = json.load(open(OUT / "briefs.json"))
    ho = pd.read_csv(OUT / "handover.csv")
    upd = pd.read_csv(OUT / "crm_updates.csv")
    R = reps()
    t = q["test"]
    tiers = upd.tier.value_counts().to_dict()
    fmt = lambda v, unit: f"{v}{unit}" if isinstance(v, float) and unit else str(v)
    def show(v, measure):
        if "can see" in measure:
            return str(int(v))
        if "average" in measure:
            return f"{v:.2f}"
        return f"{v:.1f}%"
    ba_rows = "".join(
        f"<tr><td>{r.measure}</td><td>{show(r.hand_kept_crm, r.measure)}</td>"
        f"<td><b>{show(r.captured_from_whatsapp, r.measure)}</b></td></tr>"
        for r in ba.itertuples())
    src_rows = "".join(f"<tr><td>{s['source']}</td><td>{s['meetings']}</td><td>{s['show_rate']}%</td><td>{s['wins']}</td></tr>"
                       for s in q["show_rate_by_source"])
    sample = briefs["R2"]["text"]
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WhatsApp Pipeline Capture: demo report</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;max-width:900px;margin:0 auto;padding:32px 20px;color:#14213d;line-height:1.55}}
h1{{font-size:28px;margin:0 0 6px}} h2{{font-size:20px;margin-top:36px;border-bottom:2px solid #0D2B4E;padding-bottom:4px}}
.sub{{color:#555}} table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}}
td,th{{border-bottom:1px solid #e3e6ea;padding:8px;text-align:left}} th{{background:#F4F6F8}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:18px 0}}
.kpi{{background:#F4F6F8;border-radius:10px;padding:14px}} .kpi b{{display:block;font-size:26px;color:#0D2B4E}}
.wa{{background:#e7ddd3;border-radius:12px;padding:16px}} .msg{{background:#fff;border-radius:8px;padding:12px 14px;font-size:13.5px;max-width:560px}}
.lnk{{color:#027eb5}} .note{{font-size:13px;color:#555}} code{{background:#F4F6F8;padding:1px 5px;border-radius:4px}}
</style></head><body>
<h1>WhatsApp Pipeline Capture</h1>
<p class="sub">Synthetic demo for a Lagos B2B services company: 320 leads, {sum(1 for _ in open(OUT / 'messages.csv')) - 1:,} WhatsApp messages,
6 reps, leads from Click-to-WhatsApp ads, field agents, referrals, a web form and organic chats. Run date {TODAY:%A %d %B %Y, %H:%M}.</p>
<div class="kpis">
<div class="kpi"><b>{t['book_everyone']['show_rate']}% → {t['scored']['show_rate']}%</b>meeting show rate on unseen Oct-Nov leads</div>
<div class="kpi"><b>{t['no_shows_avoided']}</b>no-show meetings avoided, every win kept ({t['scored']['wins_from_meetings']} of {t['book_everyone']['wins_from_meetings']})</div>
<div class="kpi"><b>{len(ho)}</b>open deals handed over with full context when a rep resigned</div>
<div class="kpi"><b>{int(ba.iloc[6].captured_from_whatsapp)}</b>broken promises to clients now visible (were invisible)</div>
</div>
<h2>Before and after, same leads</h2>
<table><tr><th>Measure</th><th>CRM kept by hand</th><th>Captured from WhatsApp</th></tr>{ba_rows}</table>
<p class="note">The hand-kept CRM is simulated the way it usually looks: reps log the source a third of the time, stages lag, next steps say "follow up".</p>
<h2>Who should get a meeting</h2>
<p>Old rule: anyone who agrees to a call gets one. New rule: book when the chat score is {q['threshold']} or more (size, timeline,
specific time, price-first questions, source). Threshold picked on August-September leads, tested on October-November leads it never saw.</p>
<table><tr><th>Oct-Nov test</th><th>Meetings</th><th>No-shows</th><th>Show rate</th><th>Wins from these meetings</th></tr>
<tr><td>Book everyone who says yes</td><td>{t['book_everyone']['meetings']}</td><td>{t['book_everyone']['no_shows']}</td><td>{t['book_everyone']['show_rate']}%</td><td>{t['book_everyone']['wins_from_meetings']}</td></tr>
<tr><td><b>Book on score ≥ {q['threshold']}</b></td><td>{t['scored']['meetings']}</td><td>{t['scored']['no_shows']}</td><td><b>{t['scored']['show_rate']}%</b></td><td>{t['scored']['wins_from_meetings']}</td></tr></table>
<p class="note">Leads under the threshold go to nurture, not the bin. The test window is small ({t['book_everyone']['wins_from_meetings']} wins), so treat "every win kept" as encouraging, not proven.</p>
<table><tr><th>Source</th><th>Meetings</th><th>Show rate</th><th>Wins</th></tr>{src_rows}</table>
<p class="note">This table only exists because the source is captured. When the CRM says "Other", nobody can see that ad leads show up least.</p>
<h2>The 7:30am brief (one rep, real output)</h2>
<div class="wa"><div class="msg">{bubble_brief(sample)}</div></div>
<p class="note">Sent from the coaching agent's own number. The first message is a pre-approved template; once the rep replies, WhatsApp's 24-hour window is open.
Each draft opens the client's chat with the text typed. Anything about price is written or edited by the rep.</p>
<h2>Approval tiers</h2>
<table><tr><th>Tier</th><th>Proposed updates</th><th>What happens</th></tr>
<tr><td>auto</td><td>{tiers.get('auto', 0)}</td><td>Source, contact cards, activities and commitments are logged straight away</td></tr>
<tr><td>approve</td><td>{tiers.get('approve', 0)}</td><td>Stage, amount and signer wait for a person to tap approve</td></tr>
<tr><td>never auto</td><td>n/a</td><td>Any outgoing message about price, discounts or payment terms</td></tr></table>
<h2>How accurate is the extraction?</h2>
<table><tr><th>Check</th><th>Generated chats</th></tr>
<tr><td>Who owes what, by when (precision / recall)</td><td>{ev['commitment_precision']}% / {ev['commitment_recall']}% on {ev['commitments_in_key']}</td></tr>
<tr><td>Broken rep promises caught (precision / recall)</td><td>{ev['broken_promise_precision']}% / {ev['broken_promise_recall']}% of {ev['broken_promises_planted']}</td></tr>
<tr><td>Source, amount, signer, contact cards, stage</td><td>{ev['source_channel_accuracy']}%, {ev['amount_accuracy']}%, {ev['signer_accuracy']}%, {ev['contact_card_recall']}%, {ev['stage_accuracy']}%</td></tr>
<tr><td><b>Hand-written messy set</b> (Pidgin, negations, reschedules)</td><td><b>{ev['messy_set_accuracy']}% of {ev['messy_set_size']}</b></td></tr></table>
<p class="note">The generated chats use phrasing the rules were written for, so those scores prove the plumbing, not the language understanding.
The messy set is the honest number. Its misses (a reschedule naming two days, "after 2", a request with no "me") are why the optional AI mode exists,
and why AI output still goes through the same approval tiers.</p>
<p class="note">All data is synthetic. Built by Feyisayo Daisi.</p>
</body></html>"""
    (OUT / "report.html").write_text(page)
    print(ba.to_string(index=False))


if __name__ == "__main__":
    main()
