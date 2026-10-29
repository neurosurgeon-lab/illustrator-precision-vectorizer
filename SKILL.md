---
name: layertrace
description: 将参考图片精确拆解为可编辑的分层矢量图，支持 1:1 轮廓复刻与 SVG 导出。
metadata:
  version: "1.1.0"
---

# LayerTrace — Precision Image-to-Vector Skill

## 发布范围

公开仓库和安装包仅包含通用代码、说明与配置模板；不发布用户原图、重建结果、示例数据、原始对话或需求记录、本机绝对路径、个人配置和密钥。测试输入由通用脚本在本地生成。

## 目标与非协商约束

将**用户提供的原始图像**还原为可审计、可单独编辑、可在 Adobe Illustrator 中继续处理的矢量对象；同时交付编号的 exploded-view 拆解总览图、组合预览图及文件包。

**忠实度优先**：不改变画布比例、几何轮廓、颜色、线宽、对象数量、人体姿态、器官结构、神经走向、装置连接和前后遮挡。未经明确授权，不添加、删除、移动、美化或重设计。保留原始文件，不覆盖。

**真实矢量优先**：最终可编辑 SVG 必须有 `<path>`/`<circle>`/`<rect>` 等真正矢量几何及单独对象；禁止用整张嵌入位图、base64 `<image>`、光栅化主体或仅更换扩展名冒充矢量。可以提供原图叠加校验图，但不可把它伪装成最终矢量内容。

**能力如实披露**：仅靠自动描摹不能确保像素级一致，也不能自动恢复被遮挡的真实结构。SVG 分组不等同于已验证的 Illustrator 原生图层；只有在 Illustrator 中打开并实测后才宣称图层完整保留。无可用 Illustrator 时不制造假 `.ai`。不因追求数量而牺牲可编辑性。

## 客户端兼容

本 Skill 不依赖特定 AI 客户端；支持读取本目录文件、查看图片和执行 Python 的代理可使用同一流程。Codex、Claude Code、Cursor、Gemini CLI 的目录和调用方式见 `README.md` 的客户端安装表。在当前 Skill 根目录运行相对脚本路径；不将客户端对话或用户工程纳入发布包。

## 适用任务

按原图描摹、1:1 轮廓复刻、逐部件分层、SVG 导出、Illustrator 可编辑线条、批量矢量化和拆解总览均使用本流程。不用于重新设计或凭空补全遮挡结构。

## 激活、输入与工作模式

- 默认输入：当前用户上传的一张**参考图**。若同轮提供多张，则识别主图与色彩/结构对照图；不自作主张拼合或互换参考角色。
- 优先源文件顺序：AI/SVG/EPS/PDF（若可获取真实矢量内容）→ 无损 PNG/TIFF → JPEG/截图。已有真实矢量时**直接保留/重排源路径**，不要无谓重新栅格化。
- 默认模式：`faithful`（原图精确描摹）；仅在用户明确提出更改时采用 `edit`（只修改指定部件）；当用户仅要求分析时使用 `audit`（不虚构已制作文件）。
- 来源为科研插画、线描、纯色图时，按本流程完整执行。照片、复杂纹理和半透明 3D 效果不能直接保证逐元素矢量化；采用分区混合处理并在交付时明确哪些部分仍是近似路径，**不可隐瞒**。

## V1.1 强制交付要求：连续、平滑、逐部件放大验收

- 人物、面部、手指、衣褶、器官和导线均不得出现原图没有的断裂、锯齿、碎线、折点或错接。原图中的虚线、遮挡断开和真实尖角须保留，禁止为了“连续”跨越遮挡或改变结构。
- 自动提取的像素边界、骨架分支和多边形只作中间稿；即使已转为 `<path>`、全图像素门禁通过或能修改锚点，也不能直接当最终线条。主要曲线需整理为连续贝塞尔；光滑接头核对切线，重叠填色与轮廓须贴合。拟合回退折线时必须继续手工修复，不能默默交付。
- 必须对照原图逐部件检查彩色图、纯线稿和至少 400% 放大图，检查外轮廓、内部线、线头、接缝和遮挡。发现问题则修复并重新检查。文字默认使用校对后的真实文本，核对字体、位置和字重；用户要求转曲时才交付文字轮廓。
- 所有最终导出必须启用 `--require-line-quality-review`，或在 manifest 中设置 `qa.require_line_quality_review: true`；新建工程和模板已开启。缺少逐对象审核、存在缺陷或 SVG/原图改变导致记录失效时，禁止最终 ZIP 和“已完成”声明。自定义重建脚本也必须调用同一检查器并遵守失败阻断。
- 具体审核文件和两次导出流程见 `references/line-quality.md`，交付前必须读取。审核必须基于实际看到的放大图，禁止批量自动填 `true`；这项日常视觉检查由执行任务的代理完成，无需另向用户索取批准。`--allow-draft` 仅在用户明确要求草稿时使用。

