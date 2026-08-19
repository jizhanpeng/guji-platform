"""任务查询/取消 API。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job
from ..schemas import JobOut
from ..services import queue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(status: str | None = None, limit: int = 50,
              db: Session = Depends(get_db)):
    q = db.query(Job)
    if status:
        q = q.filter_by(status=status)
    return q.order_by(Job.id.desc()).limit(limit).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    if not queue.request_cancel(db, job_id):
        raise HTTPException(400, "任务不存在或已结束")
    return {"ok": True}


@router.post("/dummy", response_model=JobOut)
def enqueue_dummy(db: Session = Depends(get_db)):
    """冒烟测试用假任务。"""
    return queue.enqueue(db, "dummy", {"seconds": 5})
