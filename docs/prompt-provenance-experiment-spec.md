# Prompt and Provenance Experiment Specification

**Status:** Deferred experiment design, documented now so Phase 1 remains small  
**Related plan:** `docs/real-photo-evaluation-plan.md`  
**Target phase:** Phase 3, after the first usable real-photo sampler and report

## 1. Purpose

Measure how Q-Judger's scores change when the same real photograph and the same frozen reference text are framed differently.

The experiment must distinguish:

1. What the image actually is.
2. What the judge is told the image is.
3. Where the reference text actually came from.
4. What the judge is told that text represents.

These are run conditions, not new Qwen facets.

## 2. Core control principle

Generate or choose one reference text for an image, save it, and reuse the exact same text across all comparison runs.

Only the framing around that text should change.

This prevents a regenerated prompt from becoming an uncontrolled variable.

## 3. Important inferred-prompt condition

For a real photograph, a model-inferred prompt is not an actual generation prompt. It is a candidate prompt that may produce images resembling the photograph.

The experiment may deliberately present that same candidate text to Q-Judger in several ways:

### A. Claimed exact generation prompt

```text
This is the exact prompt that was used to generate the image:
<reference text>
```

Recorded truth:

- Actual image provenance: real
- Actual reference role: inferred candidate generation prompt
- Presented image provenance: AI-generated, or another selected provenance condition
- Presented reference role: exact/actual generation prompt

### B. Possible generation prompt

```text
This is a possible prompt that could generate an image like this:
<reference text>
```

Recorded truth:

- Actual reference role: inferred candidate generation prompt
- Presented reference role: possible/candidate generation prompt

### C. Similar-image prompt with uncertain provenance

```text
The image may or may not be AI-generated. This prompt reportedly produces images that look similar to it:
<reference text>
```

Recorded truth:

- Presented image provenance: uncertain
- Presented reference role: similar-image prompt
- No claim that the prompt actually produced the evaluated image

### D. Neutral image description

```text
The following text describes the visible image:
<reference text>
```

Recorded truth:

- Presented reference role: image description

### E. No reference text

No prompt or description is supplied.

This is the baseline for measuring how much reference text changes scores.

## 4. Independent experimental axes

### 4.1 Actual image provenance

- `real`
- `ai_generated`

For the current photography corpus, this is always `real`.

### 4.2 Presented image provenance

- `real`
- `ai_generated`
- `uncertain`
- `omitted`

`uncertain` means the judge is explicitly told the image may be real or synthetic.

`omitted` means no provenance statement is supplied.

### 4.3 Actual reference-text role

- `none`
- `actual_generation_prompt`
- `inferred_candidate_generation_prompt`
- `manual_candidate_generation_prompt`
- `image_description`
- `photographic_intent`

### 4.4 Presented reference-text role

- `none`
- `exact_generation_prompt`
- `possible_generation_prompt`
- `similar_image_prompt`
- `image_description`
- `photographic_intent`

### 4.5 Reference-text source

- `none`
- `q_judger_inferred`
- `other_model_inferred`
- `manual`
- `original_metadata`

### 4.6 Rubric variant

- `qwen_stock`
- `real_photo_adapted`
- `icm_aware`
- Other explicitly versioned custom rubric

## 5. Run-level consistency and request isolation

### 5.1 One coherent condition per run

An evaluation run selects one immutable evaluation profile before inference starts. The profile applies to every sampled image and every active L1-dimension request in that run.

The following are run-level settings and must not vary per image or per L1 dimension:

- Presented image provenance
- Reference-text presence policy
- Reference-text source class
- Actual reference-text role
- Presented reference-text role
- Reference framing-template ID and version
- Rubric family and version
- System-instruction source/mode
- Active L1 dimensions
- Model/runtime and inference settings

Per-image reference text may contain different text because each photograph is different, but every image in the run must use the same source/role/framing rules. For example, a run may use one frozen inferred candidate prompt per image, with every prompt presented as a `possible_generation_prompt`.

Do not silently fall back to another condition. If a run requires reference text and one image has no valid frozen reference text, that image should fail or be skipped with an explicit status rather than being evaluated under a no-reference condition.

### 5.2 No mixed rubric family inside a run

A run must use one coherent rubric variant across all active L1 dimensions.

Examples:

- A `qwen_stock` run uses stock Qwen wording for every active dimension.
- A `real_photo_adapted` run uses real-photo-adapted wording for every active dimension.
- An `icm_aware` run uses the selected ICM-aware rubric family for every active dimension it defines.

Do not run stock Quality, adapted Aesthetics, and ICM-aware Creative Generation together as one normal run. If the selected rubric family does not define one of the requested dimensions, validation should fail instead of falling back to another rubric family.

