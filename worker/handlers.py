"""任务处理器注册表：job_type -> callable(db, job, ctx)。

ctx 提供：
- progress(pct: float, msg: str)  更新进度（批量落库）
- canceled() -> bool              是否收到取消请求（协作式取消）
"""
import json
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.models import Job, Project
from backend.app.services.importer import import_images, scan_folder
from backend.app.services.m5hisdoc_import import import_m5hisdoc


class JobContext:
    def __init__(self, db: Session, job: Job):
        self.db = db
        self.job = job
        self._last_flush = 0.0

    def progress(self, pct: float, msg: str = ""):
        self.job.progress = round(pct, 4)
        if msg:
            self.log(msg)
        # 最多每秒落库一次，避免高频写
        now = time.time()
        if now - self._last_flush >= 1.0:
            self.db.commit()
            self._last_flush = now

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.job.log = (self.job.log + f"\n[{ts}] {msg}").strip()

    def canceled(self) -> bool:
        self.db.refresh(self.job)
        return bool(self.job.cancel_requested)


def handle_dummy(db: Session, job: Job, ctx: JobContext):
    payload = json.loads(job.payload_json)
    seconds = int(payload.get("seconds", 5))
    for i in range(seconds):
        if ctx.canceled():
            return
        time.sleep(1)
        ctx.progress((i + 1) / seconds, f"假装干活 {i + 1}/{seconds} 秒")


def handle_import_folder(db: Session, job: Job, ctx: JobContext):
    payload = json.loads(job.payload_json)
    project = db.get(Project, payload["project_id"])
    if project is None:
        raise RuntimeError(f"项目不存在: {payload['project_id']}")
    folder = Path(payload["folder"])
    files = scan_folder(folder)
    ctx.log(f"扫描到 {len(files)} 个图像文件")
    n = import_images(db, project, files, payload.get("source", "scan"),
                      progress_cb=ctx.progress, cancel_cb=ctx.canceled)
    ctx.log(f"导入完成，共 {n} 张")


def handle_import_m5hisdoc(db: Session, job: Job, ctx: JobContext):
    payload = json.loads(job.payload_json)
    project = db.get(Project, payload["project_id"])
    if project is None:
        raise RuntimeError(f"项目不存在: {payload['project_id']}")
    stats = import_m5hisdoc(db, project, Path(payload["root"]),
                            payload.get("subset", "M5HisDoc_regular"),
                            progress_cb=ctx.progress, cancel_cb=ctx.canceled)
    ctx.log(f"导入完成：{stats['images']} 页 / {stats['annotations']} 条标注"
            f"（跳过 {stats['skipped']}）")


HANDLERS = {
    "dummy": handle_dummy,
    "import_folder": handle_import_folder,
    "import_m5hisdoc": handle_import_m5hisdoc,
}
