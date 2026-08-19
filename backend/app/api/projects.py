"""项目与图像导入 API。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Image, Project
from ..schemas import (ImageListOut, ImageOut, ImportFolderIn, ImportM5HisDocIn,
                       JobOut, ProjectCreate, ProjectOut)
from ..services import queue
from ..services.imaging import variant_path
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api", tags=["projects", "images"])


@router.post("/projects", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    if db.query(Project).filter_by(name=body.name).first():
        raise HTTPException(409, f"项目名已存在: {body.name}")
    p = Project(name=body.name, kind=body.kind,
                source_path=body.source_path, notes=body.notes)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _project_out(db, p)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return [_project_out(db, p) for p in db.query(Project).order_by(Project.id).all()]


def _project_out(db: Session, p: Project) -> ProjectOut:
    out = ProjectOut.model_validate(p)
    out.image_count = db.query(func.count(Image.id)).filter_by(project_id=p.id).scalar()
    return out


@router.post("/projects/{project_id}/import-folder", response_model=JobOut)
def import_folder(project_id: int, body: ImportFolderIn, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    from pathlib import Path
    if not Path(body.folder).is_dir():
        raise HTTPException(400, f"目录不存在: {body.folder}")
    return queue.enqueue(db, "import_folder",
                         {"project_id": project_id, "folder": body.folder,
                          "source": body.source})


@router.post("/projects/{project_id}/import-m5hisdoc", response_model=JobOut)
def import_m5hisdoc(project_id: int, body: ImportM5HisDocIn,
                    db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    from pathlib import Path
    if not Path(body.root).is_dir():
        raise HTTPException(400, f"目录不存在: {body.root}")
    return queue.enqueue(db, "import_m5hisdoc",
                         {"project_id": project_id, "root": body.root,
                          "subset": body.subset})


# ---- 图像 ----
@router.get("/images", response_model=ImageListOut)
def list_images(project_id: int | None = None, status: str | None = None,
                style_id: int | None = None, page: int = 1,
                page_size: int = 60, db: Session = Depends(get_db)):
    q = db.query(Image)
    if project_id is not None:
        q = q.filter_by(project_id=project_id)
    if status:
        q = q.filter_by(status=status)
    if style_id is not None:
        q = q.filter_by(style_id=style_id)
    total = q.count()
    items = (q.order_by(Image.id).offset((page - 1) * page_size)
             .limit(page_size).all())
    return ImageListOut(total=total, items=items)


@router.get("/images/{image_id}", response_model=ImageOut)
def get_image(image_id: int, db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图像不存在")
    return img


@router.get("/images/{image_id}/file")
def get_image_file(image_id: int, variant: str = "display",
                   db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图像不存在")
    if variant not in ("original", "display", "thumb"):
        raise HTTPException(400, "variant 须为 original/display/thumb")
    p = variant_path(img.project_id, img.id, variant)
    if not p:
        raise HTTPException(404, "文件不存在")
    return FileResponse(p)


@router.patch("/images/{image_id}", response_model=ImageOut)
def patch_image(image_id: int, body: dict, db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图像不存在")
    if "style_id" in body:
        img.style_id = body["style_id"]
    db.commit()
    db.refresh(img)
    return img
