# 项目结构、Manifest 及文件交付协议

## 安装与最短调用

将完整 Skill 文件夹放入客户端支持的 Skills 目录。Codex、Claude Code、Cursor、Gemini CLI 的目录与调用方式见 [客户端安装](../README.md#客户端安装)。其他本地代理可直接读取 `SKILL.md`，并在本目录运行脚本。

**macOS/Linux 解压安装示例：**
```bash
mkdir -p ~/.agents/skills
unzip layertrace-skill-v1.1.0.zip -d ~/.agents/skills
```

执行以下命令前，先进入已解压的 Skill 文件夹（例如 `cd ~/.agents/skills/layertrace`），否则将 `scripts/...` 换成对应的绝对路径。

```
project/
├── source.png            # 来源图片（原始备份，禁止覆盖）
├── manifest.json         # 人工/代理确认的语义图层规范
└── masks/                # 与原图同尺寸的对象独立二值蒙版，按需提供
    ├── head.png
    └── ...
```

```
python scripts/init_project.py --image /path/input.png --out /path/project
# 填好真实 layer/object/path 或蒙版后
python scripts/build_vector_package.py --project /path/project --out /path/output --require-line-quality-review
```

`init_project` 仅建立项目及色彩检查基线，不会自动识别医学结构。需要实际对象描摹；运行完成后本工具才会导出最终成果。

## manifest.json 核心字段

- `schema_version`: "1.0"。
- `source_image`: 文件名（相对 project，例如 `source.png`）。
- `canvas`: `{ "width": 800, "height": 600 }`，必须与源图一致。
- `layers`: 从**后到前**排序的数组：`id`, `name_zh`, `name_en`, `objects`。
- `objects`: `id`, `name_zh`, `name_en`, `geometry`, `fill`, `stroke`, `stroke_width`, `opacity`, `bbox`（手工 SVG 路径时必填 `[x, y, width, height]`）。
- `geometry` 二选一：`{"type":"svg_path","d":"M..."}` 或 `{"type":"mask_png","file":"masks/xxx.png"}`。
- 可选 `stroke_linecap`, `stroke_linejoin`, `fill_rule`, `notes`, `inferred_hidden`。
- `modules`: 拆解总览里的模块，每项 `id`, `name_zh`, `layer_ids` 或 `object_ids`。省略时自动每层做一个卡片。
- `qa`: 可选 `unresolved_details`: 保留未复刻细节清单。`illustrator_native_verified` 默认 false，生成脚本不会创建 `.ai`。
- 以上字段对由蒙版得到的 object 也适用；`bbox` 可省略，由蒙版自动识别。

`fill`/`stroke` 采用 `#RRGGBB` 或 `none`。`opacity` 在 `[0,1]` 之间；此版本基于纯色路径和透明度，不实现自动识别复杂渐变/图片滤镜。需要渐变时请用真正的 SVG 编辑器处理并在 QA 中说明。

## 输出文件

| 文件 | 内容 |
|---|---|
| `01_Full_Illustration.svg` | 可编辑的真 SVG，逻辑层+独立对象 |
| `02_Layer_Breakdown.svg` | 完整+所有 modules 卡片 |
| `03_Full_Preview.png` | 完整组合 SVG 渲染 |
| `04_Breakdown_Preview.png` | 拆解总览 SVG 渲染 |
| `05_Color_Palette.csv` | HEX/用途/对象数 |
| `06_Layer_Manifest.json` | 源 manifest 副本及对象指标 |
| `quality_report.json` | 矢量/XML/路径/尺寸/颜色/质量指标、限制 |
| `09_Overlay_Comparison.png` | 与参考图对齐的 50% 叠加，可选 |
| `10_Difference_Map.png` | 放大像素差异热图，可选 |
| `08_All_Files.zip` | 实际生成的文件，不含不可验证 `.ai` |

若确有 Illustrator 且成功保存才另增 `07_Illustrator_File.ai`，并将其补进 ZIP。

## 外部依赖

推荐 Python 3.10+，`Pillow`, `numpy`, `opencv-python`, `cairosvg`, `lxml`, `PyYAML`（校验 skill 时），以及可选的 `inkscape`。示例安装命令：

```
python -m pip install pillow numpy opencv-python cairosvg lxml pyyaml
```

Adobe Image Trace、Adobe 连接器等只可作为已有工具存在时的可选矢量化辅助，不是本 Skill 的强制依赖；使用云端上传工具前需检查隐私、机构合规和用户授权，不上传含患者敏感信息的原图。

**注意：**每次导出选择空的 `--out` 目录，以免把上次的文件误打包。正式 `.ai` 导出需人工在 Illustrator 中创建验证，并在完成后自行加入 ZIP；导出脚本永不伪造 `.ai`。

## 增补：强制精度复核与可编辑性

### v2 命令

```bash
python scripts/build_vector_package.py --project myproject --out export --require-line-quality-review
python scripts/build_vector_package.py --project myproject --out export_bezier --trace-mode adaptive-bezier --require-line-quality-review
python scripts/build_vector_package.py --project myproject --out export_draft --allow-draft
```

- `svg_path` 的 `bbox` **不再必填**，手填值仅用于和实际渲染出的可见 bbox 比对，拆解布局完全使用自动测量值；有明显偏差会写入 `declared_bbox_mismatches`，防止拆解部件移动/消失。
- `mask_png` 在 `--trace-mode adaptive-bezier` 时尝试三次曲线，并逐蒙版记录 `trace_diagnostics`。失败会回退到保真折线，不强制平滑。
- 支持简单 SVG 源图初始化与复用原路径，源 SVG 备份在 `original_source.svg`，源图对应 `source.png` 是供像素对照的渲染基准。
- 新增 `11_Outline_Inspection.svg` 作为线稿检查图，不是原始作图流程的证明；`06_Layer_Manifest.json` 包含 `original_project_manifest`，有助复现原始路径/蒙版来源。
- 新增 `qa.required_object_ids`（对象必须存在）、`qa.expected_object_counts_by_prefix`（按前缀精确计数）和 `qa.key_regions`（关键局部 `[x,y,w,h]` 色彩/Alpha 比较）。
- 报告包含 `fidelity_status`, `fidelity_failures`, `key_region_results`, `declared_bbox_mismatches`, `release_ready` 等状态。正式包生成也不意味着 Illustrator 原生 AI 已经检查完成。
- ROI 分区可附带 `ROI_XX_Comparison.png`；这些文件也进入最终 ZIP。

### 可调整的 QA 阈值（谨慎使用）

`qa.fidelity_thresholds` 可覆盖默认：`max_mae_rgb:12`, `max_mae_alpha:12`, `max_changed_pixel_fraction:0.12`, `max_alpha_changed_fraction:0.08`, `max_edge_mismatch_fraction:0.24`。阈值只是初筛值，不代表严肃的医学结构等价证明。不得为了让不合格图通过而任意放宽阈值。局部 ROI 的默认阈值更严格，详细示例见 `references/trace-protocol.md`。

**依然不支持**：照片全自动语义对象拆解、精确恢复被遮挡路径、任意高级 SVG 表现、任意 AI/EPS/PDF 的完备解析及无 Illustrator 的原生 AI 文件保存。源 SVG 的路径保留仅限受支持的基础矢量形状与属性。

可选 `--hires-scale 2` 输出 `13_HiRes_Preview.png`（仅高清栅格预览，不代表矢量更精准）；可选 `--include-source-project` 生成 `12_Editable_Project.zip`（源图、原始 Manifest 和蒙版；含潜在敏感资料，须主动开启）。


## 实例分割与中心线补充协议

- 推荐安装：`python -m pip install -r requirements.txt`（新增 `scikit-image`, `networkx`）。
- `python scripts/medical_instance_segment.py --project project --annotations annotations.json` 读取经用户确认的实例点和 ROI；生成 `masks/xxx.png`、`instance_annotations.json`、`instance_segmentation_report.json` 与可编辑图层规格。
- `python scripts/centerline_trace.py --project project --object-id lead_01 --mode adaptive-bezier --min-iou 0.85` 默认为检查模式；人工确认后才加 `--write-manifest`。
- `quality_report.json` 的 `guided_segmentation_summary` 和 `centerline_trace_summaries` 保留算法来源与局部质量；勾选 `--include-source-project` 后中心线报告与原有蒙版均收录于可编辑工程 ZIP。
- `scripts/instance_centerline_tests.py` 为新增的可复现回归测试；`examples/create_medical_pipeline_demo.py --out demo` 生成非临床简化图，演示全过程。
- 实例的医学语义由人工标注提供，不属于训练过的自动解剖分割模型。详细限制与错误处理：`references/medical-segmentation-centerline.md`。


## 增量交付

若用户在交互工作台成功通过导出 QA，会在 export 目录生成 `18_Illustrator_Import/`，包含逐对象独立 SVG、`illustrator_import_manifest.json`、`import_v30.jsx` 和 `README_IMPORT.txt`，同时加入 `08_All_Files.zip`。它是**原生 Layer 的 Illustrator 待运行导入包**，不是 `.ai`。只有真正的桌面 Illustrator 脚本保存/校验 `.ai` 后才可额外交付。SAM2 工作台采纳记录 `sam2_studio_audit.jsonl` 留在本地项目目录供追溯，不会作为证明解剖正确的证据。详情 `references/interactive-studio.md`。


## 补全与文字交付

`18_Modal_Illustration.svg` 精确复制可见组合图；`19_Amodal_Isolated_Objects.svg/png` 仅纳入明确批准的补全；`20_Completion_Report.json`、`21_Completion_Review.png`、`22_Unapproved_Completion_Candidates.svg/png` 与 `23_Amodal_Approval_Review.svg/png` 分别记录提案和批准结果。批准的 OCR 为完整图、拆解图及 Amodal 图中的真实 `<text>`，也记录在图层清单和质量报告的 `reviewed_editable_text` 字段中。原始审核文件只在显式 `--include-source-project` 时加入源工程 ZIP。已有 JSX 仍按 manifest 几何对象生成导入包，新增文字和 Amodal 使用相应 SVG。


## 线条编辑交付

V1.1 新增 `26_Line_Quality_Report.json`：严格模式记录原图和 SVG 哈希、待审核对象、实际审核内容和失败原因；审核文件位于工程目录的 `line_quality_review.json`。最终交付启用 `--require-line-quality-review`，失败保留诊断和 4 倍预览并阻断正式 ZIP。格式见 [line-quality.md](line-quality.md)。

默认增加 `24_Editable_Linework.svg/png` 和 `25_Editability_Report.json`。`qa.editable_stroke_object_ids` 声明可见开放描边要求；可选 `qa.max_geometry_items_per_object` 定义当前部件的几何预算。编辑结构失败与像素失败分别记录，总门禁同时考虑两者。未声明约束不等于已完成语义编辑审核。

`scripts/illustrator_native.py` 从真实 SVG 准备便携目录；实际运行 Illustrator 后，才能生成并核验 `Native_Color.ai`、可用时的 `Native_Linework.ai`、AI 回读预览与验证 JSON。原生可编辑性和视觉复刻精度分别验收，参见 `references/editable-illustrator.md`。
