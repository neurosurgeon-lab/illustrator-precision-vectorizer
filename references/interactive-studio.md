# 本地一体化工作台：SAM2 提示、局部误差、Illustrator 导入

工作台也会读取已保存的[本地模型配置](batch.md)，并修正原图像素提示坐标变换。新增的[真实权重验证](sam2-validation.json)覆盖本机合成案例；模拟预测器测试与真实权重测试分别记录。

> 适用范围：已包含可独立编辑对象的二维医学/科研插画。它不是 CT/MRI 临床病灶分割工具；不能从图像中的隐藏区推断真实医学结构。

## 工作台启动

```bash
cd ~/.agents/skills/layertrace
python -m pip install -r requirements.txt
python examples/create_interactive_v25_demo.py --out /tmp/studio30
python scripts/interactive_studio.py --project /tmp/studio30/project --no-browser
# 打开 http://127.0.0.1:8765/
```

默认不自动加载模型，也不会访问网络。若已安装官方 Meta SAM2 / PyTorch，请明确选择模型：

```bash
# 本地模型（建议；不会触发权重下载）
python scripts/interactive_studio.py --project /path/project \
  --sam2-config configs/sam2.1/sam2.1_hiera_b+.yaml \
  --sam2-checkpoint /absolute/path/sam2.1_hiera_base_plus.pt \
  --sam2-device auto

# Hugging Face 可选：首次模型加载可能下载外部权重，需要用户主动选择
python scripts/interactive_studio.py --project /path/project \
  --sam2-hf-model facebook/sam2.1-hiera-base-plus --sam2-device auto
```

实际权重/API、硬件和 MPS/CPU/CUDA 兼容需要在目标机器验证。模型懒加载：**首次点击生成候选时才加载，一次 set_image 后复用编码**。本安装包无模型权重，不声称做过真实 SAM2 推理。

## SAM2 点选（先预览、确认后写回）

1. 左侧选择 `mask_png` 对象，例如迷走神经可见部分；不存在对象时需要先建立独立实例，不能自动凭空新建医学语义标签。
2. 选择正点、负点或框选工具，在原图上标注；正确选择 `generic/nerve/lead/electrode/device/body` 类型。
3. 点击 **生成候选蒙版**；后端调用官方 `SAM2ImagePredictor.predict` 并逐候选检查 ROI、前景/背景提示、连接/孔洞与面积极限。没有合格候选会拒绝；模型预测 IoU 不是对原图真值的实测精度。
4. 检查半透明候选覆盖、端点、神经分叉及电极内孔；选择候选。点击 **确认并写回** 才替换目标 PNG，生成历史快照，可撤销。改变连通分量/孔洞必须主动勾选拓扑变更许可。
5. 接受记录追加保存于 `sam2_studio_audit.jsonl`（提示、候选质量预测、掩膜 SHA256 和人工操作确认），**不会把解剖自动审核标成已完成**。

限制：当前工作台 SAM2 只精修既有独立 PNG 蒙版。它不会自动给多个实例创建新对象，不能依据推断补全隐藏解剖。最多 80 个提示点，最大画布 4MP，避免本机误触发大推理。

## 实时差异热图（按需重新计算，非逐帧帧率承诺）

工作台右侧的“重新计算热图”按钮会按当前 `manifest.json` 的路径/图层顺序重新渲染 SVG，与不修改的参考图比较。可选整幅图或当前对象显示边界外扩 12px 的 ROI。

指标包括 RGB MAE（0–255）、alpha MAE、95 分位与最大可见差异、超过选定阈值的像素比例、ROI 像素数。透明图像在白底合成后做可见 RGB 比较，alpha 另外计算。图像以蓝/黄/红局部高误差映射方式叠加，便于定位；有复杂半透明或 ICC 的图像需进一步在 Illustrator 里检查。

**不能把热图误差等同于解剖学准确度、分割 IoU 或医学图像质量。** 当前支持手动点击重新计算，不承诺鼠标拖动同时连续实时计算，避免大尺寸图片卡顿。

## 真正的 Illustrator 原生 Layer：交付限制与操作

在本地完成 SVG 导出并通过 QA 后，工作台会在导出文件夹下生成 `18_Illustrator_Import/`，并将其加入 `08_All_Files.zip`，其中有：

- 逐对象透明 SVG：`object_0001.svg`…，每个对象占完整原画布尺寸
- `illustrator_import_manifest.json`：从后到前的层级排序、语义名称和原位置
- `import_v30.jsx`：用于桌面 Adobe Illustrator 的 ExtendScript
- `README_IMPORT.txt`：本地操作及人工验证说明

你也可单独执行：

```bash
python scripts/illustrator_import.py --project /path/project \
  --out /path/empty_illustrator_import_dir
```

然后在本机 Illustrator 里 **File → Scripts → Other Script** 选择 `import_v30.jsx`。脚本尝试创建新文档、逐对象导入 SVG、使用 Copy / Paste in Place 添加到各自原生 Layer、检查导入项与图层数量，再使用 `IllustratorSaveOptions` 保存 `Native_Illustrator_v30.ai`。有任何导入失败时不输出成功标记。需在 Illustrator 真正运行后才可能获得 `.ai` 文件；**不能因为 Python 生成了 JSX 就宣称 `.ai` 已生成或已校验**。

粘贴定位与单位换算可能因 Illustrator 版本、SVG 参数、系统配置而异。脚本只是一个待桌面验收的自动化路径。务必检查：画布大小、对象相对坐标、每根导线独立选择、颜色、透明、裁切、线帽、电极孔洞、变线宽填色路径与参考图叠加。Importer 没有对源路径进行位图化，也不会把隐藏中枢线变成 Illustrator Width Tool 配置。

## 安全与复现

- 工作台只监听 `127.0.0.1`；POST 拒绝不受信任的来源。
- 参考图 SHA 校验，拒绝外部更改后继续编辑；并发编辑使用修订号防止覆盖。
- SAM2 候选保存在内存中，编辑/撤销后旧候选失效，不允许跨对象写入。
- 不发送参考图至云端（显式启用 HF 权重下载时，会访问权重源，但本地图片不会作为 API 请求上传）。
- 桌面 AI 的验证不能在没有 Illustrator 的运行环境中冒充完成。

## 测试

```bash
python scripts/studio_v30_tests.py
python scripts/interactive_v25_tests.py
node --check webui/app.js
```

`studio_v30_tests.py` 中的 SAM2 使用可注入的 **FakePredictor**，只测接口、提示、候选保护、写回/撤销；**没有运行真实 SAM2 权重**。Illustrator JSX 仅静态存在性及对象拆分导出校验，**没有桌面 Illustrator 运行验证**。
