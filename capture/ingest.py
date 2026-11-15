"""
Turn raw WhatsApp Cloud API webhook events into one clean message table.

With Coexistence, reps keep using the WhatsApp Business app on their phone.
Inbound messages arrive as "messages" events; what reps send from the app
arrives as "smb_message_echoes". Nothing depends on a rep remembering to export.

Voice notes arrive as audio media. They are matched to a transcript
(data/voice_transcripts.csv stands in for a speech-to-text service).
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, OUT, reps  # noqa: E402

WAT_TZ = timezone(timedelta(hours=1))


def load_transcripts() -> dict:
    with open(DATA / "voice_transcripts.csv") as f:
        return {r["media_id"]: r["transcript"] for r in csv.DictReader(f)}


def ingest(path: Path = DATA / "webhook_events.jsonl") -> pd.DataFrame:
    pnid_to_rep = {f"PNID_{rid}": rid for rid in reps()}
    transcripts = load_transcripts()
    rows = []
    for line in open(path):
        ev = json.loads(line)
        for entry in ev.get("entry", []):
            for ch in entry.get("changes", []):
                v, field = ch["value"], ch["field"]
                rep = pnid_to_rep.get(v["metadata"]["phone_number_id"])
                if field == "messages":
                    msgs, direction = v.get("messages", []), "in"
                    profile = {c["wa_id"]: c["profile"]["name"] for c in v.get("contacts", [])}
                elif field == "smb_message_echoes":
                    msgs, direction, profile = v.get("message_echoes", []), "out", {}
                else:
                    continue
                for m in msgs:
                    client = m["from"] if direction == "in" else m["to"]
                    text, contacts = "", None
                    if m["type"] == "text":
                        text = m["text"]["body"]
                    elif m["type"] == "audio":
                        text = transcripts.get(m["audio"]["id"], "")
                    elif m["type"] == "contacts":
                        contacts = [{"name": c["name"]["formatted_name"], "phone": c["phones"][0].get("wa_id") or c["phones"][0]["phone"].lstrip("+")}
                                    for c in m["contacts"]]
                    ref = m.get("referral") or {}
                    rows.append({
                        "msg_id": m["id"], "ts": datetime.fromtimestamp(int(m["timestamp"]), tz=WAT_TZ).replace(tzinfo=None),
                        "client_phone": client, "client_name": profile.get(client, ""), "rep": rep,
                        "direction": direction, "type": m["type"], "text": text,
                        "contacts": json.dumps(contacts) if contacts else "",
                        "ad_source_id": ref.get("source_id", ""), "ctwa_clid": ref.get("ctwa_clid", ""),
                        "ad_headline": ref.get("headline", ""),
                    })
    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    return df


def main():
    df = ingest()
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / "messages.csv", index=False)
    print(f"ingested {len(df)} messages from {df.client_phone.nunique()} conversations "
          f"({(df.type == 'audio').sum()} voice notes transcribed)")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    main()
