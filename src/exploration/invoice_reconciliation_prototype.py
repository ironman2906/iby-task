"""
invoice_reconciliation_prototype.py  (Day 4)

Step 3 prototype: automates the invoice/vendor reconciliation check
described verbatim in Dataset B extracted_text:

    "受領した請求書のINV番号・金額・取引先名をこの一覧と照合すること。
     差異がある場合は要確認として保留する。"

INPUT: real extracted_text pulled from Dataset B session events via
loaders.get_extracted_text -- NOT hardcoded blobs. If the scan finds no
real matches, the script says so explicitly and stops; it does not
silently fall back to fabricated numbers.

OUTPUT: one decision per invoice row -- "approve" or "hold_for_review" --
with a machine-readable reason, plus provenance (session_id + timestamp)
for every real match so the demo is traceable back to source events.

Scope: the reconciliation decision only. No portal write-back, no RPA/AI
agent, no OCR pipeline -- see README/day4_findings for the scope rationale.

--------------------------------------------------------------------------
DECISION RULE HISTORY (read before trusting the approve/hold split)

v1 (initial): approve iff vendor known AND invoice_amount == master amount.
Result on real Dataset B: 0/108 approved, 108/108 held. This was NOT
treated as ground truth -- it prompted a diagnostic investigation
(diagnose_real_reconciliation_outcomes.py, diagnose_invoice_type_field.py)
into the REAL logged reconciliation outcomes already present in the
captured session text (lines like "請求書照合完了。INV-XXX　金額：Y円。
差異なし承認/差異あり要確認").

That diagnostic found:
  - Amount difference alone does NOT explain the real logged decisions
    (overlapping diff% between approved and held cases, e.g. 5.03%->held,
    5.82%->approved -- so no clean percentage tolerance is supported by
    the data, and none is used here).
  - The 種別 (type) field on the SAME invoice row -- 定常 ("routine") vs
    調整 ("adjustment") -- perfectly separated the 13 resolved outcomes
    in the diagnostic sample: 7/7 定常 rows were approved, 6/6 調整 rows
    were held.

v2 (this version): approve iff vendor known AND invoice_type == "定常".
This is an EVIDENCE-BASED HYPOTHESIS, not a confirmed production rule --
the diagnostic sample was only 13 resolved outcomes. See day4_findings.md
for the full diagnostic trail and this caveat stated in report form.
Amount-vs-master difference is still computed and logged for every row
(provenance/diagnostic value), it just no longer DRIVES the decision.
--------------------------------------------------------------------------

Usage (from the project root, e.g. D:\\intern_task_project_iby):
    python src\\exploration\\invoice_reconciliation_prototype.py --dataset-b-dir data\\dataset_b
"""
import argparse
import difflib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import list_sessions, load_session_events, get_extracted_text

# ---------------------------------------------------------------------------
# IMPORTANT SCOPE NOTE (read before trusting "vendor not found" as a bug)
#
# The source document for the vendor master is titled (per Day 3 inspection)
# "getsujitsu_teigaku_torihikisaki_ichiran" -- 定額取引先一覧, i.e. the
# *fixed-amount* vendor list. That is a company-wide reference document by
# nature (you don't publish a per-session version of "which vendors bill a
# flat fee"), which is why this script keeps vendor-master lookup GLOBAL
# across all of Dataset B by default, not scoped to the invoice row's own
# session.
#
# This also means vendors absent from the list (e.g. logistics/PO vendors
# billed variable amounts) are plausibly OUT OF SCOPE for this specific
# reconciliation rule, not a matching failure. "vendor_not_found" should be
# read with that in mind, not assumed to be a bug -- the diagnostics below
# exist so you can check this against the real session data instead of
# either of us assuming it.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# "No.1　株式会社山田製作所　製造委託費　月額 385,000円"
VENDOR_LINE_RE = re.compile(
    r"No\.(\d+)\s*　?\s*(\S+?)\s*　\s*(\S+?)\s*　?月額\s*(\S+?)円"
)

