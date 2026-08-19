# 里程碑验收记录

## M1 — 数据导入与字符标注（2026-08-19）

- M5HisDoc 导入器：10 页小样本导入，官方划分/标注正确（首页 1086 条）。
- 标注 CRUD + 页面状态机：新增→改框→改字→软删除全链路 API 验证通过。
- label_char CSV 往返导出：10/10 页与原文件**逐字节一致**（LF 行尾）。
- 全量导入（4000 页 regular + 217 万条标注）已完成；官方 label_char 存在
  完全重复行，导入时按页去重（见 commit 8970027）。

## M2 — 风格聚类（2026-08-19）

验收目标：复现 `参考资料/method2/new-dataset/styles_final.json`（358 风格）。

- 保真定位：该文件出自 `cluster_output/final/`，参数 = 阈值 0.25 + 无大簇上限
  + 单页归并半径 **0.5**（workbench 文档示例写的 0.8 会得到 350 风格）。
- 平台全链路复跑（DINO 重提取 → 491d 特征 → cosine+complete linkage →
  归并）：**358 风格 / 4000 页 / 8 单页，与 styles_final.json 集合级
  358/358 完全一致（IoU 1.0000）**，簇大小中位 5、最大 163。
- 泄漏守卫：297 个跨官方划分的簇已整体迁移到高优先级划分并锁定
  （guard 策略），迁移明细见聚类任务日志。

## M3 — 单字裁剪 / 字表 / 字模渲染 / FontDataset 导出（2026-08-19）

- 裁剪（§2.5 保真规则）：10 页小样本 5,637 张，仅 12 框丢弃（<10px/越界）；
  目检单字居中、纸底保留，≤56px 全部 fixed64 不重采样。
- 字表：940 字（min_instances=2 小样本口径），可训练 566，留出 23（5% 哈希留出）；
  中位框尺寸统计正常（63–67px 量级）。
- 字模渲染：SimSun→SimSun-ExtB 回退，566/566 全部渲染成功，0 失败。
- FontDataset 导出契约验证：用 MethodTwo-gaijing1 **原版** `dataset/font_dataset.py`
  （torch 2.13.0+cpu / torchvision 0.28.0+cpu）直接加载导出目录：
  train 543 样本抽 100、test_unknown_content 23 样本全部加载成功；
  test_unknown_style 空（小样本无 test 锁风格）且空 phase 目录已预建不报错。
- 修复：worker `JobContext.canceled()` 原用 `db.refresh(job)`，会丢弃 job 上未提交的
  log/progress（批量任务每秒 N 次取消检查时把进度日志清掉），改为标量查询。
