# 本地权重与批处理 / Local weights and folder processing

## 配置模型 / Configure a model

先安装官方 Meta SAM2 和匹配的 PyTorch / torchvision，参见 [SAM2 安装说明](https://github.com/facebookresearch/sam2#installation)。本机验证使用 PyTorch 2.7.1、torchvision 0.22.1 和 Apple MPS。模型依赖为可选安装，基础 requirements 不包含权重。

Install official Meta SAM2 and compatible PyTorch/torchvision first. The local smoke test used PyTorch 2.7.1, torchvision 0.22.1, and Apple MPS. Weights and optional model dependencies are not bundled with the Skill.

```bash
python3 scripts/configure_sam2.py --checkpoint /path/sam2.1_hiera_base_plus.pt --config configs/sam2.1/sam2.1_hiera_b+.yaml --device auto
```

配置默认保存在 `~/.config/layertrace/sam2.json`；设置 `XDG_CONFIG_HOME` 时使用其对应目录。可用 `LAYERTRACE_CONFIG_HOME` 指定共享配置文件夹。已有 Codex 配置仍可从 `CODEX_HOME/skill-config/illustrator-precision-vectorizer/sam2.json`（默认 `~/.codex/`）读取；显式 `LAYERTRACE_CONFIG_HOME` 优先。权重保留在原位置，显式模型参数优先于保存设置。

Settings default to `~/.config/layertrace/sam2.json`, respecting `XDG_CONFIG_HOME`. Set `LAYERTRACE_CONFIG_HOME` to share a configuration folder across clients. Existing Codex settings remain readable under `CODEX_HOME/skill-config/illustrator-precision-vectorizer/sam2.json` (default `~/.codex/`); an explicit `LAYERTRACE_CONFIG_HOME` takes precedence. Weights stay in their original location; explicit model flags override saved settings.

## 已有工程 / Existing projects

输入目录的直接子目录各包含一个 `manifest.json`，使用已有独立路径或蒙版导出，无需模型：

Each immediate input subdirectory must contain `manifest.json`. Existing paths and masks are exported without requiring a model:

```bash
python3 scripts/batch_vectorize.py --projects /path/projects --out /path/new-batch-export
```

## 图片与标注 / Images and annotations

`--images` 支持 PNG、JPEG、TIFF、WebP、BMP 和基础 SVG，扫描一层目录。位图 `figure.png` 使用 `figure.png.annotations.json`；`--annotations` 省略时在图片目录查找。不同扩展名的同名图片独立处理。基础 SVG 初始化后已有路径时直接导出。

The image mode scans one directory level for PNG, JPEG, TIFF, WebP, BMP, and basic SVG files. Raster image `figure.png` uses `figure.png.annotations.json`. Without `--annotations`, sidecars are read from the image directory. Files with the same stem but different extensions get separate output directories. Basic SVGs with imported paths proceed directly to export.

```bash
python3 scripts/batch_vectorize.py --images /path/images --annotations /path/annotations --out /path/new-batch-images
```

标注必须按每张原图确认。以下坐标只展示格式，使用时替换为实际值。`bbox` 为 XYWH；SAM2 内部接收转换后的 XYXY，使用官方像素坐标变换。可选 `background` 是操作者确认的背景色，不自动猜测复杂背景。以下 `batch_background*` ID 为程序保留。

Confirm annotations against each reference image. The coordinates below illustrate the format only. `bbox` is XYWH; the adapter converts it to XYXY and applies the official pixel-coordinate transform. Optional `background` declares an operator-confirmed background color. Complex backgrounds are not inferred. The `batch_background*` IDs are reserved.

```json
{
  "background": "#FFFFFF",
  "instances": [
    {
      "id": "part_01",
      "name_zh": "已确认部件",
      "name_en": "Confirmed component",
      "profile": "generic",
      "bbox": [80, 60, 160, 180],
      "fg_points": [[150, 140]],
      "bg_points": [[20, 20]],
      "max_area_fraction": 0.65
    }
  ]
}
```

缺少标注时只初始化项目并标为 `needs_annotations`。所有可见部件和背景仍需正确建立；一个目标的模型分割成功，不代表整幅图已经完整重建。

Missing annotations produce an initialized project marked `needs_annotations`. All visible components and the background still need to be represented correctly. Segmenting one target does not establish that the full illustration has been reconstructed.

## 输出与状态 / Outputs and status

每个文件或工程使用独立子目录，含 `process.log` 和 `export/`；图片模式还保留 `project/`。输入原图与工程保持不变。输出根目录必须为空，并位于输入目录外。默认顺序处理，一项失败继续下一项。每项结束后更新 `batch_summary.json` 和 `batch_summary.csv`。

Each item gets a separate directory containing `process.log` and `export/`; image mode also retains `project/`. Inputs remain unchanged. The output root must be empty and outside the input directory. Processing is sequential, continues after individual failures, and updates JSON/CSV summaries after each item.

| Status | 含义 / Meaning |
| --- | --- |
| `success` | 已导出且自动质检通过 / Exported with automatic quality gates passed |
| `draft` | 显式使用 `--allow-draft` 导出的未通过草稿 / Exported under explicit draft permission; quality gates failed |
| `needs_annotations` | 已建工程，缺少逐图标注 / Initialized project needs image-specific annotations |
| `failed` | 初始化、推理或导出失败；日志保留原因 / Initialization, inference, or export failed; see the log |

出现 `failed` 或 `needs_annotations` 时退出码为 1；参数无效时为 2。若需要失败草稿，显式添加 `--allow-draft`；它仍会记录为 draft，不会伪报通过。`sam2_executed` 为 `null` 表示推理步骤异常，尚不能确认完成。

The exit code is 1 when any item failed or needs annotations, and 2 for invalid arguments. Add `--allow-draft` only when failed-quality drafts are wanted; they remain labelled draft. A null `sam2_executed` means the inference step failed before completion could be confirmed.

## 验证 / Validation

```bash
python3 scripts/batch_tests.py
```

检查失败后继续、原图和工程不变、不同扩展名隔离、输出保护、草稿状态、配置覆盖。真实权重链路另见 [本机验证记录](sam2-validation.json)：两张合成图使用 SAM2.1 base-plus 在 MPS 上完成分割和导出，不是通用医学插画精度基准。

The checks cover failure continuation, unchanged inputs, extension isolation, output protection, draft labelling, and model overrides. The separate local validation record documents two synthetic images processed with actual SAM2.1 base-plus weights on MPS. It is not a general medical-illustration accuracy benchmark.


## 扩展 / extensions

`--input-dir` 允许混合图片和工程；`--recursive` 保留相对目录并跳过工程内部资源。`--ocr` 启用本地 OCR 候选；`--completion-annotations-dir` 读取镜像相对目录下的 `<文件或工程名>.completion.json`。实例侧文件同样保留相对目录与扩展名。详见[补全、OCR 与递归批处理](completion-batch-ocr.md)。

Use `--input-dir` for mixed images and projects, `--recursive` to preserve relative directories while skipping project internals, `--ocr` for local OCR candidates, and `--completion-annotations-dir` for mirrored `<file-or-project-name>.completion.json` sidecars. Instance sidecars also retain relative paths and file extensions. OCR failures appear in `ocr_error` without stopping geometry export; existing reviews are preserved. Input projects are copied before optional stages write review files.
