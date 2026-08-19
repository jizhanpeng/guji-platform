"""导出 API。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Export
from ..services.csv_export import export_m5hisdoc_csv

router = APIRouter(prefix="/api/exports", tags=["exports"])


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    params_json: str
    output_path: str | None
    status: str
    created_at: datetime


class M5CsvIn(BaseModel):
    image_ids: list[int]


@router.get("", response_model=list[ExportOut])
def list_exports(db: Session = Depends(get_db)):
    return db.query(Export).order_by(Export.id.desc()).limit(100).all()


@router.post("/m5hisdoc-csv", response_model=ExportOut)
def export_csv(body: M5CsvIn, db: Session = Depends(get_db)):
    if not body.image_ids:
        raise HTTPException(400, "image_ids 不能为空")
    return export_m5hisdoc_csv(db, body.image_ids)
