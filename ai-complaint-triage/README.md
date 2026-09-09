# AI-Powered Customer Complaint Assessment
### Medical devices & pharma · MBA + Generative AI for Business capstone

A complaint arrives as a paragraph of free text from a patient, nurse, or distributor.
Before anyone can act on it, a trained handler has to read it, work out what product it is,
decide how serious it is, notice what the reporter forgot to tell them, write a summary, and
send it to the right team. That takes **10–15 minutes per complaint** and it is the same
judgement call, thousands of times a year.

This project puts a GenAI step between the intake form and the work queue. The model drafts
the structured record; a human handler approves it. Measured on 40 synthetic complaints:

| | Fully manual | Keyword rules (no GenAI) | **Claude + human review** |
|---|---|---|---|
| Minutes per complaint | 12.0 | 5.0 | **4.1** |
| Category accuracy | — | 72% | **98%** |
| Product identification | — | 98% | **100%** |
| Severity accuracy | — | 42% | **95%** |
| Routing accuracy | — | 65% | **85%** |
| **Serious severity under-calls** | — | **15 of 40** | **1 of 40** |
| Human review required | 100% | 100% | **70%** |

The middle column matters as much as the right one. A rules engine is the cheap alternative
any IT team would propose first — and it silently graded 15 harm-related complaints down to
Medium or Low. In a regulated complaint process that is not a productivity problem, it is a
reportability failure. **That gap is where the GenAI value actually sits.**

Reproduce every number with `python scripts/assessment.py evaluate`. The same table is rendered
on the dashboard — both are produced by the same scoring code, so they cannot drift apart.

---

## 1. The business problem

A mid-size device and pharma company receives roughly **6,000 complaints a year** across a web
form, email, phone, and a distributor portal. Post-market surveillance rules require that
complaints are assessed for reportability quickly and consistently, so the intake step is
non-negotiable — but it is entirely manual and entirely judgement-based.

Three costs fall out of that:

1. **Handler time.** ~12 minutes of reading and re-typing per complaint, ~1,200 hours a year.
2. **Rework from misrouting.** A complaint sent to Customer Service that should have gone to
   Pharmacovigilance loses days before anyone notices.
3. **Inconsistency.** Two handlers grade the same complaint differently. Trend data built on
   inconsistent categories cannot support a CAPA decision.

## 2. The workflow

```
Intake form ─► Supabase (complaints)
                    │
                    ▼
            Claude assessment prompt          ← one call, one JSON record
                    │
                    ▼
          Supabase (assessment_ai)            ← the AI draft, never overwritten
                    │
        ┌───────────┴────────────┐
        │                        │
  needs_human_review        auto-routed
   = TRUE  (70%)            (30% · low severity only)
        │                        │
        ▼                        │
  Handler review queue ──────────┤
   accept / edit / reject        │
        │                        │
        ▼                        ▼
  Supabase (assessment_human) ─► Team work queue ─► Dashboard
```

The escalation gate is a hard rule, not a preference. A record goes to a human if **any** of:
severity is Critical or High · MDR flag is Yes or Possible · confidence < 0.75 · the product
could not be identified. Nothing that touches patient harm is ever auto-routed.

## 3. Where GenAI actually adds value

| Step | Could rules do it? | What the model adds |
|---|---|---|
| Categorise | Partly (72%) | Reads intent, not keywords. "Nobody explained how to prime it" is training, not a malfunction. |
| Identify the product | Mostly (98%) | Resolves "Glucotrack meter", "infusion pump", and blank fields against the catalogue. |
| Grade severity | **No (42%)** | Infers harm from narrative — "woke up gasping", "returned to theatre", "fluid overloaded" — with no keyword for any of them. |
| **Spot missing information** | **No** | Rules can only see what is present. The model names what is *absent*: lot number, event date, patient outcome. This is the real bottleneck — chasing facts, not typing. |
| Summarise | No | 25-word factual line, so a handler assesses from the queue without opening the record. |
| Suggest next action | No | Turns a complaint into a task. |
| Route | Partly (65%) | Caught C-1020 — a misdelivered package that disclosed another patient's name — as a **privacy incident**, not a shipping issue. No keyword router finds that. |

## 4. Business metrics

**Primary — efficiency: average intake-to-routing handling time.**
Target ≤ 5 min. Measured **4.1 min vs 12.0 manual (−66%)**.
At 6,000 complaints/year that is ~790 hours, ≈0.4 FTE, ≈**$33k/year**.

