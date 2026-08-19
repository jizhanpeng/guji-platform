# 古籍生成与修复平台（guji-platform）

面向古籍图像修复与字形生成研究的本地数据平台，覆盖**数据标注 → 复查 → 数据集导出**
全流程：字符框标注（手动 + PaddleOCR 自动）、损伤区域笔刷标注、页面风格聚类分类、
单字裁剪与复查、字表与标准字模渲染，以及两个训练数据集格式的一键导出
（方法一 HDR28K 修复数据集 / 方法二 FontDataset 字形生成数据集）。
后续扩展训练与生成模块。

## 技术栈

- 后端：Python 3.11（conda 环境 `guji`）+ FastAPI + SQLite（WAL）+ SQLAlchemy 2.0
- 任务队列：jobs 表 + 独立 worker 进程轮询（长任务串行执行）
- 前端：Vue 3 + Vite + TypeScript + Pinia + Naive UI + Konva（标注画布）
- 模型：PaddleOCR（PP-OCRv6 文字检测识别）、DINO ViT-S/16（页面风格特征）

## 功能

| 模块 | 功能 |
|---|---|
| 总览 | 项目统计仪表盘、数据库一键备份（data/backups/） |
| 图像管理 | 文件夹导入、M5HisDoc 导入（官方划分 + label_char 标注，自动去重） |
| 字符标注 | Konva 画框/变换/改字/快捷键、整页确认、PaddleOCR 自动标注（行检测+等分单字框） |
| 破损标注 | 笔刷描画三类破损（缺字/纸损/墨迹），服务端光栅化 mask |
| 风格管理 | DINO+布局+颜色 491d 特征层次聚类、二次细分、泄漏守卫（划分锁）、联系表 |
| 裁剪复查 | §2.5 保真裁剪（≤56px 定窗不重采样）、筛选网格确认/驳回、字表与字模预览 |
| 导出 | FontDataset（train/test_unknown_content/test_unknown_style）、HDR28K（512² gt/degraded/mask/content）、label_char CSV 往返 |

## 目录

```
backend/    FastAPI 应用（app/api、app/services、app/models）
worker/     任务进程（轮询 jobs 表，串行执行 OCR/聚类/裁剪/导出等长任务）
frontend/   Vue 3 前端
data/       全部用户数据（数据库、图像、mask、裁剪、嵌入缓存、导出产物、备份），不进 git
docs/       验收记录（VERIFICATION.md）
```

## 运行

```bat
:: 初始化（首次）
conda activate guji
pip install -r backend\requirements.txt
pip install paddlepaddle paddleocr   :: OCR 功能需要
cd frontend && npm install

:: 开发（三个进程：backend :8001 / worker / vite :5173）
run_dev.bat
```

前端 http://localhost:5173 ，后端 API 文档 http://localhost:8001/docs

## 数据契约

- **FontDataset**（方法二 MethodTwo-gaijing1）：`{phase}/ContentImage/u{hex}.png` +
  `{phase}/TargetImage/{style}/{style}+u{hex}.png`；风格按锁定划分路由到
  train / test_unknown_content（留出字）/ test_unknown_style（test 风格）；
  每风格每 phase ≥2 图。已用原版 `dataset/font_dataset.py` 加载验证。
- **HDR28K**（方法一 StruTexDiff 论文 §IV-A）：512×512 四件套
  `gt / degraded / mask / content` + `meta.jsonl`；退化配比
  缺字 25% / 纸损 50% / 墨迹 25%（LaMa→OpenCV Telea、Genalog→淡出+模糊+水渍
  本地近似）；手工标注的破损区域优先生成真实破损 patch。

## 设计原则

1. 数据库是唯一真值，训练数据集目录（HDR28K / FontDataset）一律由导出任务生成，不手工编辑。
2. 自动结果（OCR、聚类、自动裁剪）一律以 `auto` 状态进入复查流程，人工确认后才进导出池。
3. data/ 目录含受许可限制的数据（M5HisDoc 为 CC BY-NC-ND），不进版本库，需单独备份。
4. 划分泄漏守卫：风格簇跨官方 train/val/test 划分时整体迁移并锁定，导出按锁路由。
