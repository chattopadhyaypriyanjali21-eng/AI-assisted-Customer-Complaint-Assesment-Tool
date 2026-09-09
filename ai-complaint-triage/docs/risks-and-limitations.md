# Limitations, risks, and requirements

## Limitations of this capstone

| Limitation | Impact on the conclusions |
|---|---|
| 40 synthetic complaints; one author wrote the complaints, the gold labels **and the AI output**, in a single session | Figures measure internal consistency rather than independent agreement, so they are illustrative rather than validated — a fresh batch run would score lower. Treat 98% as a ceiling. Real intake text is also more elliptical, contains typos, mixes two complaints in one submission, and arrives in several languages. |
| Gold labels are one person's judgement | A real evaluation needs two independent complaint handlers and an inter-rater agreement figure. Where two experts disagree, no model result is meaningful. |
| The 12-minute manual baseline is an assumption | Not time-and-motion measured. The whole efficiency case rests on it. |
| No non-English complaints | An EU/APAC portfolio receives them. Untested here. |
| Single prompt, single model, temperature 0 | No ensembling, no self-consistency check, no fallback model. |
| Dashboard reads a static file | Not wired live to Supabase. Adequate for a capstone demo, not for operations. |
| Cost model excludes IT, security review, and change control | In a regulated company these are often larger than the build itself. |

## Risks

### Regulatory and quality

**Non-deterministic output in a GxP record.** The same complaint can produce a slightly
different summary on two runs. A validated system is expected to behave predictably.
*Mitigation:* temperature 0; the AI output is stored as a **draft**, never as the record of
decision; the human decision in `assessment_human` is the controlled record; prompt and model
version are stored on every row so any output can be reconstructed.

**Under-called severity leading to a missed report.** The failure that matters. A Critical
graded as Medium can miss a reporting clock.
*Mitigation:* the prompt instructs an upward bias on ambiguity; all Critical/High and all
Possible-MDR records go to human review; the under-call count is a monitored metric with
authority to disable auto-routing. Measured 0/60 on the pilot.

**Model or prompt change silently altering behaviour.** A provider model update is a change to
a validated system.
*Mitigation:* pin the model version; re-run the 60-record regression set before any change is
promoted; treat the evaluation script as the validation protocol.

### Operational

**Automation bias.** Handlers stop reading and start clicking Accept. See
`docs/human-in-the-loop.md` — complaint text shown before the draft, 10% silent audit,
edit rate monitored, throughput never the sole performance measure.

**Hallucinated facts in a regulated record.** A fabricated lot number or invented patient
outcome would be an audit finding.
*Mitigation:* explicit "never invent" instruction; every unstated field must return
`Not stated` and appear in `missing_info`; extracted lot numbers are validated against the
batch master before use.

**Skill erosion.** If handlers only ever confirm drafts, the ability to assessment cold decays,
and so does the ability to catch a bad draft.
*Mitigation:* rotate a share of complaints through blind manual assessment; that sample doubles
as the ongoing accuracy benchmark.

### Data protection and security

**PHI leaving the environment.** Complaint text routinely contains health information and
sometimes identifiers.
*Requirements:* zero-retention API configuration; a signed business associate / data
processing agreement before any real complaint text is sent; regional endpoint selection for
EU data; a de-identification pass on obvious direct identifiers at intake; and — as this
project's own C-1035 record shows — a defined privacy incident route, because complaint text
sometimes discloses a *third party's* data.

**Prompt injection through the complaint text.** The input is untrusted free text supplied by
the public. A reporter could submit text that attempts to instruct the model.
*Mitigation:* complaint text is delimited and passed as data; output is constrained to closed
enum values that are rejected at the database layer if invalid; a record that fails schema
validation goes to human review rather than being retried.

**Availability.** If the API is unreachable, intake must not stop.
*Mitigation:* complaints are written to Supabase before the model is called; assessment is a
separate asynchronous step; failure means a record sits in the human queue unassessed, which is
exactly the status quo process.

## Requirements before production

**Must have**
- Time-and-motion study of the current manual process (validates A2)
- Two-rater gold set of at least 300 real, de-identified complaints
- Signed data processing agreement and zero-retention configuration
- Validation protocol, IQ/OQ/PQ documentation, and change control for prompt and model
- Named system owner and QA approver
- 90-day shadow-mode pilot with zero serious under-calls before auto-routing is enabled

**Should have**
- Live Supabase-backed dashboard with the monthly agreement control chart
- Multilingual evaluation for EU and APAC intake
- Automated regression run on the 60-record set in the deployment pipeline

**Explicitly out of scope**
- Automated MDR reportability decisions — that determination stays with Regulatory Affairs
- Auto-closing complaints, or generating outbound correspondence to reporters
- Auto-routing anything graded Critical or High, under any circumstances
