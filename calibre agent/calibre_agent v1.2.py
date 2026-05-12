"""
Calibre Library Agent
=====================
1. Cleans Royal Road book titles using a local LLM
2. Detects FanFicFare stub errors and queues them for approval

Requirements:
  pip install ollama
  ollama pull llama3.2
  Calibre content server enabled (Preferences > Sharing > Sharing over the net)
  FanFicFare plugin installed in Calibre
"""

import subprocess
import json
import re
import sys
import ollama
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

CALIBREDB_PATH  = r"C:\Program Files\Calibre2\calibredb.exe"
CALIBRE_SERVER  = "http://localhost:8080"
LIBRARY_PATH    = None
OLLAMA_MODEL    = "llama3.2"
FILTER_TAG      = None
DRY_RUN         = False

# Threshold: if web chapter count is less than this % of local, flag as stub
STUB_THRESHOLD  = 0.75  # 75% — e.g. local=188, web=112 (59%) → flagged

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
    r'\([^)]*\d{1,2}\/\d{1,2}[^)]*\)',
    r'\[[^\]]*\d{1,2}\/\d{1,2}[^\]]*\]',
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

def run_calibredb(args: list) -> tuple[str, str]:
    """Run a calibredb command, return (stdout, stderr)."""
    cmd = [CALIBREDB_PATH] + args
    if CALIBRE_SERVER:
        cmd += ["--with-library", CALIBRE_SERVER]
    elif LIBRARY_PATH:
        cmd += ["--library-path", LIBRARY_PATH]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        return result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        print(f"\n[ERROR] calibredb not found at: {CALIBREDB_PATH}")
        sys.exit(1)

def get_all_books() -> list:
    print("Querying Calibre library...")
    args = ["list", "--fields", "id,title,authors,tags,comments,series", "--for-machine"]
    if FILTER_TAG:
        args += ["--search", f"tag:{FILTER_TAG}"]
    stdout, stderr = run_calibredb(args)
    if not stdout:
        return []
    try:
        books = json.loads(stdout)
        print(f"Found {len(books)} book(s) to process.")
        return books
    except json.JSONDecodeError:
        print("[ERROR] Could not parse calibredb output.")
        return []

def update_book_title(book_id: int, new_title: str):
    run_calibredb(["set_metadata", str(book_id), "--field", f"title:{new_title}"])

def fanficfare_update(book_id: int, overwrite: bool = False) -> tuple[str, str]:
    """Attempt a FanFicFare update on a book, optionally with overwrite."""
    args = ["catalog", "--for-machine"]
    # Use calibredb to trigger FanFicFare plugin update
    extra = ["--opt", "force_update_epub_always:true"] if overwrite else []
    stdout, stderr = run_calibredb(
        ["custom_column"] + extra  # placeholder — see note below
    )
    return stdout, stderr

def fanficfare_check(book_id: int) -> tuple[str, str]:
    """
    Run FanFicFare update attempt and return raw output.
    FanFicFare is triggered via calibredb plugin infrastructure.
    """
    stdout, stderr = run_calibredb([
        "catalog", str(book_id),
        "--pluginpath", r"C:\Program Files\Calibre2\resources\plugins",
    ])
    return stdout, stderr

# ─────────────────────────────────────────────
# STUB DETECTION
# ─────────────────────────────────────────────

def parse_stub_error(error_text: str) -> tuple[bool, int, int]:
    """
    Parse FanFicFare's chapter mismatch error.
    Returns (is_stub, local_chapters, web_chapters)
    Example error: 'Existing epub contains 188 chapters, web site only has 112.'
    """
    match = re.search(
        r'contains (\d+) chapters.*?only has (\d+)',
        error_text, re.IGNORECASE
    )
    if match:
        local = int(match.group(1))
        web   = int(match.group(2))
        ratio = web / local if local > 0 else 1
        is_stub = ratio < STUB_THRESHOLD
        return is_stub, local, web
    return False, 0, 0

