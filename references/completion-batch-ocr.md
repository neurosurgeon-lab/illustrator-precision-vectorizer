# 断裂修复、Amodal 补全、文件夹批处理与 OCR

## 原则

`01_Full_Illustration.svg` 和 `18_Modal_Illustration.svg` 均按原图可见形态导出，不被补全引擎篡改。`19_Amodal_Isolated_Objects.svg` 展示已明确接受的完整独立部件。`22_Unapproved_Completion_Candidates.svg` 展示未被接受的推断，橙色纹理只是审核提示。`23_Amodal_Approval_Review.svg` 标注已经接受的推断部位。完整隐藏区域不能由单张图片证明，应标为推断，并经过人工同意。

不擅自补完神经解剖、电极接触点、肢体轮廓或生物力学结构。该功能不是扩散式图像修复，也不是无监督准确复原。

## 一、自动断裂检测和碎片修复候选

`scripts/amodal_completion.py` 使用 8 连通域分析，检测孤立组件，估算最近轮廓间隙，测试桥接路径是否触碰其他实例；对短距离碎片提供 `proposed_short_gap`。在间隙过大、碎片面积较大、其他实例挡路时保留 `needs_manual_review` 或 `blocked_other_object`。此外使用局部形态学闭运算检测微小内凹缺口，但仅作为 `proposed_contour_notch`，避免把真实鞋底槽、设备卡扣等直接抹掉。已审批 `approve_short_gaps`、`approve_notches` 才会出现在 Amodal 图中。

## 二、可编辑隐藏轮廓（Amodal）

支持三种明确标注的隐藏区域：

1. `occluded_endpoints`：已观测的两端点 + 已声明遮挡对象，沿直线生成被遮住的部分。
2. `hidden_guide`：用户指定的多节点引导折线，在遮挡范围内生成候选细线，例如弯曲导线。
3. `hidden_polygon`：用户在遮挡物内指定闭合区域，生成填色部件的隐藏区域提案。

三者互斥；所有批准字段必须是 JSON 布尔值（`true` / `false`），字符串会报错；`approve_hidden` 缺少相应证据时报错。所有新像素限制在已声明的遮挡对象范围，且只纳入 Amodal 独立部件，不改变 Modal。未经同意只出候选预览。

**示例 JSON**，放在 `<project>/completion_annotations.json`：

```json
{
  "objects": [
    {
      "id": "vagus_nerve",
      "occluder_ids": ["electrode_cuff"],
      "occluded_endpoints": [[120, 85], [155, 89]],
      "thickness": 4,
      "max_hidden_length": 65,
      "approve_hidden": false,
      "approve_short_gaps": false,
      "approve_notches": false
    }
  ]
}
```

完成原有 SVG 导出后执行：

```bash
python scripts/amodal_completion.py --project /path/project \
  --out /path/export --annotations /path/project/completion_annotations.json
```

或者直接运行 `build_vector_package.py`，会在原有流程中自动生成双模式与审核文件（即便尚未配置遮挡，也生成无推断的拆解基线）。导出器支持 `--allow-draft` 保留失败时的审查素材，但绝不把失败草稿标成验收通过。

## 三、文件夹批量处理

```bash
python scripts/batch_vectorize.py \
  --input-dir /path/input_images --out /path/batch_output \
  --annotations-dir /path/instance_annotations \
  --completion-annotations-dir /path/completion_annotations \
  --recursive --allow-draft
```

读取 PNG、JPG、JPEG、WEBP、BMP、TIF、TIFF、简单 SVG 与含 `manifest.json` 的既有项目目录。逐张单独创建工程与输出目录，单张失败记录 `failed`，不会影响下一张。没有实例标注的位图只初始化并标记 `needs_annotations`，**不虚构已完成语义分层或矢量化**。每张已具备可编辑语义对象的图像导出 ZIP、Amodal/Modal、拆解、QA。每项结束后更新 `batch_summary.csv/json`；准确区分 `success`、`draft`、`needs_annotations`、`failed`。

相对目录保持一致：`sub/figure.png` 使用实例标注目录下的 `sub/figure.png.annotations.json`，以及补全标注目录下的 `sub/figure.png.completion.json`；已有工程 `sub/project` 使用 `sub/project.completion.json`。没有补全侧文件时使用工程内既有配置或只生成候选基线。图片分割沿用真实 SAM2 与共享本地模型配置，不退回另一套自动分割逻辑。`--images`、`--projects` 入口继续可用；都可增加 `--recursive`。

