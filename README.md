# LayerTrace — Precision Image-to-Vector Skill

[简体中文](README.md) | [English](README_EN.md)

当前版本：**1.1.0**（[更新记录](CHANGELOG.md) · [Releases](https://github.com/neurosurgeon-lab/illustrator-precision-vectorizer/releases)）。

将参考图片精确拆解为可编辑的分层矢量图，支持 1:1 轮廓复刻与 SVG 导出。

这是一个通用 AI Agent Skill，配套脚本将已经确认的对象路径或独立蒙版组合为矢量文件包。对象识别与轮廓描摹由使用该 Skill 的绘制流程完成。

## V1.1：连续平滑线条的强制交付检查

人物、面部、手指、衣褶、器官和导线须逐部件对照原图，检查彩色图、纯线稿及至少 400% 放大图。原图连续的线不得有断裂、像素阶梯、碎线和非预期折点；原图的虚线、遮挡断开与尖角保留。

新建工程和模板默认要求严格审核。最终交付启用 `--require-line-quality-review` 或 manifest 的 `qa.require_line_quality_review: true`。首次导出保留 4 倍预览和 `26_Line_Quality_Report.json`；实际检查后填写逐对象审核，再导出到新目录。审核缺失、漏对象或原图/SVG 已变化时阻断正式 ZIP。旧命令行保持兼容，未启用时状态为 `not_reviewed`，不能宣称通过新标准。

[完整审核流程与格式](references/line-quality.md)。检查器核对审核覆盖和文件哈希，视觉检查负责识别断裂与锯齿；本更新不宣称自动消除所有缺陷。文字默认保留为校对后的真实文本。

## 默认按 Illustrator 编辑方式绘制

- 清晰轮廓、可改线宽的开放贝塞尔描边与独立填色；按部件建立命名图层/组，先核对一张复杂图的编辑结构，再批量处理。
- 导出新增纯线稿 `24_Editable_Linework.svg/png` 与 `25_Editability_Report.json`。声明必须可改线宽的导线，不能被闭合色块或隐藏参考线替代，即使像素误差很低。
- 原生 Illustrator 保存与回读：新增便携 JSX 与 macOS 执行入口，实际建立图层、保存彩色/线稿 AI、回读检查，并测试开放描边的线宽和锚点编辑。
- 保留 SAM2、本地权重、批处理、交互工作台、OCR 与审核补全。编辑结构与视觉误差分开报告，安装包不包含用户原图、示例数据或个人配置。

## 补全、OCR 与递归批处理

- 断裂和轮廓缺口候选：检查短间隙、碎片与小缺口，生成单独复核图，人工批准后才加入完整部件。
- Modal/Amodal 双模式：可见轮廓保持原样；隐藏补全按指定端点、折线或多边形限定在声明的遮挡物内，另交付推断报告与高亮复核图。
- 本地 OCR：识别文字、位置和置信度；人工校对并批准后，文字作为可编辑 `<text>` 出现在完整图、拆解图和 Amodal 图中。
- 批处理扩展：混合图片与工程、递归目录、OCR 与外置补全标注；保留已验证的 SAM2 配置、坐标修复、输入保护和 JSON/CSV 状态。

## 批处理与本地权重

- 文件夹批处理：已有分层工程批量导出，配套标注的原始图片批量调用 SAM2；每项独立输出，失败继续处理其他项，生成 JSON/CSV 汇总。
- 本地权重配置：单图命令、工作台和批处理共用用户模型设置；权重不复制到仓库，也不放入安装包。
- 修复真实 SAM2 像素坐标变换：原图 XY 提示使用 `normalize_coords=True`，命令行与工作台入口一致。
- 已使用真实 SAM2.1 base-plus 权重在 Apple MPS 上验证两图批处理和工作台候选预览，详见[验证记录](references/sam2-validation.json)。

## 本地集成工作台

- 本地交互工作台：选择对象、增补或擦除蒙版、编辑路径节点与 Bézier 手柄、调整颜色和遮挡顺序，支持保存、撤销和重做。
- SAM2 交互候选：用正点、负点或提示框生成候选蒙版，经人工选择和确认后才写回；模型需要单独配置。
- 局部与整图差异热图：重新渲染当前工程，比较 RGB 和 Alpha，定位需要精修的区域。
- 亚像素与变线宽：保留边界精修、Bézier 拟合和可编辑变宽填色轮廓。
- 遮挡排序：保留显式前后约束、循环检测、候选审查和图层重排。
- Illustrator 导入准备：生成逐对象 SVG、清单和 JSX 导入脚本，供桌面 Illustrator 创建原生图层。


## 保留的矢量化功能

- 可选的 Meta SAM2/SAM2.1 适配器：使用正点、负点和提示框分割独立对象，支持 Hugging Face 模型或本地 checkpoint。
- 保守结构后处理：检查提示点、ROI、独立实例与重叠，保留孔洞和可见断裂，不补画遮挡连接。
- 保留 LAB/GrabCut 实例分割和中心线提取：将已确认的细线蒙版转换为可改线宽的开放 SVG 描边。
- 加强矢量检查：测量对象真实边界，检查关键区域、RGB/Alpha 差异和实例数量；超出质量阈值时停止最终 ZIP 导出。

## 安装

需要 Python 3.10 或更高版本。将仓库克隆到个人技能目录：

```bash
git clone https://github.com/neurosurgeon-lab/illustrator-precision-vectorizer.git ~/.agents/skills/layertrace
cd ~/.agents/skills/layertrace
python3 -m pip install -r requirements.txt
```

CairoSVG 需要本地 Cairo 库。macOS 可以通过 `brew install cairo` 安装；如果 Python 无法找到该库，将 `DYLD_FALLBACK_LIBRARY_PATH` 指向 Cairo 的 `lib` 目录。其他系统请按 [CairoSVG 安装说明](https://cairosvg.org/documentation/)配置。

将文件夹放入客户端支持的 Skills 目录，刷新技能列表后使用。

也可从 [v1.1.0 Release](https://github.com/neurosurgeon-lab/illustrator-precision-vectorizer/releases/tag/v1.1.0) 下载 `layertrace-skill-v1.1.0.zip`。升级时先备份旧技能目录，再替换为新包。

## 客户端安装

同一个 Skill 文件夹可供支持 `SKILL.md` 的本地代理读取。客户端需要查看图片、读写文件和运行 Python；原生 AI 输出还需要桌面 Illustrator。

| 客户端 | 用户级目录 | 项目级目录 | 调用方式 |
| --- | --- | --- | --- |
| Codex | `~/.agents/skills/` | `.agents/skills/` | `$layertrace` |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` | `/layertrace` |
| Cursor | `~/.cursor/skills/` 或 `~/.agents/skills/` | `.cursor/skills/` 或 `.agents/skills/` | 在 Agent 中按名称请求使用 Skill |
| Gemini CLI | `~/.gemini/skills/` 或 `~/.agents/skills/` | `.gemini/skills/` 或 `.agents/skills/` | 在对话中按名称请求使用 Skill |
| 其他本地代理 | 客户端的 Skills 目录 | 客户端的 Skills 目录 | 请求读取本目录的 `SKILL.md` 并按流程执行 |

将完整的 `layertrace/` 文件夹放进对应目录，保留 `scripts/`、`references/`、`assets/` 与 `examples/`。这些位置依据 [Claude Code](https://code.claude.com/docs/en/skills)、[Cursor](https://cursor.com/docs/context/skills) 和 [Gemini CLI](https://geminicli.com/docs/cli/skills/) 的客户端文档；本次验证覆盖 Python 工具链与配置兼容，未在每个客户端实际运行端到端绘制。`agents/openai.yaml` 是可选的 Codex 界面配置，其他客户端使用 `SKILL.md`。纯聊天网页若不能运行本地脚本，只能辅助分析。

Claude Code 安装示例：

```bash
mkdir -p ~/.claude/skills
unzip layertrace-skill-v1.1.0.zip -d ~/.claude/skills
cd ~/.claude/skills/layertrace
python3 -m pip install -r requirements.txt
```

发布包不包含用户图片、重建文件或预生成示例数据。`examples/` 只提供通用合成测试生成脚本，按需在本地运行。

## 配置本地权重

安装官方 SAM2 和匹配的 PyTorch / torchvision 后，保存本地 checkpoint 选择：

```bash
python3 scripts/configure_sam2.py --checkpoint /path/sam2.1_hiera_base_plus.pt --config configs/sam2.1/sam2.1_hiera_b+.yaml --device auto
```

配置默认保存在 `~/.config/layertrace/sam2.json`；设置 `XDG_CONFIG_HOME` 时使用其对应目录。可用 `LAYERTRACE_CONFIG_HOME` 指定共享配置文件夹。已有 Codex 配置仍可从 `CODEX_HOME/skill-config/illustrator-precision-vectorizer/sam2.json`（默认 `~/.codex/`）读取；显式 `LAYERTRACE_CONFIG_HOME` 优先。权重保留在原位置，显式模型参数优先于保存设置。

## 文件夹批处理

批量导出已有工程，输入目录的直接子目录各包含一个 `manifest.json`：

```bash
python3 scripts/batch_vectorize.py --projects /path/projects --out /path/new-batch-export
```

批量处理配套标注的图片：

```bash
python3 scripts/batch_vectorize.py --images /path/images --annotations /path/annotations --out /path/new-batch-images
```

`figure.png` 对应 `figure.png.annotations.json`。缺少标注时保留初始化项目并记为 `needs_annotations`。每项独立保存工程、导出文件及日志，失败继续，汇总到 `batch_summary.json` / CSV。输出目录必须为空且位于输入目录外。详细格式及背景色声明见[批处理指南](references/batch.md)。

## 补全、OCR 与递归批处理

正常运行 `build_vector_package.py` 会生成独立的 Modal/Amodal 与补全审核文件。将逐对象设置放在工程内 `completion_annotations.json`，可先生成候选，再检查并批准指定几何。完整示例见[补全与 OCR 指南](references/completion-batch-ocr.md)。

OCR 为可选本地依赖，在 macOS 安装示例：

```bash
brew install tesseract
python3 -m pip install pytesseract
python3 scripts/text_recognition.py --project /path/project --languages eng
```

校对 `text_review.json` 后，对确认的条目填写 `corrected_text` 并设置 `approved: true`，再导出。已有校对文件不会覆盖；另存候选可用 `--output /path/new_review.json`，导出器读取工程内的 `text_review.json`。中文识别需另装 `chi_sim` 等语言数据，本发布真实 OCR 验证仅覆盖英文合成图。SVG 字体、字距和基线仍需目视检查，原文字路径应先移除或替换，避免重影。

混合文件夹与递归处理：

```bash
python3 scripts/batch_vectorize.py --input-dir /path/input --recursive --out /path/new-export --annotations-dir /path/annotations --completion-annotations-dir /path/completions --ocr --ocr-language eng
```

保留相对路径：`sub/figure.png` 对应 `sub/figure.png.annotations.json` 和 `sub/figure.png.completion.json`；工程 `sub/project` 对应 `sub/project.completion.json`。遇到工程根即停止扫描其内部蒙版或旧导出。批量 OCR 保留既有校对；新识别默认未批准，OCR 失败单独记录，不阻断几何导出。审核通过后可再批量导出输出目录里的工程副本。

## 启动本地工作台

在技能目录中创建合成示例并启动服务：

```bash
python3 examples/create_interactive_v25_demo.py --out /path/new-studio-demo
python3 scripts/interactive_studio.py --project /path/new-studio-demo/project --no-browser
```

打开 <http://127.0.0.1:8765/>。编辑自己的项目时，将 `--project` 指向已有 `manifest.json` 和独立对象的工程目录。工作台只监听本机，读取已保存的模型设置或显式启动参数；模型在请求候选时才加载。本地 checkpoint 不触发权重下载。

## 在 AI 代理中使用

上传参考图，并输入：

```text
$layertrace
按原图描摹，保留每个部件的独立编辑能力，输出 SVG、编号拆解总览和文件包。
```

工作流程包括结构分析、对象分层、先线稿后填色、矢量组合，以及原图叠加与差异检查。已有可编辑矢量源文件时，优先保留和整理原路径。

## 直接使用脚本

需要 Python 3.10 或更高版本。先初始化项目：

```bash
python3 scripts/init_project.py --image /path/reference.png --out /path/project
```

在 `manifest.json` 中填写真实对象路径，或准备与原图同尺寸的独立对象蒙版，再导出到一个新的空目录：

```bash
python3 scripts/build_vector_package.py --project /path/project --out /path/output --require-line-quality-review
```

脚本支持手工 SVG 路径和独立 PNG 蒙版。蒙版会被转换为多边形轮廓；细致曲线可以使用手工 Bézier 路径。

基础 SVG 可以直接导入原路径并建立初始清单；不支持的复杂 SVG 特性会被拒绝：

```bash
python3 scripts/init_project.py --image /path/original.svg --out /path/svg_project
```

## 辅助分割与中心线

按原图真实像素坐标填写 [实例标注模板](assets/medical-instances.template.json)，另存为 `annotations.json`，再执行 LAB/GrabCut 辅助分割：

```bash
python3 scripts/medical_instance_segment.py --project /path/project --annotations /path/annotations.json
```

对已确认的神经或导线蒙版提取中心线。先检查报告和预览，通过后才加 `--write-manifest` 写入项目：

```bash
python3 scripts/centerline_trace.py --project /path/project --object-id nerve_01 --mode adaptive-bezier --min-iou 0.85
python3 scripts/centerline_trace.py --project /path/project --object-id nerve_01 --mode adaptive-bezier --min-iou 0.85 --write-manifest
```

## 可选 SAM2 集成

基础依赖不包含 SAM2 或模型权重。按 [Meta 官方安装说明](https://github.com/facebookresearch/sam2#installation)另装兼容的 PyTorch 和 SAM2。未配置模型时仍可使用 LAB/GrabCut 和手工路径流程。

使用 [SAM2 标注模板](assets/sam2-instances.template.json)填写正负点、`[x, y, width, height]` 提示框和对象类型。对于一个尚无图层的新项目，选择以下一种模型来源：

```bash
python3 scripts/sam2_medical_segment.py --project /path/project --annotations /path/annotations.json --hf-model facebook/sam2.1-hiera-tiny --device auto
```

或使用本地权重：

```bash
python3 scripts/sam2_medical_segment.py --project /path/project --annotations /path/annotations.json --checkpoint /path/sam2.1_hiera_tiny.pt --config configs/sam2.1/sam2.1_hiera_t.yaml --device cpu
```

Hugging Face 方式可能下载权重；本地方式需要已准备好的 checkpoint。输出包含独立蒙版、`sam2_previews/`、标注副本和 `sam2_segmentation_report.json`。检查结果后，再进行中心线提取和矢量导出。

SAM2 的预测 IoU 是模型估计分数。包内模拟测试不验证真实权重精度；对象的医学名称来自人工标注，该流程用于二维科研插画。部署与结构保护细节见 [SAM2 集成指南](references/sam2-medical-postprocessing.md)。

要在工作台中使用本地 SAM2 权重，启动时显式配置：

```bash
python3 scripts/interactive_studio.py --project /path/project --sam2-config configs/sam2.1/sam2.1_hiera_b+.yaml --sam2-checkpoint /path/sam2.1_hiera_base_plus.pt --sam2-device auto --no-browser
```

交互式 SAM2 只精修已有的独立 PNG 蒙版。先预览候选，再确认写回；编辑、撤销或重做后，旧候选失效。完整步骤见 [工作台指南](references/interactive-studio.md)。

## 可编辑线条与原生 AI

工程应先具备经检查的独立部件与线条。导线使用 `fill: none` 和实际 `stroke`，在 `qa.editable_stroke_object_ids` 声明对象 ID；可选 `qa.max_geometry_items_per_object` 约定当前部件的几何上限。颜色/轮廓追踪用于辅助，清晰贝塞尔和开放描边用于最终编辑结构。

先创建合成示例检查完整流程：

```bash
python3 examples/create_editable_v33_demo.py --out /path/new-demo
python3 scripts/build_vector_package.py --project /path/new-demo --out /path/new-export
python3 scripts/illustrator_native.py --svg /path/new-export/01_Full_Illustration.svg --out /path/new-native --run
```

`--run` 在 macOS 调用已安装的 Illustrator；省略它可生成便携导入目录，在其他平台的 Illustrator 中运行 `run_in_illustrator.jsx`。实际成功后才会有 `Native_Color.ai`、有描边时的 `Native_Linework.ai`、Illustrator 预览和 `*_verified.json`。准备目录本身不会生成 AI。

原生 AI 的保存、回读、描边和锚点编辑须在实际 Illustrator 中验证。像素精度与编辑结构分别记录，具体工程仍需检查。

## Illustrator 原生图层导入准备

完成 SVG 审核后，可以单独生成导入文件夹：

```bash
python3 scripts/illustrator_import.py --project /path/project --out /path/new-ai-import
```

工作台成功导出时也会生成 `18_Illustrator_Import/` 并加入 ZIP。该文件夹包含逐对象 SVG、导入清单和 `import_v30.jsx`。在桌面 Illustrator 中通过 **文件 → 脚本 → 其他脚本** 运行 JSX，再核查图层、坐标、颜色及保存结果。

Python 准备阶段生成导入包。只有 JSX 在 Illustrator 中实际执行并完成保存后，才可能得到原生 `.ai`；具体工程仍需检查。

## 输出文件

| 文件 | 内容 |
| --- | --- |
| `01_Full_Illustration.svg` | 按原图坐标组合的可编辑矢量图 |
| `02_Layer_Breakdown.svg` | 完整图与编号部件拆解总览 |
| `03_Full_Preview.png` | 完整图预览 |
| `04_Breakdown_Preview.png` | 拆解总览预览 |
| `05_Color_Palette.csv` | HEX 色号、用途及对象数量 |
| `06_Layer_Manifest.json` | 模块、图层、对象与路径来源 |
| `09_Overlay_Comparison.png` | 原图与重建图叠加对照 |
| `10_Difference_Map.png` | 差异定位图 |
| `11_Outline_Inspection.svg` | 最终矢量路径的线稿检查视图 |
| `12_Editable_Project.zip` | 使用 `--include-source-project` 时保存源图、蒙版、清单和来源记录 |
| `13_HiRes_Preview.png` | 使用 `--hires-scale 2` 等参数时生成放大预览 |
| `14_Variable_Width_Profiles.json` | 变线宽样本与来源信息（配置变线宽对象时） |
| `15_Occlusion_Review.png` | 遮挡分析预览（启用遮挡分析时） |
| `16_Occlusion_Stack.svg` | 遮挡排序与图层堆叠视图 |
| `17_Occlusion_Report.json` | 约束、候选与待审核遮挡关系 |
| `18_Illustrator_Import/` | 工作台导出的逐对象 SVG、清单与 JSX；不等同于 `.ai` |
| `18_Modal_Illustration.svg` | 可见组合 SVG 的精确副本 |
| `19_Amodal_Isolated_Objects.svg/png` | 独立部件与已批准的推断补全 |
| `20_Completion_Report.json` | 候选、批准状态、像素与拓扑报告 |
| `21_Completion_Review.png` | 补全位置提示 |
| `22_Unapproved_Completion_Candidates.svg/png` | 未批准候选复核图 |
| `23_Amodal_Approval_Review.svg/png` | 已批准推断高亮图 |
| `24_Editable_Linework.svg/png` | 保留可见描边的纯线稿 |
| `26_Line_Quality_Report.json` | 逐对象 4 倍线条视觉审核、文件哈希与阻断原因 |
| `25_Editability_Report.json` | 几何/开放描边数量、声明的编辑结构门禁与待审核项 |
| `ROI_XX_Comparison.png` | 配置关键区域时生成局部对照图 |
| `quality_report.json` | 文件检查、图像指标和待复核事项 |
| `08_All_Files.zip` | 汇总导出文件 |

SVG 包含真实路径和命名对象。Illustrator 导入后的原生图层需要在 Illustrator 中检查；`.ai` 文件仅在实际保存并验证后提供。内置脚本导出 SVG 文件包。

默认质量门禁失败时不生成最终 ZIP，仍保留诊断文件。`--allow-draft` 可导出明确标记失败的草稿。所有输出仍需人工检查，报告中的 `release_ready` 保持为 `false`。

`--include-source-project` 会把原始图片和标注等材料加入工程包；分享前请确认其中内容适合公开。

## 验证

```bash
python3 scripts/validate_skill.py
python3 examples/create_demo.py
python3 scripts/self_test.py
python3 scripts/regression_tests.py
python3 scripts/instance_centerline_tests.py
python3 scripts/precision_v23_tests.py
python3 scripts/occlusion_v24_tests.py
python3 scripts/interactive_v25_tests.py
python3 scripts/studio_v30_tests.py
python3 scripts/batch_tests.py
python3 scripts/v31_completion_batch_ocr_tests.py
python3 scripts/editable_v33_tests.py
python3 scripts/line_quality_tests.py
```

基础示例检查 12 个对象、5 个图层、4 个拆解模块，以及 SVG、PNG、调色板、清单、质量报告和 ZIP 导出。新增回归测试覆盖质量门禁、SVG 导入、实例分割和中心线。

安装 PyTorch 后，还可运行 SAM2 适配器模拟测试和合成示例；这些命令不下载或运行真实模型权重：

```bash
python3 scripts/sam2_integration_tests.py
python3 examples/create_sam2_adapter_demo.py --out /path/new_mock_demo
```

图像差异指标用于定位偏差，最终轮廓与结构仍需视觉核查。

开发者可使用 `node --check webui/app.js` 检查前端语法。回归覆盖批处理、坐标变换、候选保护、属性保存、撤销及 ROI 热图。本机真实权重测试为两个合成椭圆案例和工作台候选预览，不代表医学插画通用精度；具体工程的桌面 Illustrator 输出仍需实际保存并回读验证。

## 详细说明

- [线条编辑、结构门禁与原生 AI](references/editable-illustrator.md)
- [补全、OCR 与递归批处理](references/completion-batch-ocr.md)
- [Skill 指令](SKILL.md)
- [安装与 Manifest 协议](README_安装与使用.md)
- [路径描摹流程](references/trace-protocol.md)
- [实例分割与中心线](references/medical-segmentation-centerline.md)
- [SAM2 部署与结构后处理](references/sam2-medical-postprocessing.md)
- [集成工作台](references/interactive-studio.md)
- [批处理与模型配置](references/batch.md)
- [交互编辑与撤销](references/studio-editing.md)
- [亚像素与变线宽](references/precision.md)
- [遮挡约束与排序](references/occlusion.md)
- [Illustrator 与质量验收](references/quality-and-illustrator.md)
- [输出字段与交付协议](references/output-contract.md)
