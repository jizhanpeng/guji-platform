"""任务队列门面：enqueue 入队，worker 进程轮询执行。
当前实现 = jobs 表 + worker 轮询；以后换 Dramatiq/Celery 只改这个文件。
"""
import json

from sqlalchemy.orm import Session

from ..models import Job


def enqueue(db: Session, job_type: str, payload: dict) -> Job:
    job = Job(job_type=job_type, payload_json=json.dumps(payload, ensure_ascii=False))
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def request_cancel(db: Session, job_id: int) -> bool:
    job = db.get(Job, job_id)
    if job is None or job.status in ("done", "failed", "canceled"):
        return False
    if job.status == "pending":
        job.status = "canceled"
    else:
        job.cancel_requested = True  # 运行中的任务协作式取消
    db.commit()
    return True
