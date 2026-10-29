# 可视化交互精修工作台（本地浏览器）

## 适用对象与能力边界

本工作台是 **已有 project/manifest.json + 独立 SVG Path / PNG Mask 的编辑器**，不是新的自动医学语义识别模型，也不会把 JPEG 一键变成独立、准确的医学结构。需先用实例分割工具、SAM2（需要真实权重）或人工描摹建立部件，再在界面里修正。

Python 标准库 HTTP Server 本地绑定 `127.0.0.1`，前端由 `webui/index.html`、`webui/app.js`、`webui/style.css` 构成，不使用网络 CDN。参考图不允许在工作台写入。不会上传云端；对包含患者敏感信息的原图仍需遵守本地数据安全管理规定。

## 安装与启动

```bash
python -m pip install -r requirements.txt
python examples/create_interactive_v25_demo.py --out /tmp/medical_studio
python scripts/interactive_studio.py --project /tmp/medical_studio/project --port 8765
# 自动打开本地浏览器；如自动打开失败，手动访问 http://127.0.0.1:8765/
```

真实工程：

```bash
python scripts/init_project.py --image /path/figure.png --out /path/project
# 先建立每个部件的真实 mask/path + manifest（人工或实例分割工具）
python scripts/interactive_studio.py --project /path/project
```

选择左侧独立对象，然后：

1. **选择 / 显隐**：点选左侧或画布路径，眼睛按钮只影响查看状态，不会改变交付图层。
2. **增补/擦除 Mask**：选择 `＋ 蒙版` 或 `－ 蒙版`，设置像素半径后在画布拖动画笔；每个笔画写入 PNG 并生成可撤销快照。默认保持连通分量数和孔洞数，涉及医学分支连接时若确需修改，必须明确勾选“允许拓扑变化”；这不代表解剖学审核通过。
3. **路径节点与 Bézier**：对没有 transform 的 `svg_path`，在 `路径节点` 模式拖动锚点/控制点，支持绝对 M/L/C/Q/Z 的基本路径。含相对命令、椭圆弧 A、H/V/S/T 的路径**保持原样、不允许可视化拖点**，但可在源码框中编辑整个 SVG d，服务器做渲染与长度安全检查。蒙版可按按钮显式转成 SVG 路径，原始 mask 文件保留，转化可撤销。
4. **填色/描边/透明度**：直接填 HEX（`#FDEEE7`）或 `none`，调整描边宽度/透明度后点击保存；对象独立，色号不被自动替换。
5. **遮挡关系**：选择后方部件和前方部件，确认约束后写入 Manifest。DAG 环路、非法对象立即拒绝；不推断不可见神经连接。左侧列表按照导出时的最终图层顺序展示。
6. **放大观察**：使用顶部放大/缩小，或 Ctrl/⌘+滚轮；可切换原图、轮廓叠加、最终矢量或单独蒙版。
7. **撤销/重做**：点击顶部按钮（或 Ctrl/⌘+Z）；状态快照保存在项目的 `.v25_history/`，最多保留最近 48 次状态，且跨服务器重启保留。
8. **正式导出**：点击“导出 SVG / ZIP”。会实际运行 `build_vector_package.py` 完整 QA。质量不合格时默认不生成正式 ZIP；只有主动勾选“允许导出明确标注 FAIL 的草稿”，才加 `--allow-draft`，并仍以质量报告为准。

### 文件结构

- `project/manifest.json`：对象属性、路径及遮挡约束；唯一权威项目说明。
- `project/masks/*.png`：经编辑后的独立蒙版；参考图 `source*` 不变。
- `project/.v25_history/*.zip`：每次修改的本地快照，可撤销/重做；可能包含原图相关的对象形状，请妥善存储。
- `project/exports_v25/export_时间_修订/`：实际 SVG、拆解图 PNG、质量报告和 ZIP。

### 工程/安全限制

- 建议**每个项目同一时间只运行一个工作台进程**，避免多个独立进程相互覆盖；同一进程内多标签页提交使用版本号检查。禁止将本地服务通过反向代理公开到公网。
- 工作台仅绑定本机 `127.0.0.1`，限制 POST 来源、请求体大小、路径越界和非法 SVG d。它是单用户科研辅助工具，不是有身份认证的多人协作系统。
- 节点编辑只支持目前列明的 SVG 基本指令。`mask_png` 的自动转换会以忠实折线为安全基线，不保证自带 Bézier 曲线。
- 界面**不直接提供 SAM2 在线推理、AI 原生 `.ai` 保存、智能未知结构自动分层**；这三项仍依赖外部模型 / Adobe Illustrator 或人工确认。也不自动推断神经、电极或导线的不可见部分。
- **不要把交互式界面截图当成矢量精度证据**：正式结果应检查原图/复刻叠加、ROI、对象清单、闭合路径、变宽轮廓与遮挡报告。

## 可复现回归测试

```bash
python scripts/interactive_v25_tests.py
python scripts/occlusion_v24_tests.py
python scripts/regression_tests.py
node --check webui/app.js  # 若有 Node.js，非运行时必须
```

新测试覆盖：真实 PNG 笔刷写入、拓扑默认保护/显式允许、路径编辑及渲染检查、颜色修改、图层 DAG 环路拦截、跨进程重启后撤销/重做、版本号竞争拒绝、源图不变、完整导出。浏览器图形交互请另在目标电脑上用 Chrome/Edge/Safari 人工验证。
