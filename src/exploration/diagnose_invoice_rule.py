"""
diagnose_invoice_rule.py
DIAGNOSTIC ONLY. Read-only investigation of Dataset B's extracted_text
to determine whether an explicit amount-comparison rule (exact/tolerance/
percentage) is stated anywhere in the captured UI text, and to
cross-tabulate the existing 108 invoice rows against vendor/amount/flag
status. Does NOT modify, import, or call any logic from
invoice_reconciliation_prototype.py. No approval/hold decisions are
made or changed here.
"""

import sys
import re
import json
from pathlib import Path
from collections import Counter, defaultdict

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import list_sessions, load_session_events, get_extracted_text

DATA_B = Path(__file__).parent.parent.parent / "data" / "dataset_b"

KEYWORDS = [
    "許容", "誤差", "一致", "承認基準", "範囲内", "差異", "以内",
    "割合", "%", "±", "金額照合", "月額", "調整", "標準",
]


def part1_keyword_search():
    print(f"{'='*90}\nPART 1: Keyword search across all Dataset B extracted_text\n{'='*90}")
    hits = []
    seen_texts = set()  # avoid printing near-identical repeated captures

    for session_dir in list_sessions(DATA_B):
        events = load_session_events(session_dir)
        for e in events:
            text = get_extracted_text(e)
            if not text:
                continue
            matched_kw = [k for k in KEYWORDS if k in text]
            if matched_kw:
                # dedupe near-identical repeated captures (same portal state re-captured)
                fingerprint = text[:200]
                if fingerprint in seen_texts:
                    continue
                seen_texts.add(fingerprint)
                hits.append({
                    "session": session_dir.name,
                    "timestamp": e["timestamp_iso"],
                    "matched_keywords": matched_kw,
                    "text": text,
                })

    print(f"Total distinct hits: {len(hits)}\n")
    for h in hits:
        print(f"--- {h['session']} @ {h['timestamp']} ---")
        print(f"Matched: {h['matched_keywords']}")
        print(h["text"][:800])
        print()

    return hits


# --- Part 2/3: parse invoice rows directly from raw text, independent of
# the prototype's own parsing logic, to cross-check without touching it ---

AMOUNT_PATTERN = re.compile(r'([\d,]+)\s*円')
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
FLAG_TERMS = ["調整", "標準"]


def parse_amount(s):
    try:
        return int(s.replace(",", ""))
    except Exception:
        return None


def part2_and_3_crosstab():
    print(f"\n{'='*90}\nPART 2/3: Cross-tabulation of invoice rows (independent re-parse)\n{'='*90}")

    rows = []
    seen_invoice_lines = set()

    for session_dir in list_sessions(DATA_B):
        events = load_session_events(session_dir)
        for e in events:
            text = get_extracted_text(e)
            if not text:
                continue

            for vendor in VENDOR_LIST:
                if vendor not in text:
                    continue
                # scan lines near vendor mentions for amount + flag context
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    if vendor in line:
                        window = "\n".join(lines[max(0, i-1):i+4])
                        amt_matches = AMOUNT_PATTERN.findall(window)
                        if not amt_matches:
                            continue
                        for amt_str in amt_matches:
                            amt = parse_amount(amt_str)
                            if amt is None:
                                continue
                            fingerprint = f"{vendor}|{amt}|{session_dir.name}"
                            if fingerprint in seen_invoice_lines:
                                continue
                            seen_invoice_lines.add(fingerprint)

                            flags_found = [f for f in FLAG_TERMS if f in window]
                            master_amt = MASTER_AMOUNTS.get(vendor)
                            exact_match = (amt == master_amt) if master_amt else None

                            rows.append({
                                "session": session_dir.name,
                                "timestamp": e["timestamp_iso"],
                                "vendor": vendor,
                                "invoice_amount": amt,
                                "master_amount": master_amt,
                                "exact_match": exact_match,
                                "diff_pct": round(100 * abs(amt - master_amt) / master_amt, 2) if master_amt else None,
                                "flags": flags_found,
                                "context": window[:300],
                            })

    print(f"Independently re-parsed rows (vendor-matched only): {len(rows)}\n")

    # Cross-tab: match/mismatch x flag
    crosstab = defaultdict(int)
    for r in rows:
        match_key = "match" if r["exact_match"] else "mismatch"
        flag_key = ",".join(r["flags"]) if r["flags"] else "no_flag_found"
        crosstab[(match_key, flag_key)] += 1

    print("--- Cross-tab: amount match/mismatch x flag ---")
    for (match_key, flag_key), count in sorted(crosstab.items()):
        print(f"  {match_key:10s} | {flag_key:15s} : {count}")

    # Part 3 specific breakdown for mismatches
    mismatches = [r for r in rows if r["exact_match"] is False]
    flag_counter = Counter()
    for r in mismatches:
        if not r["flags"]:
            flag_counter["no_flag_found"] += 1
        else:
            flag_counter[",".join(r["flags"])] += 1

    print(f"\n--- Part 3: flag breakdown for {len(mismatches)} mismatch rows ---")
    for flag, count in flag_counter.most_common():
        print(f"  {flag:20s} {count}")

    # Show diff_pct distribution split by flag
    print(f"\n--- Mismatch diff_pct by flag ---")
    by_flag = defaultdict(list)
    for r in mismatches:
        key = ",".join(r["flags"]) if r["flags"] else "no_flag_found"
        by_flag[key].append(r["diff_pct"])
    for flag, diffs in by_flag.items():
        diffs_sorted = sorted(diffs)
        print(f"  {flag:20s} n={len(diffs)}  min={diffs_sorted[0]:.2f}%  "
              f"median={diffs_sorted[len(diffs)//2]:.2f}%  max={diffs_sorted[-1]:.2f}%")

    # Print several real examples with full provenance
    print(f"\n--- Sample examples with provenance (up to 10 mismatches) ---")
    for r in mismatches[:10]:
        print(f"\nSession: {r['session']} @ {r['timestamp']}")
        print(f"Vendor: {r['vendor']}  Invoice: {r['invoice_amount']}  Master: {r['master_amount']}  "
              f"Diff: {r['diff_pct']}%  Flags: {r['flags']}")
        print(f"Context:\n{r['context']}")

    return rows


def main():
    hits = part1_keyword_search()
    rows = part2_and_3_crosstab()

    print(f"\n{'='*90}\nSUMMARY\n{'='*90}")
    print(f"Part 1 keyword hits: {len(hits)}")
    print(f"Part 2/3 independently re-parsed vendor-matched rows: {len(rows)}")
    print("This script made NO changes to approval/hold logic, did not import")
    print("or modify invoice_reconciliation_prototype.py, and performed no commit.")


if __name__ == "__main__":
    main()