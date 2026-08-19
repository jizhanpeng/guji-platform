"""label_char CSV 导出（M5HisDoc 原始格式往返）。

每页一个 {stem}.txt，每行 x1,y1,x2,y2,<字符>，与官方 label_char 完全一致，
只导出 status=confirmed/edited 且未删除的标注。
"""
import json
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CharAnnotation, Export, Image

settings = get_settings()


def export_m5hisdoc_csv(db: Session, image_ids: list[int]) -> Export:
    export = Export(kind="m5hisdoc_csv",
                    params_json=json.dumps({"image_ids": image_ids}, ensure_ascii=False))
    db.add(export)
    db.flush()
    out_dir = settings.exports_dir / str(export.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_files = n_rows = 0
    for iid in image_ids:
        img = db.get(Image, iid)
        if img is None:
            continue
        annos = (db.query(CharAnnotation)
                 .filter_by(image_id=iid)
                 .filter(CharAnnotation.deleted_at.is_(None))
                 .filter(CharAnnotation.status.in_(["confirmed", "edited"]))
                 .order_by(CharAnnotation.id).all())
        lines = [f"{a.x1},{a.y1},{a.x2},{a.y2},{a.char or ''}" for a in annos]
        # newline="" 保持 LF，与官方 label_char 文件逐字节一致
        with open(out_dir / f"{Path(img.filename).stem}.txt", "w",
                  encoding="utf-8", newline="") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        n_files += 1
        n_rows += len(lines)

    export.output_path = str(out_dir.relative_to(settings.data_dir))
    export.status = "done"
    export.params_json = json.dumps(
        {"image_ids": image_ids, "files": n_files, "rows": n_rows}, ensure_ascii=False)
    db.commit()
    db.refresh(export)
    return export
