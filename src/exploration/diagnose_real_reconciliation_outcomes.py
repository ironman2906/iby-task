"""
diagnose_real_reconciliation_outcomes.py
DIAGNOSTIC ONLY. Extracts ONLY the structured single-line reconciliation
completion statements ("請求書照合完了。INV-XXX　金額：Y円。差異(あり|なし)...")
which are unambiguous logged outcomes, not reference text or table rows.

Vendor identification is tied STRICTLY to the same invoice row: it looks
for a line containing BOTH "請求書承認" and the exact invoice_id, and takes
the vendor name from the line immediately preceding it (the known table
layout is: ID / empID / vendor name / "請求書承認 INV-XXXX" / amount /
type / status). This avoids associating an invoice with a vendor from an
unrelated part of the same captured text (the bug in the previous script).

No changes to invoice_reconciliation_prototype.py. No commit.
"""

import sys
import re
from pathlib import Path
from collections import defaultdict

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import list_sessions, load_session_events, get_extracted_text

DATA_B = Path(__file__).parent.parent.parent / "data" / "dataset_b"

OUTCOME_PATTERN = re.compile(
    r'請求書照合完了。(INV-[\d-]+)\s*金額：([\d,]+)円。(差異なし承認|差異あり要確認)'
)

VENDOR_LIST = [
    "株式会社山田製作所", "大和商事株式会社", "東京電子工業株式会社",
    "グローバルテック合同会社", "北陸電子部品",
]
MASTER_AMOUNTS = {
    "株式会社山田製作所": 385000,
    "大和商事株式会社": 1240000,
    "東京電子工業株式会社": 562800,
    "グローバルテック合同会社": 745000,
    "北陸電子部品": 420000,
}


def find_vendor_for_invoice_strict(invoice_id, all_texts):
    """
    STRICT row-tied lookup: find a line that contains BOTH "請求書承認"
    and the exact invoice_id (e.g. "請求書承認 INV-2026-7344"), then take
    the vendor name from the line immediately before it. This matches the
    known table row layout exactly, so the vendor cannot be pulled from
    an unrelated row or a different reference block.

    Returns (vendor_or_None, all_vendors_found_set) so we can flag any
    inconsistency across multiple captures of the same invoice.
    """
    found_vendors = set()

    for t in all_texts:
        lines = t.split("\n")
        for i, line in enumerate(lines):
            if "請求書承認" in line and invoice_id in line:
                if i > 0:
                    candidate = lines[i - 1].strip()
                    if candidate in VENDOR_LIST:
                        found_vendors.add(candidate)

    if len(found_vendors) == 1:
        return next(iter(found_vendors)), found_vendors
    elif len(found_vendors) > 1:
        # Inconsistent vendor across captures for the same invoice_id -- flag, don't guess
        return None, found_vendors
    else:
        return None, found_vendors


def main():
    outcomes = []

    for session_dir in list_sessions(DATA_B):
        events = load_session_events(session_dir)
        all_texts = [get_extracted_text(e) for e in events if get_extracted_text(e)]

        for e in events:
            text = get_extracted_text(e)
            if not text:
                continue
            for m in OUTCOME_PATTERN.finditer(text):
                inv_id, amt_str, decision = m.groups()
                amt = int(amt_str.replace(",", ""))
                vendor, all_found = find_vendor_for_invoice_strict(inv_id, all_texts)

                outcomes.append({
                    "session": session_dir.name,
                    "timestamp": e["timestamp_iso"],
                    "invoice_id": inv_id,
                    "amount": amt,
                    "decision": decision,
                    "vendor": vendor,
                    "vendor_candidates": all_found,
                    "master_amount": MASTER_AMOUNTS.get(vendor) if vendor else None,
                })

    # Dedupe (same invoice line can be re-captured across successive screenshots)
    seen = set()
    deduped = []
    for o in outcomes:
        key = (o["session"], o["invoice_id"], o["amount"], o["decision"])
        if key not in seen:
            seen.add(key)
            deduped.append(o)

    print(f"Total unique reconciliation outcomes found: {len(deduped)}")

    ambiguous = [o for o in deduped if o["vendor"] is None and len(o["vendor_candidates"]) > 1]
    unresolved = [o for o in deduped if o["vendor"] is None and len(o["vendor_candidates"]) == 0]
    resolved = [o for o in deduped if o["vendor"] and o["master_amount"]]

    print(f"Resolved to a single fixed-amount vendor (row-tied): {len(resolved)}")
    print(f"Ambiguous (multiple different vendors found across captures): {len(ambiguous)}")
    print(f"Unresolved (no vendor row found at all -- likely a non-fixed-amount vendor): {len(unresolved)}\n")

    if ambiguous:
        print("--- AMBIGUOUS invoice IDs (flagged, not resolved) ---")
        for o in ambiguous:
            print(f"  {o['invoice_id']}: candidates={o['vendor_candidates']}")
        print()

    print(f"{'Invoice':16s} {'Vendor':22s} {'Amount':>10s} {'Master':>10s} {'Diff%':>8s} {'Decision'}")
    for o in resolved:
        diff_pct = 100 * abs(o["amount"] - o["master_amount"]) / o["master_amount"]
        print(f"{o['invoice_id']:16s} {o['vendor']:22s} {o['amount']:10d} "
              f"{o['master_amount']:10d} {diff_pct:7.2f}% {o['decision']}")

    by_decision = defaultdict(list)
    for o in resolved:
        diff_pct = 100 * abs(o["amount"] - o["master_amount"]) / o["master_amount"]
        by_decision[o["decision"]].append(diff_pct)

    print(f"\n--- Diff% distribution by REAL logged decision (row-tied vendor only) ---")
    for decision, diffs in by_decision.items():
        diffs_sorted = sorted(diffs)
        n = len(diffs_sorted)
        print(f"{decision}: n={n}  min={diffs_sorted[0]:.2f}%  "
              f"median={diffs_sorted[n//2]:.2f}%  max={diffs_sorted[-1]:.2f}%")

    print(f"\nThis script made NO changes to approval/hold logic, did not import")
    print(f"or modify invoice_reconciliation_prototype.py, and performed no commit.")


if __name__ == "__main__":
    main()
    