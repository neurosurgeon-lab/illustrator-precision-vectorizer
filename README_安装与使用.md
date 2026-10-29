# V1.1 连续平滑线条与真实 AI（最新版）

最终交付必须按 [V1.1 线条审核流程](references/line-quality.md) 启用 `--require-line-quality-review`，逐对象检查至少 4 倍放大图；无有效审核或文件变化时停止正式 ZIP。

默认构建清晰贝塞尔轮廓、可见开放描边和独立填色。导出器增加纯线稿和编辑结构报告；manifest 可声明必须有开放描边的导线，结构失败时停止正式 ZIP。原生入口 `illustrator_native.py` 在准备后可调用本机 Illustrator 保存并回读彩色/线稿 AI，实际检查改线宽和改锚点。操作、字段和限制见 [指南](references/editable-illustrator.md)。

# 补全、OCR 与递归批处理

保留已验证的 SAM2 权重配置与坐标修复，合入断裂/缺口候选、可审核的 Modal/Amodal、人工批准后导出的可编辑 OCR 文字。混合文件夹使用 `--input-dir`，递归使用 `--recursive`；仍使用 `batch_summary.json/csv` 和原有状态。详细命令与标注命名见 [新功能指南](references/completion-batch-ocr.md)；完整说明见[英文文档](README_EN.md)。

# 批处理与本地权重

使用 `scripts/configure_sam2.py` 保存本地权重配置，再通过 `scripts/batch_vectorize.py --projects ... --out ...` 批量导出工程，或 `--images ... --annotations ... --out ...` 处理配套标注的图片。缺少标注时记为待标注；失败继续其他项，JSON/CSV 汇总保留每项结果。完整命令和标注格式见 [批处理指南](references/batch.md)。

已修复真实 SAM2 像素提示的坐标变换，并完成所列合成案例的真实权重验证，详见 [验证记录](references/sam2-validation.json)。

# 集成工作台

本地工作台集成 **SAM2 点/框候选蒙版（确认后写回）+ 逐对象局部差异热图 + Illustrator 原生图层导入工程**。无模型、无 Illustrator 时保留全部旧版功能，但不声称已经运行真实模型或生成 AI。

```bash
cd ~/.agents/skills/layertrace
python -m pip install -r requirements.txt
python examples/create_interactive_v25_demo.py --out /tmp/studio30
python scripts/interactive_studio.py --project /tmp/studio30/project
# 打开 http://127.0.0.1:8765/
# 本机已有 SAM2 权重时，增加 --sam2-config 与 --sam2-checkpoint
```

浏览器先选独立蒙版部件，用 SAM2 ＋ 点 / − 点 / 框选提示，审核候选再确认写回；可计算整图与所选对象 ROI 热图。导出通过后在 `18_Illustrator_Import/` 使用 `import_v30.jsx` 在 Illustrator 中创建真实 Layer，需人工检查。单独命令：`python scripts/illustrator_import.py --project project --out empty_folder`。

完整功能/边界：`references/interactive-studio.md`。测试：`python scripts/studio_v30_tests.py`。

---

# 可视化工作台（基础功能）

在 矢量工程上进行本地浏览器精修，保留全部原有工具：

```bash
python -m pip install -r requirements.txt
python examples/create_interactive_v25_demo.py --out /tmp/v25_demo
python scripts/interactive_studio.py --project /tmp/v25_demo/project
# 浏览器打开 http://127.0.0.1:8765/
```

对自己的项目，用 `--project /path/to/project`。先用实例分割工具或手工建立分层实例，再进入工作台编辑；若项目只有未经分割的原图，工作台不会自动创造图层。完整说明：`references/studio-editing.md`。

---

# 遮挡重建（新增）

按下文安装后，已有独立蒙版和路径后，使用 `python scripts/occlusion_layers.py --project project` 生成遮挡关系复核报告；根据真实可见交叉手工配置 `manifest.json` 的 `occlusion.constraints`，再使用 `python scripts/build_vector_package.py --project project --out output` 导出分层文件。详细参数及风险边界见 `references/occlusion.md`。

