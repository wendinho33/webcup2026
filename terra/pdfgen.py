"""A minimal, dependency-free PDF writer for the passenger dossier.

Produces valid PDF 1.4 with Helvetica (WinAnsi) base fonts — no reportlab,
no CDN, matching the project's pure-Python ethos. Supports:

* multi-page A4 documents with automatic page breaks;
* filled rectangles, stroked rules and section headings;
* word-wrapped paragraphs and two-column key/value tables;
* page footers stamped once the total page count is known.

Text is encoded as cp1252 (what the PDF base-14 fonts expect); characters
outside that set fall back to '?'.
"""
from datetime import timezone as dt_timezone

PAGE_W, PAGE_H = 595.28, 841.89  # A4 in points
MARGIN_X = 54
MARGIN_TOP = 64
MARGIN_BOTTOM = 64
CONTENT_W = PAGE_W - 2 * MARGIN_X

# Approximate Helvetica advance widths (per 1000 units) for word-wrapping.
_NARROW = set("ijltfrI.,;:'!|()[]{}/\\ ")
_WIDE = set("mwMW@%")
_MEDIUM = set("ABCDEFGHKNOPQRSUVXYZ23456789&")


def text_width(s, size, bold=False):
    """Rough advance width of ``s`` rendered at ``size`` pt."""
    total = 0.0
    for ch in s:
        if ch in _NARROW:
            unit = 300
        elif ch in _WIDE:
            unit = 850
        elif ch in _MEDIUM:
            unit = 670
        else:
            unit = 520
        total += unit
    width = total / 1000.0 * size
    return width * 1.04 if bold else width


def escape(s):
    """Escape a string for a PDF literal, transcoded to cp1252."""
    data = str(s).encode('cp1252', errors='replace').decode('cp1252')
    out = []
    for ch in data:
        if ch in ('(', ')', '\\'):
            out.append('\\' + ch)
        elif ord(ch) < 32:
            out.append(' ')
        else:
            out.append(ch)
    return ''.join(out)


def wrap(text, size, max_width, bold=False):
    """Greedy word-wrap honouring newlines; drops empty trailing lines."""
    lines = []
    for raw in str(text).split('\n'):
        words = raw.split(' ')
        current = ''
        for word in words:
            candidate = f'{current} {word}'.strip()
            if current and text_width(candidate, size, bold) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    while lines and lines[-1] == '':
        lines.pop()
    return lines or ['']


class Canvas:
    """One PDF page's content stream under construction."""

    def __init__(self, doc):
        self.doc = doc
        self.ops = []
        self.y = PAGE_H - MARGIN_TOP

    # -- primitives -------------------------------------------------
    def rect(self, x, y, w, h, rgb, fill=True, stroke_width=0.7):
        r, g, b = rgb
        op = 'f' if fill else 'S'
        self.ops.append(
            f'{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {w:.2f} '
            f'{h:.2f} re {op}',
        )
        if not fill:
            # emulate stroke width via RG + w before the op
            self.ops[-1] = (
                f'{stroke_width:.2f} w {r:.3f} {g:.3f} {b:.3f} RG '
                f'{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S'
            )

    def line(self, x1, y1, x2, y2, rgb, width=0.7):
        r, g, b = rgb
        self.ops.append(
            f'{width:.2f} w {r:.3f} {g:.3f} {b:.3f} RG '
            f'{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S',
        )

    def text(self, x, y, s, size=10, rgb=(0.06, 0.08, 0.12), bold=False):
        r, g, b = rgb
        font = '/F2' if bold else '/F1'
        self.ops.append(
            f'BT {font} {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg '
            f'1 0 0 1 {x:.2f} {y:.2f} Tm ({escape(s)}) Tj ET',
        )

    def text_right(self, right_x, y, s, size=10, rgb=(0.06, 0.08, 0.12),
                   bold=False):
        self.text(right_x - text_width(s, size, bold), y, s, size, rgb, bold)

    def text_center(self, cx, y, s, size=10, rgb=(0.06, 0.08, 0.12),
                    bold=False):
        self.text(cx - text_width(s, size, bold) / 2, y, s, size, rgb, bold)



