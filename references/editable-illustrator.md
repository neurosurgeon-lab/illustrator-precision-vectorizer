# 线条编辑与 Illustrator 原生验证

V1.1 最终交付须同时执行 [连续平滑线条验收](line-quality.md)，命令加 `--require-line-quality-review`。以下原生编辑验证不替代逐对象 400% 放大视觉核查。

默认绘制目标是可以在 Illustrator 中直接改线宽、改色、移动部件和调整贝塞尔锚点的矢量。先构建清晰轮廓和开放描边，再建立独立填色与必要阴影，最后对照原图检查比例、位置、连接和遮挡。

## 绘制与分层

导线和可见内部划线优先使用 `fill="none"`、`stroke` 与 `stroke_width`。封闭色块和设备外壳保持少量独立闭合路径；圆环、接触面、扣件与每根线分别命名。SAM2/蒙版先帮助确认区域，`centerline_trace.py` 或手工贝塞尔再负责线条。中心线提取不合格时保留检查报告并手动修正，避免将填色轮廓和隐藏 guide 交作可改线宽的导线。

脚本不会从任意原始图片自动辨认所有部件并生成简洁线稿。输入工程需先具备经检查的对象路径；批处理复用同一绘制与检查方法。复杂图先验证一张，再处理其余图。

## 声明编辑结构

```json
{
  "qa": {
    "editable_stroke_object_ids": ["lead_01", "lead_02"],
    "max_geometry_items_per_object": {"lead_01": 1, "lead_02": 1}
  }
}
```

`editable_stroke_object_ids` 是本图必须有可见开放描边的对象；隐藏辅助线、透明路径、闭合填色不能满足该要求。可选数量上限来自当前部件的编辑设计，没有全局统一的路径数量限制。渐变、多个描边或复杂形状需要的几何可按实际情况保留。

默认导出：

```bash
python3 scripts/build_vector_package.py --project /path/project --out /path/new-export --require-line-quality-review
```

新增 `24_Editable_Linework.svg/png` 与 `25_Editability_Report.json`，保留原有彩色组合、拆解、调色板、遮挡/OCR/补全输出及差异报告。纯线稿只保留原有可见描边，不会把每条色块边界再画成线，也不自动替填色对象发明轮廓。完全没有描边时，线稿可能为空，报告据实记录。

声明的导线缺少开放描边，或超过指定几何上限，会使总 `quality_gates_passed` 为 false，默认不生成正式 ZIP。`--allow-draft` 可保留失败草稿；像素失败和结构失败分别记录。没有声明导线约束时，`editing_contract_status` 为 `no_stroke_contract_declared`，数量报告不代表语义编辑审核通过。

## 原生 AI

从实际导出的 SVG 准备原生导入目录：

```bash
python3 scripts/illustrator_native.py --svg /path/new-export/01_Full_Illustration.svg --out /path/new-native
```

准备阶段生成 `Color.svg`、有可见线条时的 `Linework.svg`、`native_jobs.json` 和 `run_in_illustrator.jsx`，不生成 AI。整个目录可以移动到另一台电脑；在桌面 Illustrator 用 **File → Scripts → Other Script** 运行 JSX。

macOS 上已安装 Illustrator 时，可直接执行：

```bash
python3 scripts/illustrator_native.py --svg /path/new-export/01_Full_Illustration.svg --out /path/new-native --run
```

将顶层命名组转换为真实 Illustrator 图层，保留内部独立部件和原有叠放。实际执行后生成 `Native_Color.ai`、有线条时的 `Native_Linework.ai`、相应 Illustrator PNG 预览与 `*_verified.json`。检查：

1. 实际保存 AI 后关闭并回读。
2. 图层、路径、锚点、描边数量与画布保持一致。
3. 无光栅对象和外链置入对象。
4. 预期有开放描边时，实际改线宽并复原、移动锚点并复原。

没有开放描边的纯填色工程不会伪报描边测试通过。脚本拒绝覆盖现有结果，不修改用户已打开的输入/输出文档；失败时不把未验证的 AI 当作成功。一次执行的部分工作可能留作诊断，请用新目录重试。

工作台及 `illustrator_import.py` 保留 `import_v30.jsx` 兼容入口，内部改为同一验证器；逐对象 SVG 仍保留。导出到另一台电脑时应复制完整 `18_Illustrator_Import/`，包含其 `Native_Editable/` 子目录。

## 两类验收

编辑结构合格，不代表与原图逐像素一致；低像素误差也不能证明部件能合理编辑。报告同时保留这两类结果。颜色/阴影近似、淡线断点、交叉归属和部件分界仍要目视检查。公开包不包含用户原图、重建结果或示例数据；测试输入在本地生成。

## English quick guide

Build clear Bézier outlines, visible open strokes, and separate fills before optimizing image similarity. Annotate required wire IDs with `qa.editable_stroke_object_ids`; optional per-object geometry budgets describe the current drawing, not a universal path limit. Hidden guides and filled silhouettes cannot satisfy an open-stroke requirement.

The normal exporter adds `24_Editable_Linework.svg/png` and `25_Editability_Report.json`. Declared editing failures withhold the final ZIP unless a failed draft was explicitly requested. Pixel fidelity and editing structure retain separate results.

Use `illustrator_native.py --svg ... --out ...` to prepare a portable JSX directory. On macOS, add `--run` to execute an installed Illustrator. Actual execution creates native color/linework AI, reopens saved files, checks layer/path/anchor counts and canvas dimensions, and tests stroke-width and anchor editing when open strokes are expected. Preparation alone creates no AI. Inspect the verification JSON and Illustrator-rendered previews; geometry, shadows, and visual fidelity still need review.
