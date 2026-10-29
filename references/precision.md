# 亚像素保真、Bézier 控制点及变线宽重建规范

## 能力边界

这两个模块均不训练/调用语义识别模型，也不判断器官、神经或电极的医学归属。输入必须是已经逐实例确认且位置正确的二值 `mask_png`；神经分叉、隐藏走行、图像抗锯齿之外的细节必须人工确认。

## A. 亚像素轮廓 `scripts/subpixel_bezier.py`

- RGB 平涂：在已确认 mask 内外的安全样本计算两种代表色及离散度；用原图 RGB 到两色连线的投影估计像素覆盖率，要求色差足够大、颜色离散度低，禁止照片与大面积渐变自动修补。
- Alpha：源图确有透明抗锯齿时直接利用原始 alpha。只有二值透明时不会凭空推断半像素位置。
- 局部约束：仅调整原 mask 边缘附近像素，不移动内部医学结构，不连接未相邻的部件，不自动填洞。
- 在 `scale=2/3/4` 超采样网格中生成二值轮廓；候选包括低简化折线和带角点保护的闭合三次 Bézier，采用 IoU、双向边界距离、孔洞数量和连通分量数同时验收。合格路径以锚点数最少为首要标准、交并比作为次级标准；不合格时原蒙版保持不变。
- 默认阈值：`--min-native-iou 0.975`、`--min-super-iou 0.94`、`--max-boundary-px 1.0`，这并非所有图片的最佳条件。小孔/细线对 IoU 特别敏感，应该调整标注或手描，放宽阈值必须有书面说明。
- 超采样分辨率不是“无损放大”或真正像素级测量；RGB 原图里的抗锯齿本身已由上一轮栅格化决定。

报告：`subpixel_<id>_report.json`；预览：`subpixel_<id>_preview_<scale>x.png`。

## B. 变线宽 `scripts/variable_width.py`

- 8 邻域骨架中心图提取每条可见路径，距离变换估计局部半径；沿图像路径平滑半径，形成左右外沿及圆端帽的封闭矢量轮廓。
- 对若干全局宽度因子进行渲染试验，选取与原始 mask IoU 最高的候选，并与单一 stroke width 基线比较。默认 QA：IoU≥0.80 与双向边缘 95 分位≤2.5 px。
- 中心线、逐点 `width_samples_px` 和可见填色 outline 均保留。生成 SVG 中可编辑的可见路径及不可见 guide path；导出的 `14_Variable_Width_Profiles.json` 能让后续工具重建宽度分布。
- **不是** Illustrator Width Tool 原生宽度曲线；原生 AI 变线宽须通过 Illustrator API/插件另行转换并实际打开检查。复杂分叉的宽度重叠、交叉遮挡必须人工审核。
- 不会擅自连接被遮挡的两个可见片段。细线尖端、宽度突变、复杂交叉可能低于数值门限而回退原始蒙版。

报告：`variable_width_<id>_report.json`、`variable_width_<id>_preview.png`。

## QA 与复现

运行：

```bash
python scripts/validate_skill.py
python scripts/self_test.py
python scripts/regression_tests.py
python scripts/instance_centerline_tests.py
python scripts/sam2_integration_tests.py  # mock adapter, NOT SAM2 true inference
python scripts/precision_v23_tests.py
python examples/create_precision_v23_demo.py --out /tmp/precision_v23_example
```

2026-10-29 的合成非临床例子：主体轮廓 Bézier 32 锚点，native mask IoU 0.9901；独立带孔装置 IoU 0.9500（示例显式放宽到了 0.94，默认阈值不变）；变宽神经样曲线 mask IoU 0.9543，对照统一线宽 IoU 0.7472，+0.2071；完整组合 RGB MAE 0.2386/255。结果是**同一示例的自洽几何重建指标**，不是 SAM2 的分割 IoU，也不能证明复杂真实医学插画 1:1 复刻。

数值通过仍需要检查人体解剖、边界闭合、颜色和遮挡关系。保留源像素与报告；不要声称已生成 AI，除非 Illustrator 真正创建并验收原生文件。
