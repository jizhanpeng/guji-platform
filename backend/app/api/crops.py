"""单字裁剪复查 + 字表 + M3 任务入口（方法二数据流水线）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import CharCrop, CharsetEntry, Image, Project, Style
from ..schemas import JobOut
from ..services.queue import enqueue

router = APIRouter(prefix="/api", tags=["crops"])
settings = get_settings()

CROP_STATUS = ("auto", "confirmed", "rejected")


class CropOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    image_id: int
    char_annotation_id: int | None
    style_id: int | None
    char: str | None
    crop_path: str
    crop_kind: str
    scale_ratio: float
    status: str
    created_at: datetime


class CropPatch(BaseModel):
    status: str


class CropBulkIn(BaseModel):
    ids: list[int]
    status: str  # confirmed | rejected


class CharsetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    char: str
    instance_count: int
    renderable: bool
    render_font: str | None
    in_trainset: bool
    is_holdout: bool
    median_box_px: float | None
    content_image_path: str | None


# ---- 裁剪列表 / 复查 ----

@router.get("/projects/{project_id}/crops")
def list_crops(project_id: int,
               status: str | None = None,
               style_id: int | None = None,
               char: str | None = None,
               page: int = Query(1, ge=1),
               per: int = Query(96, ge=1, le=500),
               db: Session = Depends(get_db)):
    q = (db.query(CharCrop).join(Image, CharCrop.image_id == Image.id)
         .filter(Image.project_id == project_id))
    if status:
        q = q.filter(CharCrop.status == status)
    if style_id:
        q = q.filter(CharCrop.style_id == style_id)
    if char:
        q = q.filter(CharCrop.char == char)
    total = q.count()
    rows = (q.order_by(CharCrop.id)
            .offset((page - 1) * per).limit(per).all())
    return {"total": total, "page": page, "per": per,
            "items": [CropOut.model_validate(r) for r in rows]}


@router.get("/projects/{project_id}/crops/stats")
def crop_stats(project_id: int, db: Session = Depends(get_db)):
    rows = (db.query(CharCrop.status, func.count())
            .join(Image, CharCrop.image_id == Image.id)
            .filter(Image.project_id == project_id)
            .group_by(CharCrop.status).all())
    return {s: n for s, n in rows}


@router.get("/crops/{crop_id}/image")
def crop_image(crop_id: int, db: Session = Depends(get_db)):
    crop = db.get(CharCrop, crop_id)
    if not crop:
        raise HTTPException(404, "裁剪不存在")
    p = settings.crops_dir / crop.crop_path
    if not p.is_file():
        raise HTTPException(404, "裁剪文件缺失")
    return FileResponse(p, media_type="image/png")


@router.patch("/crops/{crop_id}", response_model=CropOut)
def patch_crop(crop_id: int, body: CropPatch, db: Session = Depends(get_db)):
    if body.status not in CROP_STATUS:
        raise HTTPException(400, f"status 须为 {'/'.join(CROP_STATUS)}")
    crop = db.get(CharCrop, crop_id)
    if not crop:
        raise HTTPException(404, "裁剪不存在")
    crop.status = body.status
    db.commit()
    db.refresh(crop)
    return crop


@router.post("/crops/bulk-status")
def bulk_crop_status(body: CropBulkIn, db: Session = Depends(get_db)):
    if body.status not in CROP_STATUS:
        raise HTTPException(400, f"status 须为 {'/'.join(CROP_STATUS)}")
    crops = db.query(CharCrop).filter(CharCrop.id.in_(body.ids)).all()
    for c in crops:
        c.status = body.status
    db.commit()
    return {"ok": True, "count": len(crops)}


# ---- 字表 ----

@router.get("/projects/{project_id}/charset")
def list_charset(project_id: int,
                 in_trainset: bool | None = None,
                 q: str | None = None,
                 page: int = Query(1, ge=1),
                 per: int = Query(200, ge=1, le=2000),
                 db: Session = Depends(get_db)):
    """项目字表（以裁剪实例归属项目过滤）。"""
    chars = {r[0] for r in db.query(CharCrop.char)
             .join(Image, CharCrop.image_id == Image.id)
             .filter(Image.project_id == project_id)
             .filter(CharCrop.char.isnot(None)).distinct()}
    query = db.query(CharsetEntry).filter(CharsetEntry.char.in_(chars or {""}))
    if in_trainset is not None:
        query = query.filter(CharsetEntry.in_trainset == in_trainset)
    if q:
        query = query.filter(CharsetEntry.char == q)
    total = query.count()
    rows = (query.order_by(CharsetEntry.instance_count.desc())
            .offset((page - 1) * per).limit(per).all())
    return {"total": total, "page": page, "per": per,
            "items": [CharsetOut.model_validate(r) for r in rows]}


@router.get("/content/{char}/image")
def content_image(char: str):
    if len(char) != 1:
        raise HTTPException(400, "char 须为单字符")
    from ..services.render import content_filename
    p = settings.content_dir / content_filename(char)
    if not p.is_file():
        raise HTTPException(404, "ContentImage 未渲染")
    return FileResponse(p, media_type="image/png")


# ---- M3 任务入口 ----

class AutoCropIn(BaseModel):
    project_id: int
    image_ids: list[int] | None = None  # None = 全项目


class CharsetIn(BaseModel):
    project_id: int
    min_instances: int = 20
    holdout_ratio: float = 0.05


class RenderIn(BaseModel):
    only_missing: bool = True


class FontDatasetIn(BaseModel):
    project_id: int


@router.post("/jobs/auto_crop", response_model=JobOut)
def start_auto_crop(body: AutoCropIn, db: Session = Depends(get_db)):
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "项目不存在")
    return enqueue(db, "auto_crop", body.model_dump())


@router.post("/jobs/charset_rebuild", response_model=JobOut)
def start_charset(body: CharsetIn, db: Session = Depends(get_db)):
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "项目不存在")
    return enqueue(db, "charset_rebuild", body.model_dump())


@router.post("/jobs/render_content", response_model=JobOut)
def start_render(body: RenderIn, db: Session = Depends(get_db)):
    return enqueue(db, "render_content", body.model_dump())


@router.post("/jobs/export_fontdataset", response_model=JobOut)
def start_fontdataset(body: FontDatasetIn, db: Session = Depends(get_db)):
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "项目不存在")
    return enqueue(db, "export_fontdataset", body.model_dump())
