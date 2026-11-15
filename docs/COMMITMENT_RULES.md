# Commitment rules

A commitment is a message where someone takes on a dated job. The system logs it, gives it an owner and a due time, and checks later whether it was kept.

## Who owes it

| Message | Owner |
| --- | --- |
| Client asks us to act: "Call me Monday 8am", "Send the revised quote by Friday", "Tomorrow 9am works for me" | rep |
| Rep promises: "I'll send the proposal tomorrow", "I go call you Tuesday" | rep |
| Client promises: "We'll revert by Wednesday", "Let me discuss with my MD and get back to you" | client |

Not commitments: negations ("Don't call me Friday"), past events ("You said you'd send it Monday"), and anything without a date ("I'll think about it", "maybe next month").

## When it is due

- A weekday means the next one after the message date. "Monday" said on a Monday is next Monday.
- A day with no time is due at 17:00.
- Morning is 09:00, afternoon 14:00, evening 17:00, "first thing" 09:00.
- "Next week" is next Monday 10:00. "End of the week" or "before weekend" is this Friday 17:00.
- A bare hour after "at", "by", "for" or "around": 7 to 11 is morning, 12 is noon, 1 to 6 is afternoon.
- Numbers followed by staff, sites, people, million or k are never times.

## Kept or not

- Rep-owned: kept if the rep sends a message after the promise and no later than 3 hours after a timed due (7 hours after a 17:00 day deadline).
- Client-owned: kept if the client messages within 24 hours of the due time. Otherwise it is lapsed, and the rep gets a check-in task.
- A promise still inside its window is pending.

These conventions are a choice, written down so the system and the team mean the same thing by "Monday".
