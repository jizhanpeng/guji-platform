"""单字裁剪（适配方案 §2.5：保真优先，只裁不变形）。

规则：
- 过滤：宽/高 <10px、非法框、越出页面的框 → 丢弃；
- 中小字（宽高均 ≤56px）：以框心为中心裁固定 64×64 窗口，字形原始像素不动；
  窗口越出页边时用有效区域像素的中值色填充（不引入纯黑/纯白假边缘）；
- 大字（任一边 >56px）：框 +10% padding 的方形窗口，只做等比缩小到 64×64；
- 灰度化 → 三通道（保留纸面底色与墨色质感）；
- 输出 PNG 64×64。
"""
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CharAnnotation, CharCrop, Image as ImageRow
from .imaging import variant_path

settings = get_settings()

CANVAS = 64
SMALL_MAX = 56      # ≤56 定窗；>56 只缩不放
MIN_BOX = 10
BIG_PAD = 1.1       # 大字 padding 系数


def _median_gray(region: Image.Image) -> int:
    """窗口有效区域的灰度中值（纸色填充；全无效时白）。"""
    arr = np.asarray(region)
    return int(np.median(arr)) if arr.size else 255


def crop_char(page: Image.Image, x1: int, y1: int, x2: int, y2: int
              ) -> tuple[Image.Image, str, float] | None:
    """按 §2.5 裁剪单字。返回 (64×64 RGB, kind, scale_ratio)；不合格返回 None。"""
    pw, ph = page.size
    w, h = x2 - x1, y2 - y1
    if w < MIN_BOX or h < MIN_BOX or x2 <= x1 or y2 <= y1:
        return None
    if x1 < 0 or y1 < 0 or x2 > pw or y2 > ph:
        return None

    gray = page.convert("L")
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

    if w <= SMALL_MAX and h <= SMALL_MAX:
        # 定窗 64×64，不重采样
        kind, ratio, side = "fixed64", 1.0, CANVAS
    else:
        side = int(np.ceil(max(w, h) * BIG_PAD))
        kind = "downscaled"
        ratio = CANVAS / side if side > CANVAS else 1.0

    wx1, wy1 = int(round(cx - side / 2)), int(round(cy - side / 2))
    wx2, wy2 = wx1 + side, wy1 + side
    # 与页面的交集
    ix1, iy1 = max(wx1, 0), max(wy1, 0)
    ix2, iy2 = min(wx2, pw), min(wy2, ph)
    region = gray.crop((ix1, iy1, ix2, iy2))
    canvas = Image.new("L", (side, side), _median_gray(region))
    canvas.paste(region, (ix1 - wx1, iy1 - wy1))
    if side != CANVAS:
        canvas = canvas.resize((CANVAS, CANVAS), Image.LANCZOS)
    return canvas.convert("RGB"), kind, ratio


def crop_storage_path(crop_id: int) -> str:
    """相对 data/crops/ 的分片路径。"""
    return f"{crop_id % 1000:03d}/{crop_id}.png"


def auto_crop_project(db: Session, project_id: int,
                      image_ids: list[int] | None = None,
                      progress_cb=None, cancel_cb=None) -> dict:
    """对项目内 confirmed/edited 标注执行裁剪。幂等：已裁过的标注跳过。"""
    q = db.query(ImageRow).filter_by(project_id=project_id)
    if image_ids:
        q = q.filter(ImageRow.id.in_(image_ids))
    images = q.order_by(ImageRow.id).all()

    n_new = n_skip = n_drop = 0
    total = len(images)
    for i, img in enumerate(images):
        if cancel_cb and cancel_cb():
            break
        src = variant_path(project_id, img.id, "original")
        if src is None:
            continue
        annos = (db.query(CharAnnotation)
                 .filter_by(image_id=img.id)
                 .filter(CharAnnotation.deleted_at.is_(None))
                 .filter(CharAnnotation.status.in_(["confirmed", "edited"])).all())
        if not annos:
            continue
        existing = {r[0] for r in db.query(CharCrop.char_annotation_id)
                    .filter(CharCrop.image_id == img.id).all()}
        page = Image.open(src)
        page.load()
        dirty = False
        for a in annos:
            if a.id in existing:
                n_skip += 1
                continue
            out = crop_char(page, a.x1, a.y1, a.x2, a.y2)
            if out is None:
                n_drop += 1
                continue
            im, kind, ratio = out
            crop = CharCrop(image_id=img.id, char_annotation_id=a.id,
                            style_id=img.style_id, char=a.char,
                            crop_path="", crop_kind=kind, scale_ratio=ratio,
                            status="auto")
            db.add(crop)
            db.flush()  # 拿 id 定路径
            rel = crop_storage_path(crop.id)
            dst = settings.crops_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "PNG")
            crop.crop_path = rel
            n_new += 1
            dirty = True
        if dirty:
            db.commit()
        if progress_cb and (i % 10 == 0 or i == total - 1):
            progress_cb((i + 1) / total,
                        f"{i + 1}/{total} 页（新裁 {n_new} / 丢弃 {n_drop} / 跳过 {n_skip}）")
    db.commit()
    return {"cropped": n_new, "dropped": n_drop, "skipped": n_skip, "pages": total}
