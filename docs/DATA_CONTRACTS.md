# 数据契约（DATA CONTRACTS）

平台的数据库是唯一真值；以下目录树一律由导出任务生成，禁止手工编辑。

## 方法一：HDR28K（修复训练数据）

每个训练样本 = 4 张对齐的 512×512 图像，按损伤类型分顶层目录：

```
HDR28K/
  {degradation_type}/          # character_missing | paper_damage | ink_erosion
    {train|test}/
      original_images/         # 干净真值 x_gt
      degraded_images/         # 退化输入 x_d（由 original + mask 合成）
      char_mask_images/        # 损伤区域二值 mask m
      content_images/          # 字符内容图 c（标准字体按标注位置渲染）
```

- 同一样本在四个子目录中**文件名相同**。
- 损伤类型占比参考：纸张破损 50% / 文字缺失 25% / 墨迹侵蚀 25%。
- mask 与 content 在**推理阶段也需要**，因此平台支持对无配对的受损页面做同样的标注。

## 方法二：FontDataset（字形生成训练数据）

```
{font_root}/
  {phase}/                     # train | test_unknown_content | test_unknown_style
    ContentImage/{content}.png           # 标准字体渲染的内容图（.png 后缀硬编码）
    TargetImage/{style}/{style}+{content}.png
```

硬约束（来自 `font_dataset.py`）：
- 文件名以 `+` 切分 style/content —— **导出文件名统一编码**：content 段为 `u{码点hex}`（如 `book_0007+u53EF.png`），训练侧 `font_dataset.py` 加 5 行解码补丁（`chr(int(s[1:], 16))`）。
- 每个 style 目录**至少 2 张图**。
- 图像 64×64、RGB PNG。
- 划分按簇（style）原子执行：test_unknown_style = 整簇留出；test_unknown_content = 同风格、留出约 50 个高频字（训练零实例）。

## 单字裁剪保真规则（适配方案 §2.5）

- 框 <10px / 越界 / 退化框：丢弃
- 框 ≤56px：以框中心取固定 64×64 窗口，**不重采样**；越界部分用邻域纸色中值填充
- 框 >56px：方形窗口 + 10% padding，**只缩不放**；记录缩放比
- 灰度 → 3 通道 PNG

## 字表规则（适配方案 §2.4/2.6）

- 保留实例数 ≥20 的字（约 4,667 个）
- 剔除符号与非法字符（`|`、`●`、`○`、`※`、`■`、`□`、`‧` 等）
- 逐字渲染可验性检查：思源黑体/SimSun-ExtB → 花园明朝（非 BMP 兜底）；全部失败则移出字表并记录
- ContentImage 按该字原生框中位尺寸渲染（非撑满画布）
