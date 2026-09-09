"""
Complaint assessment pipeline - three commands, standard library only (plus `anthropic` if
you want to re-run the AI engine yourself).

    python assessment.py run --engine keyword    # rules-only baseline (the "before" arm)
    python assessment.py run --engine claude     # Claude Sonnet 4.5 (the "after" arm)
    python assessment.py evaluate                # scores both arms against labels_gold.csv
    python assessment.py dashboard               # writes dashboard/data.js from the AI output

`--engine claude` needs ANTHROPIC_API_KEY. Everything else runs offline.
"""

import argparse
import csv
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "complaints_raw.csv"
GOLD = DATA / "labels_gold.csv"
PRODUCTS = DATA / "products.csv"
AI_OUT = DATA / "assessment_ai.csv"
BASE_OUT = DATA / "assessment_baseline.csv"
PROMPT = ROOT / "prompts" / "assessment_prompt.md"

FIELDS = [
    "complaint_id", "received_at", "channel", "reporter_type", "region", "category",
    "product_id", "product_name", "severity", "priority_score", "mdr_reportable_flag",
    "summary", "event_date", "lot_or_serial", "patient_involved", "patient_outcome",
    "device_returned", "units_affected", "missing_info", "suggested_next_action",
    "route_team", "confidence", "needs_human_review", "review_reason",
]

# Minutes of handler effort assumed by the business case. See docs/business-case.md.
MIN_MANUAL = 12.0
MIN_AI_AUTO = 2.0
MIN_AI_REVIEWED = 5.0


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


# --------------------------------------------------------------------------------------
# Engine 1: keyword rules. This is the honest "what you get without GenAI" baseline.
# --------------------------------------------------------------------------------------

CATEGORY_RULES = [
    ("Adverse Event", ["emergency room", "hospital", "urgent care", "stitches", "died",
                       "unresponsive", "adverse", "rash", "blister"]),
    ("Shipping/Logistics", ["shipping", "shipped", "delivery", "arrived", "late", "carrier",
                            "package", "crushed"]),
    ("Billing/Order", ["invoice", "charged", "refund", "price", "billing", "order number"]),
    ("Software/Connectivity", ["app", "sync", "firmware", "pair", "login", "website",
                               "software", "update"]),
    ("Packaging/Labeling", ["label", "labeling", "leaflet", "carton", "ifu", "expiry",
                            "instructions", "printed"]),
    ("Quality/Sterility", ["seal", "sterile", "cracked", "crack", "foil", "smells", "half full"]),
    ("Usability/Training", ["training", "manual is not clear", "hard to", "too tight",
                            "cannot figure"]),
    ("Device Malfunction", ["alarm", "alarmed", "malfunction", "leak", "leaked", "blank",
                            "error", "err", "jam", "misfire", "will not", "shut itself",
                            "burst", "battery", "sticks", "frayed", "readings"]),
]

SEVERITY_RULES = [
    ("Critical", ["died", "death", "unresponsive", "emergency room", "hospital", "stitches",
                  "fainted", "life"]),
    ("High", ["urgent care", "sterile", "seal", "injury", "gasping", "delayed", "dosing",
              "wrong", "sparked", "quarantine"]),
    ("Medium", ["leak", "cracked", "error", "louder", "slower", "not fit", "out of range"]),
]

TEAM_BY_CATEGORY = {
    "Adverse Event": "Pharmacovigilance",
    "Device Malfunction": "Product Quality Engineering",
    "Quality/Sterility": "Product Quality Engineering",
    "Packaging/Labeling": "Regulatory Affairs",
    "Shipping/Logistics": "Supply Chain",
    "Billing/Order": "Customer Service",
    "Software/Connectivity": "Software Support",
    "Usability/Training": "Customer Service",
    "Product Inquiry/Feedback": "Customer Service",
    "Privacy Incident": "Privacy Office",
}

PRIORITY_BY_SEVERITY = {"Critical": 95, "High": 78, "Medium": 52, "Low": 20}


def keyword_product(row, products):
    text = f"{row['product_text']} {row['complaint_text']}".lower()
    for p in products:
        if p["product_id"] == "UNKNOWN":
            continue
        first_word = p["product_name"].split()[0].lower()
        if first_word in text:
            return p["product_id"], p["product_name"]
    return "UNKNOWN", "Unidentified / Not stated"