## 默认交付：可编辑线条与独立填色

用户要在 Illustrator 中编辑时，先明确每条线和每个部件如何被选择、改线宽、改色、移动和调整锚点，再核对原图位置与视觉差异。按以下结构制作：

- 导线、神经示意线、外轮廓与内部划线用可见的开放贝塞尔 `path` + `stroke`；导线粗细应能直接在“描边”面板修改。闭合器官、布面、设备外壳用少量闭合形状，填色与轮廓可同对象或分开命名。
- 每个实际部件保留命名图层/组，锚点和阴影路径只保留表达形状所需的数量。蒙版和 SAM2 用于确认可见区域，再转为清晰轮廓；参考 `references/medical-segmentation-centerline.md` 提取中心线或手工校正贝塞尔。
- 批量前先用一张复杂图验证线条结构，查看完整图、纯线稿及部件拆解；可在实际 Illustrator 中测试时，完成改线宽、改锚点及保存回读，再沿同一结构处理其余图。
- 颜色碎片追踪只能作为明确说明的视觉草稿，不能作为默认的 Illustrator 编辑交付。降低 RGB 误差、出现 `<path>`、分组数量增多或保留隐藏中心线，都不能替代可见开放描边和独立部件。
- 在 manifest 的 `qa.editable_stroke_object_ids` 列出必须保留开放描边的对象。可用 `qa.max_geometry_items_per_object` 按当前部件约定几何数量上限；不要把某个示例的数量当作所有图的统一阈值。导出器分别记录像素门禁和编辑结构门禁，声明的导线变成闭合色块或只有隐藏 guide 时阻断正式 ZIP；明确的 `--allow-draft` 保留失败状态。
- 默认导出彩色组合 SVG 及 `24_Editable_Linework.svg/png`、`25_Editability_Report.json`。纯线稿移除无描边填色与隐藏辅助线，保留可见描边；填色边界与线条分开时，提醒用户改外形应一起选中。
- 需要 `.ai` 时检查已有 Illustrator 工具或本机应用。使用 `scripts/illustrator_native.py --svg /path/export/01_Full_Illustration.svg --out /path/new-native --run` 在 macOS 执行本机 Illustrator；其他平台可先生成目录，再在 Illustrator 运行其 JSX。读取 `Color_verified.json` / `Linework_verified.json`：只有实际保存并回读成功才能称原生 AI 已验证。描边/锚点编辑测试与视觉复刻精度分别说明。
- 对原图的明暗、字体或密集交叉只能近似时，保留真实差异报告；不要为追求少量锚点或通过像素阈值而隐去限制、补画隐藏几何或改验收标准。

命令、manifest 字段、原生验证及失败处理见 `references/editable-illustrator.md`。


## 工作流程（严格顺序）

### 0. 锁定原图与建立审计基线

1. 读取宽高、格式、透明通道、ICC/色彩空间、源文件哈希；保留源图不变。
2. `python /path/to/layertrace/scripts/init_project.py --image /path/reference.png --out /path/project` 位图仅初始化不自动语义拆解；基础 SVG 输入可直接解析原路径并生成初始 manifest，复杂 SVG/AI/EPS/PDF 如无法无损解析则明确拒绝或依赖 Illustrator 专用工具，不虚构转换。
3. 记录坐标约定：左上角 `(0,0)`，与原图相同的 `viewBox="0 0 W H"`；任何输出的完整组合图应按此坐标复合。
4. 如果是多图同色系项目，尽量复用来源中的实际 HEX 值。原图本身有色彩管理偏差时保留源 ICC 信息，颜色取样标记色差风险。

### 1. **先结构分析与分层，再动笔**

