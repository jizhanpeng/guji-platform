"""图像派生文件（缩略图/展示图）生成。"""
from pathlib import Path

from PIL import Image as PILImage

from ..config import get_settings

settings = get_settings()


def image_storage_dir(project_id: int, image_id: int) -> Path:
    """每张图的存储目录：data/images/{project_id}/{image_id}/"""
    d = settings.images_dir / str(project_id) / str(image_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_original(project_id: int, image_id: int, src: Path) -> Path:
    """把源图复制进 data/（保留原扩展名），返回绝对路径。"""
    dst = image_storage_dir(project_id, image_id) / f"original{src.suffix.lower()}"
    if not dst.exists():
        dst.write_bytes(src.read_bytes())
    return dst


def make_derivatives(project_id: int, image_id: int, original: Path) -> dict:
    """生成 thumb.jpg / display.jpg，返回尺寸等信息。"""
    out_dir = image_storage_dir(project_id, image_id)
    with PILImage.open(original) as im:
        im = im.convert("RGB")
        w, h = im.size
        thumb = im.copy()
        thumb.thumbnail((settings.thumb_max_px, settings.thumb_max_px))
        thumb.save(out_dir / "thumb.jpg", quality=85)
        display = im.copy()
        display.thumbnail((settings.display_max_px, settings.display_max_px))
        display.save(out_dir / "display.jpg", quality=90)
    return {"width": w, "height": h}


def variant_path(project_id: int, image_id: int, variant: str) -> Path | None:
    """original / display / thumb 的实际文件路径。"""
    d = settings.images_dir / str(project_id) / str(image_id)
    if variant == "original":
        for p in d.glob("original.*"):
            return p
        return None
    p = d / f"{variant}.jpg"
    return p if p.exists() else None
