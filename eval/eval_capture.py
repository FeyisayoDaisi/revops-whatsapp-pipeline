"""
Score the capture layer against the answer key the generator planted.

  source      did we name the right channel (and the right ad, agent or referrer)?
  commitments precision and recall on who owes what by when (exact due time)
  status      did we flag the rep promises that were really broken?
  amount, signer, contacts, stage

Plus a hand-written "messy" set (data/messy_messages.csv): Pidgin, negations, past tense,
vague promises. Phrasing the generator never produced. This is the honest test.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, OUT, TODAY, answer_key, write_json  # noqa: E402
from pipeline.extract import extract_rules  # noqa: E402


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def main():
    key = {k["lead_id"]: k for k in answer_key()}
    crm = pd.read_csv(DATA / "crm_manual.csv", dtype={"phone": str})
    phone_to_lead = dict(zip(crm.phone, crm.lead_id))
    deals = pd.read_csv(OUT / "deals_captured.csv", dtype={"client_phone": str, "source_detail": str}, keep_default_na=False)
    commits = pd.read_csv(OUT / "commitments.csv", dtype={"client_phone": str}, parse_dates=["due"])
    res, misses = {}, []

    # source
    ok = det = 0
    for d in deals.itertuples():
        t = key[phone_to_lead[d.client_phone]]["source"]
        if d.source == t["channel"]:
            ok += 1
            want = {"ad": t["ad_id"], "field": t["agent"], "referral": t["referrer"]}.get(t["channel"])
            if want is None or str(want).startswith(str(d.source_detail)) and d.source_detail:
                det += 1
            else:
                misses.append({"check": "source_detail", "lead": phone_to_lead[d.client_phone], "want": want, "got": d.source_detail})
        else:
            misses.append({"check": "source", "lead": phone_to_lead[d.client_phone], "want": t["channel"], "got": d.source})
    res["source_channel_accuracy"] = pct(ok, len(deals))
    res["source_detail_accuracy"] = pct(det, len(deals))

    # commitments
    truth = {c["msg_id"]: c for k in key.values() for c in k["commitments"]}
    pred = {r.msg_id: r for r in commits.itertuples()}
    tp = sum(1 for m, p in pred.items() if m in truth and truth[m]["owner"] == p.owner
             and datetime.fromisoformat(truth[m]["due"]) == p.due.to_pydatetime())
    for m, t in truth.items():
        p = pred.get(m)
        if not p or p.owner != t["owner"] or datetime.fromisoformat(t["due"]) != p.due.to_pydatetime():
            misses.append({"check": "commitment", "msg": m, "want": f"{t['owner']} {t['due']}",
                           "got": f"{p.owner} {p.due}" if p else "none"})
    for m in pred:
        if m not in truth:
            misses.append({"check": "commitment_false_positive", "msg": m, "want": "none", "got": pred[m].said})
    res["commitment_precision"] = pct(tp, len(pred))
    res["commitment_recall"] = pct(tp, len(truth))
    res["commitments_in_key"] = len(truth)

    # broken-promise detection (rep promises with a planted kept/missed outcome, due before today)
    planted = [(m, t) for m, t in truth.items() if t["owner"] == "rep" and "kept" in t
               and datetime.fromisoformat(t["due"]) < TODAY]
    broken = {m for m, t in planted if not t["kept"]}
    flagged = {m for m, t in planted if m in pred and pred[m].status == "overdue"}
    res["broken_promise_precision"] = pct(len(broken & flagged), len(flagged))
    res["broken_promise_recall"] = pct(len(broken & flagged), len(broken))
    res["broken_promises_planted"] = len(broken)

    # amount, signer, contacts, stage
    amt_ok = amt_n = sig_ok = sig_n = con_ok = con_n = st_ok = 0
    for d in deals.itertuples():
        t = key[phone_to_lead[d.client_phone]]
        if t["amounts"]:
            amt_n += 1
            amt_ok += str(d.amount) not in ("", "nan") and int(float(d.amount)) == t["amounts"][-1]["value"]
        if t["signer"]:
            sig_n += 1
            sig_ok += d.signer == t["signer"]["name"]
        con_n += len(t["contacts"])
        con_ok += sum(c["phone"] in (d.contacts or "") for c in t["contacts"])
        st_ok += d.stage == t["stage"]
    res.update({"amount_accuracy": pct(amt_ok, amt_n), "signer_accuracy": pct(sig_ok, sig_n),
                "contact_card_recall": pct(con_ok, con_n), "stage_accuracy": pct(st_ok, len(deals))})

    # messy, hand-written set
    m_ok, m_rows = 0, []
    with open(DATA / "messy_messages.csv") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        sent = datetime.fromisoformat(r["sent"])
        x = extract_rules(r["text"], r["direction"], sent)["commitment"]
        want_owner, want_due = r["owner"] or None, r["due"] or None
        got_owner = x["owner"] if x else None
        got_due = x["due"].isoformat(timespec="minutes") if x else None
        good = got_owner == want_owner and (want_due is None or got_due == want_due)
        m_ok += good
        m_rows.append({**r, "got_owner": got_owner or "", "got_due": got_due or "", "correct": int(good)})
    res["messy_set_accuracy"] = pct(m_ok, len(rows))
    res["messy_set_size"] = len(rows)
    pd.DataFrame(m_rows).to_csv(OUT / "eval_messy_set.csv", index=False)
    pd.DataFrame(misses).to_csv(OUT / "eval_misses.csv", index=False)
    write_json(OUT / "eval_capture.json", res)
    for k, v in res.items():
        print(f"  {k:28s} {v}")


if __name__ == "__main__":
    main()