- 逐区域从背到前识别：背景 → 主体形状 → 独立填色区域 → 光影 → 轮廓 → 解剖/连接细节 → 装置/电极/固定件/导线（仅为示例，实际遮挡关系优先）。
- **部件粒度以“希望独立选择/隐藏/改色”为准**：每个电极、圆环、连接点、可移动部件、每根导线单独命名，不以一个大路径吞并。
- 区分 **module**（拆解总览卡片的逻辑模块）、**layer**（SVG/Illustrator 图层）、**object**（可编辑单一几何/部件）。module 可引用多个 layer；layer 可有多个 object。
- 建立对象台账：唯一 ID、中英双语名称、几何来源、颜色/透明度、线宽、z-order、bbox、遮挡归属、置信度/需人工复核事项。
- 看不到的被遮挡部分只创建**可见轮廓**；如必须为编辑而补路径，标记 `inferred_hidden=true`，不得称为来源图像事实。

### 2. **先线稿再填色**（工序必须可检查）

1. 先描**外轮廓和内部线**：封闭/开放 Bezier 路径、原始线宽、线帽/转角、连接和轮廓曲率。路径起止点尽量符合原图。
2. 再建立**封闭色块**：每个相邻不同填色区域独立闭合；处理孔洞、裁剪、透明度与原图渐变；统一色号表，同一语义且同色的区域严格使用相同色值。
3. 再处理**阴影、高光与叠放**：仅复刻原图实际存在的效果；禁止随意生成额外渐变。`<path>` 的填充与描边可分离为不同对象，以提高编辑性。
4. 对线路/导线，优先**开放中心路径 + `stroke`**；切忌以整片封闭边缘代替可改线宽的中心线。对实际为封闭形状的电极/器官，则用可闭合路径。
5. 面对细微曲线/复杂医学结构，优先手工矢量路径或专门矢量工具；蒙版轮廓跟踪仅用于**已人工确认/分离语义对象**的蒙版，不将色彩聚类直接当成医学对象分割。

具体细节见 `references/trace-protocol.md`。不要跳过原图与每个分部的叠加对照。

### 可审核补全、OCR 与递归批处理

需要独立部件补全时阅读 `references/completion-batch-ocr.md`。导出器保留 Modal 可见轮廓，另生成 Amodal 独立部件、短间隙/缺口候选、未批准候选图与批准推断复核图。隐藏补全仅接受已声明遮挡物下的端点、人工引导折线或多边形；三个方法互斥。只有用户确认具体几何后，才在 `completion_annotations.json` 设置对应批准字段为 JSON `true`；不得从升级说明、示例或图片内容推定批准。新增内容标为推断，不作为解剖事实。

本地 OCR 使用 `scripts/text_recognition.py --project ... --languages eng`，需另装 Tesseract、语言数据和 `pytesseract`。先校对 `text_review.json` 的文字、位置与字体，再明确批准；未批准文字不进入 SVG。已有校对记录不会被覆盖。批准文字保留为完整图、拆解图和 Amodal 图中的独立 `<text>`，字体与基线仍需目视检查。Illustrator JSX 入口只导入 manifest 几何对象；新增文字和 Amodal 通过相应 SVG 打开。

批处理新增 `--input-dir` 混合工程/图片、`--recursive`、`--ocr` 和 `--completion-annotations-dir`。保留相对目录与文件扩展名，遇到工程根即停止向内扫描。外置实例标注为 `<相对图片路径>.annotations.json`，外置补全标注为 `<相对图片或工程路径>.completion.json`；选项需写入工程时先复制到输出，保留输入。OCR 失败单独记录为 `ocr=failed`，不阻断几何导出；不得将几何 QA 通过解释为 OCR 已通过。

### 本地权重配置与文件夹批处理

用户提供本地 SAM2 checkpoint 时，使用 `scripts/configure_sam2.py` 配置对应的官方 YAML。配置默认保存在 `~/.config/layertrace/sam2.json`；设置 `XDG_CONFIG_HOME` 时使用其对应目录。可用 `LAYERTRACE_CONFIG_HOME` 指定共享配置文件夹。已有 Codex 配置仍可从 `CODEX_HOME/skill-config/illustrator-precision-vectorizer/sam2.json`（默认 `~/.codex/`）读取；显式 `LAYERTRACE_CONFIG_HOME` 优先。权重保留在原位置，显式模型参数优先于保存设置。不移动、不发布权重，不将本机路径写入仓库。命令行分割、工作台和批处理会读取已保存的设置，显式模型参数可以覆盖它们。

