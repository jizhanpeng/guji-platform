"""破损区域 mask 光栅化。

strokes_json 格式（原图坐标系）：
    [{"points": [[x, y], ...], "radius": 12, "erase": false}, ...]

光栅化为与页面同尺寸的单通道 PNG（255=破损，0=背景），存 data/masks/。
erase=true 的笔画把已画区域擦回 0（后画的笔画覆盖先画的）。
"""
import json

from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DamageRegion, Image as ImageRow

settings = get_settings()


def mask_storage_path(image_id: int, region_id: int) -> str:
    """相对 data/masks/ 的路径（按页分目录）。"""
    return f"{image_id}/{region_id}.png"


def mask_abs_path(rel: str):
    return settings.masks_dir / rel


def rasterize_strokes(width: int, height: int, strokes: list[dict]) -> Image.Image:
    """矢量笔画 → 二值 mask（L 模式，255=破损）。"""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for s in strokes:
        pts = [(float(x), float(y)) for x, y in s.get("points", [])]
        if not pts:
            continue
        radius = max(1, int(round(s.get("radius", 8))))
        ink = 0 if s.get("erase") else 255
        if len(pts) == 1:  # 单点 → 圆点
            x, y = pts[0]
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=ink)
        else:
            draw.line(pts, fill=ink, width=radius * 2, joint="curve")
            # 端点圆头
            for x, y in (pts[0], pts[-1]):
                draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=ink)
    return mask


def save_mask(db: Session, region: DamageRegion, image: ImageRow) -> str:
    """把 region.strokes_json 光栅化并写盘，更新 mask_path。返回相对路径。"""
    strokes = json.loads(region.strokes_json or "[]")
    mask = rasterize_strokes(image.width, image.height, strokes)
    rel = mask_storage_path(image.id, region.id)
    dst = settings.masks_dir / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    mask.save(dst, "PNG")
    region.mask_path = rel
    return rel


def combined_mask(db: Session, image: ImageRow) -> Image.Image:
    """该页所有非驳回区域的合成 mask（任一区域命中即 255）。"""
    import numpy as np
    out = np.zeros((image.height, image.width), dtype=np.uint8)
    regions = (db.query(DamageRegion)
               .filter_by(image_id=image.id)
               .filter(DamageRegion.status != "rejected").all())
    for r in regions:
        if not r.mask_path:
            continue
        p = settings.masks_dir / r.mask_path
        if p.is_file():
            out |= np.asarray(Image.open(p), dtype=np.uint8)
    return Image.fromarray(out, "L")
