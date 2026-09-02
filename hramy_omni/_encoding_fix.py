"""Fix cp1252-mojibake in text files: re-encode each non-ASCII run as
cp1252 and decode as UTF-8, restoring the original characters.
Genuine Unicode (emoji, arrows, box-drawing) is left untouched.
Writes a change log to _encoding_fix_log.txt.
"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

TEXT_EXT = (".py", ".md", ".toml", ".cfg", ".ini", ".css", ".html")
SKIP_DIRS = ("__pycache__", ".git")
SKIP_FILES = {"_encoding_audit.py", "_encoding_fix.py", "_qa_check.py"}

files = []
for ext in TEXT_EXT:
    files.extend(glob.glob(f"**/*{ext}", recursive=True))
files = [
    f for f in files
    if not any(d in f for d in SKIP_DIRS) and os.path.basename(f) not in SKIP_FILES
]

NON_ASCII_RUN = re.compile(r"[^\x00-\x7F]+")

# Byte values Python's cp1252 encoder refuses; they arise from original
# UTF-8 continuation bytes 0x81/0x8D/0x8F/0x90/0x9D.
EXTRA_BYTES = {
    "": 0x81, "": 0x8D, "": 0x8F, "": 0x90, "": 0x9D,
}

def try_repair(run: str):
    """Return repaired string, or None if the run is genuine Unicode."""
    buf = bytearray()
    for ch in run:
        try:
            buf.extend(ch.encode("cp1252"))
        except UnicodeEncodeError:
            if ch in EXTRA_BYTES:
                buf.append(EXTRA_BYTES[ch])
            else:
                return None
    try:
        return buf.decode("utf-8")
    except UnicodeDecodeError:
        return None

log = open("_encoding_fix_log.txt", "w", encoding="ascii", errors="backslashreplace")
total_fixed = 0

for f in sorted(files):
    with open(f, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        log.write(f"SKIP (invalid utf-8): {f}\n")
        continue

    fixed_runs = []

    def _sub(m):
        run = m.group(0)
        repaired = try_repair(run)
        if repaired is not None and repaired != run:
            ln = text[: m.start()].count("\n") + 1
            fixed_runs.append((ln, run, repaired))
            return repaired
        return run

    new_text = NON_ASCII_RUN.sub(_sub, text)
    if fixed_runs:
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        total_fixed += len(fixed_runs)
        log.write(f"FIXED {f}: {len(fixed_runs)} runs\n")
        for ln, old, new in fixed_runs:
            log.write(f"  line {ln}: {ascii(old)} -> {ascii(new)}\n")

log.write(f"\nTOTAL RUNS FIXED: {total_fixed}\n")
log.close()
print(open("_encoding_fix_log.txt", encoding="ascii").read())
