"""导入流水线：普通文件夹扫描。M5HisDoc 导入在 M1 实现。"""
from pathlib import Path

from PIL import Image as PILImage
from sqlalchemy.orm import Session

from ..models import Image, Project
from .imaging import make_derivatives, save_original

IMG_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def scan_folder(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and p.suffix.lower() in IMG_EXTS)


def import_images(db: Session, project: Project, files: list[Path],
                  source: str, progress_cb=None, cancel_cb=None) -> int:
    """逐张导入：复制原图、生成派生图、建 Image 行。返回导入数量。"""
    total = len(files)
    done = 0
    for i, src in enumerate(files):
        if cancel_cb and cancel_cb():
            break
        try:
            with PILImage.open(src) as im:
                w, h = im.size
        except Exception:
            continue  # 损坏文件跳过
        img = Image(project_id=project.id, filename=src.name,
                    rel_path="", width=w, height=h, source=source)
        db.add(img)
        db.flush()  # 拿 id
        original = save_original(project.id, img.id, src)
        make_derivatives(project.id, img.id, original)
        img.rel_path = f"{project.id}/{img.id}/{original.name}"
        done += 1
        if i % 10 == 0 or i == total - 1:
            db.commit()  # 分批提交，短事务
            if progress_cb:
                progress_cb((i + 1) / total, f"{i + 1}/{total} {src.name}")
    db.commit()
    return done
