"""Builds web/src/lib/themes/themeData.ts from OpenChamber theme JSON files.

Run, from the repository root:

    python3 web/scripts/themes_from_openchamber.py \
        <openchamber>/packages/ui/src/lib/theme/themes web/src/lib/themes/themeData.ts

Then set the upstream commit in the generated header.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

src, out = sys.argv[1], sys.argv[2]
FIELDS = [
    ("canvas", "surface", "background"),
    ("elevated", "surface", "elevated"),
    ("muted", "surface", "muted"),
    ("text", "surface", "foreground"),
    ("textSecondary", "surface", "mutedForeground"),
    ("border", "interactive", "border"),
    ("borderHover", "interactive", "borderHover"),
    ("accent", "primary", "base"),
    ("accentHover", "primary", "hover"),
    ("accentActive", "primary", "active"),
    ("selection", "interactive", "selection"),
    ("hover", "interactive", "hover"),
    ("active", "interactive", "active"),
    ("focus", "interactive", "focusRing"),
    ("error", "status", "error"),
    ("warning", "status", "warning"),
    ("success", "status", "success"),
    ("info", "status", "info"),
]
rows, missing = [], []
for path in sorted(glob.glob(os.path.join(src, "*.json"))):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    meta, colours = data["metadata"], data["colors"]
    family = re.sub(r"\s*\(?(light|dark)\)?$", "", meta["name"], flags=re.I).strip()
    values = {}
    for key, group, name in FIELDS:
        value = colours.get(group, {}).get(name)
        if value is None:
            missing.append(f"{meta['id']}.{group}.{name}")
            continue
        if not re.fullmatch(r"#[0-9a-fA-F]{3,8}", value):
            sys.exit(f"not a hex colour: {meta['id']} {group}.{name} = {value}")
        values[key] = value.lower()
    author = meta.get("author")
    rows.append((family.lower(), meta["variant"], meta["id"], family, author, values))
rows.sort(key=lambda r: (r[0], r[1] != "light"))
lines = []
for _, variant, tid, family, author, values in rows:
    body = ", ".join(f'{k}: "{v}"' for k, v in values.items())
    by = f', author: "{author}"' if author else ""
    lines.append(
        f'  {{ id: "{tid}", name: "{family}", variant: "{variant}"{by}, colours: {{ {body} }} }},'
    )
header = """// Generated from OpenChamber's theme files (packages/ui/src/lib/theme/themes/*.json,
// MIT, Copyright (c) 2025 Bohdan Triapitsyn) at upstream commit 8db0e8d73. Only the
// colours OMRS tokens use are kept. Many themes port third-party palettes; the
// palette names credit their original authors. Do not edit by hand.

import type { ThemeDefinition } from "./types";

export const THEME_DATA: readonly ThemeDefinition[] = [
"""
with open(out, "w", encoding="utf-8") as handle:
    handle.write(header + "\n".join(lines) + "\n];\n")
print(len(rows), "themes;", len(missing), "missing values:", missing[:20])
