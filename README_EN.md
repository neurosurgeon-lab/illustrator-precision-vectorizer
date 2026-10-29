# LayerTrace — Precision Image-to-Vector Skill

[English](README_EN.md) | [简体中文](README.md)

Current version: **1.1.0** ([changelog](CHANGELOG.md) · [Releases](https://github.com/neurosurgeon-lab/illustrator-precision-vectorizer/releases)).

Precisely decompose reference images into editable layered vectors, supporting 1:1 contour tracing and SVG export.

This portable AI Agent Skill guides object identification and contour tracing. Its companion scripts assemble curated object paths or individual masks into a vector file package.

## V1.1: Required Continuous and Smooth Line Review

Compare each person, face, finger, clothing fold, organ, and wire against the reference using color, linework, and at least 400% views. Repair unintended gaps, staircases, fragments, and sharp joins. Preserve source-intended dashes, occlusions, and corners.

New projects and the manifest template require strict review by default. Final skill deliveries use `--require-line-quality-review` or `qa.require_line_quality_review: true`. The first export retains a 4x preview and `26_Line_Quality_Report.json`. After actual per-object inspection, record the review and export to a fresh directory. Missing/incomplete reviews or changed source/SVG hashes block the final ZIP. Legacy CLI exports remain compatible but report `not_reviewed` when strict review is disabled.

[Review workflow and schema](references/line-quality.md). The gate validates review coverage and freshness; visual inspection identifies defects. It does not automatically detect or eliminate every gap or jagged edge. Reviewed editable text is the default.

## What's Included in - Default to clear Bézier outlines, visible open strokes with editable widths, and separate fills. Organize actual parts into named layers/groups and validate a complex example before processing a batch.
- Export dedicated linework and an editing-structure report. Required wire IDs must retain visible open strokes; filled silhouettes and hidden reference guides cannot satisfy the contract, even when image similarity passes.
- Save and verify native Illustrator files through a portable JSX bundle or the macOS runner. Create real layers, save color/linework AI, reopen files, and test stroke-width and anchor editing when open strokes are expected.
- Retain SAM2, local weights, batch processing, the studio, OCR, and reviewed completion. Editing structure and pixel fidelity have separate results. The package contains no user artwork, example datasets, or personal settings.

## Completion, OCR, and Recursive Processing

- Gap and notch proposals: inspect fragments, short gaps, and small contour notches, then review candidates before including additions in isolated objects.
- Modal/Amodal exports: preserve the visible illustration; add approved hidden regions only under declared occluders using endpoints, a guide polyline, or a polygon. Separate review sheets identify inferred additions.
- Local OCR: recognize text, boxes, and confidence scores. Only corrected and explicitly approved entries become editable SVG `<text>` in the full illustration, breakdown, and Amodal sheet.
- Extended batch processing: mixed images and projects, recursive directories, optional OCR, and external completion annotations. Shared model settings, the SAM2 coordinate fix, input protection, and JSON/CSV statuses are retained.

## Folder Processing and Local Weights

- Folder processing: export existing layered projects or run SAM2 on images with per-image annotations. Each item has separate outputs, failures do not stop later items, and JSON/CSV summaries track outcomes.
- Local model settings: the single-image CLI, studio, and batch command share a per-user checkpoint selection. Weights are neither copied into the repository nor bundled with releases.
- Fixed real SAM2 pixel-coordinate handling: original-image XY prompts now use `normalize_coords=True` in both the CLI and studio.
- Actual SAM2.1 base-plus weights were tested on Apple MPS with two batch images and a studio candidate preview. See the [validation record](references/sam2-validation.json).

## Integrated Local Studio

- Local interactive studio: select objects, add or erase mask regions, edit path nodes and Bézier handles, adjust colors and occlusion order, and save, undo, or redo changes.
- Interactive SAM2 proposals: generate candidate masks from positive points, negative points, or boxes, then write back only after explicit selection and confirmation. Model setup is separate.
- Local and full-canvas difference heatmaps: re-render the current project and compare RGB and alpha to locate areas needing refinement.
- Subpixel and variable-width tools: retain boundary refinement, Bézier fitting, and editable filled outlines for variable-width structures.
- Occlusion ordering: retain explicit ordering constraints, cycle detection, candidate review, and layer reordering.
- Illustrator import preparation: generate per-object SVGs, a manifest, and a JSX importer for creating native layers in desktop Illustrator.


## Retained Vectorization Features

- Optional Meta SAM2/SAM2.1 adapter: segment individual objects using positive points, negative points, and boxes, with Hugging Face models or local checkpoints.
- Conservative structure postprocessing: check prompts, ROIs, instance separation, and overlaps while preserving holes and visible gaps without inventing hidden connections.
- LAB/GrabCut instance segmentation and centerline extraction: convert confirmed thin-line masks into open SVG strokes with editable widths.
- Stronger vector checks: measure actual object bounds, inspect key regions, RGB/alpha differences, and instance counts, and withhold the final ZIP when quality thresholds fail.

## Installation

Python 3.10 or later is required. Clone the repository into your personal skills directory:

```bash
git clone https://github.com/neurosurgeon-lab/illustrator-precision-vectorizer.git ~/.agents/skills/layertrace
cd ~/.agents/skills/layertrace
python3 -m pip install -r requirements.txt
```

CairoSVG requires the native Cairo library. On macOS, install it with `brew install cairo`. If Python cannot locate the library, point `DYLD_FALLBACK_LIBRARY_PATH` to Cairo's `lib` directory. For other systems, follow the [CairoSVG installation instructions](https://cairosvg.org/documentation/).

Place the folder in a supported skills directory and refresh the client’s skill list.

You can also download `layertrace-skill-v1.1.0.zip` from the [v1.1.0 Release](https://github.com/neurosurgeon-lab/illustrator-precision-vectorizer/releases/tag/v1.1.0). Back up the existing skill directory before replacing it during an upgrade.

## Client Installation

The same skill folder can be read by local agents that support `SKILL.md`. The agent needs image viewing, file access, and Python execution; native AI export also requires desktop Illustrator.

| Client | User directory | Project directory | Invocation |
| --- | --- | --- | --- |
| Codex | `~/.agents/skills/` | `.agents/skills/` | `$layertrace` |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` | `/layertrace` |
| Cursor | `~/.cursor/skills/` or `~/.agents/skills/` | `.cursor/skills/` or `.agents/skills/` | Ask Agent to use the skill by name |
| Gemini CLI | `~/.gemini/skills/` or `~/.agents/skills/` | `.gemini/skills/` or `.agents/skills/` | Ask to use the skill by name |
| Other local agents | The client's skills directory | The client's skills directory | Ask it to read this folder's `SKILL.md` and follow its workflow |

Copy the entire `layertrace/` folder, including `scripts/`, `references/`, `assets/`, and `examples/`. Locations follow the [Claude Code](https://code.claude.com/docs/en/skills), [Cursor](https://cursor.com/docs/context/skills), and [Gemini CLI](https://geminicli.com/docs/cli/skills/) documentation. Validation covers Python tooling and configuration compatibility; an end-to-end drawing session has not been tested in each client. `agents/openai.yaml` is optional Codex UI metadata; other clients use `SKILL.md`. Chat-only clients without local script execution can assist with analysis.

For Claude Code:

```bash
mkdir -p ~/.claude/skills
unzip layertrace-skill-v1.1.0.zip -d ~/.claude/skills
cd ~/.claude/skills/layertrace
python3 -m pip install -r requirements.txt
```

The package contains no user artwork, reconstruction files, or pregenerated example datasets. `examples/` contains only generic synthetic-test generators for local use.

## Configure Local Weights

After installing official SAM2 and compatible PyTorch/torchvision, save a local checkpoint selection:

```bash
python3 scripts/configure_sam2.py --checkpoint /path/sam2.1_hiera_base_plus.pt --config configs/sam2.1/sam2.1_hiera_b+.yaml --device auto
```

Settings default to `~/.config/layertrace/sam2.json`, respecting `XDG_CONFIG_HOME`. Set `LAYERTRACE_CONFIG_HOME` to share a configuration folder across clients. Existing Codex settings remain readable under `CODEX_HOME/skill-config/illustrator-precision-vectorizer/sam2.json` (default `~/.codex/`); an explicit `LAYERTRACE_CONFIG_HOME` takes precedence. Weights stay in their original location; explicit model flags override saved settings.

## Folder Processing

Export existing projects whose immediate subdirectories each contain `manifest.json`:

```bash
python3 scripts/batch_vectorize.py --projects /path/projects --out /path/new-batch-export
```

Process images with per-image annotations:

```bash
python3 scripts/batch_vectorize.py --images /path/images --annotations /path/annotations --out /path/new-batch-images
```

Image `figure.png` uses `figure.png.annotations.json`. Missing annotations retain an initialized project marked `needs_annotations`. Each item gets its own project, exports, and log. Processing continues after failures and writes `batch_summary.json` / CSV. The output directory must be empty and outside the input directory. See the [batch guide](references/batch.md) for annotation and background-color declarations.

## Completion, OCR, and Recursive Processing

The normal `build_vector_package.py` export also creates Modal/Amodal files and completion review sheets. Put object-specific settings in the project's `completion_annotations.json`. Inspect proposals before explicitly approving their geometry. Hidden additions are hypotheses, not recovered anatomical facts. See the [completion guide](references/completion-batch-ocr.md) for the JSON schema.

OCR requires optional local dependencies. On macOS:

```bash
brew install tesseract
python3 -m pip install pytesseract
python3 scripts/text_recognition.py --project /path/project --languages eng
```

Correct entries in `text_review.json` using `corrected_text`, set `approved` to JSON `true` for reviewed entries, then export again. Existing reviews are never overwritten. Use `--output /path/new_review.json` for separate candidates; the exporter reads the project's `text_review.json`. Other languages require their Tesseract language data. This release's real OCR smoke test covers synthetic English text only. Inspect fonts, spacing, and baselines, and replace original text geometry to avoid duplicate lettering.

Process mixed input directories recursively:

```bash
python3 scripts/batch_vectorize.py --input-dir /path/input --recursive --out /path/new-export --annotations-dir /path/annotations --completion-annotations-dir /path/completions --ocr --ocr-language eng
```

Sidecars mirror relative paths: `sub/figure.png` uses `sub/figure.png.annotations.json` and `sub/figure.png.completion.json`; project `sub/project` uses `sub/project.completion.json`. Discovery stops at project roots to avoid treating masks and old exports as new inputs. OCR preserves existing reviews; new candidates remain unapproved. OCR failures are reported separately and do not stop geometry export. Review the output project copies, then batch-export them again when ready.

## Start the Local Studio

From the skill directory, create a synthetic demo and start the server:

```bash
python3 examples/create_interactive_v25_demo.py --out /path/new-studio-demo
python3 scripts/interactive_studio.py --project /path/new-studio-demo/project --no-browser
```

Open <http://127.0.0.1:8765/>. To edit your own project, point `--project` to an existing directory containing `manifest.json` and independent objects. The studio listens only on localhost and reads saved model settings or explicit startup flags. The model loads when candidates are requested. Local checkpoints do not trigger weight downloads.

## Use in an AI Agent

Upload a reference image and enter:

```text
$layertrace
Trace the reference image faithfully. Keep each component independently editable and deliver SVG files, a numbered component breakdown, and the complete file package.
```

The workflow covers structural analysis, object separation, outline tracing before coloring, vector assembly, and overlay and difference checks against the source image. When an editable vector source is available, preserve and organize its existing paths first.

## Use the Scripts Directly

Python 3.10 or later is required. Initialize a project:

```bash
python3 scripts/init_project.py --image /path/reference.png --out /path/project
```

Populate `manifest.json` with actual object paths, or prepare individual object masks with the same dimensions as the source image. Then export to a new, empty directory:

```bash
python3 scripts/build_vector_package.py --project /path/project --out /path/output --require-line-quality-review
```

The scripts support manually traced SVG paths and individual PNG masks. Mask contours are converted to polygons; use manually traced Bézier paths for fine curves.

Basic SVG sources can be imported directly to preserve existing paths and create an initial manifest. Unsupported complex SVG features are rejected:

```bash
python3 scripts/init_project.py --image /path/original.svg --out /path/svg_project
```

## Guided Segmentation and Centerlines

Fill in the [instance annotation template](assets/medical-instances.template.json) using actual source-image pixel coordinates, save it as `annotations.json`, and run guided LAB/GrabCut segmentation:

```bash
python3 scripts/medical_instance_segment.py --project /path/project --annotations /path/annotations.json
```

Extract centerlines from confirmed nerve or cable masks. Review the report and preview first, then add `--write-manifest` to update the project:

```bash
python3 scripts/centerline_trace.py --project /path/project --object-id nerve_01 --mode adaptive-bezier --min-iou 0.85
python3 scripts/centerline_trace.py --project /path/project --object-id nerve_01 --mode adaptive-bezier --min-iou 0.85 --write-manifest
```

## Optional SAM2 Integration

The base dependencies do not include SAM2 or model weights. Install compatible PyTorch and SAM2 separately using [Meta's official installation instructions](https://github.com/facebookresearch/sam2#installation). LAB/GrabCut and manual path workflows remain available without a model.

Use the [SAM2 annotation template](assets/sam2-instances.template.json) to specify positive and negative points, `[x, y, width, height]` boxes, and object profiles. For a new project with no existing layers, choose one model source:

```bash
python3 scripts/sam2_medical_segment.py --project /path/project --annotations /path/annotations.json --hf-model facebook/sam2.1-hiera-tiny --device auto
```

Or use local weights:

```bash
python3 scripts/sam2_medical_segment.py --project /path/project --annotations /path/annotations.json --checkpoint /path/sam2.1_hiera_tiny.pt --config configs/sam2.1/sam2.1_hiera_t.yaml --device cpu
```

The Hugging Face option may download weights; the local option requires an existing checkpoint. Outputs include individual masks, `sam2_previews/`, a copy of the annotations, and `sam2_segmentation_report.json`. Inspect these results before extracting centerlines and exporting vectors.

SAM2's predicted IoU is a model estimate. The bundled mock tests do not validate real model accuracy. Medical object names come from human annotations, and the workflow targets two-dimensional scientific illustrations. See the [SAM2 integration guide](references/sam2-medical-postprocessing.md) for deployment and structure-preservation details.

To use local SAM2 weights in the studio, explicitly configure them at startup:

```bash
python3 scripts/interactive_studio.py --project /path/project --sam2-config configs/sam2.1/sam2.1_hiera_b+.yaml --sam2-checkpoint /path/sam2.1_hiera_base_plus.pt --sam2-device auto --no-browser
```

Interactive SAM2 refines existing independent PNG masks. Preview candidates before confirming a write. Editing, undoing, or redoing invalidates old proposals. See the [studio guide](references/interactive-studio.md) for the full workflow.

## Editable Strokes and Native AI

Prepare independent parts and real strokes before export. Declare required wire IDs in `qa.editable_stroke_object_ids`; optional `qa.max_geometry_items_per_object` budgets describe the current drawing. Use masks and color tracing to assist reconstruction, then build clear curves and visible open strokes for the final editing structure.

Try the synthetic example:

```bash
python3 examples/create_editable_v33_demo.py --out /path/new-demo
python3 scripts/build_vector_package.py --project /path/new-demo --out /path/new-export
python3 scripts/illustrator_native.py --svg /path/new-export/01_Full_Illustration.svg --out /path/new-native --run
```

`--run` executes an installed Illustrator on macOS. Omit it to prepare a portable directory, then run `run_in_illustrator.jsx` in desktop Illustrator on another platform. Actual success creates `Native_Color.ai`, `Native_Linework.ai` when strokes exist, Illustrator previews, and `*_verified.json`. Preparation alone creates no AI.

Native AI save/reopen, stroke-width editing, and anchor editing must be verified in an actual Illustrator session. Pixel fidelity and editing structure remain separate results; inspect each project.

## Prepare Native Illustrator Layers

After reviewing the SVG, you can prepare an import directory separately:

```bash
python3 scripts/illustrator_import.py --project /path/project --out /path/new-ai-import
```

A successful studio export also creates `18_Illustrator_Import/` and adds it to the ZIP. It contains per-object SVGs, an import manifest, and `import_v30.jsx`. Run the JSX in desktop Illustrator through **File → Scripts → Other Script**, then inspect layers, coordinates, colors, and the saved result.

Python produces an import preparation package. A native `.ai` can only be created after the JSX actually runs and saves in Illustrator. each user project still needs geometry and visual inspection.

## Output Files

| File | Contents |
| --- | --- |
| `01_Full_Illustration.svg` | Editable vector illustration assembled in the source image's coordinate system |
| `02_Layer_Breakdown.svg` | Full illustration and numbered component breakdown |
| `03_Full_Preview.png` | Preview of the complete illustration |
| `04_Breakdown_Preview.png` | Preview of the component breakdown |
| `05_Color_Palette.csv` | HEX colors, usage, and object counts |
| `06_Layer_Manifest.json` | Modules, layers, objects, and geometry sources |
| `09_Overlay_Comparison.png` | Overlay of the source and reconstructed images |
| `10_Difference_Map.png` | Image difference map for locating discrepancies |
| `11_Outline_Inspection.svg` | Outline inspection view of the final vector paths |
| `12_Editable_Project.zip` | Source image, masks, manifest, and provenance when `--include-source-project` is enabled |
| `13_HiRes_Preview.png` | Enlarged preview when using an option such as `--hires-scale 2` |
| `14_Variable_Width_Profiles.json` | Width samples and provenance when variable-width objects are configured |
| `15_Occlusion_Review.png` | Preview when occlusion analysis is enabled |
| `16_Occlusion_Stack.svg` | Occlusion ordering and layer stack view |
| `17_Occlusion_Report.json` | Constraints, candidates, and unresolved occlusion relationships |
| `18_Illustrator_Import/` | Per-object SVGs, manifest, and JSX from studio export; not a native `.ai` file |
| `18_Modal_Illustration.svg` | Exact copy of the visible composite SVG |
| `19_Amodal_Isolated_Objects.svg/png` | Isolated objects with approved inferred additions |
| `20_Completion_Report.json` | Proposals, approval states, pixel counts, and topology |
| `21_Completion_Review.png` | Completion location preview |
| `22_Unapproved_Completion_Candidates.svg/png` | Unapproved proposal review sheet |
| `23_Amodal_Approval_Review.svg/png` | Highlighted approved additions |
| `24_Editable_Linework.svg/png` | Dedicated visible-stroke linework |
| `26_Line_Quality_Report.json` | Per-object 4x line review, bound hashes, and blocking reasons |
| `25_Editability_Report.json` | Geometry counts, required open strokes, and editing-contract checks |
| `ROI_XX_Comparison.png` | Local comparison images when key regions are configured |
| `quality_report.json` | File checks, image metrics, and items requiring review |
| `08_All_Files.zip` | Exported files bundled in a ZIP archive |

SVG files contain actual vector paths and named objects. Native Illustrator layers must be checked in Illustrator after import. An `.ai` file is provided only when it has actually been saved and verified in Illustrator; the bundled scripts export SVG file packages.

By default, failed quality gates withhold the final ZIP while retaining diagnostic files. Use `--allow-draft` to export a draft explicitly marked as failed. All outputs still require human inspection, and the report keeps `release_ready` set to `false`.

`--include-source-project` adds original images, annotations, and related materials to the project archive. Check that its contents are suitable for disclosure before sharing.

## Validation

```bash
python3 scripts/validate_skill.py
python3 examples/create_demo.py
python3 scripts/self_test.py
python3 scripts/regression_tests.py
python3 scripts/instance_centerline_tests.py
python3 scripts/precision_v23_tests.py
python3 scripts/occlusion_v24_tests.py
python3 scripts/interactive_v25_tests.py
python3 scripts/studio_v30_tests.py
python3 scripts/batch_tests.py
python3 scripts/v31_completion_batch_ocr_tests.py
python3 scripts/editable_v33_tests.py
python3 scripts/line_quality_tests.py
```

The base synthetic example checks 12 objects, 5 layers, and 4 component modules, along with SVG, PNG, palette, manifest, quality report, and ZIP output. Additional regression tests cover quality gates, SVG import, instance segmentation, and centerlines.

With PyTorch installed, you can also run the SAM2 adapter's mock tests and synthetic example. These commands do not download or run real model weights:

```bash
python3 scripts/sam2_integration_tests.py
python3 examples/create_sam2_adapter_demo.py --out /path/new_mock_demo
```

Image difference metrics help locate discrepancies; contours and structure still require visual inspection.

Developers can check frontend syntax with `node --check webui/app.js`. Regression coverage includes folder processing, coordinate transformation, proposal protection, property persistence, undo, and ROI heatmaps. Real-weight checks on this machine covered two synthetic ellipses and a studio candidate preview; they are not a general medical-illustration accuracy benchmark. Native Illustrator files require actual save, reopen, and editing checks.

## Detailed Guides

The detailed guides are currently in Chinese:

- [editable strokes and native Illustrator](references/editable-illustrator.md)
- [completion, OCR, and recursive processing](references/completion-batch-ocr.md)
- [Skill instructions](SKILL.md)
- [Installation and manifest guide](README_安装与使用.md)
- [Path tracing workflow](references/trace-protocol.md)
- [Instance segmentation and centerlines](references/medical-segmentation-centerline.md)
- [SAM2 deployment and structure postprocessing](references/sam2-medical-postprocessing.md)
- [integrated studio](references/interactive-studio.md)
- [folder processing and model settings](references/batch.md)
- [Interactive editing and undo](references/studio-editing.md)
- [Subpixel and variable-width reconstruction](references/precision.md)
- [Occlusion constraints and ordering](references/occlusion.md)
- [Illustrator compatibility and quality checks](references/quality-and-illustrator.md)
- [Output fields and delivery contract](references/output-contract.md)
