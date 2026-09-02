"""QA scan: mojibake detection via ASCII-only escape patterns."""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

# Classic UTF-8-decoded-as-cp1252 sequences as pure-ASCII escapes.
MOJIBAKE = {
    "em_dash_mojibake": "â€”",
    "bullet_mojibake": "â€¢",
    "times_mojibake": "Ã—",
    "middot_mojibake": "Â·",
    "eacute_mojibake": "Ã©",
    "lquote_mojibake": "â€œ",
    "raquo_mojibake": "Â»",
    "laquo_mojibake": "Â«",
    "egrave_mojibake": "Ã¨",
    "replacement_char": "",
    "arrow_mojibake": "â†’",
    "check_mojibake": "âœ“",
    "cross_mojibake": "âœ—",
    "box_mojibake": "â•",
}
SELF = os.path.basename(__file__)

TEXT_EXT = (".py", ".md", ".toml", ".txt", ".cfg", ".ini", ".json", ".css", ".html")
files = []
for ext in TEXT_EXT:
    files.extend(glob.glob(f"**/*{ext}", recursive=True))
files = [f for f in files if "__pycache__" not in f and ".git" not in f and os.path.basename(f) != SELF]

problems = []
for f in sorted(files):
    with open(f, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        problems.append(f"INVALID UTF-8: {f} ({e})")
        continue
    for name, bad in MOJIBAKE.items():
        if bad in text:
            ln = text[: text.index(bad)].count("\n") + 1
            problems.append(f"MOJIBAKE[{name}]: {f}:{ln}")

print(f"Scanned {len(files)} text files (excluded: {SELF}).")
if problems:
    print(f"PROBLEMS ({len(problems)}):")
    for p in problems:
        print("  " + p)
    sys.exit(1)
print("ENCODING CLEAN: no mojibake, all files valid UTF-8.")
