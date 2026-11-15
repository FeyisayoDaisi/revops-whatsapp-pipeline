"""Run with: python -m pytest -q"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.extract import extract_rules, parse_amount  # noqa: E402
from pipeline.timeparse import parse_due  # noqa: E402

THU = datetime(2026, 11, 12, 10, 15)


def test_weekday_means_next_one():
    assert parse_due("Call me Thursday 3pm", THU) == datetime(2026, 11, 19, 15, 0)


def test_day_without_time_is_5pm():
    assert parse_due("by Monday", THU) == datetime(2026, 11, 16, 17, 0)


def test_bare_hour_after_by_is_afternoon_when_small():
    assert parse_due("tomorrow by 2", THU) == datetime(2026, 11, 13, 14, 0)


def test_staff_count_is_not_a_time():
    assert parse_due("Monday, we have 15 staff", THU) == datetime(2026, 11, 16, 17, 0)


def test_naira_formats():
    assert parse_amount("comes to ₦6,200,000") == 6_200_000
    assert parse_amount("total is N6.2m") == 6_200_000
    assert parse_amount("6.2 million naira per year") == 6_200_000


def test_negation_and_past_are_not_commitments():
    assert extract_rules("Don't call me on Friday", "in", THU)["commitment"] is None
    assert extract_rules("You said you'd send it Monday", "in", THU)["commitment"] is None


def test_owner():
    assert extract_rules("I go call you tomorrow afternoon", "out", THU)["commitment"]["owner"] == "rep"
    assert extract_rules("We will revert latest Thursday", "in", THU)["commitment"]["owner"] == "client"
    assert extract_rules("Abeg call me Monday by 10", "in", THU)["commitment"]["owner"] == "rep"


def test_signer():
    s = extract_rules("Final approval sits with our CFO, Mrs Okafor.", "in", THU)["signer"]
    assert s == {"name": "Mrs Okafor", "role": "CFO"}


def test_price_from_is_not_a_quote():
    assert extract_rules("It starts from N350k a month", "out", THU)["amount"] is None