# "P6-07010448-001 V3005 グローバルテック合同会社 請求書承認 INV-2026-7344
#  716,232円 調整 登録済み"
# Extended (Day 4) to ALSO capture 種別 (定常/調整) in the SAME match as
# the vendor/invoice/amount -- this is the strict row-tied extraction: the
# type can only ever come from the exact row this regex matched, since
# \s+ already spans the newlines between each field in the captured
# extracted_text. There is no separate/global re-scan for 種別, so there
# is no possibility of associating a type from a different row or a
# different capture of the table.
# Amount group stays a WHOLE next whitespace-delimited token (greedy \S+,
# not \S+?) so a malformed token is captured-and-flagged by parse_amount
# rather than the regex silently truncating it or failing to match.
INVOICE_ROW_RE = re.compile(
    r"(P\d+-\d+-\d+)\s+(\S+)\s+(\S+?)\s+請求書承認\s+(INV-\d{4}-\d+)\s+(\S+)"
    r"\s+(定常|調整)"
)


def parse_amount(raw: str) -> Optional[int]:
    """Returns an int yen amount, or None if the field is not a clean number."""
    if raw is None:
        return None
    cleaned = raw.replace(",", "").replace("円", "").strip()
    return int(cleaned) if cleaned.isdigit() else None


@dataclass
class VendorMasterRecord:
    """
    A vendor-master entry with FULL provenance, not just the first sighting.
    If the same vendor name was captured with different amounts in
    different places, `ambiguous=True` and `monthly_amount=None` -- callers
    must treat this as unresolved, never silently pick one value.
    """
    vendor_name: str
    category: str
    monthly_amount: Optional[int]
    ambiguous: bool
    occurrences: list = field(default_factory=list)  # (amount, source) tuples


@dataclass
class InvoiceRow:
    record_id: str
    vendor_code: str
    vendor_name: str
    inv_number: str
    amount: Optional[int]
    raw_amount_text: str
    source: str
    invoice_type: Optional[str] = None  # "定常" / "調整" / None (unclear -- Day 4)


# ---------------------------------------------------------------------------
# Parsing (pure functions -- take text in, return structured data)
# ---------------------------------------------------------------------------

def parse_vendor_master_raw(text, source="synthetic"):
    """Returns every (name, category, amount, source) hit -- NOT deduped.
    Deduping happens later in build_vendor_master, where we can detect
    conflicting amounts instead of silently keeping the first one."""
    hits = []
    for m in VENDOR_LINE_RE.finditer(text):
        _, name, category, amount_raw = m.groups()
        hits.append((name, category, parse_amount(amount_raw), source))
    return hits


def build_vendor_master(raw_hits):
    """
    Groups all vendor-master sightings by name. If a name's amount agrees
    across every sighting, it's a confirmed record. If sightings disagree,
    it's marked ambiguous and monthly_amount is None -- any invoice against
    it must hold_for_review, never guess which value is right.
    """
    by_name = defaultdict(list)
    for name, category, amount, source in raw_hits:
        by_name[name].append((category, amount, source))

    master = {}
    for name, occ in by_name.items():
        distinct_amounts = {a for _, a, _ in occ if a is not None}
        category = occ[0][0]
        occurrences = [(a, s) for _, a, s in occ]
        if len(distinct_amounts) <= 1:
            amt = next(iter(distinct_amounts)) if distinct_amounts else None
            master[name] = VendorMasterRecord(name, category, amt, ambiguous=False, occurrences=occurrences)
        else:
            master[name] = VendorMasterRecord(name, category, None, ambiguous=True, occurrences=occurrences)
    return master


# Generic legal-entity suffixes. Stripped ONLY for the similarity-hint
# comparison below -- two unrelated companies both being a 株式会社
# ("Co., Ltd.") should not count as "similar." Never used for the actual
# matching decision, which stays exact-name-only.
_LEGAL_SUFFIXES = ["株式会社", "合同会社", "有限会社", "合資会社"]