def keyword_assessment(row, products):
    text = row["complaint_text"].lower()

    category = "Product Inquiry/Feedback"
    for name, keys in CATEGORY_RULES:
        if any(k in text for k in keys):
            category = name
            break

    severity = "Low"
    for name, keys in SEVERITY_RULES:
        if any(k in text for k in keys):
            severity = name
            break

    product_id, product_name = keyword_product(row, products)
    confidence = 0.5  # a keyword router has no meaningful confidence signal

    return {
        "complaint_id": row["complaint_id"],
        "received_at": row["received_at"],
        "channel": row["channel"],
        "reporter_type": row["reporter_type"],
        "region": row["region"],
        "category": category,
        "product_id": product_id,
        "product_name": product_name,
        "severity": severity,
        "priority_score": PRIORITY_BY_SEVERITY[severity],
        "mdr_reportable_flag": "Yes" if severity == "Critical" else "No",
        "summary": row["complaint_text"][:110].replace("\n", " ") + "...",
        "event_date": "Not stated",
        "lot_or_serial": row["lot_or_serial"] or "Not stated",
        "patient_involved": "Not stated",
        "patient_outcome": "Not stated",
        "device_returned": "Not stated",
        "units_affected": "Not stated",
        "missing_info": "",  # rules cannot tell which facts are absent
        "suggested_next_action": "Manual handler to assess.",
        "route_team": TEAM_BY_CATEGORY[category],
        "confidence": confidence,
        "needs_human_review": "TRUE",
        "review_reason": "Rules engine: every record needs manual confirmation",
    }


# --------------------------------------------------------------------------------------
# Engine 2: Claude
# --------------------------------------------------------------------------------------

def claude_assessment(rows, products):
    from anthropic import Anthropic  # imported lazily so the offline path has no deps

    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("Set ANTHROPIC_API_KEY before running --engine claude.")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt_doc = PROMPT.read_text(encoding="utf-8")
    system = prompt_doc.split("```")[1].strip()
    template = prompt_doc.split("```")[3].strip()
    catalogue = "\n".join(f"{p['product_id']} = {p['product_name']}" for p in products)

    results = []
    for row in rows:
        user = template.replace("{{PRODUCT_CATALOGUE}}", catalogue)
        for key, value in row.items():
            user = user.replace("{{" + key + "}}", value or "Not stated")

        msg = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1200,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        payload = json.loads(msg.content[0].text.strip().strip("`"))
        facts = payload.get("key_facts", {})
        results.append({
            "complaint_id": row["complaint_id"],
            "received_at": row["received_at"],
            "channel": row["channel"],
            "reporter_type": row["reporter_type"],
            "region": row["region"],
            "category": payload["category"],
            "product_id": payload["product_id"],
            "product_name": payload["product_name"],
            "severity": payload["severity"],
            "priority_score": payload["priority_score"],
            "mdr_reportable_flag": payload["mdr_reportable_flag"],
            "summary": payload["summary"],
            "event_date": facts.get("event_date", "Not stated"),
            "lot_or_serial": facts.get("lot_or_serial", "Not stated"),
            "patient_involved": facts.get("patient_involved", "Not stated"),
            "patient_outcome": facts.get("patient_outcome", "Not stated"),
            "device_returned": facts.get("device_returned", "Not stated"),
            "units_affected": facts.get("units_affected", "Not stated"),
            "missing_info": ";".join(payload.get("missing_info", [])),
            "suggested_next_action": payload["suggested_next_action"],
            "route_team": payload["route_team"],
            "confidence": payload["confidence"],
            "needs_human_review": str(payload["needs_human_review"]).upper(),
            "review_reason": payload.get("review_reason", ""),
        })
        print(f"  assessed {row['complaint_id']}", file=sys.stderr)
    return results


# --------------------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------------------

def score(rows, gold_by_id):
    n = len(rows)
    cat = sum(1 for r in rows if r["category"] == gold_by_id[r["complaint_id"]]["gold_category"])
    sev = sum(1 for r in rows if r["severity"] == gold_by_id[r["complaint_id"]]["gold_severity"])
    team = sum(1 for r in rows if r["route_team"] == gold_by_id[r["complaint_id"]]["gold_team"])
    prod = sum(1 for r in rows if r["product_id"] == gold_by_id[r["complaint_id"]]["gold_product_id"])

    # A missed Critical/High is the failure mode the business actually cares about.
    order = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
    undercalls = sum(
        1 for r in rows
        if order[r["severity"]] < order[gold_by_id[r["complaint_id"]]["gold_severity"]]
        and order[gold_by_id[r["complaint_id"]]["gold_severity"]] >= 2
    )

    reviewed = sum(1 for r in rows if r["needs_human_review"].upper() == "TRUE")
    minutes = reviewed * MIN_AI_REVIEWED + (n - reviewed) * MIN_AI_AUTO

    return {
        "records": n,
        "category_accuracy": cat / n,
        "product_accuracy": prod / n,
        "severity_accuracy": sev / n,
        "routing_accuracy": team / n,
        "serious_undercalls": undercalls,
        "human_review_rate": reviewed / n,
        "handling_minutes": minutes,
        "mean_confidence": statistics.mean(float(r["confidence"]) for r in rows),
    }


