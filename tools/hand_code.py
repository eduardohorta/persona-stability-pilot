"""Hand-code one item at a time. Progress is saved after every answer.

Usage: python tools/hand_code.py data/pilot-v3/hand_coding.csv
Type 1 or 0 for each item, or q to stop. Run it again to continue.
"""
from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path


def save(path: Path, fields: list[str], rows: list[dict]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def wrapped(text: str, width: int) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(textwrap.fill(line, width) if line.strip() else "")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    csv.field_size_limit(10**8)
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    width = min(shutil.get_terminal_size((100, 30)).columns, 100)
    for done, row in enumerate(rows, start=1):
        if row["human"].strip() in {"0", "1"}:
            continue
        print("\n" + "=" * width)
        print(f"Item {done} of {len(rows)}\n")
        print("QUESTION\n" + wrapped(row["question"], width) + "\n")
        print("REPLY\n" + wrapped(row["reply"], width) + "\n")
        print("RUBRIC\n" + wrapped(row["rubric"], width) + "\n")
        while True:
            answer = input("Your code (1, 0, or q to stop): ").strip().lower()
            if answer in {"0", "1", "q"}:
                break
        if answer == "q":
            print("Saved. Run the same command to continue.")
            return
        row["human"] = answer
        save(path, fields, rows)
    print(f"\nFinished: all {len(rows)} items are coded.")


if __name__ == "__main__":
    main()