```bash
python scripts/configure_sam2.py --checkpoint /path/sam2.1_hiera_base_plus.pt --config configs/sam2.1/sam2.1_hiera_b+.yaml --device auto
python scripts/batch_vectorize.py --projects /path/projects --out /path/new-batch-output
python scripts/batch_vectorize.py --images /path/images --annotations /path/annotations --out /path/new-batch-images
```

- `--projects` 逐个导出直接子目录中已有 `manifest.json` 的工程；不修改输入工程。
- `--images` 逐图初始化项目。位图需要同名完整文件名对应的标注，例如 `figure.png.annotations.json`；提示坐标与语义标签应按该图确认。可在标注顶层用 `background` 指定已确认的背景色。简单 SVG 可直接复用路径。
- 缺少标注时保留初始化项目并汇总为 `needs_annotations`；禁止把它称为已完成矢量化。批处理不会凭空生成所有医学语义标注。
- 每张图独立输出工程、导出包和日志，单项失败继续处理其他项；汇总为 `batch_summary.json` 和 CSV。区分 `success`、`draft`、`needs_annotations`、`failed`；失败或待标注时命令返回非零状态。`--allow-draft` 只用于明确允许的失败草稿。
- 输出目录必须为空且位于输入目录外，避免覆盖或混入源文件。串行逐图加载模型，优先稳定和内存隔离。
- 原图像素 XY 提示必须传给官方预测器的 `normalize_coords=True`；由官方 API 转为编码器坐标。不要将该参数设为 False。

使用与标注格式见 `references/batch.md`；回归检查为 `scripts/batch_tests.py`。本机真实权重验证记录见 `references/sam2-validation.json`，仅证明所列合成图和运行环境的链路，不代表医学插画通用精度。

### 本地集成工作台：SAM2 可提示分割 + 差异热图 + Illustrator 导入工程

保留真实 PNG/Manifest 写回、撤销/重做、Bézier 编辑与遮挡层级功能。在此基础上新增：

1. **SAM2 交互式候选**：既有 mask_png 对象选中后，在画布上放正/负点、框选，选择神经/导线/电极/设备等 profile；在后端真实模型（仅安装及显式启用时）输出多候选、置信分数及结构保护报告，用户选择候选并确认才更改独立蒙版。未确认则项目不变，禁止自动补画隐藏解剖。模型的预测分数不代表真实分割准确率。
2. **像素级局部误差热图**：点击按钮对当前工程重新渲染，按原图/矢量 RGB 与 alpha 差异显示热区，支持整图和当前对象 ROI。仅帮助定位偏差，不代表医学解剖审核。
3. **Illustrator 导入准备**：SVG 正式导出后生成 `18_Illustrator_Import/` 和逐对象 SVG、原生图层导入 JSX。此时**未生成真正 AI**；需在用户本地 Illustrator 中运行 `import_v30.jsx`，检查原生图层/位置/色号，成功后才可交付真实 `.ai`。

```bash
python -m pip install -r requirements.txt
python examples/create_interactive_v25_demo.py --out /tmp/studio30
python scripts/interactive_studio.py --project /tmp/studio30/project --no-browser
# 打开 http://127.0.0.1:8765/

# 有官方 SAM2 及本地权重时，明确启用（默认不下载）
python scripts/interactive_studio.py --project /path/project \
  --sam2-config configs/sam2.1/sam2.1_hiera_b+.yaml \
  --sam2-checkpoint /path/sam2.1_hiera_base_plus.pt --sam2-device auto

# 或先为任意已完成的项目准备桌面 AI 导入包
python scripts/illustrator_import.py --project /path/project --out /path/empty_ai_import
```

**验证范围**：API + FakePredictor + SVG + Python 导出、真实 SAM2 权重和原生 AI 分别验收；合成图原生 AI 验证见 `references/native-validation.json`。将 `18_Illustrator_Import/` 包误认为原生 AI 属于错误交付。详细说明、限制及测试见 `references/interactive-studio.md`。

### 可视化交互精修工作台（新增）

对已经有真实独立实例蒙版/路径的项目，可启动 **本地浏览器精修工作台**，不再需要直接手动修改 JSON 才能修复个别对象。此工具负责可验证的本地**编辑**，而不是对任意参考图的全自动语义识别。

```bash
python -m pip install -r requirements.txt
python examples/create_interactive_v25_demo.py --out /tmp/medical_studio
python scripts/interactive_studio.py --project /tmp/medical_studio/project --port 8765
# 本地浏览器 http://127.0.0.1:8765/
# 对真实工程则使用 --project /path/to/project
```

