"""Worker 进程：轮询 jobs 表，串行执行任务。

启动：在仓库根目录 `python -m worker.main`（需先激活 conda 环境 guji）。
GPU 模型（PaddleOCR / DINO）在后续任务的 handler 首次使用时惰性加载并常驻。
"""
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# 允许 `python -m worker.main` 从仓库根目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db import SessionLocal, init_db  # noqa: E402
from backend.app.models import Job  # noqa: E402
from worker.handlers import HANDLERS, JobContext  # noqa: E402

POLL_INTERVAL = 1.0


def run_one(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        job.status = "running"
        job.started_at = datetime.now()
        db.commit()
        ctx = JobContext(db, job)
        handler = HANDLERS.get(job.job_type)
        if handler is None:
            raise RuntimeError(f"未知任务类型: {job.job_type}")
        handler(db, job, ctx)
        if ctx.canceled():
            job.status = "canceled"
            ctx.log("任务已取消")
        else:
            job.status = "done"
            job.progress = 1.0
            ctx.log("任务完成")
    except Exception:
        db.rollback()
        job = db.get(Job, job_id)
        job.status = "failed"
        job.log = (job.log + "\n" + traceback.format_exc())[-8000:]
    finally:
        job.finished_at = datetime.now()
        db.commit()
        db.close()


def main() -> None:
    init_db()
    print(f"[worker] 启动，每 {POLL_INTERVAL}s 轮询一次", flush=True)
    while True:
        db = SessionLocal()
        job = (db.query(Job)
               .filter_by(status="pending")
               .order_by(Job.id)
               .first())
        job_id = job.id if job else None
        db.close()
        if job_id is not None:
            print(f"[worker] 领取任务 #{job_id}", flush=True)
            run_one(job_id)
        else:
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
