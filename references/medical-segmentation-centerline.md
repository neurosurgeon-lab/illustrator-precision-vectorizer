# 医学结构实例分割、细神经/导线中心线提取

## 核心定义和适用范围

采用**人工/视觉模型确认的种子、边界框、前景/背景标注**，以 OpenCV LAB 连通域或 GrabCut 创建可追溯的逐对象 PNG 蒙版；再对“线型部件”的二值蒙版进行形态学骨架提取、分支拓扑分析，转换为 `fill=none`、可编辑的 SVG stroke path。

**绝不将这些算法称为训练过医学影像的语义识别模型。** 它不自动辨认“迷走神经”“电极”“STN”“DN”等身份，所有名称必须由用户或经确认的视觉检查提供。只适合二维示意图/平涂素材的辅助拆解；光照照片、真实 MRI/CT、复杂材质、被遮挡结构不保证可靠。**不要把这个工具当作临床医学影像自动分割。**

## 安装依赖

```bash
python -m pip install -r requirements.txt
```

Python ≥3.10。`opencv-python`、`numpy`、`Pillow`、`scipy`/`scikit-image`（骨架）、`networkx`（分支拓扑）、`cairosvg`（路径质量验证）、`lxml`（SVG）、`PyYAML`（Skill 检查）。不下载或调用不明的云模型；所有运算本地进行。CairoSVG 需要系统可用的 Cairo 运行库。

## 第一步：锁定参考图

```bash
python scripts/init_project.py --image figure.png --out work/my_figure
```

不覆盖 source，不变更比例。`manifest.json` 中没有医学实例时不能声称已完成分层。

## 第二步：编制经确认的实例标注

保存 `annotations.json`（示例见 `assets/medical-instances.template.json`）：

```json
{
  "instances": [
    {
      "id": "vagus_nerve",
      "name_zh": "颈部迷走神经示意线",
      "layer_id": "02_nerve",
      "method": "seed_lab",
      "bbox": [130, 80, 160, 240],
      "fg_points": [[165, 130], [166, 210]],
      "lab_tolerance": 10
    },
    {
      "id": "implant_generator",
      "name_zh": "植入式刺激器",
      "layer_id": "04_device",
      "method": "grabcut",
      "bbox": [260, 200, 140, 110],
      "fg_points": [[322, 252]],
      "bg_points": [[265, 210], [390, 300]],
      "brush_radius": 3,
      "iterations": 5
    }
  ]
}
```

坐标相对于原图左上角，**示例坐标不可直接用于真实图片**。同色不同实体也必须有不同 ID、不同种子或 ROI。`bbox` 为硬性限制，不是供智能模型猜测。`seed_lab` 是 Lab 欧氏距离的局部颜色匹配（不是 CIEDE2000）；颜色相近、共用一色且连成一片时无法可靠分离。若多个 foreground seeds 颜色明显冲突，默认拒绝，避免把电极或阴影合并入神经；特殊多色对象需显式 `allow_multicolor: true` 且人工复核。

```bash
python scripts/medical_instance_segment.py \
  --project work/my_figure --annotations annotations.json
```

若 Manifest 已有人工图层，先检查再加 `--append`。输出 `masks/<id>.png`、`instance_annotations.json`、`instance_segmentation_report.json`，并加入独立图层/拆解模块；**自动标记等待人工复核**。当实例触碰 ROI 边缘、有多个连通分量、互相重叠时，会单独记录警告。不要把完整人物与其上设备的遮挡/不可见部分当成自动恢复出来的完整对象。若需要前后完整结构，应另行手动补充并标记 `inferred_hidden`。

## 第三步：中心线重建（只针对细长的线型实例）

完成分割后，按每根导线/神经对应的独立 `mask_png` 处理：

```bash
python scripts/centerline_trace.py --project work/my_figure \
  --object-id vagus_nerve --mode adaptive-bezier --min-iou 0.80
```

默认**仅分析与输出报告，不修改 Manifest**。输出：

