"""字符标注 API（方法一/方法二共用）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CharAnnotation, Image
from ..schemas import JobOut
from ..services.page_status import recompute_page_status
from ..services.queue import enqueue

router = APIRouter(prefix="/api", tags=["annotations"])


class CharAnnoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    image_id: int
    x1: int
    y1: int
    x2: int
    y2: int
    char: str | None
    origin: str
    confidence: float | None
    status: str


class CharAnnoCreate(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    char: str | None = None
    status: str = "confirmed"  # 手工画的框默认已确认


class CharAnnoPatch(BaseModel):
    x1: int | None = None
    y1: int | None = None
    x2: int | None = None
    y2: int | None = None
    char: str | None = None
    status: str | None = None


class BulkStatusIn(BaseModel):
    ids: list[int]
    status: str  # confirmed | rejected


@router.get("/images/{image_id}/char-annotations", response_model=list[CharAnnoOut])
def list_annotations(image_id: int, include_deleted: bool = False,
                     db: Session = Depends(get_db)):
    q = (db.query(CharAnnotation)
         .filter_by(image_id=image_id)
         .filter(CharAnnotation.status != "rejected"))
    if not include_deleted:
        q = q.filter(CharAnnotation.deleted_at.is_(None))
    return q.order_by(CharAnnotation.x1.desc(), CharAnnotation.y1).all()


@router.post("/images/{image_id}/char-annotations", response_model=CharAnnoOut)
def create_annotation(image_id: int, body: CharAnnoCreate,
                      db: Session = Depends(get_db)):
    if not db.get(Image, image_id):
        raise HTTPException(404, "图像不存在")
    anno = CharAnnotation(image_id=image_id, origin="manual", **body.model_dump())
    db.add(anno)
    db.flush()
    recompute_page_status(db, image_id)
    db.commit()
    db.refresh(anno)
    return anno


@router.patch("/char-annotations/{anno_id}", response_model=CharAnnoOut)
def patch_annotation(anno_id: int, body: CharAnnoPatch,
                     db: Session = Depends(get_db)):
    anno = db.get(CharAnnotation, anno_id)
    if not anno:
        raise HTTPException(404, "标注不存在")
    data = body.model_dump(exclude_unset=True)
    # 编辑坐标/字符时，auto 状态升级为 edited（仍待确认）；手工确认则 confirmed
    edited_box = any(k in data for k in ("x1", "y1", "x2", "y2", "char"))
    for k, v in data.items():
        setattr(anno, k, v)
    if edited_box and anno.status == "auto":
        anno.status = "edited"
    recompute_page_status(db, anno.image_id)
    db.commit()
    db.refresh(anno)
    return anno


@router.delete("/char-annotations/{anno_id}")
def delete_annotation(anno_id: int, db: Session = Depends(get_db)):
    anno = db.get(CharAnnotation, anno_id)
    if not anno:
        raise HTTPException(404, "标注不存在")
    anno.deleted_at = datetime.now()
    anno.status = "rejected"
    recompute_page_status(db, anno.image_id)
    db.commit()
    return {"ok": True}


@router.post("/char-annotations/bulk-status")
def bulk_status(body: BulkStatusIn, db: Session = Depends(get_db)):
    if body.status not in ("confirmed", "rejected"):
        raise HTTPException(400, "status 须为 confirmed 或 rejected")
    annos = (db.query(CharAnnotation)
             .filter(CharAnnotation.id.in_(body.ids)).all())
    image_ids = set()
    for anno in annos:
        anno.status = body.status
        if body.status == "rejected":
            anno.deleted_at = datetime.now()
        image_ids.add(anno.image_id)
    for iid in image_ids:
        recompute_page_status(db, iid)
    db.commit()
    return {"ok": True, "count": len(annos)}


# ---- OCR 自动标注任务 ----

class OcrIn(BaseModel):
    project_id: int
    image_ids: list[int] | None = None  # None = 全项目


@router.post("/jobs/ocr", response_model=JobOut)
def start_ocr(body: OcrIn, db: Session = Depends(get_db)):
    return enqueue(db, "ocr", body.model_dump())
