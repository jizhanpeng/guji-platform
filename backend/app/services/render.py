"""ContentImage 渲染（适配方案 §2.6）。

- 64×64 白底黑字灰度 PNG，字居中；
- 字号 ≈ 该字目标实例原生框尺寸中位数（§2.5-7 字号对齐，默认不满幅）；
- 字体回退链：SimSun（BMP）→ SimSun-ExtB（扩展 B 区）；全部失败 →
  renderable=False 并记录清单（后续可补 Hanazono 再跑）；
- 文件名：u{码点hex}.png（平台统一编码，避免非 BMP 字符做文件名的问题）。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CharsetEntry

settings = get_settings()

CANVAS = 64
DEFAULT_FONT_SIZE = 45  # 无框统计时的兜底（regular 中位数 ≈45px）

FONT_CHAIN = [
    ("simsun", r"C:\Windows\Fonts\simsun.ttc"),
    ("simsunb", r"C:\Windows\Fonts\simsunb.ttf"),  # SimSun-ExtB，覆盖扩展 B 区
]


def content_filename(char: str) -> str:
    return f"u{ord(char):x}.png"


def _load_fonts(size: int):
    for name, path in FONT_CHAIN:
        if Path(path).is_file():
            try:
                yield name, ImageFont.truetype(path, size)
            except OSError:
                continue


def render_char(char: str, font_size: int) -> tuple[Image.Image, str] | None:
    """按回退链渲染单字。返回 (64×64 灰度图, 字体名)；全失败返回 None。"""
    for name, font in _load_fonts(font_size):
        mask = font.getmask(char)
        if mask.getbbox() is None:  # 字体无此字形
            continue
        im = Image.new("L", (CANVAS, CANVAS), 255)
        draw = ImageDraw.Draw(im)
        # anchor="mm"：以字形中心对齐画布中心
        draw.text((CANVAS // 2, CANVAS // 2), char, fill=0, font=font, anchor="mm")
        return im, name
    return None


def render_content_all(db: Session, only_missing: bool = True,
                       progress_cb=None, cancel_cb=None) -> dict:
    """为全部 in_trainset 字渲染 ContentImage（含 holdout 字）。"""
    entries = (db.query(CharsetEntry).filter_by(in_trainset=True)
               .order_by(CharsetEntry.char).all())
    n_ok = n_fail = n_skip = 0
    failed: list[str] = []
    total = len(entries)
    for i, e in enumerate(entries):
        if cancel_cb and cancel_cb():
            break
        dst = settings.content_dir / content_filename(e.char)
        if only_missing and e.renderable and dst.is_file():
            n_skip += 1
            continue
        size = max(12, min(CANVAS - 4, round(e.median_box_px or DEFAULT_FONT_SIZE)))
        out = render_char(e.char, size)
        if out is None:
            e.renderable = False
            e.render_font = None
            n_fail += 1
            failed.append(e.char)
        else:
            im, font_name = out
            im.save(dst, "PNG")
            e.renderable = True
            e.render_font = font_name
            e.content_image_path = str(dst.relative_to(settings.data_dir))
            n_ok += 1
        if i % 200 == 0:
            db.commit()
            if progress_cb:
                progress_cb(i / max(total, 1), f"渲染 {i}/{total}（失败 {n_fail}）")
    db.commit()
    return {"rendered": n_ok, "failed": n_fail, "skipped": n_skip,
            "failed_chars": failed[:200]}