def _strip_legal_suffix(name):
    for suf in _LEGAL_SUFFIXES:
        name = name.replace(suf, "")
    return name.strip()


def best_name_similarity(target_name, master_names):
    """
    Non-authoritative reporting hint ONLY -- never used to change a
    decision. Finds the closest master vendor name by character
    similarity on the SUFFIX-STRIPPED names (so two companies that only
    share "Co., Ltd." don't look artificially similar), for a human to
    look at, never to auto-map.
    """
    if not master_names:
        return None, 0.0
    target_stripped = _strip_legal_suffix(target_name)
    best = max(master_names,
               key=lambda n: difflib.SequenceMatcher(None, target_stripped, _strip_legal_suffix(n)).ratio())
    ratio = difflib.SequenceMatcher(None, target_stripped, _strip_legal_suffix(best)).ratio()
    return best, ratio


def parse_invoice_list(text, source="synthetic"):
    rows = []
    for m in INVOICE_ROW_RE.finditer(text):
        record_id, vendor_code, vendor_name, inv_number, amount_raw, invoice_type = m.groups()
        rows.append(InvoiceRow(
            record_id=record_id,
            vendor_code=vendor_code,
            vendor_name=vendor_name,
            inv_number=inv_number,
            amount=parse_amount(amount_raw),
            raw_amount_text=amount_raw,
            source=source,
            invoice_type=invoice_type,  # captured in the SAME regex match -- row-tied by construction
        ))
    return rows


# ---------------------------------------------------------------------------
# Real Dataset B scan -- this is the part that replaces the hardcoded blobs
# ---------------------------------------------------------------------------

def scan_dataset_b(dataset_b_dir):
    """
    Walks every session/event in Dataset B, applies both regexes to
    context.extracted_text via loaders.get_extracted_text.

    Returns (vendor_master, invoice_rows, n_events_with_text, diagnostics)
    where diagnostics carries the session-level evidence needed to judge
    whether the master is a single global list or should be session-scoped
    (see the SCOPE NOTE at the top of this file).
    """
    sessions = list_sessions(Path(dataset_b_dir))
    if not sessions:
        print(f"WARNING: no sessions found under {dataset_b_dir} "
              f"-- check the --dataset-b-dir path.")
        return {}, [], 0, {}

    raw_vendor_hits = []
    invoice_rows = []
    n_events_with_text = 0
    vendor_sessions = set()   # sessions where >=1 vendor-master line matched
    invoice_sessions = set()  # sessions where >=1 invoice row matched

    for session_dir in sessions:
        events = load_session_events(session_dir)
        for e in events:
            text = get_extracted_text(e)
            if not text:
                continue
            n_events_with_text += 1
            source = f"real:{session_dir.name}@{e.get('timestamp_iso')}"

            v_hits = parse_vendor_master_raw(text, source=source)
            if v_hits:
                vendor_sessions.add(session_dir.name)
            raw_vendor_hits.extend(v_hits)

            i_rows = parse_invoice_list(text, source=source)
            if i_rows:
                invoice_sessions.add(session_dir.name)
            invoice_rows.extend(i_rows)

    vendor_master = build_vendor_master(raw_vendor_hits)

    # De-duplicate invoice rows captured twice because the same on-screen
    # table was OCR'd by more than one screenshot event.
    seen = set()
    deduped_rows = []
    for row in invoice_rows:
        key = (row.record_id, row.inv_number)
        if key in seen:
            continue
        seen.add(key)
        deduped_rows.append(row)

    diagnostics = {
        "vendor_sessions": vendor_sessions,
        "invoice_sessions": invoice_sessions,
        "overlap_sessions": vendor_sessions & invoice_sessions,
        "invoice_sessions_without_master_hit": invoice_sessions - vendor_sessions,
    }

    return vendor_master, deduped_rows, n_events_with_text, diagnostics


