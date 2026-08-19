"""HDR28K 风格合成退化 + 数据集导出（方法一）。

契约（论文 §IV-A，cas-sc-sample.tex）：
- 512×512 patch 成对数据：GT（原图）/ degraded（合成退化）/ mask（退化区域二值）
  / content（字模内容图，标准字体按框位渲染）；
- 三种退化：缺字（character_missing，区域内 inpaint 移除，论文用 LaMa，
  本地用 OpenCV Telea 近似）、纸损（paper_damage，黑/白随机斑块，50%）、
  墨迹侵蚀（ink_erosion，字迹淡出+模糊+水渍，论文用 Genalog，本地近似实现）；
- 类型配比 25% / 50% / 25%（与 HDR28K 一致）。

布局：
    {export}/hdr28k/{split}/gt/{n:06d}.png
    {export}/hdr28k/{split}/degraded/{n:06d}.png
    {export}/hdr28k/{split}/mask/{n:06d}.png
    {export}/hdr28k/{split}/content/{n:06d}.png
    {export}/hdr28k/{split}/meta.jsonl   # 每行: id, page, bbox, dtype, chars
"""
import json
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (CharAnnotation, DamageRegion, Export, Image as ImageRow)
from .imaging import variant_path
from .masks import combined_mask
from .render import _load_fonts

settings = get_settings()

PATCH = 512
DTYPES = ("character_missing", "paper_damage", "ink_erosion")
DTYPE_W = (0.25, 0.50, 0.25)


# ---- 退化算子（作用于 RGB ndarray，返回 (退化图, mask uint8 0/255)）----

def deg_character_missing(img: np.ndarray, boxes: list[tuple],
                          rng: random.Random) -> tuple[np.ndarray, np.ndarray]:
    """随机选若干字框（或一个文本块），inpaint 抹除。"""
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    inner = [b for b in boxes if b[0] >= 0 and b[1] >= 0 and b[2] <= w and b[3] <= h]
    if not inner:
        return img, mask
    n = max(1, round(len(inner) * rng.uniform(0.05, 0.2)))
    for x1, y1, x2, y2 in rng.sample(inner, min(n, len(inner))):
        pad = 2
        mask[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)] = 255
    # LaMa 近似：Telea inpaint
    out = cv2.inpaint(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), mask, 5,
                      cv2.INPAINT_TELEA)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB), mask


def deg_paper_damage(img: np.ndarray, rng: random.Random) -> tuple[np.ndarray, np.ndarray]:
    """随机黑/白斑块（虫蛀/氧化）：不规则椭圆+噪声边缘。"""
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    overlay = img.copy()
    n = rng.randint(1, 4)
    for _ in range(n):
        cx, cy = rng.randint(0, w - 1), rng.randint(0, h - 1)
        rx, ry = rng.randint(8, 60), rng.randint(8, 60)
        angle = rng.uniform(0, 180)
        color = 0 if rng.random() < 0.5 else 255  # 黑洞或白斑
        blob = np.zeros((h, w), np.uint8)
        cv2.ellipse(blob, (cx, cy), (rx, ry), angle, 0, 360, 255, -1)
        # 噪声边缘
        noise = np.random.default_rng(rng.randint(0, 1 << 30)).normal(
            0, 20, (h, w)).astype(np.int16)
        blob = np.clip(blob.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        blob = (blob > 128).astype(np.uint8) * 255
        overlay[blob > 0] = color
        mask |= blob
    return overlay, mask


def deg_ink_erosion(img: np.ndarray, boxes: list[tuple],
                    rng: random.Random) -> tuple[np.ndarray, np.ndarray]:
    """墨迹侵蚀：选若干字框，字迹向纸色淡出 + 轻模糊；偶发水渍暗斑。"""
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    pil = Image.fromarray(img)
    inner = [b for b in boxes if b[0] >= 0 and b[1] >= 0 and b[2] <= w and b[3] <= h]
    n = max(1, round(len(inner) * rng.uniform(0.1, 0.3))) if inner else 0
    for x1, y1, x2, y2 in rng.sample(inner, min(n, len(inner))):
        region = pil.crop((x1, y1, x2, y2))
        # 纸色 = 区域高亮分位
        arr = np.asarray(region.convert("L"))
        paper = int(np.percentile(arr, 85))
        alpha = rng.uniform(0.35, 0.7)  # 淡出程度
        faded = Image.blend(region,
                            Image.new("RGB", region.size, (paper, paper, paper)),
                            alpha)
        if rng.random() < 0.5:
            faded = faded.filter(ImageFilter.GaussianBlur(rng.uniform(0.6, 1.4)))
        pil.paste(faded, (x1, y1))
        mask[y1:y2, x1:x2] = 255
    if rng.random() < 0.3:  # 水渍：大半径半透明暗化
        stain = Image.new("L", (w, h), 0)
        sd = ImageDraw.Draw(stain)
        cx, cy = rng.randint(0, w - 1), rng.randint(0, h - 1)
        r = rng.randint(60, 200)
        sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rng.randint(30, 70))
        stain = stain.filter(ImageFilter.GaussianBlur(r / 3))
        dark = np.asarray(pil).astype(np.int16) - np.asarray(stain)[..., None]
        pil = Image.fromarray(np.clip(dark, 0, 255).astype(np.uint8))
        mask |= (np.asarray(stain) > 20).astype(np.uint8) * 255
    return np.asarray(pil), mask


