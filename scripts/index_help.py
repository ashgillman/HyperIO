#!/usr/bin/env python3
"""Make a local searchable text index from an already extracted CHM."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title_parts = []
        self.skip = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
            if self.in_title:
                self.title_parts.append(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for path in sorted(args.extracted_dir.rglob("*.htm")):
        document = Text()
        # The supplied pages declare UTF-8; retain replacements for unreadable bytes.
        document.feed(path.read_text(encoding="utf-8", errors="replace"))
        relative = path.relative_to(args.extracted_dir)
        output = args.output_dir / relative.with_suffix(".txt")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(re.sub(r"\s+", " ", " ".join(document.parts)).strip() + "\n", encoding="utf-8")
        index.append({"page": relative.as_posix(), "title": " ".join(document.title_parts).strip(),
                      "text": output.relative_to(args.output_dir).as_posix()})
    (args.output_dir / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"Indexed {len(index)} help pages in {args.output_dir}")


if __name__ == "__main__":
    main()