界面支持左侧独立对象选择/显隐，中间原图-矢量-叠加-所选蒙版切换以及缩放，右侧蒙版增补/擦除、M/L/C/Q/Z 绝对坐标路径节点及 Bézier 手柄拖动、颜色/描边修改、遮挡前后约束、撤销/重做、一键调用现有 SVG/拆解/质量报告导出器。每次保存写入实际 PNG 蒙版或 `manifest.json`，保留 `.v25_history/` 快照；原始参考图不可修改。蒙版连通分量或孔洞变化默认阻断，只有用户明确确认后才允许，仍需人工检查神经解剖。遮挡 DAG 形成环或明显视觉不一致的项目不会被认定质量合格。

**限制：** 需要先通过分割工具或手工创建语义对象；不能从单张未知医学插画自动建立所有部件。节点拖动不支持 SVG 圆弧 A/H/V 等命令（原路径保留，允许通过 SVG path 源码框手工修改）。未配置可选 SAM2 功能时不运行模型权重；工作台不直接生成真实 `.ai`，也不补画遮挡下的医学结构。软件仅绑定本机端口，不宜向互联网开放。详细操作、目录结构及测试见 `references/studio-editing.md`。测试命令：`python scripts/interactive_v25_tests.py`。

### 亚像素轮廓与变线宽重建（可选增强）

在**完成实例分割、核对输入蒙版后**再使用；这两个步骤不能替代语义分割，也不会恢复神经解剖或遮挡结构。

**亚像素边界与 Bézier**：`scripts/subpixel_bezier.py` 只对原图中**足够平涂、前背景颜色可分**或**有可信 alpha 边界**的独立色块启用。读取原始像素的抗锯齿混合信息生成局部覆盖率，在 2–4× 网格上拟合开放/闭合轮廓，并比较原图蒙版 IoU、放大边界误差、连通分量和孔洞数量；要求全部满足后才允许写回。若颜色对比不足、图像为照片/复杂渐变、孔洞消失或轮廓误差过大，**必须回退原 mask_png/手动描摹**。像素采样估计并非真实连续边界的精确真值。

```bash
python scripts/subpixel_bezier.py --project /path/project --object-id body_outline --scale 3
# 审核 subpixel_body_outline_report.json 和 3x 预览后才写回：
python scripts/subpixel_bezier.py --project /path/project --object-id body_outline --scale 3 --write-manifest
```

**神经、导线变线宽**：`scripts/variable_width.py` 从已确认的单个细线蒙版提取可见中心路径、骨架局部距离、平滑宽度样本，并将左右外沿组合成**真实可编辑 SVG 填色轮廓**。对比“统一宽度描边”基线，选择最小错误宽度系数；对于跨越/分叉或下方被遮挡的线，不推断神经归属。写回后对象继续占一个独立 Layer/Object，此外在同一对象中存储**隐藏中心线 SVG guide**、`width_samples_px` 数组；`14_Variable_Width_Profiles.json` 包含各段宽度配置。**SVG 1.1 无通用原生变宽 stroke 属性；该交付绝非 Illustrator 原生 Width Tool profile。**

```bash
python scripts/variable_width.py --project /path/project --object-id vagus_visible --min-iou 0.80
# 核验 variable_width_vagus_visible_report.json、预览和分叉提示后：
python scripts/variable_width.py --project /path/project --object-id vagus_visible --min-iou 0.80 --write-manifest
```

默认两个工具均只写独立报告，不会覆盖项目 manifest；写回前必须检查边缘与医学结构。详细 QA、合成基准结果、不可承诺的部分见 `references/precision.md`。回归测试：`python scripts/precision_v23_tests.py`。示例：`python examples/create_precision_v23_demo.py --out /tmp/v23_example`。

### 显式遮挡约束 + 智能候选 + SVG 图层重排（新增）

在实例分割与精度精修后，先确定每个部件的**已知可见范围**，再分析重叠位置、前后层级与图层归属。`scripts/occlusion_layers.py` 能通过渲染后的不透明重叠区域计算颜色支持的前景候选，区分**已人工确认关系**、**强颜色候选**、**不确定的遮挡/贴靠**。颜色证据不能证明不可见神经的连接方向；绝不生成新隐藏段或自动补画。

关键操作：

