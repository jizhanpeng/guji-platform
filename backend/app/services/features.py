"""页面风格特征提取（移植自 参考资料/method2/new-dataset/01_improved_cluster.py）。

特征 = DINO ViT-S/16 CLS 嵌入(384d, 逐图 L2 归一化)
     + 布局指纹(79d, 原始值)
     + 纸墨颜色纹理(28d, 原始值)，共 491d。

与原脚本的关键差异：布局/颜色块**不在提取时 z-score**，而是存原始值，
z-score 推迟到聚类时按当前语料计算（见 clustering.prepare_matrix）。
这样新增页面可以增量追加特征而不失效；对全集聚类时与原脚本逐位等价。

存储：data/embeddings/project_{id}.npz，数组 ids:int64[N] + X:float32[N,491]。
"""
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Image as ImageRow

settings = get_settings()

DINO_DIM = 384
LAYOUT_DIM = 79
COLOR_DIM = 28
TOTAL_DIM = DINO_DIM + LAYOUT_DIM + COLOR_DIM  # 491

try:
    _BILINEAR = Image.Resampling.BILINEAR
except AttributeError:  # Pillow < 9.1
    _BILINEAR = Image.BILINEAR


def features_path(project_id: int) -> Path:
    return settings.embeddings_dir / f"project_{project_id}.npz"


def load_features(project_id: int) -> tuple[np.ndarray, np.ndarray]:
    """返回 (ids int64[N], X float32[N,491])；无缓存时返回空数组。"""
    p = features_path(project_id)
    if not p.is_file():
        return np.zeros(0, dtype=np.int64), np.zeros((0, TOTAL_DIM), dtype=np.float32)
    z = np.load(p)
    return z["ids"].astype(np.int64), z["X"].astype(np.float32)


def save_features(project_id: int, ids: np.ndarray, X: np.ndarray) -> None:
    settings.embeddings_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(features_path(project_id), ids=ids, X=X)


# ---- 布局指纹（79d，原始值）----

