# 古籍生成与修复平台（guji-platform）

面向古籍图像修复与字形生成研究的本地数据标注平台。当前包含**数据标注模块**（字符框标注、损伤区域标注、风格分类、单字裁剪、复查、导出），后续扩展训练与生成模块。

## 技术栈

- 后端：Python 3.11（conda 环境 `guji`）+ FastAPI + SQLite（WAL）+ SQLAlchemy 2.0
- 任务队列：jobs 表 + 独立 worker 进程轮询（GPU 任务串行执行）
- 前端：Vue 3 + Vite + TypeScript + Pinia + Naive UI + Konva（标注画布）

## 目录

```
backend/    FastAPI 应用（app/api、app/services、app/pipelines、app/models）
worker/     任务进程（轮询 jobs 表，串行执行 OCR/聚类/裁剪/导出等长任务）
frontend/   Vue 3 前端
data/       全部用户数据（数据库、图像、mask、裁剪、嵌入缓存、导出产物），不进 git
docs/       数据契约文档（HDR28K / FontDataset）
```

## 运行

```bat
:: 初始化（首次）
conda activate guji
pip install -r backend\requirements.txt
cd frontend && npm install

:: 开发（三个进程）
run_dev.bat
```

前端 http://localhost:5173 ，后端 API 文档 http://localhost:8000/docs

## 设计原则

1. 数据库是唯一真值，训练数据集目录（HDR28K / FontDataset）一律由导出任务生成，不手工编辑。
2. 自动结果（OCR、聚类、自动裁剪）一律以 `auto` 状态进入复查流程，人工确认后才进导出池。
3. data/ 目录含受许可限制的数据（M5HisDoc 为 CC BY-NC-ND），不进版本库，需单独备份。
