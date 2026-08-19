"""全局配置：路径、GPU 开关等。所有数据路径相对 data/ 根目录。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# guji-platform 根目录（backend/app/config.py -> 上三级）
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    data_dir: Path = DATA_DIR
    db_url: str = f"sqlite:///{(DATA_DIR / 'platform.db').as_posix()}"

    # 派生图参数
    thumb_max_px: int = 512
    display_max_px: int = 2048

    # DINO 权重（方法二聚类用，本地加载）
    dino_model_path: str = r"D:\jzp\sues-thesis-main\参考资料\method3\klora\dino-vits16"

    model_config = {"env_prefix": "GUJI_"}

    # ---- 常用子目录（惰性创建）----
    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def masks_dir(self) -> Path:
        return self.data_dir / "masks"

    @property
    def crops_dir(self) -> Path:
        return self.data_dir / "crops"

    @property
    def embeddings_dir(self) -> Path:
        return self.data_dir / "embeddings"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def content_dir(self) -> Path:
        """ContentImage（标准字体渲染图）目录。"""
        return self.data_dir / "content"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.images_dir, self.masks_dir,
                  self.crops_dir, self.embeddings_dir, self.exports_dir,
                  self.content_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
