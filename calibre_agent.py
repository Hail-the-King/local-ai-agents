"""
Calibre Library Agent
=====================
Cleans Royal Road book titles in your Calibre library using a local Ollama LLM.

Requirements:
  pip install ollama
  ollama pull llama3.2
  Calibre content server enabled (Preferences > Sharing > Sharing over the net)
"""

import subprocess
import json
import re
import sys
import ollama

# ─────────────────────────────────────────────
# CONFIGURATION — edit these to match your setup
# ─────────────────────────────────────────────

CALIBREDB_PATH  = r"C:\Program Files\Calibre2\calibredb.exe"
CALIBRE_SERVER  = "http://localhost:8080"  # must match port in Calibre prefs
LIBRARY_PATH    = None        # only used if NOT using the content server
OLLAMA_MODEL    = "llama3.2"
FILTER_TAG      = None        # None = all books, or e.g. "Royal Road"
DRY_RUN         = False        # set False when you're happy with results

# ─────────────────────────────────────────────
# REGEX PRE-CLEANER
# ─────────────────────────────────────────────

NOISE_PATTERNS = [
    r'\[STUB\]', r'\(STUB\)', r'\bSTUB\b',
    r'\[WIP\]', r'\(WIP\)', r'\bWIP\b',
    r'\[HIATUS\]', r'\(HIATUS\)',
    r'\[COMPLETE\]', r'\(COMPLETE\)', r'\bCOMPLETE\b',
    r'\[DROPPED\]', r'\(DROPPED\)',
    r'\[ON HOLD\]', r'\(ON HOLD\)',
    r'v\d+\.\d+(\.\d+)?',
    r'\[(Vol|Volume|Book|Arc)\.?\s*\d+\]',
    r'\((Vol|Volume|Book|Arc)\.?\s*\d+\)',
    r'\[\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\]',
    r'\(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\)',
    r'Updated?\s*:?\s*\d{1,2}[\/\-]\d{1,2}',
    r'\|\s*Royal Road', r'- Royal Road',
    r'\(Royal Road\)', r'\[Royal Road\]',
    r'(?i)\(web serial\)', r'(?i)\(litrpg\)',
    r'(?i)\s*-\s*(ongoing|complete|hiatus|dropped)$',
    # ── NEW: catches any bracketed phrase containing a date ──
    r'\([^)]*\d{1,2}\/\d{1,2}[^)]*\)',
    r'\[[^\]]*\d{1,2}\/\d{1,2}[^\]]*\]',
    # ── NEW: explicit stubbing/status phrases ──
    r'(?i)\(stubbing soon[^)]*\)',
    r'(?i)\[stubbing soon[^\]]*\]',
    r'(?i)\(going on hiatus[^)]*\)',
    r'(?i)\(on hiatus[^)]*\)',
    r'(?i)\(taking a break[^)]*\)',
]

def regex_preclean(title: str) -> str:
    cleaned = title
    for pattern in NOISE_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(" -:_|,.")
    return cleaned

# ─────────────────────────────────────────────
# CALIBRE INTERFACE
# ─────────────────────────────────────────────

def run_calibredb(args: list) -> str:
    cmd = [CALIBREDB_PATH] + args

    if CALIBRE_SERVER:
        cmd += ["--with-library", CALIBRE_SERVER]
    elif LIBRARY_PATH:
        cmd += ["--library-path", LIBRARY_PATH]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            print(f"  [calibredb error] {result.stderr.strip()}")
        return result.stdout.strip()
    except FileNotFoundError:
        print(f"\n[ERROR] calibredb not found at: {CALIBREDB_PATH}")
        print("Update CALIBREDB_PATH in the script.")
        sys.exit(1)

def get_all_books() -> list:
    print("Querying Calibre library...")
    args = ["list", "--fields", "id,title,authors,tags,comments,series", "--for-machine"]
    if FILTER_TAG:
        args += ["--search", f"tag:{FILTER_TAG}"]
    raw = run_calibredb(args)
    if not raw:
        return []
    try:
        books = json.loads(raw)
        print(f"Found {len(books)} book(s) to process.")
        return books
    except json.JSONDecodeError:
        print("[ERROR] Could not parse calibredb output.")
        print("Raw output:", raw[:500])
        return []

def update_book_title(book_id: int, new_title: str):
    run_calibredb(["set_metadata", str(book_id), "--field", f"title:{new_title}"])

# ─────────────────────────────────────────────
# LLM TITLE CLEANER
# ─────────────────────────────────────────────

def llm_clean_title(raw_title: str, pre_cleaned: str, author: str, series: str) -> str:
    prompt = f"""You are a librarian cleaning book titles from Royal Road (a web serial fiction platform).
Authors often append noise to titles: status tags, version numbers, date stamps, platform suffixes.

Return ONLY the clean canonical title. No explanation, no quotes.

Rules:
- Remove: [STUB], (WIP), [HIATUS], [COMPLETE], [DROPPED], (ON HOLD)
- Remove: version numbers (v1.2), date stamps ([01/15/24]), platform tags (| Royal Road)
- Preserve the author's intended title as closely as possible
- If already clean, return exactly as-is

Original title: {raw_title}
Pre-cleaned (regex): {pre_cleaned}
Author: {author}
Series: {series or "N/A"}

Clean title:"""

    try:
        response = ollama.chat(model=OLLAMA_MODEL,
                               messages=[{"role": "user", "content": prompt}])
        cleaned = response["message"]["content"].strip().strip('"').strip("'")
        if len(cleaned) > len(raw_title) + 20 or "\n" in cleaned:
            return pre_cleaned
        return cleaned
    except Exception as e:
        print(f"  [LLM error] {e} — using regex result")
        return pre_cleaned

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Calibre Agent — Royal Road Title Cleaner")
    print("=" * 55)
    if DRY_RUN:
        print("  *** DRY RUN — no changes will be written ***")
    print()

    try:
        ollama.list()
    except Exception:
        print("[ERROR] Cannot reach Ollama. Run: ollama serve")
        sys.exit(1)

    books = get_all_books()
    if not books:
        print("No books found. Check FILTER_TAG or LIBRARY_PATH.")
        return

    changed = skipped = 0

    for book in books:
        book_id = book.get("id")
        title   = book.get("title", "").strip()
        author  = book.get("authors", "Unknown")
        series  = book.get("series", "") or ""
        if isinstance(author, list):
            author = ", ".join(author)

        pre_cleaned = regex_preclean(title)

        if pre_cleaned != title:
            print(f"\n[{book_id}] {title}")
            print(f"  Author : {author}")
            final_title = llm_clean_title(title, pre_cleaned, author, series)
            print(f"  Cleaned: {final_title}")

            if final_title == title:
                print("  -> No change needed.")
                skipped += 1
                continue

            if not DRY_RUN:
                update_book_title(book_id, final_title)
                print("  OK Updated.")
            else:
                print("  [DRY RUN] Would update.")
            changed += 1
        else:
            skipped += 1

    print()
    print("=" * 55)
    print(f"  Done. {changed} would be updated, {skipped} already clean.")
    print("=" * 55)
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()