```bash
python scripts/occlusion_layers.py --project /path/project --out /path/occlusion_review
# 目视确认 review PNG/stack SVG/JSON 后，在 manifest 中设置：
# "occlusion":{"constraints":[{"behind":"nerve","front":"device","source":"user_confirmed"}]}
python scripts/build_vector_package.py --project /path/project --out /path/export --require-line-quality-review
# 强制检查全部明显重叠时：qa.require_resolved_occlusions = true
```

导出器会校验遮挡关系 DAG（循环报错），计算最终后→前排序，在同一语义层被其他层穿插时拆分实际 SVG Layer run，同时保留所有对象路径及原图层归属。新增 `15_Occlusion_Review.png`、`16_Occlusion_Stack.svg`、`17_Occlusion_Report.json`；对源图中看不到但工程中已存在的路径统计遮挡面积并标记来源待审核。只有操作者显式 `--accept-candidates --write-manifest` 才允许将可见颜色候选写入 Manifest，仍标记未做解剖审核。

**绝不能用强制顺序或颜色接近来证明真实神经连接；半透明叠加、同色、三重交叉、全遮盖都可能无法判断。** 详情与字段见 `references/occlusion.md`。测试 `python scripts/occlusion_v24_tests.py`；示例 `python examples/create_occlusion_v24_demo.py --out /tmp/occlusion_demo`。

### SAM2 可提示分割 + 医学结构保护（新增，环境满足时优先）

针对已由用户确认类别的神经、导线、电极、装置及人体等**二维科研插画结构**，新增可运行的官方 Meta SAM2/SAM2.1 推理适配器 `scripts/sam2_medical_segment.py` 和保守后处理模块 `scripts/medical_mask_postprocess.py`。与 LAB/GrabCut 并存：可优先用 SAM2 对复杂色块进行提示式分割，缺 SAM2 权重/依赖时仍可用旧模块，不得假装 SAM2 已执行。

- 按 `assets/sam2-instances.template.json` 准备**用户图像的真实像素坐标**：每个目标单独 `id`、`fg_points`、`bg_points`、`bbox`、`profile`。点/框用于分割，**医学结构名称来自人工确认，不是模型诊断**。
- 官方 SAM2 图像 API：`predictor.set_image(RGB)`，`predict(point_coords,point_labels,box,multimask_output=True,normalize_coords=True)`；提示使用原图像素 XY 坐标，由官方 API 按原图尺寸变换到模型坐标。逐实例使用预测 IoU 与硬性提示约束选择候选，保留拒绝原因。可用 Hugging Face 模型名或本地 checkpoint/config。基础依赖不会自动下载模型。
- 医学后处理：`nerve/lead` 严格保留断裂/端点/分支，不推断遮挡连接；`electrode/device` 保留孔洞和独立部件；`body` 保持原图范围。默认不形态学闭合、不填洞、不过度平滑；所有实例需人工审核。仅平涂细线可显式启用有像素限制的近邻色彩微修复。
- 产物直接写入逐实例 PNG mask + Manifest，并带独立 SVG 图层、轮廓预览与 `sam2_segmentation_report.json`；再用 `centerline_trace.py` 和 SVG 生成器。不同实例的可见像素重叠默认拒绝。
- 真实模型能力**未在本 Skill 附带的 mock 回归测试中被验证**：必须安装 SAM2 和提供 checkpoint；模拟联调不得称为 SAM2 精度实测。详见 `references/sam2-medical-postprocessing.md`。

```bash
python scripts/sam2_medical_segment.py --project /path/project \
  --annotations /path/annotations.json --hf-model facebook/sam2.1-hiera-tiny --device auto
# 也可使用 --checkpoint /path/sam2.1_hiera_tiny.pt --config configs/sam2.1/sam2.1_hiera_t.yaml
```

### 医学实例分割与线条中心线自动提取（增强）

当用户给出参考图并希望减少手工勾线时，优先采用**经人工/视觉模型确认的实例种子+区域约束**，用 `scripts/medical_instance_segment.py` 生成逐对象蒙版；对经确认的细神经/导线类蒙版，执行 `scripts/centerline_trace.py`，输出开放、可改描边宽度的 SVG 中心线。完整标注格式、命令与风险限制见 `references/medical-segmentation-centerline.md`。

实际命令示例（`annotations.json` 必须根据用户原图确定坐标，不能使用示例坐标充数）：

```bash
python scripts/medical_instance_segment.py --project /path/project --annotations /path/annotations.json
python scripts/centerline_trace.py --project /path/project --object-id nerve_01 --mode adaptive-bezier --min-iou 0.85
# 目视检查 centerline_nerve_01_report.json 与 preview，再写入 Manifest
python scripts/centerline_trace.py --project /path/project --object-id nerve_01 --mode adaptive-bezier --min-iou 0.85 --write-manifest
```

