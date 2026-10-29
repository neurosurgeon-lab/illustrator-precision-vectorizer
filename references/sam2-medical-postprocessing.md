# — SAM2 可提示分割与医学插画保守后处理

## 使用范围与能力边界

此模块处理用户提供的**二维医学科学插画和科研图形摘要**，不是 CT、MRI、显微组织或临床医疗图像的诊断性自动分割模型。`nerve / lead / electrode / device / body` 是**用户标注的绘图部件类型**，不是 SAM2 能识别的医学解剖类别；标签是否正确必须由专业人员确认。不存在自动推断隐藏神经/导线、真实解剖连接或修补被遮挡部分的功能。

核心顺序：输入 RGB 参考图 → 官方 Meta SAM2 ImagePredictor → 正/负点与 XYXY 提示框 → 模型多候选 → 提示点及可见 ROI 的严格硬约束 → 专用后处理 → 逐对象 PNG 蒙版、检查预览、JSON 质量报告及 Manifest → 中心线跟踪 → 可编辑 SVG/ZIP。

**SAM2 预测的 IoU 分数不是原图实际 IoU**。必须检查预览与最终矢量结果，尤其神经、电极和导线的末端位置。

## 实际安装 SAM2（可选的额外依赖，不随 ZIP 分发）

保持基础依赖安装：

```bash
python -m pip install -r requirements.txt
```

按照 Meta 的官方仓库说明，在新环境安装满足 `python>=3.10`、`torch>=2.5.1`、`torchvision>=0.20.1` 的 PyTorch，随后安装 SAM2（请勿将同名非官方模块当作 Meta 代码）：

```bash
# 推荐直接按照 https://github.com/facebookresearch/sam2 选择适配平台的 PyTorch
python -m pip install torch torchvision huggingface_hub
# 在单独工作目录中安装官方代码，注意安装时可能需要联网/系统依赖：
git clone https://github.com/facebookresearch/sam2.git
cd sam2
python -m pip install -e .
cd ..
```

本 Skill 只使用 `sam2.build_sam.build_sam2/build_sam2_hf` + `sam2.sam2_image_predictor.SAM2ImagePredictor` 官方接口。模型权重未纳入 ZIP，不会假装已预先训练/下载。CPU 和 Apple Silicon MPS 可手动选择，但设备支持与性能取决于 SAM2、Torch 版本和本机环境；若 MPS 报算子问题，尝试 `--device cpu`。CUDA 环境优先选择 CUDA（显存须足够）。

## 最短命令

```bash
# 1：创建工作工程
python scripts/init_project.py --image /path/figure.png --out /path/work

# 2：根据原图编辑各实例的语义、前景点/负点、bbox 和 profile
cp assets/sam2-instances.template.json annotations.json

# 3a：通过 Hugging Face 读取官方 checkpoint（需模型权重联网/已缓存）
python scripts/sam2_medical_segment.py --project /path/work \
  --annotations annotations.json --hf-model facebook/sam2.1-hiera-tiny --device auto

# 3b：离线本地 checkpoint（与 3a 二选一）
python scripts/sam2_medical_segment.py --project /path/work \
  --annotations annotations.json \
  --config configs/sam2.1/sam2.1_hiera_t.yaml \
  --checkpoint /local/checkpoints/sam2.1_hiera_tiny.pt --device cpu

# 4：将已确认的细长部件转为开放可编辑 SVG 路径；先不写入
python scripts/centerline_trace.py --project /path/work \
  --object-id vagus_nerve_visible --mode adaptive-bezier --min-iou 0.85

# 人工查看检查图、中心线报告后，再写入 Manifest
python scripts/centerline_trace.py --project /path/work \
  --object-id vagus_nerve_visible --mode adaptive-bezier --min-iou 0.85 --write-manifest

# 5：组装 SVG、拆解图、对比 QA 和文件包
python scripts/build_vector_package.py --project /path/work \
  --out /path/export --include-source-project
```

`--append` 仅在已有图层项目上且已确认不会重复时使用。模型预测器设图一次、逐对象分别推理；提示是**原始图像像素 XY 坐标**，bbox 是 `[x, y, width, height]`，代码先转换为 XYXY，再由官方 API 使用 `normalize_coords=True` 按原图尺寸变换到模型坐标。不要填写示例坐标给真实用户的插画。

