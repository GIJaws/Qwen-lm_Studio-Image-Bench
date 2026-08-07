# Custom Real-Photo and ICM Rubric Packs

**Status:** Experimental one-image prototype  
**Branch:** `chatgpt/custom-rubric-packs`  
**Base:** `chatgpt/stateful-concurrency`

## Purpose

Test whether Q-Judger can make useful judgments about photographic properties
outside the fixed Qwen-Image-Bench taxonomy, without modifying or overwriting the
stock Qwen dimensions.

Custom outputs are:

- Explicitly labelled `custom`
- Experimental prompted judgments
- Not official Qwen-Image-Bench scores
- Not covered by Qwen's reported human-agreement results

The stock dimensions remain available unchanged on the lower branches.

## Versioned pack identities

Custom rubrics use immutable, explicit identities:

```text
birds_of_stone_real_photo_v1
birds_of_stone_icm_v1
```

After a rubric has been used in a saved run, do not silently rewrite that file.
Create a new version such as:

```text
birds_of_stone_icm_v2.json
```

This keeps old result files interpretable and allows direct comparisons between
rubric versions.

## Included starter packs

### `rubrics/birds_of_stone_real_photo_v1.json`

One custom L1 dimension, **Photographic Effectiveness**, covering:

- Subject or Visual Anchor
- Composition and Flow
- Layer Separation
- Light Structure
- Colour and Tonal Coherence
- Energy and Mood
- Distinctiveness
- Technique Intentionality
- Unintended Failure Control

The wording explicitly avoids treating intentional blur, noise, clipping,
unusual colour, and unconventional framing as defects by themselves.

### `rubrics/birds_of_stone_icm_v1.json`

One custom L1 dimension, **Intentional Motion**, covering:

- Motion Structure
- Directional Coherence
- Layering and Repetition
- Subject Anchor
- Motion-Sharpness Contrast
- Flash-Freeze Integration
- Energy and Emotional Impact
- Movement Intentionality
- Distinctiveness
- Intent-Appropriate Legibility
- Uncontrolled Smear and Obstruction Control

Sharpness is not treated as a monotonic quality metric. The rubric asks whether
retained sharpness strengthens the visible motion treatment when it is present.

Both starter packs are drafts intended to produce evidence for later refinement.
They are not assumed to be calibrated simply because the underlying model was
fine-tuned as Q-Judger.

## JSON pack structure

```json
{
  "schema_version": 1,
  "id": "example_pack",
  "version": 1,
  "name": "Example Pack v1",
  "classification": "custom",
  "description": "What this pack measures.",
  "dimensions": [
    {
      "id": "example_dimension",
      "label": "Example Dimension",
      "description": "Dimension purpose.",
      "groups": [
        {
          "id": "example_group",
          "label": "Example Group",
          "facets": [
            {
              "id": "example_facet",
              "label": "Example Facet",
              "prompt": "The exact visual question to judge."
            }
          ]
        }
      ]
    }
  ]
}
```

IDs must use lowercase letters, numbers, underscores, or hyphens. Dimension,
group, and facet IDs and labels must be unique within their relevant scope.

## Run both starter packs on one image

The one-image CLI deliberately keeps this first custom-rubric experiment small:

```bash
uv run --active python run_custom_rubrics.py \
  --image "/absolute/path/to/photo.jpg" \
  --rubric rubrics/birds_of_stone_real_photo_v1.json \
  --rubric rubrics/birds_of_stone_icm_v1.json \
  --model "qwen-image-bench-mlx" \
  --lm-studio-timeout 900
```

Behavior:

1. Decode, orient, and resize the JPEG once.
2. Create one stored LM Studio shared image context.
3. Run every custom dimension as an independent branch from that response ID.
4. Detect the loaded instance's `config.parallel` value and keep at most that
   many branch requests in flight.
5. Stream prompt-processing and generation progress by default.
6. Save one `result.json` beneath `local/custom-runs/`.

An explicit concurrency override remains available:

```bash
--concurrency 4
```

Because both current packs contain one dimension, they can run concurrently as
two branches. Additional packs or dimensions remain queued locally if the count
exceeds the effective concurrency limit.

## Run only the ICM pack

```bash
uv run --active python run_custom_rubrics.py \
  --image "/absolute/path/to/icm-photo.jpg" \
  --rubric rubrics/birds_of_stone_icm_v1.json \
  --model "qwen-image-bench-mlx" \
  --lm-studio-timeout 900
```

## Evidence and scoring

Evidence is requested by default. Disable it only for a controlled comparison:

```bash
--no-evidence
```

Custom facets use the same raw categories for initial comparability:

```text
0 = Fail  -> 0
1 = Pass  -> 60
2 = Excel -> 100
N/A       -> excluded
```

Aggregation is:

```text
applicable facets -> mean group score
applicable groups -> mean custom dimension score
```

The result file preserves raw responses, evidence, mapped values, custom facet
identities, inference stats, pack metadata, effective concurrency, and the
stateful shared context.

## Stateful caveat

The custom CLI uses the experimental stateful path because it is the quickest way
to test several new dimensions against one photograph without resending the
image in each request.

LM Studio documents stored conversations and branching via `response_id`, but
this project does not assume that branching guarantees reuse of the VLM image or
KV cache. Compare timing and input-token statistics in the saved result.

The shared context also includes a minimal `READY` assistant turn. Custom scores
must therefore be compared only with runs that clearly record the same execution
mode.

## Current boundary

This branch intentionally does not yet:

- Run custom packs across a folder sample
- Merge stock and custom results into the main static report
- Add custom recipe weights or filters to the report
- Provide a visual rubric editor
- Claim calibration or agreement with Jacob's selections

The immediate question is whether the two small packs produce differentiated,
interpretable scores and evidence on representative photographs. Folder-scale
integration should follow only after that result is inspected.