def layout_features(im: Image.Image, thumb_size: int = 512) -> np.ndarray:
    """竖排古籍布局指纹：投影曲线 + 列统计 + 密度 + 边距。"""
    im = im.convert("L")
    w, h = im.size
    scale = thumb_size / min(w, h)
    im = im.resize((int(w * scale), int(h * scale)), _BILINEAR)
    arr = np.asarray(im, dtype=np.float32) / 255.0
    nh, nw = arr.shape

    h_proj = arr.mean(axis=1)  # [H]
    v_proj = arr.mean(axis=0)  # [W]

    def downsample(signal, target=32):
        idx = np.linspace(0, len(signal) - 1, target).astype(int)
        return signal[idx]

    h_feat = downsample(h_proj, 32)
    v_feat = downsample(v_proj, 32)
    h_stats = np.array([h_feat.mean(), h_feat.std(), h_feat.min(), h_feat.max()])
    v_stats = np.array([v_feat.mean(), v_feat.std(), v_feat.min(), v_feat.max()])
    densities = np.array([(arr < 0.3).mean(), (arr < 0.5).mean(), (arr < 0.7).mean()])

    paper_color = np.percentile(arr, 95)
    paper_mask = arr > (paper_color - 0.1)
    margins = np.array([
        paper_mask[:nh // 8, :].mean(), paper_mask[-nh // 8:, :].mean(),
        paper_mask[:, :nw // 8].mean(), paper_mask[:, -nw // 8:].mean(),
    ])
    feat = np.concatenate([h_feat, v_feat, h_stats, v_stats, densities, margins])
    assert feat.shape[0] == LAYOUT_DIM
    return feat.astype(np.float32)


# ---- 纸墨颜色 + 纹理（28d，原始值）----

def color_features(im: Image.Image, thumb_size: int = 256) -> np.ndarray:
    im = im.convert("RGB").resize((thumb_size, thumb_size), _BILINEAR)
    rgb = np.asarray(im, dtype=np.float32) / 255.0
    # 注意：原脚本 gray 保持 0–255（未除 255）。z-score 对仿射不变，
    # 但梯度直方图的 range=(0,0.3) 是绝对阈值，必须沿用 0–255 刻度才能复现。
    gray = np.asarray(im.convert("L"), dtype=np.float32)

    thr = np.percentile(gray, 80)
    paper_pixels = rgb[gray >= thr]
    paper_median = (np.median(paper_pixels, axis=0) if len(paper_pixels)
                    else np.array([0.9, 0.85, 0.8]))
    paper_std = (np.std(paper_pixels, axis=0) if len(paper_pixels)
                 else np.array([0.05, 0.05, 0.05]))

    thr_dark = np.percentile(gray, 20)
    ink_pixels = rgb[gray <= thr_dark]
    ink_median = (np.median(ink_pixels, axis=0) if len(ink_pixels)
                  else np.array([0.1, 0.05, 0.05]))

    gray_percentiles = np.percentile(gray, [5, 10, 25, 50, 75, 90, 95])

    gy, gx = np.gradient(gray)
    mag = np.sqrt(gx * gx + gy * gy)
    h_g = np.histogram(mag, bins=12, range=(0, 0.3))[0].astype(np.float32)
    h_g = h_g / max(h_g.sum(), 1)

    feat = np.concatenate([paper_median, paper_std, ink_median,
                           gray_percentiles, h_g]).astype(np.float32)
    assert feat.shape[0] == COLOR_DIM
    return feat


# ---- DINO 嵌入（384d）----

class DinoEncoder:
    """惰性加载的 DINO ViT-S/16 编码器（本地权重，GPU 可用则用）。"""

    def __init__(self, model_dir: str | None = None):
        self.model_dir = model_dir or settings.dino_model_path
        self._model = None
        self._processor = None
        self._device = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        import torch
        from transformers import ViTImageProcessor, ViTModel
        self._processor = ViTImageProcessor.from_pretrained(
            self.model_dir, local_files_only=True)
        self._model = ViTModel.from_pretrained(self.model_dir, local_files_only=True)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device).eval()
        assert self._model.config.hidden_size == DINO_DIM

    def encode(self, images: list[Image.Image]) -> np.ndarray:
        """一批 PIL 图 → [B,384] L2 归一化 CLS 嵌入。"""
        import torch
        self._ensure_loaded()
        resized = [im.convert("RGB").resize((224, 224), _BILINEAR) for im in images]
        inp = self._processor(images=resized, return_tensors="pt")
        inp = {k: v.to(self._device) for k, v in inp.items()}
        with torch.no_grad():
            out = self._model(**inp)
        cls = out.last_hidden_state[:, 0, :]
        cls = cls / cls.norm(dim=-1, keepdim=True)
        return cls.cpu().numpy().astype(np.float32)


# ---- 项目级批量提取 ----

def embed_project(db: Session, project_id: int, batch: int = 16,
                  progress_cb=None, cancel_cb=None) -> dict:
    """为项目中尚无特征的图像提取 491d 特征并追加进 npz 缓存。

    返回统计 dict。幂等：已有特征的图像跳过。
    """
    from ..services.imaging import variant_path

    ids, X = load_features(project_id)
    have = set(ids.tolist())
    rows = (db.query(ImageRow).filter_by(project_id=project_id)
            .order_by(ImageRow.id).all())
    todo = [r for r in rows if r.id not in have]
    if not todo:
        return {"total": len(rows), "embedded": 0, "cached": len(have)}

    dino = DinoEncoder()
    new_feats = []
    new_ids = []
    for i, row in enumerate(todo):
        if cancel_cb and cancel_cb():
            break
        src = variant_path(project_id, row.id, "original")
        if src is None:
            continue
        im = Image.open(src)
        im.load()
        lay = layout_features(im)
        col = color_features(im)
        dvec = dino.encode([im])[0]
        new_feats.append(np.concatenate([dvec, lay, col]))
        new_ids.append(row.id)
        if progress_cb and (i % batch == 0 or i == len(todo) - 1):
            progress_cb((i + 1) / len(todo), f"特征提取 {i + 1}/{len(todo)}")

    if new_ids:
        ids = np.concatenate([ids, np.array(new_ids, dtype=np.int64)])
        X = np.concatenate([X, np.stack(new_feats).astype(np.float32)])
        save_features(project_id, ids, X)
    return {"total": len(rows), "embedded": len(new_ids), "cached": len(have)}