# LayerTrace 安装与快速使用

本 Skill 把 **已确认的语义对象路径、独立蒙版** 组装成高保真 SVG/拆解图，并对源图进行全图、局部几何与色彩验收。v2 不承诺照片或复杂医学插画一键自动 1:1 矢量化；语义分割仍需要人为或视觉模型确认，每根神经/导线、每个电极都需独立建立对象。

## 安装

支持 Codex、Claude Code、Cursor、Gemini CLI 及可读取 `SKILL.md`、查看图片和运行 Python 的其他本地代理。各客户端目录和调用方式见 [客户端安装表](README.md#客户端安装)。以下以通用 `.agents/skills` 目录为例。

```bash
mkdir -p ~/.agents/skills
unzip layertrace-skill-v1.1.0.zip -d ~/.agents/skills
python -m pip install -r ~/.agents/skills/layertrace/requirements.txt
python ~/.agents/skills/layertrace/scripts/validate_skill.py
python ~/.agents/skills/layertrace/examples/create_demo.py
python ~/.agents/skills/layertrace/scripts/self_test.py
python ~/.agents/skills/layertrace/scripts/regression_tests.py
```

## 图片输入：最短流程

```bash
cd ~/.agents/skills/layertrace
python scripts/init_project.py --image /path/reference.png --out /path/myproject
# 绘制/确认语义对象的原尺寸独立蒙版与 SVG 路径，编辑 myproject/manifest.json
python scripts/build_vector_package.py --project /path/myproject --out /path/export
```

如果是纯色区域、已知种子点，可先半自动建立独立蒙版：

```bash
python scripts/seed_segment.py --project /path/myproject --seeds /path/seeds.json
# 必须手工校正标签/色号/边界/分层，才能进行正式导出
```

其中 `seeds.json` 示例：

```json
{"objects":[
  {"id":"body_fill","name_zh":"人体基础填色","x":143,"y":188,"tolerance":9,"layer_id":"01_Fills"},
  {"id":"cap_fill","name_zh":"脑电帽","x":230,"y":110,"tolerance":10,"layer_id":"02_Cap"}
]}
```

**重要**：种子点不是医学语义智能识别；对于颜色连通的神经、导线、皮肤阴影等，仍须手工修正蒙版和中心线。默认使用高保真折线路径。平滑曲线可选 `--trace-mode adaptive-bezier`，只有通过局部轮廓误差门槛才自动采用。

## 导入 SVG 源图

```bash
python scripts/init_project.py --image /path/original.svg --out /path/svg_project
python scripts/build_vector_package.py --project /path/svg_project --out /path/svg_export
```

对于基础 SVG，导入原路径并自动建立初始 Manifest。对于文本、滤镜、剪切、外部图片、复杂 ViewBox 等不支持对象，程序会**明确拒绝**，不以近似图冒充原路径。

## 严格质量验收

默认：如果 RGB、Alpha、变更像素比例或 `qa.key_regions` 指定局部超过阈值，`build_vector_package.py` 以非零状态结束，**不输出最终 ZIP**，保留 `quality_report.json`、差异图供修正。如果确实需要失败草稿，可添加 `--allow-draft`，但草稿报告的 `release_ready` 仍为 false。

所有成功生成的包仍标 `exported_svg_needs_review`，因为医学结构、对象编辑性和 Illustrator 原生图层必须经过人工验证。只要没有真实在 Illustrator 中保存及回读验证，就不能声称交付了 AI 文件。

完整格式、检查阈值、输出文件及 Manifest 字段见 `references/output-contract.md`；逐对象轮廓标准见 `references/trace-protocol.md`。

## 其他可选输出

```bash
# 双倍尺寸检查预览：不会改变原始 SVG 坐标和几何
python scripts/build_vector_package.py --project /path/myproject --out /path/hires_export --hires-scale 2

# 私有工程保存：额外打包源图、原始 SVG（若有）、独立蒙版与 Manifest
# 原始图可能包含患者信息，须确认保管与共享范围
python scripts/build_vector_package.py --project /path/myproject --out /path/full_project_export --include-source-project
```

质量验收遵循原图忠实度高于美化的要求。


## 医学实例分割及中心线（新增）

新增 `medical_instance_segment.py`：在原图坐标提供 ROI、前景点/背景点后，通过 `seed_lab` 或 `grabcut` 生成独立部件 mask；多颜色前景点冲突默认报错，避免误把神经和电极粘在一起。新增 `centerline_trace.py`：从已确认的细神经/导线蒙版计算骨架、端点、分叉和闭环，转为可单独选择的 SVG 开放描边对象，并按 mask IoU 与边界距离检查拟合质量。

从本目录运行：

```bash
python -m pip install -r requirements.txt
python scripts/init_project.py --image input.png --out project
# 先按真实图像填写 assets/medical-instances.template.json 的坐标并另存 annotations.json
python scripts/medical_instance_segment.py --project project --annotations annotations.json
python scripts/centerline_trace.py --project project --object-id vagus_nerve --min-iou .85
# 目视检查 JSON/PNG 后，加 --write-manifest 才会替换原 mask 为 SVG stroke
python scripts/build_vector_package.py --project project --out export --include-source-project
```

细节见 `references/medical-segmentation-centerline.md`，非临床测试 `python scripts/instance_centerline_tests.py`。对复杂医学插画仍须人工标注并复核：这不是通用训练模型的全自动语义识别，也不能将无监督分割当成医学结构事实。

## SAM2 正/负点、框选与医学结构后处理（新增）

本版有**真实的 SAM2 模型加载/预测代码**，但**不附权重**；必须另行安装 Meta 官方 `facebookresearch/sam2` 及兼容的 PyTorch，才能实际推理。`scripts/sam2_integration_tests.py` 使用模拟预测器，仅检查参数、后处理、质量门禁和文件导出，不能代表模型精度。

```bash
# 安装方式和完整命令见 references/sam2-medical-postprocessing.md
python scripts/sam2_medical_segment.py --project project \
  --annotations annotations.json --hf-model facebook/sam2.1-hiera-tiny --device auto
# 若本地已具备模型：
python scripts/sam2_medical_segment.py --project project \
  --annotations annotations.json \
  --checkpoint /path/sam2.1_hiera_tiny.pt \
  --config configs/sam2.1/sam2.1_hiera_t.yaml --device cpu

# 测试：仅模拟预测器，不下载权重
python scripts/sam2_integration_tests.py
python examples/create_sam2_adapter_demo.py --out /tmp/sam2_adapter_demo
```

输出含 `sam2_segmentation_report.json`、`sam2_previews/*.png`、`masks/*.png`；每个目标独立进入 Manifest。需复核神经分支/端点、同色相邻电极、装置孔洞、ROI 裁切及无遮挡部位。参考 `assets/sam2-instances.template.json` 和 `references/sam2-medical-postprocessing.md`。


## 增强（精度优先 / 可选）

前提：你已经通过 SAM2、GrabCut 或人工获得**一个对象对应一个蒙版**。

```bash
python -m pip install -r requirements.txt
python scripts/subpixel_bezier.py --project /path/project --object-id head --scale 3
python scripts/subpixel_bezier.py --project /path/project --object-id head --scale 3 --write-manifest
python scripts/variable_width.py --project /path/project --object-id nerve --min-iou 0.80
python scripts/variable_width.py --project /path/project --object-id nerve --min-iou 0.80 --write-manifest
python scripts/build_vector_package.py --project /path/project --out /path/export
python scripts/precision_v23_tests.py
```

以上两个精修工具默认先写 JSON 报告，只有主动传 `--write-manifest` 且数值门禁通过才替换原对象几何。输出的变线宽主体是**填色矢量轮廓**，同时提供不可见的中心线及可复原宽度数据；不是原生 Illustrator Width Tool profile。测试数据属于合成非临床示意图，不能推断真实神经结构分割精度。详见 `references/precision.md`。