def cmd_evaluate():
    gold_by_id = {g["complaint_id"]: g for g in read_csv(GOLD)}
    arms = []
    if BASE_OUT.exists():
        arms.append(("Keyword rules (baseline)", read_csv(BASE_OUT)))
    if AI_OUT.exists():
        arms.append(("Claude assessment (GenAI)", read_csv(AI_OUT)))
    if not arms:
        sys.exit("No assessment output found. Run `python assessment.py run --engine keyword` first.")

    manual_minutes = len(gold_by_id) * MIN_MANUAL
    print(f"\nBenchmark: fully manual intake = {manual_minutes:.0f} min "
          f"({MIN_MANUAL:.0f} min x {len(gold_by_id)} complaints)\n")
    print(f"{'Metric':<26}" + "".join(f"{name:>28}" for name, _ in arms))
    results = [(name, score(rows, gold_by_id)) for name, rows in arms]
    for label, key, fmt in [
        ("Category accuracy", "category_accuracy", "{:.0%}"),
        ("Product ID accuracy", "product_accuracy", "{:.0%}"),
        ("Severity accuracy", "severity_accuracy", "{:.0%}"),
        ("Routing accuracy", "routing_accuracy", "{:.0%}"),
        ("Serious under-calls", "serious_undercalls", "{:.0f}"),
        ("Human review rate", "human_review_rate", "{:.0%}"),
        ("Handling minutes", "handling_minutes", "{:.0f}"),
    ]:
        print(f"{label:<26}" + "".join(fmt.format(s[key]).rjust(28) for _, s in results))

    for name, s in results:
        saved = manual_minutes - s["handling_minutes"]
        print(f"\n{name}: {saved:.0f} min saved vs manual "
              f"({saved / manual_minutes:.0%} reduction, "
              f"{s['handling_minutes'] / s['records']:.1f} min per complaint)")
    print()


# --------------------------------------------------------------------------------------

def cmd_run(engine):
    rows = read_csv(RAW)
    products = read_csv(PRODUCTS)
    if engine == "keyword":
        write_csv(BASE_OUT, [keyword_assessment(r, products) for r in rows])
        print(f"Wrote {BASE_OUT.relative_to(ROOT)} ({len(rows)} records, keyword rules)")
    else:
        write_csv(AI_OUT, claude_assessment(rows, products))
        print(f"Wrote {AI_OUT.relative_to(ROOT)} ({len(rows)} records, Claude)")


def comparison_payload():
    """Scored through the same score() path as `evaluate`, so the two cannot disagree."""
    gold_by_id = {g["complaint_id"]: g for g in read_csv(GOLD)}
    arms = []
    for label, path in (("Keyword rules", BASE_OUT), ("Claude + human review", AI_OUT)):
        if path.exists():
            s = score(read_csv(path), gold_by_id)
            s["name"] = label
            s["minutes_per_complaint"] = s["handling_minutes"] / s["records"]
            # Formatted here so the browser never re-rounds and drifts from the CLI table.
            s["display"] = {
                "minutes_per_complaint": f"{s['minutes_per_complaint']:.1f}",
                "category_accuracy": f"{s['category_accuracy']:.0%}",
                "product_accuracy": f"{s['product_accuracy']:.0%}",
                "severity_accuracy": f"{s['severity_accuracy']:.0%}",
                "routing_accuracy": f"{s['routing_accuracy']:.0%}",
                "serious_undercalls": f"{s['serious_undercalls']} of {s['records']}",
                "human_review_rate": f"{s['human_review_rate']:.0%}",
            }
            arms.append(s)
    return {
        "records": len(gold_by_id),
        "manual_minutes_per_complaint": f"{MIN_MANUAL:.1f}",
        "manual_review_rate": "100%",
        "arms": arms,
    }


def cmd_dashboard():
    rows = read_csv(AI_OUT)
    target = ROOT / "dashboard" / "data.js"
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        "// Generated by scripts/assessment.py dashboard - do not edit by hand.\n"
        "const ASSESSMENT_DATA = " + json.dumps(rows, indent=1) + ";\n\n"
        "const COMPARISON = " + json.dumps(comparison_payload(), indent=1) + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {target.relative_to(ROOT)} ({len(rows)} records + engine comparison)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--engine", choices=["keyword", "claude"], default="keyword")
    sub.add_parser("evaluate")
    sub.add_parser("dashboard")

    args = parser.parse_args()
    if args.cmd == "run":
        cmd_run(args.engine)
    elif args.cmd == "evaluate":
        cmd_evaluate()
    else:
        cmd_dashboard()


if __name__ == "__main__":
    main()
