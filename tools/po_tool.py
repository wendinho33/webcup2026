"""Line-oriented helpers for filling gettext .po files (Terra Nova i18n).

po_list  — print "<msgid-line><TAB><msgid>" for every entry that is
           untranslated or fuzzy, so translations can be authored against
           stable line numbers.
po_fill  — apply "<msgid-line><TAB><translation>" records, rewriting the
           msgstr, clearing any fuzzy flag and obsolete #| references.

Usage:
    python tools/po_tool.py list fr
    python tools/po_tool.py fill fr /tmp/tr_fr_1.tsv [/tmp/tr_fr_2.tsv ...]
"""
import re
import sys
from pathlib import Path

PO_ROOT = Path(__file__).resolve().parent.parent / 'locale'


def parse_entries(text):
    """Yield (msgid_line_no, block_lines) per entry.

    The block spans the whole non-blank run (references, flags, msgid and
    msgstr), while the line number points at the ``msgid`` line itself so
    fills stay anchored even when comments change.
    """
    lines = text.split('\n')
    n = len(lines)
    i = 0
    while i < n:
        if lines[i].startswith('msgid '):
            top = i
            while top > 0 and lines[top - 1] != '':
                top -= 1
            bottom = i
            while bottom + 1 < n and lines[bottom + 1] != '':
                bottom += 1
            yield i + 1, top + 1, lines[top:bottom + 1]
            i = bottom + 1
        else:
            i += 1


def block_msgid(block_lines):
    out = []
    for line in block_lines:
        if line.startswith('msgid '):
            out.append(line[len('msgid '):])
        elif line.startswith('"') and out:
            out.append(line)
    return unquote(''.join(out)) if out else None


def unquote(raw):
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
    joined = ''.join(parts)
    return (
        joined
        .replace('\\n', '\n')
        .replace('\\"', '"')
        .replace('\\\\', '\\')
    )


def quote(value):
    escaped = (
        value
        .replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('\n', '\\n')
    )
    return f'"{escaped}"'


def block_is_fuzzy(block_lines):
    return any(
        line.startswith('#,') and 'fuzzy' in line
        for line in block_lines
    )


def block_msgstr_empty(block_lines):
    seen = False
    after = False
    for line in block_lines:
        if line.startswith('msgstr'):
            seen = True
            after = True
            if line.split(' ', 1)[-1] != '""':
                return False
        elif after and line.startswith('"'):
            return False
    return seen


def load(path):
    text = path.read_text(encoding='utf-8')
    return text.split('\n')


def cmd_list(locale):
    path = PO_ROOT / locale / 'LC_MESSAGES' / 'django.po'
    lines = load(path)
    text = '\n'.join(lines)
    for lineno, _top, block in parse_entries(text):
        msgid = block_msgid(block)
        if msgid is None or msgid == '':
            continue
        if block_msgstr_empty(block) or block_is_fuzzy(block):
            flat = msgid.replace('\n', '\\n')
            print(f'{lineno}\t{flat}')


def cmd_fill(locale, tsv_paths):
    path = PO_ROOT / locale / 'LC_MESSAGES' / 'django.po'
    lines = load(path)
    text = '\n'.join(lines)
    entries = list(parse_entries(text))
    by_start = {lineno: (top, block) for lineno, top, block in entries}

    edits = []
    for tsv_path in tsv_paths:
        for raw in Path(tsv_path).read_text(encoding='utf-8').splitlines():
            if not raw.strip():
                continue
            lineno_str, translation = raw.split('\t', 1)
            lineno = int(lineno_str)
            translation = translation.replace('\\n', '\n')
            if lineno not in by_start:
                raise SystemExit(f'{tsv_path}: line {lineno} is not a msgid')
            edits.append((lineno, by_start[lineno][0], by_start[lineno][1],
                          translation))

    # Rewrite from the bottom up so line numbers stay valid.
    for lineno, top, orig_block, translation in sorted(edits, reverse=True):
        block = list(orig_block)
        orig_len = len(block)
        new_block = []
        skip_obsolete = False
        for line in block:
            if line.startswith('#,') and 'fuzzy' in line:
                flags = [
                    f.strip() for f in line[len('#,'):].split(',')
                    if f.strip() and f.strip() != 'fuzzy'
                ]
                if flags:
                    new_block.append('#, ' + ', '.join(flags))
                skip_obsolete = True
                continue
            if skip_obsolete and line.startswith('#|'):
                continue
            new_block.append(line)
        block = new_block
        has_plural = any(l.startswith('msgid_plural ') for l in block)
        if has_plural:
            nplurals = 2
            m = re.search(r'nplurals\s*=\s*(\d+)', '\n'.join(lines[:40]))
            if m:
                nplurals = int(m.group(1))
            parts = [p for p in translation.split(' ||| ')]
            rendered = []
            for i in range(nplurals):
                value = parts[i] if i < len(parts) else parts[-1]
                rendered.append(f'msgstr[{i}] ' + quote(value))
        else:
            rendered = ['msgstr ' + quote(translation)]
        out = []
        replaced = False
        for line in block:
            if line.startswith('msgstr'):
                if not replaced:
                    out.extend(rendered)
                    replaced = True
                continue
            if replaced and line.startswith('"'):
                continue  # drop old continuation lines
            out.append(line)
        if not replaced:
            raise SystemExit(f'line {lineno}: no msgstr found in block')
        lines[top - 1:top - 1 + orig_len] = out

    path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'{path}: {len(edits)} entries filled')


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, locale = sys.argv[1], sys.argv[2]
    if cmd == 'list':
        cmd_list(locale)
    elif cmd == 'fill':
        cmd_fill(locale, sys.argv[3:])
    else:
        raise SystemExit(f'unknown command {cmd!r}')


if __name__ == '__main__':
    main()