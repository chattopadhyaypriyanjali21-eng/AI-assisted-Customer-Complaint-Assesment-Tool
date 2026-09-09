# Human review point

The AI does not decide anything. It prepares a draft. A qualified complaint handler makes the
decision, and that decision is what the business acts on and what the auditor sees.

## The gate

A complaint is held for human review if **any** condition is true:

| Condition | Why |
|---|---|
| `severity` is Critical or High | Anything with a harm pathway is a human call, always |
| `mdr_reportable_flag` is Yes or Possible | Reportability is a regulatory determination, not a model output |
| `confidence` < 0.75 | The model is telling you it is guessing |
| `product_id` = UNKNOWN | You cannot open a complaint file against an unidentified product |

On the pilot set this holds **28 of 40 (70%)**. The remaining 30% — low-severity billing,
shipping, app, and usability items — auto-route to the owning team with a spot-check only.

The gate is deliberately conservative. A false alarm costs 3 minutes of a handler's time; a
missed Critical costs a regulatory finding. That asymmetry should be stated out loud in the
presentation, because it is the whole reason the threshold sits where it does.

## What the handler does

The review queue shows the AI draft side by side with the original complaint text. The handler
takes one of three actions, in a target of 3–5 minutes:

- **Accept** — the draft is correct. Commit to `assessment_human` and route.
- **Edit** — correct category, severity, team, or MDR flag. The AI draft in `assessment_ai` is
  **never overwritten**; the correction is a separate row. You need both to measure agreement
  and to answer "what did the system say, and what did the human decide?"
- **Reject** — the draft is unusable (wrong product, garbled input). Assessment from scratch and
  log the reason.

The handler is also responsible for the `missing_info` list — contacting the reporter for lot
number, event date, or patient outcome. This is the step that actually determines how fast a
complaint can be closed, and it is the step the model helps most with, because it names the
gaps in seconds instead of on a second read-through.

## Guarding against rubber-stamping

The realistic failure mode is not a bad model. It is a handler who clicks Accept 60 times an
hour because the draft is usually right. Automation bias is the top risk in this design.

Four controls:

1. **The queue is sorted by priority, not arrival.** Highest-consequence work gets fresh
   attention, not end-of-shift attention.
2. **The complaint text is shown first, the AI draft second.** The handler forms a view before
   seeing the suggestion.
3. **Silent audit sample.** 10% of Accepted records are independently re-assessed monthly by a
   second reviewer. If accept-without-edit rate exceeds 95% while the audit disagrees, the
   handler is retrained.
4. **Edit rate is a monitored metric, not a performance target.** Handlers are never measured
   on throughput alone — that is how you manufacture rubber-stamping.

## The review data is the monitoring system

Every human decision writes to `assessment_human`, and `v_ai_agreement` turns those decisions into
a monthly control chart: category agreement, severity agreement, routing agreement, severity
under-calls, average review minutes.

This gives you drift detection for free. If Anthropic ships a new model version, or the prompt
is edited, or the complaint mix shifts because a new product launched, agreement moves before
anything visible breaks.

**Standing rule:** if severity under-calls in `v_ai_agreement` is greater than zero in any
month, the auto-route path is disabled and 100% of complaints go to human review until the
cause is found and the fix is revalidated.

## Roles

| Role | Owns |
|---|---|
| Complaint handler | Accept / edit / reject; chase missing information |
| QA lead | Monthly agreement review; authority to disable auto-routing |
| Regulatory affairs | Final MDR reportability determination — never delegated to the model |
| System owner | Prompt version control; revalidation after any model or prompt change |