# ---------------------------------------------------------------------------
# Reconciliation logic
# ---------------------------------------------------------------------------

def old_rule_decision(row, vendor_master):
    """
    v1 rule, kept ONLY for before/after comparison reporting -- does not
    affect the actual decisions list. Replicates exactly what v1 did:
    approve iff known vendor AND invoice_amount == master amount.
    """
    if row.amount is None:
        return "hold_for_review"
    vendor = vendor_master.get(row.vendor_name)
    if vendor is None or vendor.ambiguous or vendor.monthly_amount is None:
        return "hold_for_review"
    return "approve" if row.amount == vendor.monthly_amount else "hold_for_review"


def reconcile(vendor_master, invoice_rows, session_diagnostics=None):
    """
    Returns a list of (row, decision, reason, reason_code, old_decision)
    tuples.

    Safety checks (unchanged from v1):
        unknown vendor            -> hold_for_review
        malformed amount          -> hold_for_review
        duplicate invoice         -> hold_for_review
        ambiguous master amount   -> hold_for_review  (never guess)
        malformed master amount   -> hold_for_review

    NEW decision driver (Day 4, evidence-based -- see module docstring):
        invoice_type == "定常"    -> approve
        invoice_type == "調整"    -> hold_for_review
        invoice_type unclear/None -> hold_for_review

    Amount-vs-master difference is computed and included in the reason
    string for every row that reaches the type-based branch, for
    provenance/diagnostic value -- it no longer drives the decision.
    """
    master_names = list(vendor_master.keys())
    seen_inv = set()
    decisions = []

    for row in invoice_rows:
        old_decision = old_rule_decision(row, vendor_master)

        if row.inv_number in seen_inv:
            decisions.append((row, "hold_for_review",
                               f"duplicate INV number {row.inv_number} already "
                               f"seen earlier in this batch",
                               "duplicate_invoice", old_decision))
            continue
        seen_inv.add(row.inv_number)

        if row.amount is None:
            decisions.append((row, "hold_for_review",
                               f"malformed amount field: {row.raw_amount_text!r} "
                               f"could not be parsed as a number",
                               "malformed_amount", old_decision))
            continue

        vendor = vendor_master.get(row.vendor_name)
        if vendor is None:
            reason = "vendor not found in master list"
            # Non-authoritative hint only -- never changes the decision.
            candidate, ratio = best_name_similarity(row.vendor_name, master_names)
            if candidate and ratio >= 0.5:
                reason += (f" (possible name variant of '{candidate}', "
                           f"similarity={ratio:.2f} -- unconfirmed, needs human review)")
            if session_diagnostics is not None:
                in_vendor_session = row.source.split("@")[0].replace("real:", "") in \
                    {s for s in session_diagnostics.get("vendor_sessions", set())}
                reason += f"; row's own session had a master hit: {in_vendor_session}"
            decisions.append((row, "hold_for_review", reason, "vendor_not_found", old_decision))
            continue

        if vendor.ambiguous:
            conflict_desc = ", ".join(f"{a:,}円" if a is not None else "None"
                                       for a, _ in vendor.occurrences)
            decisions.append((row, "hold_for_review",
                               f"vendor master amount is AMBIGUOUS -- conflicting "
                               f"values found across sources: [{conflict_desc}]. "
                               f"Not resolving automatically.",
                               "master_amount_ambiguous", old_decision))
            continue

        if vendor.monthly_amount is None:
            decisions.append((row, "hold_for_review",
                               "vendor master amount is malformed -- cannot compare",
                               "master_amount_malformed", old_decision))
            continue

        diff = abs(row.amount - vendor.monthly_amount)
        diff_pct = (100 * diff / vendor.monthly_amount) if vendor.monthly_amount else None
        diff_note = (f"amount diff vs master: {diff:,}円 "
                      f"({diff_pct:.2f}% -- logged for provenance, NOT the decision driver)")

        # --- Day 4 decision driver: 種別, not amount match ---
        if row.invoice_type == "定常":
            decisions.append((row, "approve",
                               f"invoice_type=定常 (evidence-based rule, see module docstring); "
                               f"{diff_note}",
                               "type_teijou_evidence_based", old_decision))
        elif row.invoice_type == "調整":
            decisions.append((row, "hold_for_review",
                               f"invoice_type=調整 (evidence-based rule, see module docstring); "
                               f"{diff_note}",
                               "type_chousei_evidence_based", old_decision))
        else:
            decisions.append((row, "hold_for_review",
                               f"invoice_type could not be determined from this row "
                               f"(got {row.invoice_type!r}); {diff_note}",
                               "type_unclear", old_decision))

    return decisions


