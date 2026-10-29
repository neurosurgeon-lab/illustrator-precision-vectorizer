# LayerTrace V1.1

2026-10-29 · 发布标签：`v1.1.0`

## 发布整理与客户端兼容

Skill 名称：`layertrace`；展示标题：LayerTrace — Precision Image-to-Vector Skill。

将参考图片精确拆解为可编辑的分层矢量图，支持 1:1 轮廓复刻与 SVG 导出。

- 移除用户图像、重建结果、预生成示例、原始需求记录及历史版本展示。
- 提供 Codex、Claude Code、Cursor、Gemini CLI 的安装目录和使用说明；其他本地代理可直接读取 `SKILL.md`。
- 模型配置使用通用目录，支持 `LAYERTRACE_CONFIG_HOME` 与 `XDG_CONFIG_HOME`，兼容已有 Codex 配置。
- 客户端接入依据官方文档；逐客户端的端到端绘制尚未实测。

## 连续平滑线条成为最终交付条件

修正旧流程允许自动像素边界和骨架碎线通过编辑检查后直接交付的问题。人物、面部、手指、衣褶、器官和导线须逐对象对照原图、彩色图、纯线稿及至少 400% 放大图；非预期断裂、锯齿、碎线与折点必须先修复。原图虚线、遮挡断开和真实尖角保持原样。

- 新增 `--require-line-quality-review` 和 `qa.require_line_quality_review: true`；Skill 最终交付必须启用，新建工程和 manifest 模板默认开启。旧命令行保持兼容，关闭严格审核时明确记录 `not_reviewed`。
- 新增 `26_Line_Quality_Report.json` 和自动 4 倍预览。工程内 `line_quality_review.json` 须覆盖所有可见几何对象，审核与原图及 SVG 的 SHA-256 绑定。
- 缺少审核、漏对象、错误布尔值、低于 4 倍或文件哈希失效时，不生成正式 ZIP。只有用户明确要求草稿时才允许 `--allow-draft`，报告保留失败状态。
- 默认保留校对后的真实文本，核对字体、字重和位置；用户要求转曲时才交付文字轮廓。
- 新增针对低像素误差却未审核、审核遗漏/失效、4 倍预览、显式草稿和 manifest 开关的回归测试。

检查器验证审核覆盖与时效，视觉核查负责识别线条缺陷；不宣称自动识别或消除所有断裂、锯齿。此次未改动分割和曲线拟合算法，极细补全候选仍可能缺少闭合轮廓。公开包不包含用户原图、重建结果、示例数据或个人配置。

下载 `layertrace-skill-v1.1.0.zip` 与 `SHA256SUMS.txt`。先备份旧技能再替换，模型权重和个人配置不随安装包发布。审核流程见 [line-quality.md](references/line-quality.md)。

## English release notes

This package removes user artwork, reconstruction results, pregenerated examples, original request records, and old release labels. Installation instructions cover Codex, Claude Code, Cursor, and Gemini CLI. Model settings use a client-neutral location with explicit overrides and existing Codex configuration compatibility. Per-client end-to-end drawing has not been tested.

V1.1 makes continuous, smooth, source-faithful lines a final-delivery requirement. Pixel boundaries and skeleton fragments must be refined and inspected per object using color, linework, and at least 400% views. Preserve intentional dashes, occlusions, and corners.

The skill requires `--require-line-quality-review` or `qa.require_line_quality_review: true`; new projects and the manifest template enable it. Strict exports generate a 4x preview and `26_Line_Quality_Report.json`, and withhold the final ZIP until a complete `line_quality_review.json` matches the current source/SVG SHA-256 hashes. Missing objects, non-boolean approvals, insufficient scale, or stale hashes block delivery. Explicit drafts retain failed status. Legacy CLI exports remain compatible and report `not_reviewed` when strict review is disabled.

Reviewed live text is the default. New regressions exercise the review gate independently of image similarity. The checker validates review coverage and freshness, not automatic defect recognition; segmentation and fitting algorithms are unchanged. The earlier thin-completion limitation remains. User artwork, reconstruction results, example datasets, and personal settings are excluded.

Install `layertrace-skill-v1.1.0.zip` after backing up the existing skill. Weights and personal settings are excluded.
