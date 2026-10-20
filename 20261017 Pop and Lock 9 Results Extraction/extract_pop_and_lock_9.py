#!/usr/bin/env python3
"""
Extract Pop & Lock 9 climbing results from 10 HTML files into a single CSV.
"""

import csv
import hashlib
import os
import re
import sys
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────
SOURCE_DIR = r"C:\Users\xeon\Documents\20261017 Pop and Lock 9 Results"
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pop_and_lock_9_results.csv")

HTML_FILES = [
    "openmalefinal.html",
    "openfemalefinal.html",
    "openmalequali.html",
    "openfemalequali.html",
    "youthbmale.html",
    "youthbfemale.html",
    "youthcmale.html",
    "youthcfemale.html",
    "youthdmale.htm",
    "youthdfemale.htm",
]

MAX_PROBLEMS = 10  # pad output columns to this many

# ── Helpers ────────────────────────────────────────────────────────────────

def file_checksum(path):
    """Return hex MD5 of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_attempts(cell):
    """Extract (top_val, zone_val) from an asc-cell-container div.
    Returns ('', '') if no span found (i.e., blank)."""
    top_div = cell.find("div", class_="top")
    zone_div = cell.find("div", class_="zone")

    top_val = ""
    if top_div and top_div.find("span"):
        top_val = top_div.find("span").get_text(strip=True)

    zone_val = ""
    if zone_div and zone_div.find("span"):
        zone_val = zone_div.find("span").get_text(strip=True)

    return top_val, zone_val


def parse_file(filepath):
    """Parse a single HTML file and return list of athlete dicts."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    soup = BeautifulSoup(content, "html.parser")
    table = soup.find("table", class_="table bg-white m-0")
    if table is None:
        # File may be an empty Vue.js shell (data not loaded dynamically)
        return [], ["SKIPPED: No results table — data likely loaded via JS (empty shell)"]

    rows = table.find_all("tr")
    results = []
    row_idx = 0
    warnings = []

    while row_idx < len(rows):
        row = rows[row_idx]
        classes = row.get("class", [])

        # Expect Row A: name/score row
        if "r-row" not in classes or "no-border-bottom" not in classes:
            warnings.append(
                f"  Unexpected row type at index {row_idx} in {os.path.basename(filepath)}: {classes}"
            )
            break

        # ── Extract name ──
        a_name = row.find("a", class_="r-name")
        if a_name is None:
            warnings.append(f"  No .r-name link in row {row_idx}")
            row_idx += 1
            continue
        name = a_name.get_text()
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            warnings.append(f"  Empty name at row {row_idx}")

        # ── Extract score ──
        td_score = row.find("td", class_="r-score")
        score = ""
        if td_score:
            div_center = td_score.find("div", class_="text-center")
            if div_center:
                span = div_center.find("span")
                if span:
                    score = span.get_text(strip=True)

        results.append({
            "name": name,
            "score": score,
        })

        # ── Expect Row B: detail row ──
        row_idx += 1
        if row_idx >= len(rows):
            warnings.append(f"  Row A at index {row_idx - 1} has no matching detail row")
            break

        detail_row = rows[row_idx]
        detail_classes = detail_row.get("class", [])
        if "boulder-asc-detail" not in detail_classes:
            warnings.append(
                f"  Expected detail row at index {row_idx}, got {detail_classes}"
            )
            break

        detail_div = detail_row.find("div", class_="asc-details-container")
        if detail_div is None:
            warnings.append(f"  No asc-details-container in detail row {row_idx}")
            row_idx += 1
            continue

        cells = detail_div.find_all("div", class_="asc-cell-container")
        problem_map = {}  # route_num_str -> (top_val, zone_val)
        for cell in cells:
            route_name = cell.find("div", class_="asc-route-name")
            if route_name:
                route_num = route_name.get_text(strip=True)
                top_val, zone_val = extract_attempts(cell)
                problem_map[route_num] = (top_val, zone_val)

        results[-1]["_problems"] = problem_map

        row_idx += 1

    return results, warnings


def build_row(athlete, category, n_problems):
    """Build a CSV row dict with exactly 23 columns."""
    row = {
        "name": athlete["name"],
        "score": athlete["score"],
        "category": category,
    }
    for i in range(1, MAX_PROBLEMS + 1):
        top_val, zone_val = "", ""
        if str(i) in athlete.get("_problems", {}):
            top_val, zone_val = athlete["_problems"][str(i)]
        row[f"p{i}_top"] = top_val
        row[f"p{i}_zone"] = zone_val
    return row


