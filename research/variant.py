"""Write a copy of the Pine script with some input defaults overridden.

Usage: python variant.py <src> <dst> "Input Title=value" ...
Values are inserted verbatim (quote strings yourself, e.g. 'Risk Mode="Fixed"').
"""
import re
import sys

src, dst, *pairs = sys.argv[1:]
text = open(src, encoding="utf-8").read()
for pair in pairs:
    if pair.startswith("RAW:"):
        old, new = pair[4:].split("=>", 1)
        if text.count(old) != 1:
            sys.exit(f"raw '{old}' matched {text.count(old)} times")
        text = text.replace(old, new)
        continue
    title, value = pair.split("=", 1)
    pat = re.compile(r'(input(?:\.\w+)?\()([^,]+?)(,\s*"' + re.escape(title) + r'")')
    text, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text)
    if n != 1:
        sys.exit(f"input '{title}' matched {n} times")
open(dst, "w", encoding="utf-8", newline="").write(text)
print("wrote", dst, pairs)