A deliberately mixed one-off experiment can still be performed manually at a lower level, but it must not be represented as a normal homogeneous run.

### 5.3 Separate runs for separate conditions

Changing any experimental variant creates a new run. Do not mix real-photo, AI-presented, uncertain-provenance, prompt-present, and prompt-absent conditions within one run.

Comparisons should reuse the same sample manifest or explicit image list so the image cohort remains fixed while the run-level condition changes.

Examples:

```text
Run A: presented as real, no reference, stock rubric
Run B: presented as AI-generated, no reference, stock rubric
Run C: provenance uncertain, inferred prompt presented as possible, stock rubric
Run D: presented as real, no reference, real-photo-adapted rubric
```

### 5.4 L1 dimensions are logically isolated

Each active L1 dimension is evaluated as an independent stateless request containing:

- The same run-level profile condition
- The same image
- The same per-image frozen reference text, when the run uses one
- Only the dimension-specific checklist/output request needed for that L1 pass

No Quality result is passed into Aesthetics, no Aesthetics result is passed into Creative Generation, and no dimension can see another dimension's output.

The backend may execute requests serially, concurrently, or in batches. That is a scheduling detail. The experimental requirement is logical isolation and no conversation-history chaining.

### 5.5 Run identity must make variants obvious

Every run manifest and report header must expose the selected condition without requiring inspection of raw prompts.

Minimum visible identity fields:

- Run ID
- Evaluation profile ID and version
- Actual provenance
- Presented provenance
- Reference source
- Actual reference role
- Presented reference role
- Reference framing-template ID/version
- Rubric ID/version/classification
- System-instruction source
- Active dimensions
- Model/runtime/API mode
- Sample-manifest ID

The run should also store a stable condition signature or digest derived from the normalized run-level profile. Every per-image result references the run/profile identity rather than independently selecting variants.

## 6. Recommended stored schema

```json
{
  "run_id": "run-stable-id",
  "sample_manifest_id": "sample-stable-id",
  "evaluation_profile": {
    "id": "uncertain-similar-prompt-stock",
    "version": 1,
    "condition_digest": "sha256-of-normalized-run-profile"
  },
  "actual_provenance": "real",
  "presented_provenance": "uncertain",
  "reference_policy": {
    "source": "q_judger_inferred",
    "actual_role": "inferred_candidate_generation_prompt",
    "presented_role": "similar_image_prompt",
    "framing_template_id": "similar-image-uncertain-v1",
    "required": true
  },
  "rubric": {
    "id": "qwen_stock",
    "version": "upstream",
    "classification": "official"
  },
  "system_instructions": {
    "source": "lm_studio_preset"
  },
  "dimensions": [
    "Quality",
    "Aesthetics",
    "Creative Generation"
  ],
  "model": {
    "runtime": "lm_studio",
    "api_mode": "stateless"
  },
  "image_results": [
    {
      "image_id": "image-stable-id",
      "reference": {
        "id": "reference-text-stable-id",
        "digest": "sha256-of-exact-text",
        "text": "A musician under saturated red stage lights..."
      }
    }
  ]
}
```

The report should show both the actual and presented roles so deliberately misleading conditions remain auditable.

## 7. Suggested staged comparison

Do not run the complete cross-product initially.

### Stage A: Reference-role effect

Hold presented provenance fixed and compare separate runs:

1. No reference text
2. Neutral description
3. Possible generation prompt
4. Claimed exact generation prompt
5. Similar-image prompt

Use the same frozen text for conditions 2 through 5 where meaningful.

### Stage B: Provenance-framing effect

Hold reference text and presented role fixed and compare separate runs:

1. Provenance omitted
2. Explicitly real
3. Explicitly AI-generated
4. Explicitly uncertain

### Stage C: Interaction test

Run a small selected subset of combinations that appeared most informative in Stages A and B.

### Stage D: Rubric wording

Compare stock Qwen wording with a real-photo-adapted rubric in separate runs while holding provenance and reference framing fixed.

## 8. Reporting requirements

A future multi-run comparison report should support:

- Same image aligned across runs
- Same stable facet aligned across runs
- Delta in raw L3 score
- Delta in mapped score
- Delta in L2/L1/aggregate values
- Actual versus presented provenance
- Actual versus presented reference role
- Exact frozen reference text and digest
- Rubric/version
- Model/runtime/version
- Condition digest
- Explicit confirmation that each run is internally homogeneous

## 9. Scope boundary

This specification does not add work to the first usable real-photo milestone.

The first baseline remains one coherent run:

- Actual provenance: real
- Presented provenance: real
- No reference text
- Stock Qwen rubric
- Stateless LM Studio
- Quality, Aesthetics, and Creative Generation enabled

The schema should remain forward-compatible with this experiment, but prompt inference, condition matrices, and multi-run comparison are deferred.
