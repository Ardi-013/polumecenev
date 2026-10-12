import re
import sys
from pathlib import Path


def extract_changelog(version: str, changelog_path: Path) -> str:
    content = changelog_path.read_text(encoding="utf-8")
    escaped_v = re.escape(version)
    pattern = rf"##\s*\[{escaped_v}\][^\n]*\n(.*?)(?=\n##\s*\[|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        raise ValueError(f"Version [{version}] not found in {changelog_path}")
    return match.group(1).strip()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: extract_release_notes.py <version> <path_to_changelog> [output_file]")
        sys.exit(1)
    ver = sys.argv[1].lstrip("v")
    path = Path(sys.argv[2])
    notes = extract_changelog(ver, path)

    if len(sys.argv) >= 4:
        Path(sys.argv[3]).write_text(notes + "\n", encoding="utf-8")
    else:
        sys.stdout.buffer.write((notes + "\n").encode("utf-8"))

