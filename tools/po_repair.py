"""Rewrite a (possibly damaged) .po file into canonical, valid form.

Recovers msgid/msgstr pairs with a tolerant state machine — skips stray
comment lines inside entries, drops fuzzy flags and #| references, and
emits every entry as clean single-line quoted strings. Used to repair a
file after a partial fill; translations are never lost.

Usage:  python tools/po_repair.py <locale>
"""
import re
import sys
from pathlib import Path

PO_ROOT = Path(__file__).resolve().parent.parent / 'locale'


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


class Entry:
    def __init__(self):
        self.refs = []
        self.flags = []
        self.msgid = None
        self.msgid_plural = None
        self.msgstr = {}
        self.section = None

    @property
    def is_header(self):
        return self.msgid == ''


def repair(locale):
    path = PO_ROOT / locale / 'LC_MESSAGES' / 'django.po'
    lines = path.read_text(encoding='utf-8').split('\n')
    entries = []
    cur = None

    def flush():
        nonlocal cur
        if cur is not None and cur.msgid is not None:
            entries.append(cur)
        cur = None

    for line in lines:
        if line.startswith('#:'):
            if cur is None:
                cur = Entry()
            if line not in cur.refs:
                cur.refs.append(line)
            continue
        if line.startswith('#,'):
            if cur is None:
                cur = Entry()
            for flag in line[2:].split(','):
                flag = flag.strip()
                if flag and flag != 'fuzzy':
                    cur.flags.append(flag)
            continue
        if line.startswith('#'):
            continue  # #| obsolete and translator comments are dropped
        if line.startswith('msgid_plural '):
            cur.msgid_plural = unquote(line[len('msgid_plural '):])
            cur.section = 'plural'
            continue
        if line.startswith('msgid '):
            flush()
            cur = Entry()
            cur.msgid = unquote(line[len('msgid '):])
            cur.section = 'id'
            continue
        if line.startswith('msgstr['):
            m = re.match(r'msgstr\[(\d+)\] (.*)', line)
            cur.msgstr[int(m.group(1))] = unquote(m.group(2))
            cur.section = ('plural', int(m.group(1)))
            continue
        if line.startswith('msgstr '):
            cur.msgstr[0] = unquote(line[len('msgstr '):])
            cur.section = ('str', 0)
            continue
        if line.startswith('"'):
            value = unquote(line)
            if cur is None or cur.section is None:
                continue
            if cur.section == 'id':
                cur.msgid += value
            elif cur.section == 'plural' and isinstance(cur.section, str):
                cur.msgid_plural += value
            elif isinstance(cur.section, tuple):
                kind, idx = cur.section
                key = idx if kind == 'str' else idx
                cur.msgstr[key] = cur.msgstr.get(key, '') + value
            continue
        if line.strip() == '':
            continue
        # Anything else: ignore
    flush()

    out = []
    header = next((e for e in entries if e.is_header), None)
    if header is not None:
        out.append(header.refs and ' '.join(header.refs) or '# Translations template.')
        if header.flags:
            out.append('#, ' + ', '.join(header.flags))
        out.append('msgid ""')
        out.append('msgstr ' + quote(header.msgstr.get(0, '')))
        out.append('')
    for entry in entries:
        if entry.is_header or entry.msgid is None:
            continue
        if entry.refs:
            out.append(entry.refs[0])
        if entry.flags:
            out.append('#, ' + ', '.join(entry.flags))
        out.append('msgid ' + quote(entry.msgid))
        if entry.msgid_plural is not None:
            out.append('msgid_plural ' + quote(entry.msgid_plural))
            out.append('msgstr[0] ' + quote(entry.msgstr.get(0, '')))
            out.append('msgstr[1] ' + quote(entry.msgstr.get(1, '')))
        else:
            out.append('msgstr ' + quote(entry.msgstr.get(0, '')))
        out.append('')
    path.write_text('\n'.join(out), encoding='utf-8')
    print(f'{path}: {len(entries)} entries canonicalised')


if __name__ == '__main__':
    repair(sys.argv[1])