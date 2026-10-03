"""Set translations by exact msgid (line numbers irrelevant).

Usage:
    python tools/po_set.py <locale> <file.json>

The JSON file maps msgid -> translation (``\\n`` escapes for multiline
msgids; ``singular ||| plural`` for plural entries, extra forms split the
same way). Fuzzy flags are cleared. Exits non-zero if a key is missing.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from po_tool import PO_ROOT, block_msgid, quote  # noqa: E402


def set_entries(locale, data):
    path = PO_ROOT / locale / 'LC_MESSAGES' / 'django.po'
    lines = path.read_text(encoding='utf-8').split('\n')

    # Locate entries by msgid (tolerant parse: walk msgid lines).
    entries = []  # (msgid, top, bottom_inclusive, msgid_line)
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].startswith('msgid '):
            top = i
            while top > 0 and lines[top - 1] != '':
                top -= 1
            bottom = i
            while bottom + 1 < n and lines[bottom + 1] != '':
                bottom += 1
            block = lines[top:bottom + 1]
            mid = None
            for j, l in enumerate(block):
                if l.startswith('msgid '):
                    mid = top + j
                    break
            # tolerant msgid: join all quoted runs until msgstr
            parts = []
            collect = False
            for l in block:
                if l.startswith('msgid '):
                    collect = True
                    parts.append(l[len('msgid '):])
                    continue
                if collect and l.startswith('msgstr'):
                    collect = False
                    continue
                if collect and l.startswith('"'):
                    parts.append(l)
                    continue
                if collect and l.startswith('#'):
                    continue
            raw = ''.join(parts)
            m_parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
            mid_text = (
                ''.join(m_parts).replace('\\n', '\n')
                .replace('\\"', '"').replace('\\\\', '\\')
            )
            entries.append((mid_text, top, bottom, mid, block))
            i = bottom + 1
        else:
            i += 1

    nplurals = 2
    m = re.search(r'nplurals\s*=\s*(\d+)', '\n'.join(lines[:40]))
    if m:
        nplurals = int(m.group(1))

    applied = set()
    edits = []
    for msgid, top, bottom, mid, block in entries:
        if msgid in data:
            applied.add(msgid)
            edits.append((top, block, data[msgid]))

    missing = set(data) - applied
    if missing:
        raise SystemExit('msgid not found: ' + repr(sorted(missing)))

    for top, block, translation in sorted(edits, key=lambda e: e[0], reverse=True):
        out = []
        skip_obsolete = False
        for line in block:
            if line.startswith('#,') and 'fuzzy' in line:
                flags = [
                    f.strip() for f in line[2:].split(',')
                    if f.strip() and f.strip() != 'fuzzy'
                ]
                if flags:
                    out.append('#, ' + ', '.join(flags))
                skip_obsolete = True
                continue
            if skip_obsolete and line.startswith('#|'):
                continue
            out.append(line)
        block = out
        orig_len = None
        # recompute original span length from current block state
        has_plural = any(l.startswith('msgid_plural ') for l in block)
        if has_plural:
            parts = translation.split(' ||| ')
            rendered = []
            for i in range(nplurals):
                value = parts[i] if i < len(parts) else parts[-1]
                rendered.append(f'msgstr[{i}] ' + quote(value))
        else:
            rendered = ['msgstr ' + quote(translation)]
        final = []
        replaced = False
        for line in block:
            if line.startswith('msgstr'):
                if not replaced:
                    final.extend(rendered)
                    replaced = True
                continue
            if replaced and line.startswith('"'):
                continue
            final.append(line)
        # replace in lines: find span from top to top+len(ORIGINAL block)
        # (block already cleaned; locate bottom by scanning from top)
        span = top
        while span < n and lines[span] != '' or (span < n and False):
            break
        # safer: recompute bottom from original lines
        b = top
        while b + 1 < n and lines[b + 1] != '':
            b += 1
        lines[top:b + 1] = final

    path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'{path}: {len(edits)} entries set')


if __name__ == '__main__':
    locale = sys.argv[1]
    data = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
    set_entries(locale, data)