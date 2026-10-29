# V1.1 连续平滑线条：最终交付必读

## 修复与核查

像素蒙版边缘和骨架图经常保留阶梯噪声、伪分叉、短碎线；简单换成 SVG 不会消除这些缺陷。先按原图识别每条可见线，再整理少量贝塞尔段。连续光滑段共享端点并匹配切线方向；在原图实际尖角处分段。保留原图轮廓、姿态、遮挡、物件和颜色，不能用平滑替代保真。

逐部件查看原图、彩色 SVG、纯线稿和至少 4 倍放大图：

- 人物头发、脸颈、耳廓、鼻唇、手掌、每根手指、衣领和衣褶；器官边缘与内部线；设备和导线接头。
- 原图连续的线没有断点、孤立碎线、像素阶梯、尖刺和非预期折点；轮廓与填色贴合，没有双重错位边缘。
- 虚线、自由端点、遮挡下的分段、独立部件之间的空隙和真实尖角与原图一致，不得擅自连接或圆化。
- 彩色图中被填色掩盖的问题仍须在线稿中检查。有 Illustrator 时，保存回读后的 AI 预览也须放大核对。

发现缺陷后修复源路径并重新核查；不能靠全图低 MAE、路径数量、`stroke-linejoin="round"` 或“AI 可编辑”代替。

## 启用阻断

最终交付统一使用严格模式；已有命令行兼容旧项目，未开启时报告只能为 `not_reviewed`，不得宣称通过本标准。manifest 可持久设置 `qa.require_line_quality_review: true`；命令行标志始终强制执行。

```bash
python3 scripts/build_vector_package.py --project /path/project --out /path/review-pass --require-line-quality-review
```

首次运行保留 SVG、诊断文件、4 倍预览和 `26_Line_Quality_Report.json`，返回 2，不生成最终 ZIP。执行代理实际查看这些材料后，在工程目录写入 `line_quality_review.json`：

```json
{
  "source_sha256": "COPY_FROM_26_LINE_QUALITY_REPORT",
  "svg_sha256": "COPY_FROM_26_LINE_QUALITY_REPORT",
  "reviewed_scale": 4,
  "reviewer": "codex_visual_review",
  "objects": [
    {
      "object_id": "USE_EACH_REQUIRED_OBJECT_ID",
      "no_unintended_gaps": true,
      "no_jagged_edges": true,
      "source_matched": true,
      "notes": "Record any source-intended corner, gap or dash here."
    }
  ]
}
```

必须逐项覆盖报告中的 `required_object_ids`，包括填色形状的边界。仅在实际检查通过后将相应字段设为 JSON 布尔 `true`；不提供自动批准脚本。发现问题时保留 `false`，修复后重新生成待审核文件和哈希。

然后以同一源工程导出到新目录：

```bash
python3 scripts/build_vector_package.py --project /path/project --out /path/final-pass --require-line-quality-review
```

审核缺失、漏对象、值为字符串 `"true"`、放大倍数不足、原图或 SVG 哈希变化均阻断最终 ZIP。审核记录只与当前文件对应，编辑后须重新核查。检查器验证审核覆盖与时效，**不自动识别所有断裂或锯齿**；通过状态表明当前文件有完整视觉审核记录，不能伪称数学证明。

自定义源文件脚本可直接调用 `scripts/line_quality.py` 的 `inspect_line_quality(svg_bytes, elements, source_sha256, review_path, required=True)`；`elements` 为唯一对象 ID 到实际 SVG 组的映射。报告失败时保留诊断，禁止打正式 ZIP。实际图层和文字检查与此门禁分别完成。

`--allow-draft` 只供用户明确要求草稿时使用，报告保留失败状态。未通过时不将草稿复制、命名或描述为最终版。
