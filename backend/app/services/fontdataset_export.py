"""FontDataset 导出（方法二 MethodTwo-gaijing1 数据集契约）。

目录：
    {out}/{phase}/ContentImage/u{hex}.png
    {out}/{phase}/TargetImage/{style}/{style}+u{hex}.png

phase 划分（以风格 locked_split 为准，泄漏守卫已在聚类时保证簇内一致）：
- train：锁定 train/val 的风格 × 非 holdout 训练字
- test_unknown_content：锁定 train/val 的风格 × holdout 字（内容未见）
- test_unknown_style：锁定 test 的风格 × 非 holdout 训练字（风格未见）

约束：风格在每出现的 phase 内必须 ≥2 张图（loader 要随机抽"同风格另一张"做
风格参考）；同一 (style, char) 保留第一次出现的裁剪（一名一图）。
"""
import json
import shutil
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (CharCrop, CharsetEntry, Export, Image as ImageRow, Style)
from .render import content_filename

settings = get_settings()

PHASES = ("train", "test_unknown_content", "test_unknown_style")


def _phase_of(style: Style, is_holdout: bool) -> str | None:
    if style.locked_split == "test":
        return None if is_holdout else "test_unknown_style"
    # train / val / 未锁定（手工风格等）一律进 train 侧
    return "test_unknown_content" if is_holdout else "train"


def export_fontdataset(db: Session, project_id: int,
                       progress_cb=None, cancel_cb=None) -> Export:
    export = Export(kind="fontdataset",
                    params_json=json.dumps({"project_id": project_id}))
    db.add(export)
    db.flush()
    out_root = settings.exports_dir / str(export.id) / "font"
    for phase in PHASES:
        # ContentImage 与 TargetImage 都预建：某 phase 无样本时目录为空，
        # 但 FontDataset 初始化要求路径存在
        (out_root / phase / "ContentImage").mkdir(parents=True, exist_ok=True)
        (out_root / phase / "TargetImage").mkdir(parents=True, exist_ok=True)

    # 训练字表（含 holdout 标记）；渲染失败的字无法配对 ContentImage，跳过
    entries = {e.char: e for e in db.query(CharsetEntry)
               .filter_by(in_trainset=True, renderable=True).all()}

    rows = (db.query(CharCrop, ImageRow, Style)
            .join(ImageRow, CharCrop.image_id == ImageRow.id)
            .join(Style, ImageRow.style_id == Style.id)  # 用图像当前风格，防重聚类后过期
            .filter(ImageRow.project_id == project_id)
            .filter(CharCrop.status != "rejected")
            .order_by(CharCrop.id).all())

    # (phase, style, char) -> crop_path；保留第一次出现
    picked: dict[tuple, str] = {}
    for crop, img, style in rows:
        e = entries.get(crop.char)
        if e is None:
            continue
        phase = _phase_of(style, e.is_holdout)
        if phase is None:
            continue
        key = (phase, style.name, crop.char)
        if key not in picked:
            picked[key] = crop.crop_path

    # 每 phase×style ≥2 图过滤
    by_phase_style: dict[tuple, list] = defaultdict(list)
    for (phase, style_name, char), rel in picked.items():
        by_phase_style[(phase, style_name)].append((char, rel))

    n_files = n_skip_style = 0
    chars_per_phase: dict[str, set] = defaultdict(set)
    total = len(by_phase_style)
    for i, ((phase, style_name), items) in enumerate(sorted(by_phase_style.items())):
        if cancel_cb and cancel_cb():
            break
        if len(items) < 2:
            n_skip_style += 1
            continue
        tdir = out_root / phase / "TargetImage" / style_name
        tdir.mkdir(parents=True, exist_ok=True)
        for char, rel in items:
            src = settings.crops_dir / rel
            if not src.is_file():
                continue
            shutil.copyfile(src, tdir / f"{style_name}+u{ord(char):x}.png")
            chars_per_phase[phase].add(char)
            n_files += 1
        if progress_cb and i % 50 == 0:
            progress_cb(i / max(total, 1), f"导出 {i}/{total} 风格目录")

    # ContentImage：按 phase 实际出现的字符复制
    n_content = 0
    for phase, chars in chars_per_phase.items():
        cdir = out_root / phase / "ContentImage"
        for char in chars:
            src = settings.content_dir / content_filename(char)
            if src.is_file():
                shutil.copyfile(src, cdir / content_filename(char))
                n_content += 1

    stats = {"target_images": n_files, "content_images": n_content,
             "skipped_styles_lt2": n_skip_style,
             "phases": {p: {"styles": len({s for (ph, s) in by_phase_style if ph == p}),
                            "chars": len(chars_per_phase.get(p, set()))}
                        for p in PHASES}}
    export.output_path = str((settings.exports_dir / str(export.id)).relative_to(settings.data_dir))
    export.status = "done"
    export.params_json = json.dumps({"project_id": project_id, **stats}, ensure_ascii=False)
    db.commit()
    db.refresh(export)
    return export
