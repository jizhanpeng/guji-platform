"""破损区域标注 API（方法一）。"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..config import get_settings
from ..constants import DAMAGE_STATUS, DAMAGE_TYPES
from ..db import get_db
from ..models import DamageRegion, Image
from ..services import masks as mask_svc

router = APIRouter(prefix="/api", tags=["damage"])
settings = get_settings()


class Stroke(BaseModel):
    points: list[list[float]]
    radius: int = 8
    erase: bool = False


class DamageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    image_id: int
    damage_type: str
    strokes_json: str | None
    mask_path: str | None
    origin: str
    status: str
    created_at: datetime


class DamageCreate(BaseModel):
    damage_type: str
    strokes: list[Stroke] = []
    status: str = "confirmed"  # 手工画的默认已确认


class DamagePatch(BaseModel):
    damage_type: str | None = None
    strokes: list[Stroke] | None = None
    status: str | None = None


def _validate(damage_type: str | None, status: str | None):
    if damage_type is not None and damage_type not in DAMAGE_TYPES:
        raise HTTPException(400, f"damage_type 须为 {'/'.join(DAMAGE_TYPES)}")
    if status is not None and status not in DAMAGE_STATUS:
        raise HTTPException(400, f"status 须为 {'/'.join(DAMAGE_STATUS)}")


@router.get("/images/{image_id}/damage-regions", response_model=list[DamageOut])
def list_damage(image_id: int, db: Session = Depends(get_db)):
    return (db.query(DamageRegion).filter_by(image_id=image_id)
            .filter(DamageRegion.status != "rejected")
            .order_by(DamageRegion.id).all())


@router.post("/images/{image_id}/damage-regions", response_model=DamageOut)
def create_damage(image_id: int, body: DamageCreate, db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图像不存在")
    _validate(body.damage_type, body.status)
    region = DamageRegion(
        image_id=image_id, damage_type=body.damage_type, origin="manual",
        status=body.status,
        strokes_json=json.dumps([s.model_dump() for s in body.strokes]),
    )
    db.add(region)
    db.flush()  # 拿 id 定 mask 路径
    mask_svc.save_mask(db, region, img)
    db.commit()
    db.refresh(region)
    return region


@router.patch("/damage-regions/{region_id}", response_model=DamageOut)
def patch_damage(region_id: int, body: DamagePatch, db: Session = Depends(get_db)):
    region = db.get(DamageRegion, region_id)
    if not region:
        raise HTTPException(404, "破损区域不存在")
    _validate(body.damage_type, body.status)
    if body.damage_type is not None:
        region.damage_type = body.damage_type
    if body.status is not None:
        region.status = body.status
    if body.strokes is not None:
        region.strokes_json = json.dumps([s.model_dump() for s in body.strokes])
        mask_svc.save_mask(db, region, db.get(Image, region.image_id))
    db.commit()
    db.refresh(region)
    return region


@router.delete("/damage-regions/{region_id}")
def delete_damage(region_id: int, db: Session = Depends(get_db)):
    region = db.get(DamageRegion, region_id)
    if not region:
        raise HTTPException(404, "破损区域不存在")
    region.status = "rejected"
    db.commit()
    return {"ok": True}


@router.get("/damage-regions/{region_id}/mask")
def damage_mask(region_id: int, db: Session = Depends(get_db)):
    region = db.get(DamageRegion, region_id)
    if not region or not region.mask_path:
        raise HTTPException(404, "mask 不存在")
    p = settings.masks_dir / region.mask_path
    if not p.is_file():
        raise HTTPException(404, "mask 文件缺失")
    return FileResponse(p, media_type="image/png")


@router.get("/images/{image_id}/damage-mask")
def combined_damage_mask(image_id: int, db: Session = Depends(get_db)):
    """该页全部有效区域的合成 mask（训练/导出用）。"""
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图像不存在")
    import io
    buf = io.BytesIO()
    mask_svc.combined_mask(db, img).save(buf, "PNG")
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(buf, media_type="image/png")
