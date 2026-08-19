"""风格 CRUD + 聚类任务入口 + 泄漏守卫 + 联系表。"""
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Image, Project, Style, StyleHistory
from ..schemas import JobOut
from ..services.imaging import variant_path
from ..services.queue import enqueue

router = APIRouter(prefix="/api", tags=["styles"])
settings = get_settings()


class StyleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    method: str
    notes: str | None
    locked_split: str | None
    image_count: int = 0
    splits: dict[str, int] = {}  # 成员页的 official_split 分布


class StylePatch(BaseModel):
    name: str | None = None
    notes: str | None = None
    locked_split: str | None = None


class MoveIn(BaseModel):
    style_id: int | None  # None = 移出风格
    force: bool = False   # 目标风格锁定时，允许随迁 official_split


def _style_out(db: Session, style: Style) -> StyleOut:
    out = StyleOut.model_validate(style)
    rows = db.query(Image).filter_by(style_id=style.id).all()
    out.image_count = len(rows)
    for r in rows:
        if r.official_split:
            out.splits[r.official_split] = out.splits.get(r.official_split, 0) + 1
    return out


@router.get("/projects/{project_id}/styles", response_model=list[StyleOut])
def list_styles(project_id: int, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    style_ids = {r.style_id for r in db.query(Image).filter_by(project_id=project_id).all()
                 if r.style_id is not None}
    styles = [db.get(Style, sid) for sid in sorted(style_ids)]
    return [_style_out(db, s) for s in styles]


@router.post("/projects/{project_id}/styles", response_model=StyleOut)
def create_style(project_id: int, body: StylePatch, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "风格名不能为空")
    if db.query(Style).filter_by(name=name).first():
        raise HTTPException(409, f"风格名 {name} 已存在")
    style = Style(name=name, method="manual", notes=body.notes,
                  locked_split=body.locked_split)
    db.add(style)
    db.commit()
    db.refresh(style)
    return _style_out(db, style)


@router.patch("/styles/{style_id}", response_model=StyleOut)
def patch_style(style_id: int, body: StylePatch, db: Session = Depends(get_db)):
    style = db.get(Style, style_id)
    if not style:
        raise HTTPException(404, "风格不存在")
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        clash = db.query(Style).filter_by(name=data["name"]).first()
        if clash and clash.id != style_id:
            raise HTTPException(409, f"风格名 {data['name']} 已存在")
    if "locked_split" in data and data["locked_split"]:
        bad = [r.filename for r in db.query(Image).filter_by(style_id=style_id).all()
               if r.official_split and r.official_split != data["locked_split"]]
        if bad:
            raise HTTPException(
                409, f"该风格有 {len(bad)} 页不属于 {data['locked_split']} 划分"
                     f"（如 {bad[:3]}），请先迁移页面或解除锁定")
    for k, v in data.items():
        setattr(style, k, v)
    db.commit()
    db.refresh(style)
    return _style_out(db, style)


@router.post("/images/{image_id}/style")
def move_image(image_id: int, body: MoveIn, db: Session = Depends(get_db)):
    """把图像移入/移出风格（泄漏守卫：锁定风格的划分必须匹配）。"""
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图像不存在")
    target = db.get(Style, body.style_id) if body.style_id else None
    if body.style_id and not target:
        raise HTTPException(404, "风格不存在")
    if target and target.locked_split and img.official_split \
            and img.official_split != target.locked_split:
        if not body.force:
            raise HTTPException(
                409, f"风格 {target.name} 已锁定 {target.locked_split} 划分，"
                     f"该页属于 {img.official_split}；force=true 可将该页一并迁移")
        img.official_split = target.locked_split
    old = img.style_id
    if old != body.style_id:
        db.add(StyleHistory(image_id=image_id, from_style_id=old,
                            to_style_id=body.style_id, reason="手动调整"))
        img.style_id = body.style_id
    db.commit()
    return {"ok": True, "from": old, "to": body.style_id}


# ---- 联系表（按需生成 + 成员指纹缓存）----

@router.get("/styles/{style_id}/sheet")
def contact_sheet(style_id: int, per: int = 16, thumb: int = 192, cols: int = 4,
                  db: Session = Depends(get_db)):
    """该风格的抽样拼图（JPG）。成员变化时指纹变化 → 自动重新生成。"""
    style = db.get(Style, style_id)
    if not style:
        raise HTTPException(404, "风格不存在")
    rows = (db.query(Image).filter_by(style_id=style_id)
            .order_by(Image.id).all())
    if not rows:
        raise HTTPException(400, "风格下没有页面")
    fp = hashlib.md5(",".join(str(r.id) for r in rows).encode()).hexdigest()[:10]
    out_dir = settings.exports_dir / "_sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"style_{style_id}_{fp}_{per}_{thumb}_{cols}.jpg"
    if not out.exists():
        from PIL import Image as PILImage
        pick = [rows[int(i)] for i in
                __import__("numpy").linspace(0, len(rows) - 1, min(per, len(rows))).astype(int)]
        rows_n = (len(pick) + cols - 1) // cols
        sheet = PILImage.new("RGB", (cols * thumb, rows_n * thumb), (255, 255, 255))
        for k, r in enumerate(pick):
            p = variant_path(r.project_id, r.id, "thumb") \
                or variant_path(r.project_id, r.id, "original")
            if p is None:
                continue
            im = PILImage.open(p).convert("RGB")
            im.thumbnail((thumb, thumb))
            sheet.paste(im, ((k % cols) * thumb, (k // cols) * thumb))
        sheet.save(out, quality=85)
    return FileResponse(out, media_type="image/jpeg")


# ---- 聚类任务 ----

class EmbedIn(BaseModel):
    project_id: int


class ClusterIn(BaseModel):
    project_id: int
    threshold: float = 0.25
    max_cluster_pages: int = 0     # 0 = 不解散大簇（复现 t025_nocap）
    merge_radius: float = 0.8      # 单页归并半径；<=0 关闭
    dino_only: bool = False
    split_policy: str = "guard"    # guard | keep
    name_prefix: str = "book"


class SubclusterIn(BaseModel):
    threshold: float
    dino_only: bool = True


@router.post("/jobs/embed", response_model=JobOut)
def start_embed(body: EmbedIn, db: Session = Depends(get_db)):
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "项目不存在")
    return enqueue(db, "embed", {"project_id": body.project_id})


@router.post("/jobs/cluster", response_model=JobOut)
def start_cluster(body: ClusterIn, db: Session = Depends(get_db)):
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "项目不存在")
    if body.split_policy not in ("guard", "keep"):
        raise HTTPException(400, "split_policy 须为 guard 或 keep")
    return enqueue(db, "cluster", body.model_dump())


@router.post("/styles/{style_id}/subcluster", response_model=JobOut)
def start_subcluster(style_id: int, body: SubclusterIn, db: Session = Depends(get_db)):
    style = db.get(Style, style_id)
    if not style:
        raise HTTPException(404, "风格不存在")
    img = db.query(Image).filter_by(style_id=style_id).first()
    if not img:
        raise HTTPException(400, "风格下没有页面")
    return enqueue(db, "subcluster", {
        "project_id": img.project_id, "style_id": style_id,
        "threshold": body.threshold, "dino_only": body.dino_only,
    })
