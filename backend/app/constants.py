"""状态与枚举常量（字符串存库，便于 SQL 直接读）。"""

# ---- 项目类型 ----
PROJECT_KINDS = ("m5hisdoc", "scans", "other")

# ---- 图像来源 ----
IMAGE_SOURCES = ("m5hisdoc_regular", "m5hisdoc_hard", "scan", "other")

# ---- 官方划分（M5HisDoc）----
SPLITS = ("train", "val", "test")

# ---- 页面状态（由标注状态派生，事务内重算）----
PAGE_STATUS = ("unannotated", "auto_labeled", "in_review", "reviewed", "exported")

# ---- 字符标注 ----
ANNO_ORIGINS = ("m5hisdoc", "ocr", "manual")
ANNO_STATUS = ("auto", "confirmed", "edited", "rejected")

# ---- 损伤区域 ----
DAMAGE_TYPES = ("character_missing", "paper_damage", "ink_erosion")
DAMAGE_ORIGINS = ("manual", "auto", "m5hisdoc_hard_derived")
DAMAGE_STATUS = ("draft", "confirmed", "rejected")

# ---- 风格 ----
STYLE_METHODS = ("cluster", "manual", "subcluster", "merged")

# ---- 单字裁剪 ----
CROP_KINDS = ("fixed64", "downscaled")
CROP_STATUS = ("auto", "confirmed", "rejected")

# ---- 导出 ----
EXPORT_KINDS = ("hdr28k", "fontdataset", "m5hisdoc_csv")
EXPORT_STATUS = ("running", "done", "failed")

# ---- 任务 ----
JOB_TYPES = (
    "dummy", "import_folder", "import_m5hisdoc",
    "ocr", "suggest_damage",
    "embed", "cluster", "subcluster",
    "auto_crop", "charset_rebuild", "render_content",
    "degrade", "export_hdr28k", "export_fontdataset", "contact_sheet",
)
JOB_STATUS = ("pending", "running", "done", "failed", "canceled")