class Document:
    """Multi-page document builder that serialises to PDF bytes."""

    def __init__(self, title='Terra Nova', subject='', author='Terra Nova'):
        self.title = title
        self.subject = subject
        self.author = author
        self.pages = [Canvas(self)]
        self.footer = ''

    # -- page management --------------------------------------------
    @property
    def page(self):
        return self.pages[-1]

    def space(self, needed):
        """Break the page when the cursor cannot fit ``needed`` points."""
        if self.page.y - needed < MARGIN_BOTTOM:
            self.pages.append(Canvas(self))

    def heading(self, label, note=''):
        """Section bar: filled strip + title (+ optional right-hand note)."""
        self.space(58)
        c = self.page
        y = c.y - 34
        c.rect(MARGIN_X, y, CONTENT_W, 26, (0.043, 0.075, 0.14))
        c.rect(MARGIN_X, y, 3.5, 26, (1.0, 0.698, 0.341))
        c.text(MARGIN_X + 14, y + 8.5, label.upper(), size=11.5,
               rgb=(0.94, 0.96, 1.0), bold=True)
        if note:
            c.text_right(MARGIN_X + CONTENT_W - 12, y + 9, note, size=8.5,
                         rgb=(0.61, 0.71, 0.85))
        c.y = y - 14

    def paragraph(self, text, size=9.5, rgb=(0.16, 0.2, 0.28), gap=8,
                  bold=False, indent=0):
        lines = wrap(text, size, CONTENT_W - indent, bold)
        leading = size * 1.45
        for line in lines:
            self.space(leading + gap)
            self.page.y -= leading
            self.page.text(MARGIN_X + indent, self.page.y, line, size=size,
                           rgb=rgb, bold=bold)
        self.page.y -= gap

    def kv_rows(self, rows, columns=2):
        """Key/value pairs laid out in ``columns`` balanced columns."""
        col_w = (CONTENT_W - (columns - 1) * 22) / columns
        per = -(-len(rows) // columns)  # ceil
        chunks = [rows[i * per:(i + 1) * per] for i in range(columns)]
        top = self.page.y
        bottoms = []
        for ci, chunk in enumerate(chunks):
            self.page.y = top
            x = MARGIN_X + ci * (col_w + 22)
            for key, value in chunk:
                vlines = wrap(str(value), 10, col_w, bold=False)
                block = 16 + 13.5 * len(vlines) + 8
                self.space(block)
                y = self.page.y - 12
                self.page.text(x, y, key.upper(), size=7,
                               rgb=(0.45, 0.51, 0.6), bold=True)
                for vline in vlines:
                    y -= 13.5
                    self.page.text(x, y, vline, size=10,
                                   rgb=(0.07, 0.09, 0.14))
                self.page.y = y - 8
                bottoms.append(self.page.y)
        if bottoms:
            self.page.y = min(bottoms)
        self.page.y -= 6

    def table(self, headers, rows, widths, aligns=None):
        """Zebra-striped table with a dark header; breaks across pages."""
        aligns = aligns or ['l'] * len(headers)
        pad = 5
        head_h = 20

        def draw_header():
            c = self.page
            c.rect(MARGIN_X, c.y - head_h, CONTENT_W, head_h,
                   (0.075, 0.11, 0.19))
            x = MARGIN_X
            for i, head in enumerate(headers):
                c.text(x + pad, c.y - head_h + 6.5, head.upper(), size=7,
                       rgb=(0.75, 0.82, 0.93), bold=True)
                x += widths[i]
            c.y -= head_h

        self.space(head_h + 24)
        draw_header()
        for ri, row in enumerate(rows):
            cell_lines = [
                wrap(cell, 8.5, widths[i] - 2 * pad)
                for i, cell in enumerate(row)
            ]
            row_h = max(18, 13 * max(len(lines) for lines in cell_lines) + 8)
            if self.page.y - row_h < MARGIN_BOTTOM:
                self.pages.append(Canvas(self))
                draw_header()
            c = self.page
            if ri % 2 == 0:
                c.rect(MARGIN_X, c.y - row_h, CONTENT_W, row_h,
                       (0.955, 0.965, 0.985))
            x = MARGIN_X
            for i, lines in enumerate(cell_lines):
                y = c.y - 13
                for line in lines:
                    if aligns[i] == 'r':
                        c.text_right(x + widths[i] - pad, y, line, size=8.5)
                    else:
                        c.text(x + pad, y, line, size=8.5)
                    y -= 13
                x += widths[i]
            c.y -= row_h
            self.page.line(MARGIN_X, c.y, MARGIN_X + CONTENT_W, c.y,
                           (0.85, 0.88, 0.93), 0.5)

    # -- serialisation ------------------------------------------------
    def render(self):
        """Stamp footers, then serialise the whole document to PDF bytes."""
        total = len(self.pages)
        stamp = self.footer or 'Terra Nova · Mission Control'
        for i, canvas in enumerate(self.pages, start=1):
            canvas.line(MARGIN_X, 44, PAGE_W - MARGIN_X, 44,
                        (0.85, 0.88, 0.93), 0.6)
            canvas.text(MARGIN_X, 30, stamp, size=7.5,
                        rgb=(0.5, 0.55, 0.63))
            canvas.text_right(PAGE_W - MARGIN_X, 30,
                              f'Page {i} of {total}', size=7.5,
                              rgb=(0.5, 0.55, 0.63))

        objects = []  # 1-based: objects[n-1] is body of object n

        def add(body):
            objects.append(body)
            return len(objects)

        # Reserve 1 = catalog, 2 = pages tree (filled in at the end).
        catalog_id = add('')
        pages_id = add('')
        font1 = add(
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica '
            '/Encoding /WinAnsiEncoding >>',
        )
        font2 = add(
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold '
            '/Encoding /WinAnsiEncoding >>',
        )

        kids = []
        for canvas in self.pages:
            stream = '\n'.join(canvas.ops).encode('cp1252', errors='replace')
            content_id = add(
                f'<< /Length {len(stream)} >>\nstream\n'
                .encode('ascii') + stream + b'\nendstream',
            )
            page_id = add(
                '<< /Type /Page /Parent 2 0 R '
                f'/MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] '
                f'/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> '
                f'/Contents {content_id} 0 R >>',
            )
            kids.append(f'{page_id} 0 R')

        objects[pages_id - 1] = (
            f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {len(kids)} >>'
        )
        objects[catalog_id - 1] = (
            f'<< /Type /Catalog /Pages {pages_id} 0 R >>'
        )
        info_id = add(
            '<< /Title ' + f'({escape(self.title)})'
            + ' /Author ' + f'({escape(self.author)})'
            + ' /Subject ' + f'({escape(self.subject)})'
            + ' /Creator (Terra Nova dossier) >>',
        )

        out = bytearray()
        out += b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
        offsets = [0] * (len(objects) + 1)
        for n, body in enumerate(objects, start=1):
            offsets[n] = len(out)
            if isinstance(body, bytes):
                head = f'{n} 0 obj\n'.encode('ascii')
                out += head + body + b'\nendobj\n'
            else:
                out += f'{n} 0 obj\n{body}\nendobj\n'.encode('cp1252',
                                                             errors='replace')
        xref_pos = len(out)
        count = len(objects) + 1
        out += f'xref\n0 {count}\n'.encode('ascii')
        out += b'0000000000 65535 f \n'
        for n in range(1, count):
            out += f'{offsets[n]:010d} 00000 n \n'.encode('ascii')
        out += (
            f'trailer\n<< /Size {count} /Root {catalog_id} 0 R '
            f'/Info {info_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n'
        ).encode('ascii')
        return bytes(out)

        self.page.y -= 10
