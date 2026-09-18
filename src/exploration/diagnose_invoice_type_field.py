"""
diagnose_invoice_type_field.py
DIAGNOSTIC ONLY. Extends the row-tied strict extraction approach to also
capture the 種別 (調整/定常) column from the SAME table row as the vendor
and invoice_id, then cross-tabs it against the real logged decision
(差異なし承認 / 差異あり要確認) for the 13 previously-resolved outcomes.

Table row layout (confirmed from prior inspection):
  ID
  社員ID (emp_id, e.g. V3005)
  vendor name
  "請求書承認 {invoice_id}"
  amount (円)
  種別 (調整 or 定常)
  ステータス (登録済み / 未処理)

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
TYPE_TERMS = ["調整", "定常"]


def find_row_fields_for_invoice(invoice_id, all_texts):
    """
    Strictly row-tied: find the line containing BOTH "請求書承認" and the
    exact invoice_id. Vendor = line immediately before. Type (種別) and
    status = scanned from the next few lines after the amount line, using
    the KNOWN column order (amount -> 種別 -> ステータス) rather than
    proximity alone, to avoid pulling from adjacent unrelated rows.
    """
    found_vendors = set()
    found_types = set()
    found_statuses = set()

    for t in all_texts:
        lines = t.split("\n")
        for i, line in enumerate(lines):
            if "請求書承認" in line and invoice_id in line:
                # vendor: immediately before
                if i > 0 and lines[i - 1].strip() in VENDOR_LIST:
                    found_vendors.add(lines[i - 1].strip())

                # amount, type, status: immediately after, in that fixed order
                # line i+1 = amount (e.g. "716,232円"), i+2 = type, i+3 = status
                if i + 2 < len(lines):
                    candidate_type = lines[i + 2].strip()
                    if candidate_type in TYPE_TERMS:
                        found_types.add(candidate_type)
                if i + 3 < len(lines):
                    candidate_status = lines[i + 3].strip()
                    found_statuses.add(candidate_status)

    return found_vendors, found_types, found_statuses


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

                vendors, types, statuses = find_row_fields_for_invoice(inv_id, all_texts)

                vendor = next(iter(vendors)) if len(vendors) == 1 else None
                invoice_type = next(iter(types)) if len(types) == 1 else (
                    "AMBIGUOUS" if len(types) > 1 else "NOT_FOUND"
                )

                outcomes.append({
                    "session": session_dir.name,
                    "timestamp": e["timestamp_iso"],
                    "invoice_id": inv_id,
                    "amount": amt,
                    "decision": decision,
                    "vendor": vendor,
                    "vendor_candidates": vendors,
                    "invoice_type": invoice_type,
                    "type_candidates": types,
                    "master_amount": MASTER_AMOUNTS.get(vendor) if vendor else None,
                })

    seen = set()
    deduped = []
    for o in outcomes:
        key = (o["session"], o["invoice_id"], o["amount"], o["decision"])
        if key not in seen:
            seen.add(key)
            deduped.append(o)

    resolved = [o for o in deduped if o["vendor"] and o["master_amount"]]

    print(f"Total unique reconciliation outcomes: {len(deduped)}")
    print(f"Resolved to a single fixed-amount vendor: {len(resolved)}\n")

    print(f"{'Invoice':16s} {'Vendor':22s} {'Diff%':>7s} {'種別':10s} {'Decision'}")
    for o in resolved:
        diff_pct = 100 * abs(o["amount"] - o["master_amount"]) / o["master_amount"]
        print(f"{o['invoice_id']:16s} {o['vendor']:22s} {diff_pct:6.2f}% "
              f"{o['invoice_type']:10s} {o['decision']}")

    # Cross-tab: 種別 x decision
    crosstab = defaultdict(int)
    for o in resolved:
        crosstab[(o["invoice_type"], o["decision"])] += 1

    print(f"\n--- Cross-tab: 種別 (type) x logged decision ---")
    print(f"{'種別':10s} {'差異なし承認':>12s} {'差異あり要確認':>14s}")
    for t in ["調整", "定常", "AMBIGUOUS", "NOT_FOUND"]:
        approved = crosstab.get((t, "差異なし承認"), 0)
        held = crosstab.get((t, "差異あり要確認"), 0)
        if approved or held:
            print(f"{t:10s} {approved:12d} {held:14d}")

    # Flag any NOT_FOUND / AMBIGUOUS type cases explicitly
    unclear = [o for o in resolved if o["invoice_type"] in ("NOT_FOUND", "AMBIGUOUS")]
    if unclear:
        print(f"\n--- {len(unclear)} resolved outcomes with unclear 種別 (needs manual check) ---")
        for o in unclear:
            print(f"  {o['invoice_id']}: type_candidates={o['type_candidates']}")

    print(f"\nThis script made NO changes to approval/hold logic, did not import")
    print(f"or modify invoice_reconciliation_prototype.py, and performed no commit.")


if __name__ == "__main__":
    main()