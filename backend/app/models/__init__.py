"""ORM 模型。约定：整型主键；created_at/updated_at；标注类软删除（deleted_at）。"""
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(20))  # PROJECT_KINDS
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    images: Mapped[list["Image"]] = relationship(back_populates="project")


class Style(Base):
    __tablename__ = "styles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)  # book_0001 等
    method: Mapped[str] = mapped_column(String(20), default="manual")  # STYLE_METHODS
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 簇级划分锁：防泄漏闸。非空时该风格只能含对应 split 的页面
    locked_split: Mapped[str | None] = mapped_column(String(10), nullable=True)  # SPLITS
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    images: Mapped[list["Image"]] = relationship(back_populates="style")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    rel_path: Mapped[str] = mapped_column(Text)  # 相对 data/images/{project_id}/
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    dpi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="scan")  # IMAGE_SOURCES
    official_split: Mapped[str | None] = mapped_column(String(10), nullable=True)  # SPLITS
    style_id: Mapped[int | None] = mapped_column(ForeignKey("styles.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="unannotated")  # PAGE_STATUS
    phash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    project: Mapped[Project] = relationship(back_populates="images")
    style: Mapped[Style | None] = relationship(back_populates="images")
    char_annotations: Mapped[list["CharAnnotation"]] = relationship(back_populates="image")
    damage_regions: Mapped[list["DamageRegion"]] = relationship(back_populates="image")


class CharAnnotation(Base):
    __tablename__ = "char_annotations"
    __table_args__ = (
        # OCR 幂等：同一图同一来源同框不重复
        UniqueConstraint("image_id", "origin", "x1", "y1", "x2", "y2",
                         name="uq_anno_image_origin_box"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), index=True)
    # 原图坐标系
    x1: Mapped[int] = mapped_column(Integer)
    y1: Mapped[int] = mapped_column(Integer)
    x2: Mapped[int] = mapped_column(Integer)
    y2: Mapped[int] = mapped_column(Integer)
    char: Mapped[str | None] = mapped_column(String(4), nullable=True)  # 单字符（含非 BMP）
    origin: Mapped[str] = mapped_column(String(20))  # ANNO_ORIGINS
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # OCR 分数
    status: Mapped[str] = mapped_column(String(20), default="auto")  # ANNO_STATUS
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    image: Mapped[Image] = relationship(back_populates="char_annotations")


class DamageRegion(Base):
    __tablename__ = "damage_regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), index=True)
    damage_type: Mapped[str] = mapped_column(String(30))  # DAMAGE_TYPES
    # 矢量笔画（JSON：[{points:[[x,y]...], radius, erase}]），保存时服务端光栅化
    strokes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    mask_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # 相对 data/masks/
    origin: Mapped[str] = mapped_column(String(30), default="manual")  # DAMAGE_ORIGINS
    status: Mapped[str] = mapped_column(String(20), default="draft")  # DAMAGE_STATUS
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    image: Mapped[Image] = relationship(back_populates="damage_regions")


class StyleHistory(Base):
    __tablename__ = "style_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), index=True)
    from_style_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_style_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CharCrop(Base):
    __tablename__ = "char_crops"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), index=True)
    char_annotation_id: Mapped[int | None] = mapped_column(
        ForeignKey("char_annotations.id"), nullable=True, unique=True)  # 幂等
    style_id: Mapped[int | None] = mapped_column(ForeignKey("styles.id"), nullable=True, index=True)
    char: Mapped[str | None] = mapped_column(String(4), nullable=True)
    crop_path: Mapped[str] = mapped_column(Text)  # 相对 data/crops/，按 DB id 分片
    crop_kind: Mapped[str] = mapped_column(String(20))  # CROP_KINDS
    scale_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="auto")  # CROP_STATUS
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CharsetEntry(Base):
    __tablename__ = "charset_entries"

    char: Mapped[str] = mapped_column(String(4), primary_key=True)  # 单字符（含非 BMP）
    instance_count: Mapped[int] = mapped_column(Integer, default=0)
    renderable: Mapped[bool] = mapped_column(Boolean, default=False)
    render_font: Mapped[str | None] = mapped_column(String(50), nullable=True)
    in_trainset: Mapped[bool] = mapped_column(Boolean, default=False)
    is_holdout: Mapped[bool] = mapped_column(Boolean, default=False)  # test_unknown_content 留出
    content_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    median_box_px: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # EXPORT_KINDS
    params_json: Mapped[str] = mapped_column(Text)  # 完整参数快照
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # EXPORT_STATUS
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(40))  # JOB_TYPES
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # JOB_STATUS
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    log: Mapped[str] = mapped_column(Text, default="")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
