"""
Who should get a sales meeting?

The old rule: anyone who says yes to a call gets one. Volume looks great, then half the
meetings no-show and reps burn their week chasing people who were never going to buy.

This scores every lead from what they said in the chat BEFORE the meeting was booked
(no peeking at outcomes): fit (size, sites, industry) and intent (timeline, a specific time,
price-first questions, vague answers, source). Every point has a plain reason.

The meeting threshold is chosen on August and September leads only, then tested on
October and November leads it has never seen. Leads under the threshold are not dropped:
they go to a nurture sequence and can earn a meeting later.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, OUT, TODAY, company, write_json  # noqa: E402
from pipeline.timeparse import has_clock_time  # noqa: E402

TARGET = company()["target_industries"]
URGENT = r"\b(next month|this quarter|urgently|as soon as possible|asap|from january|current vendor is leaving)\b"
VAGUE = r"\b(not sure|still thinking|maybe|next year|just checking)\b"
PRICE_FIRST = r"\b(how much|price list|your price|cost)\b"


def score_lead(conv: pd.DataFrame, source: str) -> tuple[int, list[str]]:
    """Score using only inbound messages up to and including the meeting acceptance."""
    inbound = conv[conv.direction == "in"].text.fillna("").tolist()
    pre = []
    for t in inbound:
        pre.append(t)
        if re.search(r"\b(call me|let'?s talk|works for me|abeg call)\b", t, re.I):
            break
    text = " ".join(pre)
    s, why = 40, []
    m = re.search(r"\b(\d+)\s*(?:staff|of us|people|employees)\b", text)
    if m:
        n = int(m.group(1))
        if n >= 15:
            s += 20; why.append(f"+20 size: {n} staff")
        elif n < 10:
            s -= 25; why.append(f"-25 size: only {n} staff")
    m = re.search(r"\b(\d+)\s*sites\b", text)
    if m and int(m.group(1)) >= 2:
        s += 10; why.append(f"+10 {m.group(1)} sites")
    if any(re.search(rf"\b{re.escape(i)}\b", text, re.I) for i in TARGET):
        s += 5; why.append("+5 target industry")
    if re.search(URGENT, text, re.I):
        s += 20; why.append("+20 clear timeline")
    if re.search(VAGUE, text, re.I):
        s -= 15; why.append("-15 vague timeline")
    first_need = pre[1] if len(pre) > 1 else (pre[0] if pre else "")
    if re.search(PRICE_FIRST, first_need, re.I) and not re.search(r"\bstaff\b", first_need):
        s -= 25; why.append("-25 asked price before sharing any need")
    if pre and has_clock_time(pre[-1]):
        s += 10; why.append("+10 named a specific time")
    if source == "referral":
        s += 10; why.append("+10 referral")
    return max(0, min(100, s)), why


def main():
    msgs = pd.read_csv(OUT / "messages.csv", parse_dates=["ts"], keep_default_na=False, dtype={"client_phone": str})
    deals = pd.read_csv(OUT / "deals_captured.csv", dtype={"client_phone": str}, keep_default_na=False)
    crm = pd.read_csv(DATA / "crm_manual.csv", dtype={"phone": str})
    out = pd.read_csv(DATA / "outcomes.csv", parse_dates=["created", "meeting_time"])
    lead_of = dict(zip(crm.phone, crm.lead_id))
    rows = []
    for d in deals.itertuples():
        conv = msgs[msgs.client_phone == d.client_phone].sort_values("ts")
        sc, why = score_lead(conv, d.source)
        rows.append({"client_phone": d.client_phone, "lead_id": lead_of[d.client_phone], "source": d.source,
                     "score": sc, "reasons": "; ".join(why)})
    q = pd.DataFrame(rows).merge(out, on="lead_id", suffixes=("", "_o"))
    q.to_csv(OUT / "lead_scores.csv", index=False)

    # only meetings that have already happened (or were missed) can be judged
    judged = q[(q.accepted_meeting == 1) & q.meeting_time.notna() & (q.meeting_time <= TODAY)].copy()
    judged["showed"] = judged.showed.astype(int)
    split = pd.Timestamp(company()["train_until"]) + pd.Timedelta(days=1)
    train, test = judged[judged.created < split], judged[judged.created >= split]

    def stats(df, thr=None):
        b = df if thr is None else df[df.score >= thr]
        return {"meetings": len(b), "showed": int(b.showed.sum()), "no_shows": int(len(b) - b.showed.sum()),
                "show_rate": round(100 * b.showed.mean(), 1) if len(b) else None,
                "wins_from_meetings": int(b.won.sum()), "wins_available": int(df.won.sum())}

    # pick the threshold on TRAIN: highest show rate that still keeps at least 90% of wins
    best = None
    for thr in range(20, 85, 5):
        s = stats(train, thr)
        if s["wins_available"] and s["wins_from_meetings"] / s["wins_available"] >= .9:
            if best is None or s["show_rate"] > best[1]["show_rate"]:
                best = (thr, s)
    thr = best[0]
    res = {"threshold": thr, "rule": "book a meeting when score >= threshold; below it, nurture first",
           "train": {"book_everyone": stats(train), "scored": stats(train, thr)},
           "test": {"book_everyone": stats(test), "scored": stats(test, thr)}}
    t = res["test"]
    res["test"]["meetings_saved"] = t["book_everyone"]["meetings"] - t["scored"]["meetings"]
    res["test"]["no_shows_avoided"] = t["book_everyone"]["no_shows"] - t["scored"]["no_shows"]
    res["test"]["wins_kept_pct"] = round(100 * t["scored"]["wins_from_meetings"] / t["book_everyone"]["wins_from_meetings"], 1)
    # show rate by source (why "Source = Other" hides money)
    by_src = judged.groupby("source").agg(meetings=("showed", "size"), show_rate=("showed", "mean"), wins=("won", "sum"))
    by_src["show_rate"] = (100 * by_src.show_rate).round(1)
    by_src.to_csv(OUT / "show_rate_by_source.csv")
    res["show_rate_by_source"] = by_src.reset_index().to_dict("records")
    write_json(OUT / "qualification.json", res)
    print(f"threshold {thr} (picked on Aug-Sep). Oct-Nov test: show rate "
          f"{t['book_everyone']['show_rate']}% -> {t['scored']['show_rate']}%, "
          f"{res['test']['no_shows_avoided']} no-shows avoided, wins kept {res['test']['wins_kept_pct']}%")


if __name__ == "__main__":
    main()
