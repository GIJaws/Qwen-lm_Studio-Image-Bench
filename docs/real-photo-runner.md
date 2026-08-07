# Real-Photo Runner

This branch contains the first operational slice of the real-photo prototype: JPEG folder sampling, stateless LM Studio inference, durable incremental outputs, and a deliberately small static HTML report.

The richer ranking/filter/profile report described in the planning documents is a later slice. The canonical outputs produced now are designed so that report work will not require rerunning Q-Judger.

## Scope

The runner currently:

- Discovers `.jpg` and `.jpeg` files, case-insensitively
- Searches recursively by default
- Samples up to `N` files without replacement
- Generates a fresh 64-bit image-sampling seed from OS entropy by default
- Accepts `--sample-seed <int>` to reproduce or choose a specific image sample
- Keeps the LM Studio inference seed independent, with default `42`
- Writes the effective image-sampling seed to the sample manifest
- Writes the sample manifest before inference
- Uses the stock Qwen checklists
- Evaluates Quality, Aesthetics, and Creative Generation by default
- Allows repeatable `--dimension` selection or `--all-dimensions`
- Records disabled dimensions as not evaluated
- Requests one brief evidence statement per facet by default
- Supports `--no-evidence` for the original score-only JSON shape
- Preserves source aspect ratio and EXIF orientation
- Sends one independent stateless LM Studio request per active L1 dimension
- Omits an application system message so an LM Studio preset can own system instructions
- Writes per-dimension checkpoints and per-image results incrementally
- Resumes compatible interrupted runs and skips already completed work
- Generates normalized long-form CSV exports and a static HTML report
- Exports per-facet evidence to `facet-scores.csv` and shows it in the report

## Clone the implementation branch

```bash
git clone \
  --branch chatgpt/real-photo-runner \
  --single-branch \
  https://github.com/GIJaws/Qwen-lm_Studio-Image-Bench.git

cd Qwen-lm_Studio-Image-Bench
```

For an existing clone:

```bash
git pull --ff-only
```

## Install with uv

The LM Studio and real-photo path does not require PyTorch, Transformers, or ms-swift.

```bash
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements-lm-studio.txt
```

Run the local unit tests:

```bash
uv run --active python -m unittest discover -s tests -v
```

## Prepare LM Studio

1. Load the Qwen-Image-Bench-compatible MLX model.
2. Start the local server.
3. Configure any real-photo system instructions in the LM Studio model preset.
4. Find the model identifier exposed by the server:

```bash
curl -s http://localhost:1234/v1/models | python -m json.tool
```

The runner deliberately uses stateless `/v1/chat/completions` calls and does not investigate or depend on prompt caching.

## Run a small sample

```bash
uv run --active python run_real_photos.py \
  --folder "/absolute/path/to/jpeg-folder" \
  --sample-count 3 \
  --model "<LM_STUDIO_MODEL_ID>"
```

By default this will:

- Search subfolders
- Generate a fresh 64-bit sampling seed from OS entropy
- Select at most three unique JPEGs
- Print and record the effective sample seed
- Keep the LM Studio inference seed at `42`
- Run Quality, Aesthetics, and Creative Generation
- Request a brief evidence string for each facet
- Preserve source aspect ratio within a `1024`-pixel long edge
- Write output under `local/runs/`
- Generate `report.html`

To reproduce a particular image sample or choose a specific image-selection seed:

```bash
--sample-seed 42
```

The image-sampling seed is independent from the LM Studio inference seed. Changing `--sample-seed` changes which JPEGs are selected but does not change the default model seed.

## Select dimensions

Run one or more specific stock Qwen L1 dimensions by repeating `--dimension`:

```bash
uv run --active python run_real_photos.py \
  --folder "/absolute/path/to/jpeg-folder" \
  --sample-count 3 \
  --dimension "Quality" \
  --dimension "Real-world Fidelity" \
  --model "<LM_STUDIO_MODEL_ID>"
```

Run all five stock dimensions:

```bash
--all-dimensions
```

`--dimension` and `--all-dimensions` cannot be combined in the same run.

Use the exact score-only output shape without the evidence extension:

```bash
--no-evidence
```

Evidence is diagnostic metadata. It does not alter the official `0/1/2/N/A` mapping or aggregation code, but asking for evidence is recorded as a distinct profile/output-schema condition.

Disable recursive traversal with:

```bash
--no-recursive
```

Skip HTML generation with:

```bash
--no-html-report
```

## Run artifacts

Each run directory contains:

```text
run-directory/
├── run.json
├── sample-manifest.json
├── results.jsonl
├── facet-scores.csv
├── aggregate-scores.csv
├── checkpoints/
└── report.html
```

- `run.json` records the immutable evaluation condition, runtime, model, preprocessing, and status.
- `sample-manifest.json` records the source folder, effective image-sampling seed, eligible count, selected ordered paths, and sampling method.
- `results.jsonl` preserves one complete archival record per evaluated image.
- `facet-scores.csv` is a long-form L3 table containing scores, applicability, and evidence for custom charts and analysis.
- `aggregate-scores.csv` contains L2, L1, and active-dimension aggregate rows.
- `checkpoints/` preserves completed dimension requests before an image result is finalized.
- `report.html` is a local static viewer that references the original JPEG files.

These local artifacts can contain absolute source paths. The default `local/` output tree is ignored by Git and must not be committed to the public repository.

## Resume an existing run

Re-run the same command with the existing run directory. The stored manifest controls the already-selected sample, so a fresh random seed is not used to replace it:

```bash
uv run --active python run_real_photos.py \
  --folder "/absolute/path/to/jpeg-folder" \
  --sample-count 3 \
  --model "<LM_STUDIO_MODEL_ID>" \
  --run-dir "local/runs/<EXISTING_RUN_DIRECTORY>"
```

The runner validates the stored condition and source folder, skips completed image results, and reuses any per-dimension checkpoint for an interrupted image.

## Regenerate the report without inference

```bash
uv run --active python render_report.py "local/runs/<RUN_DIRECTORY>"
```

## Current limitations

- No custom ranking/filter recipe editor yet
- No EXIF capture filters yet
- No custom rubric-pack loader yet
- No automatic retry policy for a request that returns a terminal error
- No multi-run comparison UI
- No inferred-prompt or provenance experiment runner
- No stateful LM Studio mode
- Direct full-resolution source references may become slow for very large report pages; thumbnail generation remains deferred until needed

See the planning documents for the subsequent Option C slices.