def print_report(title, decisions):
    print(f"\n=== {title} ===")
    if not decisions:
        print("  (no rows)")
        return
    print(f"{'record_id':16s} {'vendor':22s} {'inv_number':16s} {'amount':>12s}  "
          f"{'type':6s} decision          old_decision      reason  [source]")
    for row, decision, reason, reason_code, old_decision in decisions:
        amount_str = f"{row.amount:,}円" if row.amount is not None else row.raw_amount_text
        type_str = row.invoice_type or "?"
        print(f"{row.record_id:16s} {row.vendor_name:22s} {row.inv_number:16s} "
              f"{amount_str:>12s}  {type_str:6s} {decision:16s}  {old_decision:16s}  "
              f"{reason}  [{row.source}]")


def print_before_after(decisions):
    old_approve = sum(1 for d in decisions if d[4] == "approve")
    old_hold = sum(1 for d in decisions if d[4] == "hold_for_review")
    new_approve = sum(1 for d in decisions if d[1] == "approve")
    new_hold = sum(1 for d in decisions if d[1] == "hold_for_review")
    changed = sum(1 for d in decisions if d[1] != d[4])

    print(f"\n=== BEFORE / AFTER COMPARISON ===")
    print(f"  OLD rule (exact amount match):  approve={old_approve:4d}  hold={old_hold:4d}")
    print(f"  NEW rule (種別-based, Day 4):    approve={new_approve:4d}  hold={new_hold:4d}")
    print(f"  Rows where the decision CHANGED: {changed}")

    reason_counts = Counter(d[3] for d in decisions)
    print(f"\n  New-rule reason code breakdown:")
    for code, count in reason_counts.most_common():
        print(f"    {code:32s} {count}")


# ---------------------------------------------------------------------------
# Synthetic edge cases -- clearly labeled as constructed tests, NOT dataset
# evidence. They exercise logic paths that may not appear in this small a
# sample of real Dataset B rows.
# ---------------------------------------------------------------------------

