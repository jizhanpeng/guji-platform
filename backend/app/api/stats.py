"""仪表盘统计 + 数据库备份。"""
import shutil
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import (CharAnnotation, CharCrop, DamageRegion, Export, Image,
                      Job, Project, Style)

router = APIRouter(prefix="/api", tags=["stats"])
settings = get_settings()


def _count_by(db: Session, model, col, project_id: int | None = None,
              join_image: bool = False) -> dict[str, int]:
    q = db.query(col, func.count())
    if project_id is not None:
        if join_image:
            q = q.join(Image, model.image_id == Image.id).filter(Image.project_id == project_id)
        else:
            q = q.filter(model.project_id == project_id)
    return {str(k): n for k, n in q.group_by(col).all()}


@router.get("/stats")
def stats(project_id: int | None = None, db: Session = Depends(get_db)):
    """平台/项目级统计（仪表盘）。"""
    projects = []
    pq = db.query(Project).order_by(Project.id).all()
    for p in pq:
        if project_id and p.id != project_id:
            continue
        images = _count_by(db, Image, Image.status, p.id)
        splits = _count_by(db, Image, Image.official_split, p.id)
        annos = _count_by(db, CharAnnotation, CharAnnotation.status, p.id, join_image=True)
        anno_origins = _count_by(db, CharAnnotation, CharAnnotation.origin, p.id, join_image=True)
        crops = _count_by(db, CharCrop, CharCrop.status, p.id, join_image=True)
        n_styles = db.query(Style).filter_by(project_id=p.id).count()
        n_damage = (db.query(DamageRegion).join(Image, DamageRegion.image_id == Image.id)
                    .filter(Image.project_id == p.id)
                    .filter(DamageRegion.status != "rejected").count())
        projects.append({
            "id": p.id, "name": p.name, "kind": p.kind,
            "images": images, "splits": splits,
            "annotations": annos, "annotation_origins": anno_origins,
            "crops": crops, "styles": n_styles, "damage_regions": n_damage,
        })
    recent_jobs = (db.query(Job).order_by(Job.id.desc()).limit(8).all())
    exports = (db.query(Export).order_by(Export.id.desc()).limit(8).all())
    return {
        "projects": projects,
        "recent_jobs": [{
            "id": j.id, "job_type": j.job_type, "status": j.status,
            "progress": j.progress, "created_at": j.created_at.isoformat(),
        } for j in recent_jobs],
        "recent_exports": [{
            "id": e.id, "kind": e.kind, "status": e.status,
            "output_path": e.output_path, "created_at": e.created_at.isoformat(),
        } for e in exports],
    }


@router.post("/backup")
def backup():
    """把 platform.db 打成带时间戳的 zip 存 data/backups/（WAL 下先 checkpoint）。"""
    from ..db import engine
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE);")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = settings.data_dir / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"platform_{ts}.zip"
    db_path = settings.data_dir / "platform.db"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, "platform.db")
    size_mb = round(out.stat().st_size / 1024 / 1024, 2)
    # 只保留最近 20 份
    olds = sorted(out_dir.glob("platform_*.zip"))[:-20]
    for f in olds:
        f.unlink()
    return {"ok": True, "path": str(out.relative_to(settings.data_dir)), "size_mb": size_mb}
