"""Parse the annotation rules PDF into structured records with associated images.

Strategy: walk pages, track the current section heading (e.g. "4.13 摩托车"),
and emit one record per page containing the page text + the images on that page,
tagged with the active section so retrieval can surface the right rule + examples.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import fitz  # PyMuPDF

# headings like "4.13 摩托车", "3.1.4 遮挡截断", "9.4 重卡和挂车的判断标准"
HEADING_RE = re.compile(r"^\d+(?:\.\d+){0,3}\s*[\u4e00-\u9fffA-Za-z]")


@dataclass
class Record:
    source: str
    page: int
    section: str
    text: str
    images: list = field(default_factory=list)


def _active_sections(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if HEADING_RE.match(s) and len(s) < 40:
            out.append(s)
    return out


def ingest(pdf_path: str, out_dir: str, dpi: int = 130) -> list[Record]:
    pdf_path = Path(pdf_path)
    out = Path(out_dir)
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    records: list[Record] = []
    current_section = "文档开头"

    # also render full-page images so the model can see layout+boxes in context
    page_render_dir = out / "pdf_pages"
    page_render_dir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(doc):
        pno = i + 1
        text = page.get_text()
        secs = _active_sections(text)
        if secs:
            current_section = secs[0]

        # render the whole page (keeps annotation boxes + captions together)
        page_png = f"pdf_pages/page_{pno:02d}.png"
        pix = page.get_pixmap(dpi=dpi)
        pix.save(out / page_png)

        # also extract embedded raster images individually
        imgs = []
        for j, info in enumerate(page.get_images(full=True)):
            xref = info[0]
            try:
                base = doc.extract_image(xref)
            except Exception:
                continue
            ext = base.get("ext", "png")
            fname = f"images/pdf_p{pno:02d}_{j+1}.{ext}"
            with open(out / fname, "wb") as fh:
                fh.write(base["image"])
            imgs.append(fname)

        section_path = " > ".join(secs) if secs else current_section
        records.append(
            Record(
                source="pdf:联合标注规则V2.5",
                page=pno,
                section=section_path,
                text=f"[第{pno}页 | {section_path}]\n{text}".strip(),
                images=[page_png] + imgs,
            )
        )

    with open(out / "pdf_records.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    print(f"pages={len(records)} embedded_images={sum(len(r.images)-1 for r in records)}")
    return records


if __name__ == "__main__":
    import sys
    import config
    pdf = sys.argv[1] if len(sys.argv) > 1 else config.PDF_PATH
    out = sys.argv[2] if len(sys.argv) > 2 else str(config.KB_DIR)
    ingest(pdf, out)