# ---- patch 采样与内容图 ----

def _sample_window(boxes: list[tuple], pw: int, ph: int,
                   rng: random.Random) -> tuple[int, int] | None:
    """以某个字框为中心采 512 窗口（页内裁剪，不足 512 的页跳过）。"""
    if pw < PATCH or ph < PATCH or not boxes:
        return None
    x1, y1, x2, y2 = rng.choice(boxes)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    ox = min(max(cx - PATCH // 2 + rng.randint(-160, 160), 0), pw - PATCH)
    oy = min(max(cy - PATCH // 2 + rng.randint(-160, 160), 0), ph - PATCH)
    return ox, oy


def render_content_patch(chars: list[tuple]) -> Image.Image:
    """字模内容图：白底，标准字体按框位渲染（模拟 character content 输入）。
    chars 为窗口内相对坐标。"""
    canvas = Image.new("L", (PATCH, PATCH), 255)
    draw = ImageDraw.Draw(canvas)
    for x1, y1, x2, y2, c in chars:
        size = max(10, min(120, max(x2 - x1, y2 - y1)))
        font = next((f for _, f in _load_fonts(size)), None)
        if font is None or font.getmask(c).getbbox() is None:
            continue
        draw.text(((x1 + x2) / 2, (y1 + y2) / 2), c,
                  fill=0, font=font, anchor="mm")
    return canvas


def export_hdr28k(db: Session, project_id: int, patches_per_page: int = 4,
                  seed: int = 42, progress_cb=None, cancel_cb=None) -> Export:
    export = Export(kind="hdr28k",
                    params_json=json.dumps({"project_id": project_id,
                                            "patches_per_page": patches_per_page,
                                            "seed": seed}))
    db.add(export)
    db.flush()
    root = settings.exports_dir / str(export.id) / "hdr28k"

    images = (db.query(ImageRow).filter_by(project_id=project_id)
              .order_by(ImageRow.id).all())
    counters: dict[str, int] = {}
    metas: dict[str, list] = {}
    n_skip_small = 0
    total = len(images)

    for pi, img_row in enumerate(images):
        if cancel_cb and cancel_cb():
            break
        if img_row.width < PATCH or img_row.height < PATCH:
            n_skip_small += 1
            continue
        src = variant_path(project_id, img_row.id, "original")
        if src is None:
            continue
        split = img_row.official_split or "train"
        rng = random.Random(f"{seed}:{img_row.id}")
        page = np.asarray(Image.open(src).convert("RGB"))
        annos = (db.query(CharAnnotation)
                 .filter_by(image_id=img_row.id)
                 .filter(CharAnnotation.deleted_at.is_(None))
                 .filter(CharAnnotation.status != "rejected")
                 .filter(CharAnnotation.char.isnot(None)).all())
        boxes = [(a.x1, a.y1, a.x2, a.y2) for a in annos]
        chars = [(a.x1, a.y1, a.x2, a.y2, a.char) for a in annos if len(a.char) == 1]

        # 手工破损区域：有则优先生成一个"真实破损"patch
        manual = (db.query(DamageRegion).filter_by(image_id=img_row.id)
                  .filter(DamageRegion.status == "confirmed").all())
        windows: list[tuple[int, int, str | None]] = []
        if manual:
            full_mask = np.asarray(combined_mask(db, img_row))
            ys, xs = np.nonzero(full_mask)
            if len(xs):
                cx, cy = (xs.min() + xs.max()) // 2, (ys.min() + ys.max()) // 2
                ox = min(max(cx - PATCH // 2, 0), img_row.width - PATCH)
                oy = min(max(cy - PATCH // 2, 0), img_row.height - PATCH)
                windows.append((ox, oy, "manual"))
        for _ in range(patches_per_page):
            win = _sample_window(boxes, img_row.width, img_row.height, rng)
            if win:
                windows.append((win[0], win[1], None))

        for ox, oy, forced in windows:
            gt = page[oy:oy + PATCH, ox:ox + PATCH].copy()
            win_boxes = [(x1 - ox, y1 - oy, x2 - ox, y2 - oy)
                         for x1, y1, x2, y2 in boxes
                         if x2 > ox and x1 < ox + PATCH and y2 > oy and y1 < oy + PATCH]
            win_chars = [(x1 - ox, y1 - oy, x2 - ox, y2 - oy, c)
                         for x1, y1, x2, y2, c in chars
                         if x2 > ox and x1 < ox + PATCH and y2 > oy and y1 < oy + PATCH]
            if forced == "manual":
                dtype = manual[0].damage_type
                mask_full = np.asarray(combined_mask(db, img_row))
                pmask = mask_full[oy:oy + PATCH, ox:ox + PATCH].copy()
                if dtype == "character_missing":
                    deg = cv2.cvtColor(cv2.inpaint(
                        cv2.cvtColor(gt, cv2.COLOR_RGB2BGR), pmask, 5,
                        cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB)
                elif dtype == "ink_erosion":
                    deg, _ = deg_ink_erosion(gt, win_boxes, rng)
                    # 手工区域之外不动：仅在 mask 内采用退化结果
                    deg = np.where(pmask[..., None] > 0, deg, gt)
                else:  # paper_damage：mask 内填黑/白
                    fill = 0 if rng.random() < 0.5 else 255
                    deg = gt.copy()
                    deg[pmask > 0] = fill
                pmask_out = pmask
            else:
                dtype = rng.choices(DTYPES, weights=DTYPE_W)[0]
                if dtype == "character_missing":
                    deg, pmask_out = deg_character_missing(gt, win_boxes, rng)
                elif dtype == "paper_damage":
                    deg, pmask_out = deg_paper_damage(gt, rng)
                else:
                    deg, pmask_out = deg_ink_erosion(gt, win_boxes, rng)
            if pmask_out.sum() == 0:
                continue

            idx = counters.get(split, 0)
            counters[split] = idx + 1
            name = f"{idx:06d}.png"
            for sub in ("gt", "degraded", "mask", "content"):
                (root / split / sub).mkdir(parents=True, exist_ok=True)
            Image.fromarray(gt).save(root / split / "gt" / name)
            Image.fromarray(deg).save(root / split / "degraded" / name)
            Image.fromarray(pmask_out).save(root / split / "mask" / name)
            render_content_patch(win_chars).save(root / split / "content" / name)
            metas.setdefault(split, []).append({
                "id": name, "page_id": img_row.id, "filename": img_row.filename,
                "bbox": [ox, oy, ox + PATCH, oy + PATCH], "dtype": dtype,
                "n_chars": len(win_chars),
                "chars": "".join(c for *_, c in win_chars)[:200],
            })
        if progress_cb and pi % 10 == 0:
            progress_cb(pi / max(total, 1), f"{pi}/{total} 页（{sum(counters.values())} patch）")

    for split, rows in metas.items():
        with open(root / split / "meta.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats = {"patches": counters, "skipped_small_pages": n_skip_small}
    export.output_path = str((settings.exports_dir / str(export.id)).relative_to(settings.data_dir))
    export.status = "done"
    export.params_json = json.dumps(
        {"project_id": project_id, "patches_per_page": patches_per_page,
         "seed": seed, **stats}, ensure_ascii=False)
    db.commit()
    db.refresh(export)
    return export
