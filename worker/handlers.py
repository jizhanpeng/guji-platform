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

from backend.app.models import CharCrop, Image, Job, Project, Style
from backend.app.services.clustering import (apply_groups_to_db, cluster_matrix_for_images,
                                             cluster_stats, groups_from_labels, labels_at,
                                             linkage_matrix, merge_singletons)
from backend.app.services.features import embed_project
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


def handle_embed(db: Session, job: Job, ctx: JobContext):
    """提取项目全部页面的 491d 风格特征（DINO+布局+颜色），增量幂等。"""
    payload = json.loads(job.payload_json)
    stats = embed_project(db, payload["project_id"],
                          progress_cb=ctx.progress, cancel_cb=ctx.canceled)
    ctx.log(f"特征提取完成：新增 {stats['embedded']}，复用缓存 {stats['cached']}，"
            f"项目共 {stats['total']} 页")


def _drop_auto_styles(db: Session, project_id: int, ctx: JobContext):
    """重聚类前清理：摘下项目图像的旧自动风格并删除空壳 Style。"""
    img_ids = [r.id for r in db.query(Image).filter_by(project_id=project_id).all()]
    old_ids = {r.style_id for r in db.query(Image).filter(Image.id.in_(img_ids)).all()
               if r.style_id is not None}
    if not old_ids:
        return
    dropped = 0
    for sid in old_ids:
        style = db.get(Style, sid)
        if style is None or style.method == "manual":
            continue  # 手工风格不拆
        if db.query(CharCrop).filter_by(style_id=sid).first():
            ctx.log(f"风格 {style.name} 已有裁剪产物，跳过清理")
            continue
        for img in db.query(Image).filter_by(style_id=sid).all():
            if img.id in img_ids:
                img.style_id = None
        db.flush()
        if not db.query(Image).filter_by(style_id=sid).first():
            db.delete(style)
            dropped += 1
    db.commit()
    if dropped:
        ctx.log(f"清理旧自动风格 {dropped} 个")


def handle_cluster(db: Session, job: Job, ctx: JobContext):
    """全项目层次聚类 → 风格。默认参数复现 styles_final.json（t=0.25, nocap, merge 0.8）。"""
    payload = json.loads(job.payload_json)
    pid = payload["project_id"]
    threshold = float(payload.get("threshold", 0.25))
    max_pages = int(payload.get("max_cluster_pages", 0))
    merge_radius = payload.get("merge_radius", 0.8)
    dino_only = bool(payload.get("dino_only", False))
    split_policy = payload.get("split_policy", "guard")
    prefix = payload.get("name_prefix", "book")

    ids, X = cluster_matrix_for_images(db, pid, dino_only=dino_only)
    ctx.log(f"聚类输入: {len(ids)} 页 × {X.shape[1]} 维"
            f"（{'仅 DINO' if dino_only else 'DINO+布局+颜色'}），阈值 {threshold}")
    ctx.progress(0.1, "计算 linkage 矩阵…")
    Z = linkage_matrix(X)
    ctx.progress(0.6, "切分簇…")
    labels = labels_at(Z, threshold)
    groups, n_dissolved = groups_from_labels(labels, ids, max_cluster_pages=max_pages)
    if n_dissolved:
        ctx.log(f"大簇解散: {n_dissolved} 个 >{max_pages} 页的簇拆为单页")
    if merge_radius is not None and merge_radius > 0:
        groups, detail = merge_singletons(groups, X, ids, merge_radius=float(merge_radius))
        ctx.log(f"单页归并: {detail['merged']} 归并 / {detail['failed']} 保持独立"
                f"（半径 {merge_radius}）")
    stats = cluster_stats(groups)
    ctx.progress(0.8, "写入数据库…")
    _drop_auto_styles(db, pid, ctx)
    styles = apply_groups_to_db(db, pid, groups, method="cluster",
                                split_policy=split_policy,
                                name_prefix=prefix, log=ctx.log)
    ctx.log(f"聚类完成: {stats['n_styles']} 风格 / {stats['n_pages']} 页，"
            f"单页 {stats['singletons']}，≥10页 {stats['styles_ge_10']}，"
            f"最大 {stats['size_max']}（新建 {len(styles)} 个 Style）")


def handle_subcluster(db: Session, job: Job, ctx: JobContext):
    """单风格二次细分（06_subcluster.py 移植，默认仅 DINO 384d）。"""
    payload = json.loads(job.payload_json)
    pid = payload["project_id"]
    style = db.get(Style, payload["style_id"])
    if style is None:
        raise RuntimeError("风格不存在")
    threshold = float(payload["threshold"])
    dino_only = bool(payload.get("dino_only", True))

    img_ids = [r.id for r in db.query(Image).filter_by(style_id=style.id).all()]
    if len(img_ids) < 2:
        raise RuntimeError(f"风格 {style.name} 只有 {len(img_ids)} 页，无法细分")
    ids, X = cluster_matrix_for_images(db, pid, image_ids=img_ids, dino_only=dino_only)
    ctx.log(f"细分 {style.name}: {len(ids)} 页，阈值 {threshold}"
            f"（{'仅 DINO' if dino_only else '全特征'}）")
    Z = linkage_matrix(X)
    labels = labels_at(Z, threshold)
    groups, _ = groups_from_labels(labels, ids)  # 细分解散不设上限
    stats = cluster_stats(groups)
    styles = apply_groups_to_db(db, pid, groups, method="subcluster",
                                split_policy="keep",
                                name_prefix=f"{style.name}_sub", log=ctx.log)
    # 子风格继承父划分锁
    for s in styles:
        s.locked_split = s.locked_split or style.locked_split
    # 父风格已空则删除
    db.flush()
    if not db.query(Image).filter_by(style_id=style.id).first():
        db.delete(style)
    db.commit()
    ctx.log(f"细分完成: {len(groups)} 个子风格，单页 {stats['singletons']}，"
            f"最大 {stats['size_max']}")


HANDLERS = {
    "dummy": handle_dummy,
    "import_folder": handle_import_folder,
    "import_m5hisdoc": handle_import_m5hisdoc,
    "embed": handle_embed,
    "cluster": handle_cluster,
    "subcluster": handle_subcluster,
}
