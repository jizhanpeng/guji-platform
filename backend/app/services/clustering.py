"""风格聚类（移植自 new-dataset/01_improved_cluster.py + 02_merge_singletons.py
+ 06_subcluster.py），数据库落地。

与原脚本的一致性约定：
- prepare_matrix 对布局/颜色块做语料级 z-score（原脚本在提取时做，效果相同），
  DINO 块已逐图 L2 归一化，直接使用；
- 距离 = cosine，linkage = complete，fcluster(criterion='distance')；
- max_cluster_pages：超过的簇解散为单页（宁拆勿混；0=不限制）；
- merge_singletons：单页按簇中心 cosine 距离归并到 ≤ merge_radius 的最近多页簇；
- dino_only：取前 384 维（06 的经验：文件夹内布局/颜色趋同会淹没 DINO 判别力）。
"""
import numpy as np
from sqlalchemy.orm import Session

from ..models import Image as ImageRow, Style, StyleHistory
from .features import DINO_DIM, load_features

SPLIT_PRIORITY = {"train": 0, "val": 1, "test": 2}


def prepare_matrix(X_raw: np.ndarray, dino_only: bool = False) -> np.ndarray:
    """原始 491d → 聚类矩阵：布局/颜色块 z-score，dino_only 时只取前 384 维。"""
    if dino_only:
        return X_raw[:, :DINO_DIM].astype(np.float32)
    dino = X_raw[:, :DINO_DIM]
    blocks = []
    for sl in (slice(DINO_DIM, -28), slice(-28, None)):
        b = X_raw[:, sl]
        mu, sd = b.mean(0), b.std(0) + 1e-6
        blocks.append((b - mu) / sd)
    return np.concatenate([dino] + blocks, axis=1).astype(np.float32)


def linkage_matrix(X: np.ndarray) -> np.ndarray:
    from scipy.cluster.hierarchy import linkage as sci_linkage
    from scipy.spatial.distance import pdist
    return sci_linkage(pdist(X, metric="cosine"), method="complete")


def labels_at(Z: np.ndarray, threshold: float) -> np.ndarray:
    from scipy.cluster.hierarchy import fcluster
    return fcluster(Z, t=threshold, criterion="distance") - 1


def groups_from_labels(labels: np.ndarray, keys: list,
                       max_cluster_pages: int = 0) -> tuple[list[list], int]:
    """簇标签 → 组列表（按大小降序，组内保持输入序）；过大簇解散为单页。

    返回 (groups, n_dissolved)。
    """
    by_label: dict[int, list] = {}
    for lab, k in zip(labels, keys):
        by_label.setdefault(int(lab), []).append(k)
    groups, n_dissolved = [], 0
    for g in by_label.values():
        if max_cluster_pages and len(g) > max_cluster_pages:
            n_dissolved += 1
            groups.extend([[k] for k in g])
        else:
            groups.append(g)
    groups.sort(key=lambda g: (-len(g), str(g[0])))
    return groups, n_dissolved


def merge_singletons(groups: list[list], X: np.ndarray, keys: list,
                     merge_radius: float = 0.8) -> tuple[list[list], dict]:
    """单页归并到最近多页簇（02_merge_singletons.py 的移植）。

    X/keys 与 groups 中的元素一一对应（keys 用于索引特征行）。
    返回 (new_groups, detail)。
    """
    row_of = {k: i for i, k in enumerate(keys)}
    singles = [g for g in groups if len(g) == 1]
    multis = [g for g in groups if len(g) > 1]
    if not singles or not multis:
        return groups, {"merged": 0, "failed": len(singles)}

    centers = []
    for g in multis:
        centers.append(X[[row_of[k] for k in g]].mean(axis=0))
    centers = np.stack(centers)
    centers = centers / (np.linalg.norm(centers, axis=1, keepdims=True) + 1e-8)

    merged, failed = 0, 0
    for g in singles:
        vec = X[row_of[g[0]]]
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        dists = 1.0 - centers @ vec
        j = int(np.argmin(dists))
        if dists[j] <= merge_radius:
            multis[j].append(g[0])
            merged += 1
        else:
            failed += 1
    # multis 已含归并页；未归并的单页保留为独立组
    out = [sorted(g, key=str) for g in multis]
    for g in singles:
        vec = X[row_of[g[0]]]
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        dists = 1.0 - centers @ vec
        if dists.min() > merge_radius:
            out.append(g)
    out.sort(key=lambda g: (-len(g), str(g[0])))
    return out, {"merged": merged, "failed": failed}


def cluster_stats(groups: list[list]) -> dict:
    sizes = sorted((len(g) for g in groups), reverse=True)
    n = len(sizes)
    return {
        "n_styles": n,
        "n_pages": sum(sizes),
        "size_median": float(np.median(sizes)) if n else 0,
        "size_max": sizes[0] if n else 0,
        "singletons": sum(1 for s in sizes if s == 1),
        "styles_ge_10": sum(1 for s in sizes if s >= 10),
    }


def cluster_matrix_for_images(db: Session, project_id: int,
                              image_ids: list[int] | None = None,
                              dino_only: bool = False):
    """取项目特征并组装聚类矩阵。返回 (ids list[int], X)。"""
    ids, X = load_features(project_id)
    if image_ids is not None:
        want = set(image_ids)
        mask = np.array([i in want for i in ids.tolist()])
        ids, X = ids[mask], X[mask]
    if len(ids) == 0:
        raise RuntimeError("无可用特征，请先运行特征提取任务")
    return ids.tolist(), prepare_matrix(X, dino_only=dino_only)


def apply_groups_to_db(db: Session, project_id: int, groups: list[list[int]],
                       method: str, split_policy: str = "guard",
                       name_prefix: str = "book", log=print) -> list[Style]:
    """把聚类组写入 DB：新建 Style、改 images.style_id、写 StyleHistory。

    split_policy:
      - "guard": 组内页面 split 不一致时，全组归入优先级最高的 split
        （train>val>test 中 train 最优先），并锁定 style.locked_split；
      - "keep":  不动 official_split；混合 split 的组只告警不锁定。
    组内元素为图像 id。返回新建的 Style 列表。
    """
    rows = {r.id: r for r in db.query(ImageRow)
            .filter(ImageRow.id.in_([k for g in groups for k in g])).all()}
    styles = []
    n_warn = 0
    for i, g in enumerate(groups):
        style = Style(name=f"{name_prefix}_{i:04d}", method=method, project_id=project_id)
        db.add(style)
        db.flush()
        splits = {rows[k].official_split for k in g if rows[k].official_split}
        if len(splits) == 1:
            style.locked_split = next(iter(splits))
        elif len(splits) > 1:
            n_warn += 1
            if split_policy == "guard":
                target = min(splits, key=lambda sp: SPLIT_PRIORITY.get(sp, 0))
                style.locked_split = target
                for k in g:
                    if rows[k].official_split != target:
                        log(f"  泄漏守卫: 图像 {rows[k].filename} "
                            f"{rows[k].official_split} → {target}（随组 {style.name}）")
                        rows[k].official_split = target
            else:
                log(f"  警告: 组 {style.name} 跨划分 {sorted(splits)}（未处理）")
        for k in g:
            row = rows[k]
            if row.style_id != style.id:
                db.add(StyleHistory(image_id=k, from_style_id=row.style_id,
                                    to_style_id=style.id, reason=f"{method} 聚类"))
                row.style_id = style.id
        styles.append(style)
    if n_warn:
        log(f"共 {n_warn} 个组跨官方划分（split_policy={split_policy}）")
    db.commit()
    return styles
