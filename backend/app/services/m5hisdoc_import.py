"""M5HisDoc 数据集导入器。

目录结构（root 指向包含 split 文件的那一层）：
    {root}/{subset}/images/image_N.jpg
    {root}/{subset}/label_char/image_N.txt     每行 x1,y1,x2,y2,<字符>
    {root}/split_train.txt  split_val.txt  split_test.txt   每行 image_N（无扩展名）

标注导入为 origin='m5hisdoc'、status='confirmed'（官方真值，视为已确认）。
重复导入按 filename 幂等跳过。
"""
from pathlib import Path

from PIL import Image as PILImage
from sqlalchemy.orm import Session

from ..models import CharAnnotation, Image, Project
from .imaging import make_derivatives, save_original


def read_splits(root: Path) -> dict[str, str]:
    """stem -> 'train'|'val'|'test'"""
    mapping: dict[str, str] = {}
    for split in ("train", "val", "test"):
        f = root / f"split_{split}.txt"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                stem = line.strip()
                if stem:
                    mapping[stem] = split
    return mapping


def parse_label_char(path: Path) -> list[tuple[int, int, int, int, str]]:
    """解析 label_char 文件：x1,y1,x2,y2,<字符>。字符字段可能含逗号，按前 4 段切。"""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",", 4)
        if len(parts) < 5:
            continue
        try:
            x1, y1, x2, y2 = (int(float(v)) for v in parts[:4])
        except ValueError:
            continue
        rows.append((x1, y1, x2, y2, parts[4]))
    return rows


def import_m5hisdoc(db: Session, project: Project, root: Path, subset: str,
                    progress_cb=None, cancel_cb=None) -> dict:
    """导入一个子集（M5HisDoc_regular / M5HisDoc_hard）。返回统计信息。"""
    images_dir = root / subset / "images"
    labels_dir = root / subset / "label_char"
    if not images_dir.is_dir():
        raise RuntimeError(f"图像目录不存在: {images_dir}")

    source = "m5hisdoc_regular" if "regular" in subset else "m5hisdoc_hard"
    splits = read_splits(root)
    files = sorted(p for p in images_dir.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    total = len(files)
    # 幂等：项目内已有 filename 集合
    existing = {r[0] for r in db.query(Image.filename)
                .filter_by(project_id=project.id).all()}

    n_images = n_annos = n_skipped = 0
    for i, src in enumerate(files):
        if cancel_cb and cancel_cb():
            break
        if src.name in existing:
            n_skipped += 1
            continue
        try:
            with PILImage.open(src) as im:
                w, h = im.size
        except Exception:
            n_skipped += 1
            continue
        img = Image(project_id=project.id, filename=src.name, rel_path="",
                    width=w, height=h, source=source,
                    official_split=splits.get(src.stem),
                    status="reviewed")  # 官方标注视为已复查
        db.add(img)
        db.flush()
        original = save_original(project.id, img.id, src)
        make_derivatives(project.id, img.id, original)
        img.rel_path = f"{project.id}/{img.id}/{original.name}"

        label_file = labels_dir / f"{src.stem}.txt"
        if label_file.exists():
            # 官方 label_char 偶有完全重复的行（同框同字），按页去重以满足
            # (image_id, origin, box) 唯一约束（OCR 幂等约束，对真值同样生效）
            seen: set[tuple[int, int, int, int]] = set()
            for x1, y1, x2, y2, char in parse_label_char(label_file):
                if (x1, y1, x2, y2) in seen:
                    continue
                seen.add((x1, y1, x2, y2))
                db.add(CharAnnotation(
                    image_id=img.id, x1=x1, y1=y1, x2=x2, y2=y2,
                    char=char or None, origin="m5hisdoc", status="confirmed"))
                n_annos += 1
        n_images += 1
        if i % 20 == 0 or i == total - 1:
            db.commit()
            if progress_cb:
                progress_cb((i + 1) / total, f"{i + 1}/{total} {src.name}")
    db.commit()
    return {"images": n_images, "annotations": n_annos, "skipped": n_skipped}
