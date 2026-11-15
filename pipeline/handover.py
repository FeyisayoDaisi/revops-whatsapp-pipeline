"""
A rep resigned on Friday. Does the pipeline leave with them?

Because every chat on the company number was captured, each open deal is handed to
another rep with the full story: who they spoke to, who signs, the amount, what was
promised and what is overdue. The client keeps messaging the same company number.
The file also shows what the hand-kept CRM held for the same deals, for comparison.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, OUT, TODAY, reps  # noqa: E402


def open_deals(deals: pd.DataFrame) -> pd.DataFrame:
    return deals[~deals.stage.isin(["won", "lost"]) & (deals.days_quiet <= 45)]


def main():
    R = reps()
    left = [r for r in R.values() if r.get("left_on")]
    deals = pd.read_csv(OUT / "deals_captured.csv", dtype={"client_phone": str}, keep_default_na=False,
                        parse_dates=["last_msg", "last_in", "last_out"])
    commits = pd.read_csv(OUT / "commitments.csv", dtype={"client_phone": str}, parse_dates=["due"])
    crm = pd.read_csv(DATA / "crm_manual.csv", dtype={"phone": str}, keep_default_na=False)
    active = [r for r in R if not R[r].get("left_on")]
    load = open_deals(deals).groupby("rep").size().reindex(active, fill_value=0).to_dict()
    rows, md = [], []
    for rep in left:
        mine = open_deals(deals[deals.rep == rep["id"]]).copy()
        mine["amt"] = pd.to_numeric(mine.amount, errors="coerce").fillna(0)
        mine = mine.sort_values("amt", ascending=False)
        md.append(f"# Handover: {rep['name']} left on {rep['left_on']}\n")
        md.append(f"{len(mine)} open deals, ₦{mine.amt.sum():,.0f} quoted. Each one moves to the rep with the lightest load. "
                  "Clients keep messaging the same company number, so nothing changes on their side.\n")
        for d in mine.itertuples():
            new = min(load, key=load.get)
            load[new] += 1
            c = commits[commits.client_phone == d.client_phone].sort_values("due")
            owed = c[c.status.isin(["overdue", "pending"]) & (c.owner == "rep")]
            theirs = c[c.status.isin(["lapsed", "pending"]) & (c.owner == "client")]
            m = crm[crm.phone == d.client_phone].iloc[0]
            rows.append({"client_phone": d.client_phone, "client": d.client_name, "from_rep": rep["id"], "to_rep": new,
                         "stage": d.stage, "amount": d.amount, "signer": f"{d.signer} ({d.signer_role})" if d.signer else "",
                         "source": f"{d.source} {d.source_detail}".strip(),
                         "we_owe": "; ".join(f"{r.topic} (due {r.due:%a %d %b %H:%M}, {r.status})" for r in owed.itertuples()),
                         "they_owe": "; ".join(f"{r.topic} (due {r.due:%a %d %b}, {r.status})" for r in theirs.itertuples()),
                         "last_message": d.last_text[:90], "days_quiet": d.days_quiet,
                         "crm_had_stage": m.stage, "crm_had_amount": m.amount, "crm_had_signer": m.signer,
                         "crm_had_next_step": m.next_step})
            md.append(f"## {d.client_name} → {R[new]['name']}\n"
                      f"- Stage: **{d.stage}** · Amount: {'₦{:,.0f}'.format(float(d.amount)) if d.amount else 'not quoted yet'} · Source: {d.source} {d.source_detail}\n"
                      f"- Who signs: {rows[-1]['signer'] or 'not named yet'}\n"
                      f"- We owe: {rows[-1]['we_owe'] or 'nothing open'}\n"
                      f"- They owe: {rows[-1]['they_owe'] or 'nothing open'}\n"
                      f"- Last message ({d.days_quiet} days ago): \"{d.last_text[:90]}\"\n"
                      f"- What the hand-kept CRM had: stage {m.stage or 'blank'}, amount {m.amount or 'blank'}, "
                      f"signer {m.signer or 'blank'}, next step {m.next_step or 'blank'}\n")
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "handover.csv", index=False)
    (OUT / "handover.md").write_text("\n".join(md))
    print(f"handover: {len(out)} open deals moved, {(out.we_owe != '').sum()} with promises we still owe")


if __name__ == "__main__":
    main()