递归扫描遇到工程根即停止，不把项目蒙版或旧导出再次识别为输入；输出目录必须为空并位于输入外。OCR 或外置补全需要写文件时，先复制已有工程到输出，原工程保持不变。批量 OCR 保留已有校对，失败记录在 `ocr_error`，不阻断几何导出；几何 `success` 不表示 OCR 已通过。完成校对后，可对输出中的工程副本再次批量导出到新目录。

注：对于视频、PDF 和 AI 源文件，请先用现有合适的工具导出支持的图像或 SVG，不能将不支持的格式偷偷转成黑盒位图处理。

## 四、文本识别和 SVG 可编辑文字图层

安装本地 Tesseract 命令行程序及所需语言包，并执行 `python -m pip install pytesseract`。示例：

```bash
python scripts/text_recognition.py --project /path/project --languages eng+chi_sim
```

首次执行会写入 `text_review.json`，记录每个词的内容、bbox、置信度、语言和来源哈希，同时生成 `text_review.png` 供复核。已有校对文件不被覆盖；需要另存时用 `--output /path/new_review.json`，预览与 JSON 同名。导出器仍读取项目内的 `text_review.json`。识别候选默认全部 `approved=false`，尤其是中文、医学缩写、数字、单位、p 值和复杂旋转字体，必须人工校对。在 JSON 中将正确结果填入 `corrected_text` 并将 `approved` 设置为 `true`，再运行原有导出命令。批准的文字以独立 `<g><text>...</text></g>` 写入 SVG/完整合成预览。其他未批准文本不自动插入。

**注意：** OCR 不能可靠还原精确字库、字重、字距或排版；文本 bbox 和基线是近似，需 Illustrator 人工检查字体。不要把原图中文字当作矢量路径和 OCR 新文字同时输出，造成重影；应选择以认可的文字层替换相关原对象。若模型没有安装，本步骤报错，但原有矢量流程仍可执行。`text_review.json` 原始审核记录默认不打包；已批准的文字会出现在 SVG、图层清单与质量报告中。审核记录可能含患者姓名等敏感文本，仅在用户显式选择 `--include-source-project` 时纳入源工程。

批量 OCR 需增加 `--ocr --ocr-language eng+chi_sim`；各项输出仍需逐张校对。当前真实 OCR 验证使用 Tesseract 5.5.4 和 pytesseract 0.3.13 的英文合成样例；中文语言数据与复杂医学字体尚未验证。引擎置信度不代表总体准确率。

## 五、新增交付文件

- `18_Modal_Illustration.svg`：原图可见组合 SVG 的精确副本
- `19_Amodal_Isolated_Objects.svg/png`：已批准的完整分部
- `20_Completion_Report.json`：检测结果、推断状态、变更像素、拓扑报告
- `21_Completion_Review.png`：补全的位置提示
- `22_Unapproved_Completion_Candidates.svg/png`：未批准候选图
- `23_Amodal_Approval_Review.svg/png`：批准的隐藏补全高亮复核图
- `18_inferred_<id>.png` / `22_proposal_<id>.png`：相应生成蒙版
- `batch_summary.csv/json`：批量项目汇总
- `text_review.json/png`：本地 OCR 校对记录（仅源工程保存）

## 六、验收

专项测试：`python scripts/v31_completion_batch_ocr_tests.py`。前代回归仍应执行 `self_test.py`、`regression_tests.py`、`instance_centerline_tests.py`、`sam2_integration_tests.py`、`precision_v23_tests.py`、`occlusion_v24_tests.py`、`interactive_v25_tests.py`、`studio_v30_tests.py`。

**能力边界：** 这是无损 Modal + 可审核 Amodal 的保守辅助系统。复杂鞋、人体肌肉轮廓、遮挡肢体、神经走行仍需要人确认补全几何。不能从结果推断隐藏部分在实际解剖上准确。当前 Illustrator JSX 导入器读取 manifest 中的几何对象；新增 OCR 文字和 Amodal 应通过相应 SVG 打开。真正的 AI 工程须在 Illustrator 中实际保存并验收。
