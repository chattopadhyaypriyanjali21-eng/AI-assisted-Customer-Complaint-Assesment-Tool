# Business case

Every number here is either measured on the 60-complaint pilot set or listed as an explicit
assumption. Nothing is a black box — reproduce the measured rows with
`python scripts/assessment.py evaluate`.

## Assumptions

| # | Assumption | Value | Where it came from | If it is wrong |
|---|---|---|---|---|
| A1 | Annual complaint volume | 6,000 | Typical mid-size device + pharma portfolio | Savings scale linearly; below ~2,000/yr the build cost is hard to justify |
| A2 | Manual intake-to-routing time | 12 min | Midpoint of the observed 10–15 min range | The single most load-bearing assumption. **Time 30 complaints with a stopwatch before funding this.** |
| A3 | Fully-loaded handler cost | $42/hr (~$87k/yr) | Complaint handler / QA associate | Linear |
| A4 | Manual misroute rate | 15% | Assumption, not measured | Only affects the supporting metric |
| A5 | Rework per misroute | 20 min | Assumption | Only affects the supporting metric |
| A6 | Model cost | ~$0.01/complaint | ~1,500 input + 400 output tokens, Sonnet pricing | Negligible either way |

## Measured on the pilot set (n = 40)

| | Manual | Keyword rules | Claude + review |
|---|---|---|---|
| Minutes per complaint | 12.0 | 5.0 | **4.1** |
| Category accuracy | — | 72% | **98%** |
| Product ID accuracy | — | 98% | **100%** |
| Severity accuracy | — | 42% | **95%** |
| Routing accuracy | — | 65% | **85%** |
| Serious under-calls | — | 15 | **1** |
| Human review rate | 100% | 100% | **70%** |

Time model: reviewed records cost 5 min (read the draft, check it, accept or edit);
auto-routed records cost 2 min (spot-check only). 70% × 5 + 30% × 2 = **4.1 min**.

## Annual arithmetic

**Efficiency (primary metric)**
```
6,000 complaints × 7.9 min saved = 47,400 min = 790 hours
790 hours × $42                                = $33,200
```

**Rework avoided (supporting metric)**
```
Manual misroutes  6,000 × 15% × 20 min = 300 hours
AI misroutes      6,000 × 15% × 20 min = 300 hours
Difference                             =   0 hours
```

> Note: **no rework saving is claimed.** Measured AI routing accuracy is 85%, i.e. a 15%
> misroute rate — identical to the rate assumed for manual intake in A4. On this pilot the
> model does not beat a human at routing, so this line is worth nothing. The 20-point gain is
> over the *rules* alternative (65%), which is not the comparator this case runs against.
> If prompt work lifts routing above 85% the line becomes real money; today it is zero.

**Gross annual benefit ≈ $33,200 — efficiency alone.**

**Costs**
```
Build (one-off, ~3 weeks of one analyst + review)      $22,000
Validation & documentation (one-off, regulated system) $12,000
Model + Supabase (annual)                                 $600
Prompt maintenance, revalidation, monitoring (annual)   $10,000
```

Year 1 net ≈ **−$11,400**. Year 2 onward ≈ **+$22,600/year**.
Payback lands around the middle of year 2.

**On the money alone this project is marginal, and the presentation should say so.** The
efficiency case does not carry it. It is carried by the second primary metric.

## The part that is not in the spreadsheet

The keyword baseline under-graded **15 of 40** complaints that involved actual or credible
patient harm. The AI arm under-graded **1**. Under-calling severity at intake is how a
reportable event misses its filing clock. One late or missed report can cost more in
remediation, warning-letter exposure, and audit response than the entire program saves in a
decade.

The correct framing for the exec audience:

> The productivity saving pays for the system. The severity-grading accuracy is why you
> build it.

## What would falsify this case

- **A2 is wrong.** If manual intake is really 6 minutes, gross benefit halves and the project
  does not clear its cost. Measure it first.
- **Review rate does not fall.** If quality assurance insists on 100% human review, per-complaint
  time is 5 min not 4 min, and benefit drops ~40%. Still positive, but thinner.
- **Handlers do not redeploy.** 0.4 FTE of saved time is only money if that capacity moves to
  investigation and CAPA backlog. If it evaporates into slack, the return is quality-only.
- **Agreement rate decays.** If `v_ai_agreement` drops below 85% after a model or prompt
  change and cannot be recovered, auto-routing is disabled and the time saving is lost.

## Pilot design

Run 90 days in shadow mode: the model assesses every incoming complaint, humans continue to
work manually, and neither sees the other. Compare on `v_ai_agreement`. Go-live on the
auto-route path only if serious under-calls are zero across the full shadow period.