def build_edge_cases(vendor_master, real_rows):
    cases = []

    confirmed_master = {n: v for n, v in vendor_master.items()
                         if not v.ambiguous and v.monthly_amount is not None}

    # 0a. Dedicated, unambiguous synthetic APPROVE case -- 定常 type,
    #     exact master amount. Demonstrates the approve path works even
    #     if the real sample under-represents it.
    if confirmed_master:
        name, vendor = next(iter(confirmed_master.items()))
        cases.append(InvoiceRow(
            record_id="P6-TEST-900-APPROVE", vendor_code="V_APPROVE",
            vendor_name=name, inv_number="INV-2026-TESTAPPROVE",
            amount=vendor.monthly_amount, raw_amount_text=str(vendor.monthly_amount),
            source="synthetic:dedicated_approve_case (定常)",
            invoice_type="定常",
        ))

    # 0b. Dedicated synthetic HOLD case via 調整 type, even with an EXACT
    #     amount match -- demonstrates that 種別, not amount equality, now
    #     drives the decision (this case would have approved under v1).
    if confirmed_master:
        name, vendor = next(iter(confirmed_master.items()))
        cases.append(InvoiceRow(
            record_id="P6-TEST-905-CHOUSEI-HOLD", vendor_code="V_CHOUSEI",
            vendor_name=name, inv_number="INV-2026-TESTCHOUSEI",
            amount=vendor.monthly_amount, raw_amount_text=str(vendor.monthly_amount),
            source="synthetic:dedicated_chousei_hold_case (調整, exact amount)",
            invoice_type="調整",
        ))

    # 0c. Unclear/missing invoice_type -- should hold, not guess.
    if confirmed_master:
        name, vendor = next(iter(confirmed_master.items()))
        cases.append(InvoiceRow(
            record_id="P6-TEST-906-UNCLEAR-TYPE", vendor_code="V_UNCLEAR",
            vendor_name=name, inv_number="INV-2026-TESTUNCLEAR",
            amount=vendor.monthly_amount, raw_amount_text=str(vendor.monthly_amount),
            source="synthetic:unclear_type_case",
            invoice_type=None,
        ))

    # 1. Vendor not in master list.
    cases.append(InvoiceRow(
        record_id="P6-TEST-901", vendor_code="V9999",
        vendor_name="存在しない商事株式会社", inv_number="INV-2026-9901",
        amount=100000, raw_amount_text="100,000", source="synthetic:vendor_not_found",
        invoice_type="定常",
    ))

    # 2. Malformed amount field (OCR garble / non-numeric).
    cases.append(InvoiceRow(
        record_id="P6-TEST-902", vendor_code="V0001",
        vendor_name=next(iter(vendor_master), "unknown_vendor"),
        inv_number="INV-2026-9902",
        amount=None, raw_amount_text="N/A", source="synthetic:malformed_amount",
        invoice_type="定常",
    ))

    # 3. Duplicate INV number. Both copies must be in THIS SAME batch --
    #    reconcile() is called once per batch and its "seen" set is fresh
    #    each call, so a duplicate that only appears once here would never
    #    exercise the check. Base it on a real row's identity if one
    #    exists (more representative), but append it twice regardless.
    if real_rows:
        base = real_rows[0]
        dup_vendor_name, dup_inv, dup_amount, dup_raw, dup_type = (
            base.vendor_name, base.inv_number, base.amount, base.raw_amount_text,
            base.invoice_type)
    else:
        dup_vendor_name = next(iter(vendor_master), "unknown_vendor")
        dup_inv, dup_amount, dup_raw, dup_type = "INV-2026-DUPTEST", 100000, "100,000", "定常"

    cases.append(InvoiceRow(
        record_id="P6-TEST-903-DUP", vendor_code="V_DUP",
        vendor_name=dup_vendor_name, inv_number=dup_inv,
        amount=dup_amount, raw_amount_text=dup_raw,
        source="synthetic:duplicate_inv (1st occurrence)",
        invoice_type=dup_type,
    ))
    cases.append(InvoiceRow(
        record_id="P6-TEST-904-DUP", vendor_code="V_DUP",
        vendor_name=dup_vendor_name, inv_number=dup_inv,
        amount=dup_amount, raw_amount_text=dup_raw,
        source="synthetic:duplicate_inv (2nd occurrence, should be flagged)",
        invoice_type=dup_type,
    ))

    return cases


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-b-dir", default="data/dataset_b",
                     help=r"Path to Dataset B, e.g. data\dataset_b")
    args = ap.parse_args()

    print(f"Scanning {args.dataset_b_dir} for real vendor-master and "
          f"invoice-row text...")
    vendor_master, real_rows, n_events_with_text, diag = scan_dataset_b(args.dataset_b_dir)

    # ---- 1. vendor-master records -----------------------------------
    print(f"\nEvents with non-empty extracted_text scanned: {n_events_with_text}")
    print(f"\n[1] Real vendor-master entries (deduped by name): {len(vendor_master)}")
    for name, v in vendor_master.items():
        n_sessions = len({s.split("@")[0] for _, s in v.occurrences})
        flag = "  ** AMBIGUOUS (conflicting amounts) **" if v.ambiguous else ""
        amt = f"{v.monthly_amount:,}円" if v.monthly_amount is not None else "N/A"
        print(f"  - {name} ({v.category}): {amt}  "
              f"[seen {len(v.occurrences)}x across {n_sessions} session(s)]{flag}")

    # ---- 2. invoice rows ----------------------------------------------
    print(f"\n[2] Real invoice rows (deduped): {len(real_rows)}")
    type_counts = Counter(r.invoice_type for r in real_rows)
    print(f"  invoice_type breakdown: {dict(type_counts)}")

    # ---- 3. master <-> invoice session association ---------------------
    print(f"\n[3] Session association between vendor master and invoice rows:")
    print(f"  Sessions containing >=1 vendor-master line : {len(diag.get('vendor_sessions', []))}")
    print(f"  Sessions containing >=1 invoice row        : {len(diag.get('invoice_sessions', []))}")
    print(f"  Sessions with BOTH (overlap)                : {len(diag.get('overlap_sessions', []))}")
    print(f"  Invoice sessions with NO master hit         : {len(diag.get('invoice_sessions_without_master_hit', []))}")
    print("  Interpretation: if the master appears in very few sessions while")
    print("  invoices span many, that is consistent with ONE global reference")
    print("  document (see SCOPE NOTE at top of file) -- not a scoping bug.")
    print("  If the same vendor name shows conflicting amounts across sessions")
    print("  (flagged AMBIGUOUS above), that WOULD be evidence for session-")
    print("  local lists, and those rows are held for review, not guessed.")

    if not vendor_master or not real_rows:
        print("\nNo usable real vendor-master + invoice-row pair was found in "
              "Dataset B extracted_text with the current regexes. Do NOT "
              "substitute fabricated numbers -- report this as a limitation.")
        real_decisions = []
    else:
        real_decisions = reconcile(vendor_master, real_rows, session_diagnostics=diag)

    approve = [d for d in real_decisions if d[1] == "approve"]
    hold = [d for d in real_decisions if d[1] == "hold_for_review"]
    reason_counts = Counter(d[3] for d in hold)

    # ---- 4 & 5. approve / hold counts ----------------------------------
    print(f"\n[4] Real approve count: {len(approve)}")
    print(f"[5] Real hold_for_review count: {len(hold)}")
    if not approve:
        print("  NOTE: the real captured sample contained NO confirmed approve "
              "case. This is reported as-is, not fabricated. See the dedicated "
              "synthetic approve case in the edge-case section below for proof "
              "the approve path itself works correctly.")

    # ---- 6. hold reasons breakdown --------------------------------------
    print(f"\n[6] Hold reasons breakdown:")
    for code, count in reason_counts.most_common():
        print(f"  {code}: {count}")

    # ---- 7. at least 2 real examples with provenance ---------------------
    print(f"\n[7] Real examples with provenance:")
    examples = (approve[:2] + hold[:2]) if approve else hold[:4]
    if not examples:
        print("  (no real decisions to show)")
    for row, decision, reason, code, old_decision in examples:
        amt = f"{row.amount:,}円" if row.amount is not None else row.raw_amount_text
        print(f"  {row.record_id} | {row.vendor_name} | {row.inv_number} | {amt} "
              f"| type={row.invoice_type} -> {decision} ({code}) | old_rule={old_decision} "
              f"| {reason} | source={row.source}")

    if real_decisions:
        print_before_after(real_decisions)

    print_report("REAL DATASET B RECONCILIATION (full)", real_decisions)

    # ---- 8. synthetic edge cases -----------------------------------------
    edge_cases = build_edge_cases(vendor_master, real_rows)
    edge_decisions = reconcile(vendor_master, edge_cases, session_diagnostics=diag)
    print_report("[8] EDGE CASE TESTS (synthetic -- not dataset evidence)", edge_decisions)


if __name__ == "__main__":
    main()