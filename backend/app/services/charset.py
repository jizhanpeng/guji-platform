"""字表构建（charset_rebuild）：从裁剪产物聚合字符统计。

- instance_count：有效裁剪实例数；
- median_box_px：原始标注框 max(w,h) 的中位数（§2.5-7 渲染字号对齐用）；
- 字符过滤：仅保留字母/数字类（unicode L*/N*），剔除符号、标点、非法字符；
- in_trainset：instance_count >= min_instances；
- is_holdout：训练字符中按哈希确定性留出（test_unknown_content 用，
  相同字符集重复运行结果一致）。
"""
import unicodedata
from statistics import median

from sqlalchemy.orm import Session

from ..models import CharAnnotation, CharCrop, CharsetEntry, Image as ImageRow


def _keep_char(char: str) -> bool:
    if not char or len(char) != 1:
        return False
    cat = unicodedata.category(char)
    return cat[0] in ("L", "N")


def _holdout(char: str, ratio: float) -> bool:
    """确定性留出：码点 Knuth 乘法哈希分桶，跨进程/重跑结果一致。"""
    h = (sum(ord(c) for c in char) * 2654435761 % 2**32) / 2**32
    return h < ratio


def rebuild_charset(db: Session, project_id: int, min_instances: int = 20,
                    holdout_ratio: float = 0.05,
                    progress_cb=None, cancel_cb=None) -> dict:
    rows = (db.query(CharCrop.char, CharAnnotation.x1, CharAnnotation.y1,
                     CharAnnotation.x2, CharAnnotation.y2)
            .join(CharAnnotation, CharCrop.char_annotation_id == CharAnnotation.id)
            .join(ImageRow, CharCrop.image_id == ImageRow.id)
            .filter(ImageRow.project_id == project_id)
            .filter(CharCrop.status != "rejected")
            .all())
    stats: dict[str, list] = {}
    for char, x1, y1, x2, y2 in rows:
        if not _keep_char(char):
            continue
        stats.setdefault(char, []).append(max(x2 - x1, y2 - y1))

    n = len(stats)
    n_train = n_holdout = 0
    for i, (char, sizes) in enumerate(sorted(stats.items())):
        if cancel_cb and cancel_cb():
            break
        entry = db.get(CharsetEntry, char) or CharsetEntry(char=char)
        entry.instance_count = len(sizes)
        entry.median_box_px = float(median(sizes))
        entry.in_trainset = len(sizes) >= min_instances
        entry.is_holdout = bool(entry.in_trainset and _holdout(char, holdout_ratio))
        n_train += entry.in_trainset
        n_holdout += entry.is_holdout
        db.merge(entry)
        if i % 200 == 0:
            db.commit()
            if progress_cb:
                progress_cb(i / max(n, 1), f"字表 {i}/{n}")
    db.commit()
    return {"chars": n, "trainable": n_train, "holdout": n_holdout,
            "min_instances": min_instances}