- 两种实例策略：`seed_lab` 颜色连通域、`grabcut` 人工前/背景标记配合 ROI；相同颜色的电极也可以按不同种子分开，但同色相连部件不能无依据自动区分。多前景种子跨不同颜色会默认报错，防止神经+电极粘连。
- 中心线策略：骨架化 + 8 邻域拓扑图 + 分支/端点/闭环检测，SVG 开放路径，拟合前后 IoU/边缘距离检查。`adaptive-bezier` 不合格时回退原折线，stroke 默认沿用源实例色值。
- 对十字交叉、分叉、遮挡和变线宽结构，系统只记录可见像素与疑点，不臆断真实神经连接。语义标签来自已确认标注，**不能宣称模型自动认出医学解剖**，更不能将该功能用于临床 CT/MRI 自动分割或治疗规划。
- 默认只生成中心线路径报告，不覆盖原来的蒙版对象；IoU 达标后人工检查才用 `--write-manifest`，未达标可保留原蒙版封闭路径。即使局部 IoU 高，也不代表医学解剖审核完成。

### 3. 结构重建及文件生成

- 编辑项目 `manifest.json`，逐层填入真实 `path` 或与原图等尺寸的独立 `mask_png`；提供每个对象的名称、颜色、z-order 等，示例见 `assets/manifest.template.json`。
- 在可运行本地脚本的环境中执行（`/path/to/layertrace` 替换为实际安装位置；也可先 `cd` 进入 Skill 目录再使用相对路径）：

```bash
python /path/to/layertrace/scripts/build_vector_package.py --project /path/project --out /path/output --require-line-quality-review
```

- 该脚本负责：显式遮挡关系约束的 SVG 叠放顺序重建（仅配置 occlusion 时启用）、真实 SVG 路径组合、渲染测量每个对象真实 bbox、可命名组、拆解图 SVG、预览 PNG、线稿检查视图、调色板、逐对象清单、全图/局部质控报告和 ZIP。**脚本不负责自动辨认脑/神经/电极；LAB/GrabCut 及 SAM2 辅助实例分割都依赖用户确认的正负点/ROI，骨架中心线依赖已分离的蒙版，不会凭空产生真实医学解剖标签**；图层/蒙版/手工路径必须先由绘制流程建立。
- 使用工具中若有可靠矢量化功能（Illustrator Image Trace/第三方路径工具/已连接 Adobe image_vectorize），仅可作为初稿；在医学图中必须再做对象拆分与形状核对。不能误把自动生成的数千个无意义色斑声称为语义独立的图层。
- 输出的 SVG 使用标准 SVG + `inkscape:label`/`inkscape:groupmode="layer"` 辅助图层标识；**Illustrator 导入后的真实图层结构需单独核验**。

### 4. 拆解总览（必做）

同一张白色或浅色大画布：`00` 为完整组合图；`01...N` 为独立结构模块，采用不变形缩放，中文编号+名称，独立卡片间无遮挡。可按 module 汇总几十根小导线为一张卡片，**但文件内部每根仍为独立对象**。根据复杂度可补一张层级示意，禁止用拆解卡片标题污染最终完整插画。

### 5. 质量门禁（未通过不宣称完成）

- 几何：原始画布尺寸、位置、主轮廓和遮挡一致；叠加预览检验错位。
- 结构：数清电极、导线、环、固定件；每个需要独立编辑的对象保持独立、可单独隐藏/改色。
- 颜色：相同色号复用；纯色图不被加上新的渐变；透明度、线宽正确。
- SVG：每个对象单独渲染证实其有真实可见像素；自动检测 bbox，不信任用户手填位置；XML 可解析；无 `<image>`/`foreignObject`；SVG 可渲染；图层/对象 ID 不重复。
- 量化：计算 RGB/Alpha MAE、变更像素比例、边缘错配率；按 `qa.key_regions` 单独检测神经/电极/线缆端点；一旦超过阈值，默认停止最终 ZIP 导出（仍留下质量报告及差异图），只有 `--allow-draft` 才交付明确标为 FAIL 的失败草稿。数值只是初筛，不作为单独的“像素级复刻证明”。
- 遮挡（）：明确约束无环，层级排序与参考图交叉一致；不对遮挡下的神经连接作无依据补全。对强颜色候选必须人工确认；启用严格门禁时任何显著未明确重叠不得正式打包。
- 编辑结构：核对 `25_Editability_Report.json` 的可见描边与声明对象；未声明导线约束时仅报告数量，不声称已通过语义编辑审核。
- Illustrator：能打开 SVG；对象能独立选取。只有在用户机器或实际 Illustrator 环境中完成验证，才可输出 `.ai` 并称为原生文件。
- 未复现的部位和使用的近似/自动描摹方法必须列入 `quality_report.json`/最终回复。

