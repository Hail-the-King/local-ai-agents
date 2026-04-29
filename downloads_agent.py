"""
Downloads Cleanup Agent
=======================
Uses a local LLM to judge each file in your Downloads folder and moves
suspected junk to a staging folder for you to review.

Junk = installers, downloaders, temp files, one-time-use executables, etc.
Keep = documents, media, projects, game files, archives with real content.

Requirements:
  pip install ollama
  ollama pull llama3.2
"""

import os
import sys
import shutil
import ollama
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

DOWNLOADS_DIR   = Path(r"C:\Users\Bslig\Downloads")
STAGING_DIR     = Path(r"C:\Users\Bslig\Downloads\_JUNK_REVIEW")
OLLAMA_MODEL    = "llama3.2"
DRY_RUN         = False   # Set False when happy with results

# Files to always skip — never touch these
ALWAYS_KEEP_EXTENSIONS = {
    ".mp3", ".mp4", ".mkv", ".avi", ".mov", ".flac", ".wav",  # media
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".psd",          # images
    ".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".txt",         # documents
    ".py", ".js", ".ts", ".html", ".css", ".json", ".xml",     # code/projects
    ".zip", ".rar", ".7z",                                      # archives (LLM judges these)
    ".epub", ".mobi", ".cbz",                                   # books
    ".sav", ".save",                                            # game saves
}

# Files to always flag as junk without asking LLM — clear cut cases
ALWAYS_JUNK_EXTENSIONS = {
    ".tmp", ".temp", ".crdownload", ".part", ".partial",
    ".~", ".log",
    ".msi",    # Windows installer packages
    ".msp",    # Windows installer patches
    ".msu",    # Windows update packages
}

# ─────────────────────────────────────────────
# LLM JUDGE
# ─────────────────────────────────────────────

def llm_judge(filename: str, extension: str, size_kb: float) -> tuple[str, str]:
    """
    Ask the LLM whether a file is junk or worth keeping.
    Returns (verdict, reason) where verdict is 'JUNK' or 'KEEP'.
    """
    prompt = f"""You are helping clean up a Windows Downloads folder. Judge whether this file is junk or worth keeping.

KEEP if the file is likely:
- A document, spreadsheet, or PDF the user created or needs
- Media: music, video, images, photos
- A game file, game mod, or game-related download
- A project file or source code
- An archive (.zip/.rar) that likely contains real content (mods, assets, projects)
- Software the user likely still uses regularly (e.g. a main application installer)

JUNK if the file is likely:
- A one-time-use installer or downloader (setup_*.exe, *_installer.exe, *downloader*)
- A browser download helper or web installer stub
- A temp or partial download file
- Duplicate or redundant installer for something already installed
- A patch or updater for software that auto-updates anyway
- Clearly outdated (old version numbers in the filename)

Filename: {filename}
Extension: {extension}
Size: {size_kb:.1f} KB

Respond in exactly this format:
VERDICT: JUNK or KEEP
REASON: one sentence explanation"""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response["message"]["content"].strip()
        verdict = "KEEP"
        reason  = "Could not parse response"

        for line in text.splitlines():
            if line.startswith("VERDICT:"):
                v = line.replace("VERDICT:", "").strip().upper()
                if "JUNK" in v:
                    verdict = "JUNK"
                elif "KEEP" in v:
                    verdict = "KEEP"
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        return verdict, reason

    except Exception as e:
        return "KEEP", f"LLM error ({e}) — defaulting to KEEP"


# ─────────────────────────────────────────────
# FILE MOVER
# ─────────────────────────────────────────────

def move_to_staging(file_path: Path):
    """Move a file to the staging folder, preserving relative subfolder structure."""
    relative = file_path.relative_to(DOWNLOADS_DIR)
    dest = STAGING_DIR / relative
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Handle name collisions
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        dest = dest.parent / f"{stem}__{file_path.stat().st_mtime:.0f}{suffix}"

    shutil.move(str(file_path), str(dest))


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Downloads Cleanup Agent")
    print("=" * 60)
    if DRY_RUN:
        print("  *** DRY RUN — no files will be moved ***")
    print(f"  Scanning : {DOWNLOADS_DIR}")
    print(f"  Staging  : {STAGING_DIR}")
    print()

    # Verify Ollama
    try:
        ollama.list()
    except Exception:
        print("[ERROR] Cannot reach Ollama. Run: ollama serve")
        sys.exit(1)

    if not DOWNLOADS_DIR.exists():
        print(f"[ERROR] Downloads directory not found: {DOWNLOADS_DIR}")
        sys.exit(1)

    # Collect all files recursively, skip the staging dir itself
    all_files = [
        p for p in DOWNLOADS_DIR.rglob("*")
        if p.is_file() and STAGING_DIR not in p.parents and p.parent != STAGING_DIR
    ]

    print(f"Found {len(all_files)} file(s) to evaluate.\n")

    kept = 0
    junked = 0
    skipped = 0
    log_lines = []

    for file_path in all_files:
        filename  = file_path.name
        extension = file_path.suffix.lower()
        try:
            size_kb = file_path.stat().st_size / 1024
        except Exception:
            continue

        # Always-keep extensions — skip LLM entirely
        if extension in ALWAYS_KEEP_EXTENSIONS:
            kept += 1
            skipped += 1
            continue

        # Always-junk extensions — no need to ask LLM
        if extension in ALWAYS_JUNK_EXTENSIONS:
            verdict = "JUNK"
            reason  = "Temp/partial download file"
        else:
            verdict, reason = llm_judge(filename, extension, size_kb)

        # Display result
        icon = "JUNK" if verdict == "JUNK" else "KEEP"
        print(f"[{icon}] {filename}")
        print(f"       {reason}")

        log_lines.append(f"{icon}\t{filename}\t{reason}")

        if verdict == "JUNK":
            junked += 1
            if not DRY_RUN:
                try:
                    move_to_staging(file_path)
                    print(f"       -> Moved to staging.")
                except Exception as e:
                    print(f"       -> Move failed: {e}")
        else:
            kept += 1

    # Write log
    if not DRY_RUN and log_lines:
        log_path = STAGING_DIR / f"_cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines), encoding="utf-8")
        print(f"\nLog saved to: {log_path}")

    print()
    print("=" * 60)
    print(f"  Done. {junked} flagged as junk, {kept} kept, {skipped} skipped (safe extension).")
    print("=" * 60)

    if junked > 0 and not DRY_RUN:
        print(f"\nReview your junk files at:\n  {STAGING_DIR}")
        print("Delete the folder when you're satisfied, or fish out anything you want to keep.")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()