def prompt_overwrite(book: dict, local_chapters: int, web_chapters: int) -> bool:
    """Ask the user whether to overwrite a stubbed book."""
    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │  STUB DETECTED — APPROVAL REQUIRED          │")
    print("  └─────────────────────────────────────────────┘")
    print(f"  Title  : {book.get('title')}")
    print(f"  Author : {book.get('authors')}")
    print(f"  Local  : {local_chapters} chapters")
    print(f"  Web    : {web_chapters} chapters")
    print(f"  Lost   : {local_chapters - web_chapters} chapters will be replaced")
    print()
    print("  The author has stubbed this story. Overwriting will")
    print("  replace your local epub with the current web version.")
    print()

    while True:
        choice = input("  Overwrite? [y/n]: ").strip().lower()
        if choice in ("y", "yes"):
            return True
        elif choice in ("n", "no"):
            return False
        else:
            print("  Please enter y or n.")

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
        cleaned = cleaned.strip(" ")
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
    print("  Calibre Library Agent")
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

    title_changed = 0
    title_skipped = 0
    stubs_approved = 0
    stubs_skipped = 0
    stub_queue = []

    # ── PASS 1: Title Cleaning ──
    print()
    print("─" * 55)
    print("  PASS 1 — Title Cleaning")
    print("─" * 55)

    for book in books:
        book_id = book.get("id")
        title   = book.get("title", "").strip()
        author  = book.get("authors", "Unknown")
        series  = book.get("series", "") or ""
        comments = book.get("comments", "") or ""

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
                title_skipped += 1
                continue

            if not DRY_RUN:
                update_book_title(book_id, final_title)
                print("  OK Updated.")
            else:
                print("  [DRY RUN] Would update.")
            title_changed += 1

            # Queue for stub check if title had stub indicators
            stub_indicators = ["stub", "hiatus", "dropped", "on hold"]
            if any(s in title.lower() for s in stub_indicators):
                stub_queue.append(book)
        else:
            title_skipped += 1

    # ── PASS 2: Stub Detection ──
    # This pass reads FanFicFare error output from calibredb
    # To use this, run a FanFicFare update from Calibre's GUI first,
    # then copy the error text into a file for the agent to parse.
    # Full automation is possible but requires FanFicFare CLI integration.

    print()
    print("─" * 55)
    print("  PASS 2 — Stub / Chapter Mismatch Check")
    print("─" * 55)
    print()

    # Check for a fanficfare error log dropped by the GUI
    error_log = Path(r"C:\Users\Bslig\Documents\AfterburnerLogs") / "fanficfare_errors.txt"

    if error_log.exists():
        print(f"  Reading FanFicFare error log: {error_log.name}")
        raw_errors = error_log.read_text(encoding="utf-8", errors="replace")

        # Match error blocks to books by title
        for book in books:
            title = book.get("title", "")
            author = book.get("authors", "Unknown")
            if isinstance(author, list):
                author = ", ".join(author)

            # Look for this book's entry in the error log
            if title.split("(")[0].strip()[:20] in raw_errors:
                is_stub, local_ch, web_ch = parse_stub_error(raw_errors)
                if is_stub:
                    approve = prompt_overwrite(book, local_ch, web_ch)
                    if approve:
                        print(f"  -> Approved. Run FanFicFare with Overwrite on: {title}")
                        print(f"     URL: {book.get('comments', 'check metadata for URL')}")
                        stubs_approved += 1
                    else:
                        print(f"  -> Skipped.")
                        stubs_skipped += 1
    else:
        print("  No FanFicFare error log found.")
        print(f"  To use stub detection, save FanFicFare's error output to:")
        print(f"  {error_log}")
        print()
        print("  How to do this:")
        print("  1. Run 'Download/Update' on your Royal Road books in Calibre")
        print("  2. When errors appear, click 'Show Details'")
        print("  3. Copy all the text and paste it into the file above")
        print("  4. Run this agent again")

    # ── SUMMARY ──
    print()
    print("=" * 55)
    print(f"  Titles  : {title_changed} updated, {title_skipped} already clean")
    print(f"  Stubs   : {stubs_approved} approved for overwrite, {stubs_skipped} skipped")
    print("=" * 55)

    if stubs_approved > 0:
        print()
        print("  For approved overwrites, go to each book in Calibre,")
        print("  right-click → Download/Update → switch mode to Overwrite.")

    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
