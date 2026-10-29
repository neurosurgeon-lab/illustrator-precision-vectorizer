# 可见遮挡关系与语义图层重建（工程技术约束）

## 新增能力与真实性边界

- 以 **已独立建立的矢量路径/蒙版** 为输入，根据前后顺序约束构建有向无环图（DAG），可复现地计算后→前对象顺序。
- 保守分析两个已绘制对象在参考图中的**可见重叠区域**：仅在二者透明度足够高、色彩可区分、没有第三个前景物体、距离边界不近且原图颜色显著支持某一候选时，给出 `strong_appearance_candidate`。它不是医学语义或真实拓扑验证。
- 对同色、半透明、三层重叠、细线遮挡、遮盖区域不可见、接触但不重叠情况标记待复核，不自动连接被挡住的神经、导线或电极。
- 同一逻辑层在 z-order 中被其他层插入时，创建多个实际 SVG display layer run，保留 `data-original-layer-id` 和源逻辑组归属。独立对象 ID/颜色/路径不合并。
- 输出两种可审计材料：`15_Occlusion_Review.png`（绿色=已有约束的局部重叠，橙色=可见外观候选，红色=未判定重叠），`16_Occlusion_Stack.svg`（前→后显示顺序），`17_Occlusion_Report.json`（图约束、对象可见比例及未决问题）。这些不等于医学结构连接的事实。

## Manifest 配置

原有 `schema_version: "1.0"` 不需要升级。可在 manifest 根部增加：

```json
{
  "occlusion": {
    "constraints": [
      {"behind": "vagus_nerve", "front": "electrode_01", "source": "user_confirmed"},
      {"behind": "cable_01", "front": "device_case", "source": "source_vector"}
    ],
    "exclude_from_inference": ["background"]
  },
  "qa": {"require_resolved_occlusions": true}
}
```

每个 `front` / `behind` 必须是已存在的独立 object ID。方向固定 `behind → front`；循环边、重复边、未知 ID、缺少来源记录会报错。`source` 是记录数据来源，不能仅因填写 `user_confirmed` 而宣称医学审核真正执行；用户应实际检查。对完全看不见的隐藏段，不要自动创建路径：如果仅在原始矢量文件中存在可编辑完整路径，建议设置 `geometry_provenance="source_vector"`；如果由用户提供完整路径可设置 `"author_supplied_vector"`；如果出于编辑目的推断补画，保留 `inferred_hidden=true` 并写入 QA 的 unresolved_details。所有已作者绘制的隐藏几何均须审阅。

## 执行命令

```bash
# 先生成遮挡分析；默认不改动图层和 Manifest
python scripts/occlusion_layers.py --project /path/project --out /path/occlusion_review

# 人工审核 15、16 及 occlusion_analysis_report.json，再将已确认关系写入 occlusion.constraints。
# 如果明确接受颜色证据候选（仍不是解剖认证），可以显式调用：
python scripts/occlusion_layers.py --project /path/project \
  --accept-candidates --write-manifest

# 之后进行已有完整 SVG 导出，编辑 Manifest 有遮挡字段即启用遮挡检查。
python scripts/build_vector_package.py --project /path/project --out /path/export

# 若配置 qa.require_resolved_occlusions=true，任何未明确约束的显著重叠都会阻止 ZIP。
# 诊断材料仍输出，但不能把 QA 失败草稿称为合格：
python scripts/build_vector_package.py --project /path/project --out /path/export_draft --allow-draft
```

不推荐在复杂医学结构上自动运行 `--accept-candidates`。人工先确认 SAM2/GrabCut 独立蒙版准确，再检查连接、前后关系和明确的遮挡结束点。想强制所有工程生成重叠分析，运行导出器 `--analyze-occlusion`；未配置遮挡关系时的旧 导出保持原有行为。

## 定量验收及禁用自动断言的场景

1. 面积/遮挡：报告每个**已经绘制** SVG 对象的 `authored_pixel_count`、`opaque_occluded_pixel_count`、`estimated_visible_pixel_count` 和遮挡比例。背景通常被排除在颜色推断之外但仍可计入可见面积。
2. 重叠颜色判据：仅将高 Alpha、不在 AA 边缘、恰好两层、至少 12 个有效像素且参考图明显更接近上方对象的交叉认定为**候选**；三层和小于阈值的细导线交叉不能进行肯定判断。
3. 图约束：每条明确边必须在最终合成 SVG 的 z-order 中得到满足。存在有向环时**提前失败**，不写回 Manifest。
4. 受控写回：`--write-manifest` 必须和显式 `--accept-candidates` 同用。未通过校验则不得修改原始 Manifest；候选写入后均标记 `review_status: not_anatomically_verified`。
5. 严格门禁：`qa.require_resolved_occlusions` 可以阻止未明确排序的显著重叠直接打包，但即使所有门禁通过，`quality_report.json` 的 `release_ready` 仍为 false，必须人工及 Illustrator 实测核验。
6. 半透明渐变、跨多像素复杂抗锯齿、阴影透明叠加、多个路径交汇和被完全遮盖的线条**不可仅凭当前输入推断**。建议保持可见段，不自动补全。
7. `15_Occlusion_Review.png` 是重叠区域复核底图，不是医学解剖标注；`16_Occlusion_Stack.svg` 是层级文字总览，不能代替 Illustrator 原生 AI 测试。

## 测试与示例

```bash
python scripts/occlusion_v24_tests.py
python examples/create_occlusion_v24_demo.py --out /tmp/occlusion_demo
```

演示采用**作者预先知道全路径**的非临床医学风格合成图，验证排序重建，不证明真实隐藏结构可由图片恢复。演示输入初始 Manifest 排序错误，用户已确认的三条约束使最后图层顺序正确。源图与输出渲染 0 RGB MAE 的指标只适用于此合成几何，不能代表 SAM2、临床神经解剖或一般插画的准确度。
