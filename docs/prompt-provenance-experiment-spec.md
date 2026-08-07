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

## 5. Recommended stored schema

```json
{
  "actual_provenance": "real",
  "presented_provenance": "uncertain",
  "reference": {
    "id": "reference-text-stable-id",
    "digest": "sha256-of-exact-text",
    "source": "q_judger_inferred",
    "actual_role": "inferred_candidate_generation_prompt",
    "presented_role": "similar_image_prompt",
    "text": "A musician under saturated red stage lights...",
    "framing_template_id": "similar-image-uncertain-v1"
  },
  "rubric": {
    "id": "qwen_stock",
    "version": "upstream"
  }
}
```

The report should show both the actual and presented roles so deliberately misleading conditions remain auditable.

## 6. Suggested staged comparison

Do not run the complete cross-product initially.

### Stage A: Reference-role effect

Hold presented provenance fixed and compare:

1. No reference text
2. Neutral description
3. Possible generation prompt
4. Claimed exact generation prompt
5. Similar-image prompt

Use the same frozen text for conditions 2 through 5 where meaningful.

### Stage B: Provenance-framing effect

Hold reference text and presented role fixed and compare:

1. Provenance omitted
2. Explicitly real
3. Explicitly AI-generated
4. Explicitly uncertain

### Stage C: Interaction test

Run a small selected subset of combinations that appeared most informative in Stages A and B.

### Stage D: Rubric wording

Compare stock Qwen wording with a real-photo-adapted rubric while holding provenance and reference framing fixed.

## 7. Reporting requirements

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

## 8. Scope boundary

This specification does not add work to the first usable real-photo milestone.

The first baseline remains:

- Actual provenance: real
- Presented provenance: real
- No reference text
- Stock Qwen rubric
- Stateless LM Studio
- Quality, Aesthetics, and Creative Generation enabled

The schema should remain forward-compatible with this experiment, but prompt inference, condition matrices, and multi-run comparison are deferred.