- `centerline_vagus_nerve_report.json`：路径 `d`、stroke 宽度、轮廓误差、端点数、分支结点数、连通组件及警告；
- `centerline_vagus_nerve_preview.png`：SVG 中心描边实际渲染出的二值轮廓，供逐像素对照。

符合要求且检查后，可执行 `--write-manifest` 写回真正的 SVG 开放路径：

```bash
python scripts/centerline_trace.py --project work/my_figure \
  --object-id vagus_nerve --mode adaptive-bezier \
  --min-iou 0.85 --write-manifest
```

- **输出线色默认沿用原实例 `fill`**，无有效 HEX 时要求显式 `--stroke '#RRGGBB'`。
- 骨架基于 `skimage.morphology.skeletonize`，以八邻域构图，删除导致虚假分支的冗余对角边；相邻多像素交点合并为共同 junction hub。
- 连通枝、环和端点不会凭空连结。交叉/Y形/分叉报告会标记“无法确定神经归属、遮挡方向”。对于可独立编辑的分叉生成 `<id>_branch_XX` 多条路径，保留单独对象和名称。
- 估计统一 stroke-width，并以不同候选线宽重新渲染计算**原始线型蒙版 vs 中心线描边 IoU**、双向边界距离 95 分位数；只有达到阈值才可写回（`--allow-draft` 可强制保存待修改草稿，但仍不代表合格）。
- `adaptive-bezier` 仅在候选曲线通过形状比较时采用，否则回退折线，**不会为追求圆滑而改变神经/设备走行**。
- 不能给变线宽神经、被设备截断的细线、同色相交导线承诺完整路径。与轮廓法相比，开放线允许直接编辑描边宽度与曲率，但细节还需要人工修正。

## 第四步：组合导出和独立质控

```bash
python scripts/build_vector_package.py \
  --project work/my_figure --out work/export --include-source-project
```

该命令将生成组合/拆解 SVG、PNG、颜色/图层清单、局部及整图差异图、`quality_report.json`、ZIP 等；默认禁止视觉质控失败的正式 ZIP。`--include-source-project` 额外打包源图、原始蒙版、实例标注、实例报告及中心线报告，有助可重复审计；**可能含患者资料，仅在知情且符合机构数据规定时使用**。

`quality_report.json` 会提供 `guided_segmentation_summary` 和 `centerline_trace_summaries`。其中 IoU 是**线条重建对其输入蒙版的匹配**，不是医学解剖准确性指标；整图 MAE 不能证明关键小电极正确。必要时为关键神经、电极触点、端点设置 `qa.key_regions`，在 Illustrator 手动查看每个路径的端点与遮挡。

## 质量门禁和失效行为

| 场景 | 处理 |
|---|---|
| 同色不同对象但位置分开 | 不同标注/种子生成独立蒙版 |
| 前景点跨越电极与神经两种颜色 | 默认报错，必须重新落点或明确多色模式 |
| ROI 上下边缘裁断神经 | 标记 ROI 边界接触，需要扩大 ROI/人工重画 |
| 神经 Y 形分叉 | 保留多个开放路径，标记结点和分支数 |
| 交叉导线 | 保留拓扑“交叉点”，不自动指定线缆连通意义 |
| 源蒙版与 stroke IoU 不达标 | 禁止自动替换 manifest；可保留蒙版封闭轮廓作为保真 fallback |
| 线型蒙版只有独立噪声点 | 报错，不伪装为有效中心路径 |
| 区域严重色差/重要局部遗漏 | `build_vector_package.py` 拦截正式文件包 |

## 自动化覆盖边界

- 的算法提供**实例的可复现辅助分割**，不是通用 prompt-driven 基础模型（SAM/SAM2）或医学结构分类器；未包含第三方模型权重，也没有声称能无监督分辨解剖结构。
- 该管道适合**人工/视觉模型先确定坐标与语义，再使用本地可复现代码去描摹**。阴影渐变、重叠接触、变宽线条尤其需要人工修正。
- AI 原生格式只能由实际 Adobe Illustrator 创建与核验，SVG 分组不保证 AI 原生 Layer 组织。
