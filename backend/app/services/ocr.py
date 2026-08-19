"""PaddleOCR 自动文字标注（方法一/扫描页）。

spike 结论（2026-08-19，paddleocr 3.7.0 + paddlepaddle CPU）：
- PP-OCRv6 检出的是**竖排文本行**（整列一个条带），不是单字；
  识别文本与该列字数基本对齐 → 行框按字数等分为单字框（竖列纵向等分）；
- Windows + 新版 paddle 必须 `enable_mkldnn=False`，否则 oneDNN PIR 报错；
- CPU 约 35-40s/页，模型常驻 worker 进程内复用。

识别错字会导致等分错位——产物一律 status='auto'，人工复查后确认。
"""
import unicodedata

from sqlalchemy.orm import Session

from ..models import CharAnnotation, Image as ImageRow
from .imaging import variant_path

_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(use_doc_orientation_classify=False,
                         use_doc_unwarping=False,
                         use_textline_orientation=False,
                         enable_mkldnn=False,  # Windows/oneDNN PIR bug 规避
                         lang="ch")
    return _ocr


def _keep(char: str) -> bool:
    if not char or char.isspace():
        return False
    return unicodedata.category(char)[0] in ("L", "N", "P")


def split_line_to_chars(box: list[int], text: str) -> list[tuple[int, int, int, int, str]]:
    """行框按字数等分为单字框。竖列（h>w）纵向切，横排横向切。"""
    chars = [c for c in text if _keep(c)]
    n = len(chars)
    x1, y1, x2, y2 = (int(v) for v in box)
    if n == 0 or x2 <= x1 or y2 <= y1:
        return []
    w, h = x2 - x1, y2 - y1
    out = []
    for i, c in enumerate(chars):
        if h >= w:  # 竖排：自上而下
            cy1 = y1 + round(h * i / n)
            cy2 = y1 + round(h * (i + 1) / n)
            out.append((x1, cy1, x2, cy2, c))
        else:       # 横排：自左而右
            cx1 = x1 + round(w * i / n)
            cx2 = x1 + round(w * (i + 1) / n)
            out.append((cx1, y1, cx2, y2, c))
    return out


def ocr_image(db: Session, image: ImageRow) -> dict:
    """对单页跑 OCR 并写入 CharAnnotation（origin='ocr'，幂等）。"""
    src = variant_path(image.project_id, image.id, "original")
    if src is None:
        return {"lines": 0, "chars": 0, "skipped": 0}
    res = _get_ocr().predict(str(src))
    existing = {(a.x1, a.y1, a.x2, a.y2)
                for a in db.query(CharAnnotation)
                .filter_by(image_id=image.id, origin="ocr").all()}
    n_lines = n_chars = n_skip = 0
    for r in res:
        for box, text, score in zip(r["rec_boxes"], r["rec_texts"], r["rec_scores"]):
            n_lines += 1
            for x1, y1, x2, y2, c in split_line_to_chars(list(box), text):
                if (x1, y1, x2, y2) in existing:
                    n_skip += 1
                    continue
                db.add(CharAnnotation(image_id=image.id, x1=x1, y1=y1, x2=x2, y2=y2,
                                      char=c, origin="ocr", confidence=float(score),
                                      status="auto"))
                n_chars += 1
    # 页面状态推进到自动标注
    from .page_status import recompute_page_status
    db.flush()
    recompute_page_status(db, image.id)
    db.commit()
    return {"lines": n_lines, "chars": n_chars, "skipped": n_skip}


def ocr_project(db: Session, project_id: int, image_ids: list[int] | None = None,
                progress_cb=None, cancel_cb=None) -> dict:
    q = db.query(ImageRow).filter_by(project_id=project_id)
    if image_ids:
        q = q.filter(ImageRow.id.in_(image_ids))
    images = q.order_by(ImageRow.id).all()
    tot = {"lines": 0, "chars": 0, "skipped": 0}
    for i, img in enumerate(images):
        if cancel_cb and cancel_cb():
            break
        s = ocr_image(db, img)
        for k in tot:
            tot[k] += s[k]
        if progress_cb:
            progress_cb((i + 1) / len(images),
                        f"{i + 1}/{len(images)} 页（新增 {tot['chars']} 字）")
    return {**tot, "pages": len(images)}