**Primary — safety guardrail: serious severity under-call rate.**
Percentage of complaints the human reviewer upgrades from Medium/Low to High/Critical.
Target 0%. Measured **1 of 40 (2.5%)** against **15 of 40 for the rules engine**.
This metric has veto power: it is why the auto-route path is restricted to Low and Medium
records with no MDR flag, and why 70% of records still reach a human.

**Supporting — first-time-right routing.** 85% vs 65% for rules. Note this is *not* claimed as
a saving: 85% routing accuracy is a 15% misroute rate, the same rate assumed for manual
intake, so the model beats the rules alternative here but not a human. See
`docs/business-case.md`.

> **Cost note worth making in the presentation:** the model cost is roughly **$0.01 per
> complaint — under $200/year**. The expense in a regulated environment is not inference, it is
> validation, prompt version control, and the human review capacity you must keep staffed.

## 5. Human review point

`docs/human-in-the-loop.md` defines it. Short version: the AI never closes a complaint. It
produces a *draft* that a qualified handler accepts, edits, or rejects in the review queue,
and every one of those decisions is written to `assessment_human` — which doubles as the ongoing
accuracy measurement (`v_ai_agreement`). The human review step is not a safety blanket bolted
on at the end; it is the data source that tells you whether the system still works next
quarter.

**The one under-call proves the point.** On C-1008 the model graded a German-only labelling
breach as Medium; the reviewer upgraded it to High. That is exactly the correction the review
queue exists to catch, and it is why the guardrail metric is measured rather than assumed.

## 6. Limitations, risks, requirements

See `docs/risks-and-limitations.md`. The four that would sink the project if ignored:
model non-determinism in a GxP record, over-trust by a handler clicking "Accept" 60 times an
hour, PHI leaving the environment through the API, and the fact that **one author wrote the
complaints, the gold labels and the AI output** — so these accuracy figures are a design
demonstration, not a validation study.

---

## Repository contents

| Path | What it is |
|---|---|
| `data/complaints_raw.csv` | 40 synthetic complaints — messy, realistic, no real patient data |
| `data/products.csv` | 10-product catalogue (8 devices, 2 Rx) |
| `data/labels_gold.csv` | Human-reviewed ground truth used to score both engines |
| `data/assessment_ai.csv` | Claude output — the main artifact |
| `data/assessment_baseline.csv` | Keyword-rules output — generated, the comparison arm |
| `prompts/assessment_prompt.md` | The prompt, with the design rationale for each choice |
| `scripts/assessment.py` | `run` / `evaluate` / `dashboard` — standard library only |
| `sql/01_schema.sql` | Supabase schema: 3 tables, 2 reporting views |
| `dashboard/index.html` | Static dashboard — trends, severity mix, engine comparison, live review queue |
| `docs/business-case.md` | Assumptions, ROI arithmetic, what would falsify it |
| `docs/human-in-the-loop.md` | The review SOP and escalation rules |
| `docs/risks-and-limitations.md` | Risks, mitigations, and deployment requirements |

## Running it

```powershell
cd scripts
python assessment.py run --engine keyword    # build the baseline arm
python assessment.py evaluate                # print the comparison table
python assessment.py dashboard               # refresh dashboard/data.js
```

Then open `dashboard/index.html` in a browser — no server needed. Python 3 only; nothing to
install. The dashboard charts load Chart.js from a CDN, so they need internet; the KPI cards
and review queue work offline.

To regenerate the AI arm yourself: `pip install anthropic`, set `ANTHROPIC_API_KEY`, then
`python assessment.py run --engine claude`. Roughly $0.50 of credits for the 40 records.
`data/assessment_ai.csv` ships as a saved artifact, so `evaluate` and `dashboard` run offline
with no API access. If you do re-run it, re-run `evaluate` and update the table above.

## Tool stack

| Tool | Used for |
|---|---|
| **Claude (Sonnet 4.5)** | The assessment call — classification, extraction, gap detection, summarisation |
| **Claude Code** | Built the pipeline, the scoring harness, and the dashboard |
| **Supabase (Postgres)** | Intake table, AI draft table, human decision table, agreement views |
| **Web form** | Intake — writes straight to `complaints` |
| **CSV / spreadsheet** | Synthetic dataset, gold labels, and the ROI model — kept flat so a non-technical reviewer can open them |
| **Anthropic Messages API** | Programmatic access, temperature 0, versioned prompt |

## Data statement

All 40 complaints, contact addresses, lot numbers, product names, and companies are
**synthetic and invented for this capstone**. No real patient, customer, or product data was
used. Product names do not correspond to any marketed device or drug.