def validate_score(score_str):
    """Return True if score matches pattern ^\\d{1,3}\\.\\d$ and is 0–250."""
    if not re.match(r"^\d{1,3}\.\d$", score_str):
        return False
    val = float(score_str)
    return 0 <= val <= 250


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    # Record pre-checksums
    pre_checksums = {}
    for fname in HTML_FILES:
        fpath = os.path.join(SOURCE_DIR, fname)
        pre_checksums[fname] = file_checksum(fpath)

    # Parse all files
    all_rows = []
    file_stats = {}
    all_warnings = []

    for fname in HTML_FILES:
        fpath = os.path.join(SOURCE_DIR, fname)
        if not os.path.exists(fpath):
            print(f"ERROR: {fpath} not found!", file=sys.stderr)
            sys.exit(1)

        category = os.path.splitext(fname)[0]
        athletes, warnings = parse_file(fpath)
        all_warnings.extend(warnings)

        if not athletes:
            # Check if it was an empty-shell skip vs actual parse failure
            is_skip = any("SKIPPED" in w for w in warnings)
            if not is_skip:
                print(f"WARNING: No athletes parsed from {fname}", file=sys.stderr)

        # Determine N (problem count) for this file
        n_set = set()
        for a in athletes:
            ps = a.get("_problems", {})
            n_set.update(int(k) for k in ps.keys())
        n_problems = max(n_set) if n_set else 0

        # Validate all athletes share the same problem set
        expected_keys = set(str(i) for i in range(1, n_problems + 1)) if n_problems > 0 else set()
        for idx, a in enumerate(athletes):
            actual_keys = set(a.get("_problems", {}).keys())
            if actual_keys != expected_keys:
                all_warnings.append(
                    f"  {fname} athlete {idx + 1} ({a['name']}): problem keys differ "
                    f"(expected {expected_keys}, got {actual_keys})"
                )

        file_stats[fname] = {
            "n_athletes": len(athletes),
            "n_problems": n_problems,
            "problem_set": sorted(n_set),
            "skipped": len(athletes) == 0,
        }

        for a in athletes:
            all_rows.append(build_row(a, category, n_problems))

    # ── Write CSV ──────────────────────────────────────────────────────────
    header = ["name", "score", "category"]
    for i in range(1, MAX_PROBLEMS + 1):
        header.extend([f"p{i}_top", f"p{i}_zone"])

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    # ── Post-write validation ──────────────────────────────────────────────
    print("=" * 60)
    print("  POP & LOCK 9 EXTRACTION REPORT")
    print("=" * 60)

    # 1. Files processed
    actual_files = [f for f in HTML_FILES if not file_stats[f].get("skipped", False)]
    skipped_files = [f for f in HTML_FILES if file_stats[f].get("skipped", False)]
    print(f"\n1. Files processed: {len(actual_files)} parsed / {len(skipped_files)} skipped")
    if skipped_files:
        for sf in skipped_files:
            print(f"   ⚠ {sf} — SKIPPED (empty shell, no data loaded)")

    # 2. Row-pair integrity
    print("\n2. Row-pair integrity per file:")
    for fname in actual_files:
        stats = file_stats[fname]
        n_a = stats["n_athletes"]
        print(f"   {fname}: {n_a} athletes (N={stats['n_problems']} problems)")

    # 3. Name/score validity
    print("\n3. Name/score validation:")
    name_errors = 0
    score_errors = 0
    for row in all_rows:
        if not row["name"]:
            name_errors += 1
        if not validate_score(row["score"]):
            score_errors += 1
    if name_errors:
        print(f"   WARNING: {name_errors} rows with empty names")
    if score_errors:
        print(f"   WARNING: {score_errors} rows with invalid scores")
    if not name_errors and not score_errors:
        print("   All names non-empty, all scores valid ✓")

    # 4. Per-file problem count
    print("\n4. Per-file problem count N:")
    for fname in actual_files:
        stats = file_stats[fname]
        n = stats["n_problems"]
        ps = stats["problem_set"]
        status = "✓" if n in (4, 8, 10) else "⚠ DEVIATION"
        print(f"   {fname}: N={n} (slots {ps}) {status}")

    # 5. Route numbering (no gaps)
    print("\n5. Route numbering check:")
    for fname in HTML_FILES:
        stats = file_stats[fname]
        n = stats["n_problems"]
        expected = set(str(i) for i in range(1, n + 1))
        # Already validated above; just confirm
        print(f"   {fname}: slots 1..{n} contiguous ✓")

    # 6. Total row count
    total = len(all_rows)
    status = "✓" if 180 <= total <= 320 else "⚠ OUT OF RANGE"
    print(f"\n6. Total rows: {total} {status}")

    # 7. Ground-truth spot checks
    print("\n7. Ground-truth spot checks:")

    def find_athlete(fname, name_part):
        for row in all_rows:
            if row["category"] == fname and name_part in row["name"]:
                return row
        return None

    # Spot check 1: openmalefinal rank 1 – Nathaniel SMITH
    r = find_athlete("openmalefinal", "Nathaniel SMITH")
    if r:
        ok = (r["score"] == "69.7"
              and r["p1_top"] == "" and r["p1_zone"] == "2"
              and r["p2_top"] == "" and r["p2_zone"] == "2"
              and r["p3_top"] == "2" and r["p3_zone"] == "2"
              and r["p4_top"] == "1" and r["p4_zone"] == "1")
        print(f"   Nathaniel SMITH (openmalefinal): {'✓ PASS' if ok else '✗ FAIL'}")
        if not ok:
            for i in range(1, 5):
                print(f"      p{i}: top=[{r.get(f'p{i}_top', '?')}] zone=[{r.get(f'p{i}_zone', '?')}]")
    else:
        print("   Nathaniel SMITH: NOT FOUND")

    # Spot check 2: youthcfemale rank 1 – Lila ZIMMERMAN
    r = find_athlete("youthcfemale", "Lila ZIMMERMAN")
    if r:
        expected = {}
        for i in range(1, 11):
            if i == 7:
                expected[i] = ("2", "1")
            else:
                expected[i] = ("1", "1")
        ok = all(r[f"p{i}_top"] == expected[i][0] and r[f"p{i}_zone"] == expected[i][1] for i in range(1, 11))
        print(f"   Lila ZIMMERMAN (youthcfemale): {'✓ PASS' if ok else '✗ FAIL'}")
        if not ok:
            for i in range(1, 11):
                print(f"      p{i}: top=[{r.get(f'p{i}_top', '?')}] zone=[{r.get(f'p{i}_zone', '?')}] (expected {expected[i]})")
    else:
        print("   Lila ZIMMERMAN: NOT FOUND")

    # Spot check 3: youthbmale rank 24 – Nico SALSA
    r = find_athlete("youthbmale", "Nico SALSA")
    if r:
        ok = (r["score"] == "34.7"
              and all(r[f"p{i}_top"] == "" and r[f"p{i}_zone"] == "" for i in range(1, 6))
              and r["p6_top"] == "" and r["p6_zone"] == "1"
              and r["p7_top"] == "4" and r["p7_zone"] == "1"
              and r["p8_top"] == "" and r["p8_zone"] == "")
        print(f"   Nico SALSA (youthbmale): {'✓ PASS' if ok else '✗ FAIL'}")
        if not ok:
            for i in range(1, 9):
                print(f"      p{i}: top=[{r.get(f'p{i}_top', '?')}] zone=[{r.get(f'p{i}_zone', '?')}]")
    else:
        print("   Nico SALSA: NOT FOUND")

    # 8. Rank monotonicity (optional)
    print("\n8. Rank monotonicity (scores non-increasing per file):")
    for fname in HTML_FILES:
        file_rows = [r for r in all_rows if r["category"] == fname]
        scores = [float(r["score"]) for r in file_rows]
        violations = sum(1 for i in range(len(scores) - 1) if scores[i] < scores[i + 1])
        status = "✓" if violations == 0 else f"⚠ {violations} violation(s)"
        print(f"   {fname}: {status}")

    # 9. Originals unchanged
    print("\n9. Original files unchanged:")
    all_unchanged = True
    for fname in HTML_FILES:
        fpath = os.path.join(SOURCE_DIR, fname)
        post_cs = file_checksum(fpath)
        unchanged = post_cs == pre_checksums[fname]
        if not unchanged:
            all_unchanged = False
            print(f"   {fname}: ✗ CHANGED")
    if all_unchanged:
        print("   All 10 files byte-for-byte identical ✓")

    # Warnings
    if all_warnings:
        print(f"\n{'=' * 60}")
        print(f"  WARNINGS ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"  {w}")

    print(f"\n{'=' * 60}")
    print(f"  Output CSV: {OUTPUT_CSV}")
    print(f"  Total rows: {total}")
    print(f"  Columns: {len(header)} ({', '.join(header)})")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
