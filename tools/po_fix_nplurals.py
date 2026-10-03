"""Enforce each plural entry against the header's nplurals for a locale.

Usage: python tools/po_fix_nplurals.py <locale>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from po_tool import PO_ROOT  # noqa: E402


def fix(locale):
    path = PO_ROOT / locale / 'LC_MESSAGES' / 'django.po'
    lines = path.read_text(encoding='utf-8').split('\n')
    m = re.search(r'nplurals\s*=\s*(\d+)', '\n'.join(lines[:40]))
    nplurals = int(m.group(1)) if m else 2

    out = []
    i = 0
    changed = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('msgid_plural '):
            out.append(line)
            i += 1
            forms = []
            while i < len(lines) and lines[i].startswith('msgstr['):
                forms.append(lines[i].split(' ', 1)[1])
                i += 1
            if len(forms) > nplurals:
                changed += len(forms) - nplurals
                forms = forms[:nplurals]
            elif len(forms) < nplurals:
                while len(forms) < nplurals:
                    forms.append(forms[-1])
                changed += 1
            for idx, value in enumerate(forms):
                out.append(f'msgstr[{idx}] {value}')
            continue
        out.append(line)
        i += 1
    path.write_text('\n'.join(out), encoding='utf-8')
    print(f'{path}: nplurals={nplurals}, {changed} form(s) adjusted')


if __name__ == '__main__':
    fix(sys.argv[1])