详细验收见 `references/quality-and-illustrator.md`。允许按用户确认的 seed 坐标执行 `scripts/seed_segment.py` 辅助颜色连通组件分离，但这不构成自动医学语义识别。蒙版可选择 `--trace-mode adaptive-bezier`：仅在与原始保真轮廓误差达标时使用三次曲线，否则自动回退折线。

支持 `qa.required_object_ids` 和 `qa.expected_object_counts_by_prefix` 校验电极/导线实例数；关键小结构应设置 `qa.key_regions` 单独质控。所有自动通过的作品仍须人工检查后才能声称与原图准确一致。

## 交付合约

总是尽最大能力直接提供实际文件，而不止建议。默认文件名见 `references/output-contract.md`。至少应包含：

1. `01_Full_Illustration.svg`：原图坐标、真实可编辑路径。
2. `02_Layer_Breakdown.svg`：编号模块的矢量拆解总览。
3. `03_Full_Preview.png`：组合效果。
4. `04_Breakdown_Preview.png`：拆解图预览。
5. `05_Color_Palette.csv`：所有颜色/用途及数量。
6. `06_Layer_Manifest.json`：模块-图层-对象层级和路径来源。
7. `07_Illustrator_File.ai`：**仅当确实有 Illustrator 生成并验证时**提供。
8. `08_All_Files.zip`：已经生成的文件及校验材料；不含虚假 `.ai`。
9. `09_Overlay_Comparison.png`、`10_Difference_Map.png`、`quality_report.json`：图像偏差材料。
10. `11_Outline_Inspection.svg`：显示最终路径线稿的复核图，不伪称创作过程证据。
11. `15_Occlusion_Review.png`、`16_Occlusion_Stack.svg`、`17_Occlusion_Report.json`（启用遮挡分析时）：可见交叉复核、图层堆叠和有证据范围的候选/待审计报告。
12. `ROI_XX_Comparison.png`：按需输出关键医学小区域对照。

输出缺项时说明具体原因，不捏造 URL、空壳文件或不存在的路径。用户需求只有分析时可仅给清单，但当其要求拆解与文件时必须尝试实际制作。

## 最终答复（中文）

依次给出：**①原图元素与模块/图层/对象数 ②拆解总览图 ③完整预览图 ④SVG/ZIP/真实 AI（若有）的下载方式 ⑤核查结果与无法复刻/未经 Illustrator 验证的部分**。不得写“100% 无差异”“完美一比一”，除非具备对应可复核证据。

当用户只上传图片并说“按固定流程”，直接启动，无需重复询问风格、背景、比例和图层数。对难以自动识别的实例应据实际能力手工/视觉确认、给出尚需复核的缺陷，不得虚构真实路径。若关键源文件无法取得，明确说明而不是编造输出。

## 参考文档（按需读取）

- `references/editable-illustrator.md`：默认线条编辑结构、纯线稿输出、导线门禁与实际 Illustrator 原生保存/回读。

- `references/studio-editing.md`：交互精修、蒙版/节点/遮挡编辑、撤销、正式导出与安全限制。
- `references/occlusion.md`：图层遮挡 DAG、局部像素证据、审查与安全写回限制。
- `references/trace-protocol.md`：路径描摹、蒙版、前后层、医学装置、复杂图特殊处理。
- `references/sam2-medical-postprocessing.md`：官方 SAM2 推理适配器、配置、医学分割保护与真实验证边界。
- `references/precision.md`：亚像素颜色模型、边缘/孔洞验收、贝塞尔搜索、变宽轮廓及真实编辑限制。
- `references/medical-segmentation-centerline.md`：实例标注、GrabCut、骨架中心线、验证、错误回退和可复现示例。
- `references/quality-and-illustrator.md`：品质验证、数值检查及 AI 真伪标准。
- `references/output-contract.md`：项目 manifest 字段、交付表与安装运行方式。