## 医学插画专用策略（不改变原图）

| `profile` | 重点保护与检查 | 禁止的默认行为 |
| --- | --- | --- |
| `nerve` | 保留细分支、可见连通片段；报告骨架端点、可能分叉 | 不自动桥接遮挡、不加粗到失真、不推断真实神经走行 |
| `lead` | 每根线独立对象；报告交叉/分叉，保留开放路径 | 不推断交叉点哪根导线在前，不自动合并两根线 |
| `electrode` | 保留电极孔洞、内圈、多实例、独立轮廓 | 不强制圆形化、不填实空心电极 |
| `device` | 保留壳体轮廓/孔洞，逐组件编辑 | 不抹去小开孔、不重绘未显露器件细节 |
| `body` | 保留原图姿态/人物比例 | 不基于模型补充不可见解剖 |
| `generic` | 只按提示与 ROI 保守筛选 | 不假设其医学身份 |

默认严格要求：所有正点在目标蒙版内、所有负点在外；超出 ROI/alpha 直接裁剪；多断开组件默认报错、需显式 `allow_disconnected:true` 才保留**可见且未连接**的片段；明显面积异常报错；实例重叠默认报错。每个实例必须独立写入 `masks/<id>.png`。不能手工修改 Manifest 中的 Mask ID 来冒充独立实例。

对纯色细线可以*显式*开启 `color_refine:true`：仅在蒙版周边 1–5 像素、由正点颜色限制的可见区域内补充少量彩色像素，最大增加比例由 `max_added_fraction` 限制。不会跨越远端断裂补线；出现连通分量/空洞变化一定记录警告。此模式只适用于 `nerve/lead/electrode`，默认关闭。对电极内孔、图像中的白色洞口采取**不填洞**的保守策略。

## 质量证据、输出与错误处理

- `sam2_segmentation_report.json`：保存每个实例 profile、预测的 IoU、未通过的候选原因、组件数、洞数、骨架提示、实际可见 bbox、输入图 SHA256、模型来源和是否为真实 SAM2 推理。
- `sam2_previews/<id>.png`：颜色覆盖、蒙版实际轮廓、前景/负点及 ROI 边界的可视复核图。
- `sam2_annotations.json`：可追溯的原始提示点、框与 profile。
- `masks/<id>.png`：后续 SVG 描摹所需的**独立原像素尺寸蒙版**。
- `manifest.json`：每个目标独立加入 layer/object/module，不与邻近电极或导线合并。

当多候选均不满足硬约束时立即报错，而非默默选最高分。写入前检查对象/模块 ID 重复、已存在目标文件以及互相重叠的可见区域；未解决的交叉、遮挡和前后关系不自动补全。带有 `actual_sam2_inference=false` 的 mock 测试只说明**API 管线联调**，不是 SAM2 实际精度验证。

## 本版本已验证 / 尚未验证

已验证（本地无权重测试）：

1. 外部预测器注入、SAM2 参数格式、模型候选选择和错误拦截。
2. 正/负提示点，XYWH→XYXY，原图像素坐标通过官方 API 归一化并变换。
3. 两个同色电极的实例独立性、电极内孔保留、断裂神经拒绝自动接通。
4. 可见实例重叠拒绝、失败时不写入部分蒙版/Manifest。
5. 独立蒙版可交给既有 `centerline_trace.py` 和 `build_vector_package.py` 导出 SVG。

尚未验证（不能夸称）：

1. 真实 SAM2.1 权重的加载与实际图像精度、速度、GPU/MPS 兼容性。
2. 不同风格、低分辨率、复杂阴影、透明度和严重遮挡下的分割 Dice/边界 F1。
3. Illustrator 原生 AI 的图层显示/保存能力（需实际 Illustrator 环境）。

推荐在用户真实插画上手工标注至少 10–20 例高难度小部件，计算独立实例 IoU、boundary F1、骨架端点/分支遗漏、同色对象误合并率，并与 LAB/GrabCut 对比。这是**后续真实精度评估计划**，不是已经完成的数据。

参考：Meta 官方 SAM2 仓库 https://github.com/facebookresearch/sam2（安装及图像接口）。
