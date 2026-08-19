"""Pydantic DTO（请求/响应）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- 项目 ----
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = "scans"  # m5hisdoc | scans | other
    source_path: str | None = None
    notes: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: str
    source_path: str | None
    notes: str | None
    created_at: datetime
    image_count: int = 0


# ---- 图像 ----
class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    filename: str
    width: int
    height: int
    source: str
    official_split: str | None
    style_id: int | None
    status: str
    created_at: datetime


class ImagePatch(BaseModel):
    style_id: int | None = None


class ImageListOut(BaseModel):
    total: int
    items: list[ImageOut]


class ImportFolderIn(BaseModel):
    folder: str  # 服务器本地绝对路径
    source: str = "scan"


# ---- 任务 ----
class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_type: str
    payload_json: str
    status: str
    progress: float
    log: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
