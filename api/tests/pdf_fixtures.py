"""
Tiny valid-PDF builder for tests.

Building this by hand (instead of adding a PDF-authoring dependency like
reportlab just for test fixtures) keeps M2's dependency list to what the
app actually needs at runtime. This writes just enough PDF syntax --
objects, an xref table, a trailer -- for pypdf to read it back correctly.
"""


def build_minimal_pdf(text: str = "") -> bytes:
    """Build a minimal single-page PDF. Empty `text` produces a PDF with
    no text-showing operator, simulating a scanned/image-only PDF."""
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    content_stream = f"BT /F1 18 Tf 72 700 Td ({escaped}) Tj ET" if escaped else ""

    object_bodies = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content_stream)} >>\nstream\n{content_stream}\nendstream",
    ]

    pdf = "%PDF-1.4\n"
    offsets = []
    for index, body in enumerate(object_bodies, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n{body}\nendobj\n"

    xref_offset = len(pdf)
    count = len(object_bodies) + 1
    pdf += f"xref\n0 {count}\n0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"

    return pdf.encode("latin-1")
