"""Audit: find every non-ASCII run in all text files. Writes ASCII-only
report to _encoding_report.txt (console output is truncated/unreliable).

Corruption pattern: UTF-8 bytes were decoded as cp1252 somewhere in the
write pipeline, turning e.g. U+2014 (em-dash) into the 3-char sequence
U+00E2 U+20AC U+201D. Repair = encode('cp1252').decode('utf-8') per run.
"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

SELF = os.path.basename(__file__)
TEXT_EXT = (".py", ".md", ".toml", ".cfg", ".ini", ".css", ".html")
SKIP_DIRS = ("__pycache__", ".git")

files = []
for ext in TEXT_EXT:
    files.extend(glob.glob(f"**/*{ext}", recursive=True))
files = [
    f for f in files
    if not any(d in f for d in SKIP_DIRS)
    and os.path.basename(f) not in (SELF, "_qa_check.py", "_encoding_fix.py")
]

NON_ASCII_RUN = re.compile(r"[^\x00-\x7F]+")

# cp1252 byte values that Python's cp1252 encoder refuses to map back.
# These arise when the original UTF-8 contained bytes 0x81/0x8D/0x8F/0x90/0x9D.
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
                return None  # genuine non-cp1252 Unicode (emoji, arrows, box chars)
    try:
        return buf.decode("utf-8")
    except UnicodeDecodeError:
        return None

out = open("_encoding_report.txt", "w", encoding="ascii", errors="backslashreplace")

total_runs = 0
repairable = 0
per_file = {}
for f in sorted(files):
    with open(f, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        out.write(f"INVALID UTF-8: {f} ({e})\n")
        continue
    lines = text.splitlines()
    for ln, line in enumerate(lines, 1):
        for m in NON_ASCII_RUN.finditer(line):
            run = m.group(0)
            repaired = try_repair(run)
            total_runs += 1
            if repaired is not None and repaired != run:
                repairable += 1
                per_file[f] = per_file.get(f, 0) + 1
                tag = "MOJIBAKE"
                rep = ascii(repaired)
            else:
                tag = "legit-unicode"
                rep = "(genuine)"
            out.write(f"{tag} {f}:{ln} run={ascii(run)} -> {rep}\n")

out.write(f"\nTOTAL NON-ASCII RUNS: {total_runs}\n")
out.write(f"REPAIRABLE MOJIBAKE RUNS: {repairable}\n")
out.write("PER-FILE MOJIBAKE COUNTS:\n")
for f, c in sorted(per_file.items()):
    out.write(f"  {f}: {c}\n")
out.close()
print(open("_encoding_report.txt", encoding="ascii").read())

