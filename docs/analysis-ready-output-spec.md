# Analysis-Ready Output Specification

**Status:** Required data-contract design for the real-photo prototype  
**Related plan:** `docs/real-photo-evaluation-plan.md`  
**Branch:** `chatgpt/photo-sampling-report-mvp`

## 1. Purpose

Make every evaluation run easy to reuse for custom visualizations, charts, statistical comparisons, and future report variants without rerunning inference or scraping data back out of the generated HTML.

The static HTML report is one consumer of the run data. It must not be the only usable representation of the results.

This specification does not require built-in comparison charts in the first prototype. It requires a stable, analysis-friendly output contract so charts can be created later in Python, JavaScript, spreadsheets, notebooks, or another report renderer.

## 2. Core principles

1. Preserve immutable raw model output.
2. Preserve official Qwen-derived L3, L2, L1, and active-dimension aggregate scores.
3. Store normalized observations in long-form records, not only nested JSON blobs.
4. Use stable identifiers so the same image, facet, prompt/reference text, and run condition can be joined across runs.
5. Keep run conditions and score observations separate.
6. Keep custom ranking recipes separate from immutable official results.
7. Version every schema and rubric/profile identity that affects interpretation.
8. Keep `N/A`, `not_evaluated`, parse failures, and missing data distinct.
9. Do not require the HTML report to recover or reconstruct the canonical data.

## 3. Minimum MVP artifacts

A real-photo run should produce a local run directory containing at least:

```text
run-directory/
├── run.json
├── sample-manifest.json
├── results.jsonl
├── facet-scores.csv
├── aggregate-scores.csv
└── report.html
```

Generated local artifacts remain ignored by Git.

### 3.1 `run.json`

One versioned object describing the run-level condition:

- Run ID
- Schema version
- Evaluation-profile ID/version/digest
- Actual and presented provenance
- Reference-text policy and framing
- Rubric ID/version/classification
- Active dimensions
- Model identifier
- Runtime and API mode
- Inference settings
- Sample-manifest ID
- Start/end timestamps
- Completion/interruption status
- Counts for successes, failures, skipped images, and parse errors

### 3.2 `sample-manifest.json`

The durable pre-inference sample selection:

- Source folder
- Recursive setting
- Eligible extensions
- Seed
- Requested maximum
- Eligible count
- Selected count
- Ordered selected paths
- Sampling-without-replacement declaration

### 3.3 `results.jsonl`

One self-contained record per evaluated image. Each record should preserve:

- `run_id`
- `image_id`
- Source path and source-root-relative path
- Sample order
- Pixel width/height and aspect ratio where available
- Reference-text ID/digest when used
- Raw model responses per active L1 dimension
- Parsed and repaired score hierarchy
- Official derived scores
- Request/parse/error status

The record may contain nested structures because it is the complete per-image archival result.

### 3.4 `facet-scores.csv`

A normalized long-form table with one row per:

```text
run × image × L1 × L2 × L3 facet
```

Minimum columns:

```text
schema_version
run_id
image_id
sample_index
source_relative_path
profile_id
profile_version
condition_digest
rubric_id
rubric_version
rubric_classification
actual_provenance
presented_provenance
reference_id
reference_digest
reference_actual_role
reference_presented_role
l1_id
l1_label
l2_id
l2_label
facet_id
facet_concept_id
facet_label
raw_score
mapped_score
applicability
parse_status
request_status
```

`raw_score` is one of `0`, `1`, `2`, or blank when unavailable. `mapped_score` is `0`, `60`, `100`, or blank. `applicability` distinguishes at least:

- `applicable`
- `na`
- `not_evaluated`
- `missing`
- `parse_failed`

This table is the primary charting and comparison surface.

### 3.5 `aggregate-scores.csv`

A normalized long-form table for official derived scores at different hierarchy levels.

Minimum columns:

```text
schema_version
run_id
image_id
sample_index
score_level
l1_id
l2_id
score_id
score_label
score
applicable_count
aggregation_method
```

`score_level` supports:

- `l2`
- `l1`
- `active_dimension_aggregate`

The active-dimension aggregate must remain clearly labelled and must not be presented as directly equivalent to the published five-pillar benchmark total when dimensions or prompts differ.

### 3.6 `report.html`

The static report consumes the same canonical run data and may embed a serialized copy for convenience, but the CSV/JSONL artifacts remain independently usable.

## 4. Stable identifiers

### 4.1 Run identity

Each run has:

- `run_id`: unique execution identity
- `condition_digest`: digest of normalized run-level experimental conditions
- `profile_id` and `profile_version`

Two executions using the same condition still have different `run_id` values but may share a `condition_digest`.

### 4.2 Image identity

Each result must include a stable `image_id` suitable for joining the same source image across runs.

Preferred identity:

```text
sha256 of the source JPEG bytes
```

The absolute path is retained as provenance but is not the primary comparison key. Moving a byte-identical JPEG should not change its identity. Editing or re-exporting the image creates a new identity, which is correct.

### 4.3 Facet identity

Do not rely only on display labels.

Each observation includes:

- `facet_id`: stable ID for the exact rubric facet
- `facet_concept_id`: stable conceptual ID used across rubric variants only when the measurement remains intentionally comparable
- Human-readable labels separately

Example:

```text
facet_id: qwen_stock.quality.detail.edge_clarity
facet_concept_id: quality.detail.edge_clarity
```

A custom facet with genuinely different meaning receives a different concept ID.

### 4.4 Reference-text identity

When prompt/reference experiments are introduced, each frozen per-image reference text has:

- `reference_id`
- Exact text
- SHA-256 digest of the exact text
- Actual source and role
- Presented role
- Framing-template ID/version

The same frozen reference text can then be compared across different run-level framing conditions.

## 5. Comparison guarantees

### 5.1 Same image across runs

Join on:

```text
image_id + facet_concept_id
```

Then retain `run_id`, `condition_digest`, `rubric_id`, and exact `facet_id` so the comparison remains auditable.

### 5.2 Different images within or across runs

Group or compare by:

```text
facet_concept_id
```

while preserving `image_id`, run identity, and profile/rubric metadata.

### 5.3 Same sample under different conditions

Reuse the same `sample_manifest_id` or explicit ordered image list. Each new prompt/provenance/rubric condition creates a separate run.

### 5.4 Same inferred reference text under different framing

Reuse the same `reference_id` and `reference_digest`. Only the run-level presented provenance, presented reference role, or framing-template identity changes.

## 6. Official versus custom scores

Official Qwen outputs and official derived scores are immutable canonical data.

Custom ranking recipes are separate versioned inputs. A custom score is reproducible from:

```text
canonical facet scores + recipe JSON
```

Do not overwrite official score columns with custom results.

A later derived export may include custom-score rows, but each must carry:

- Recipe ID/version
- Recipe digest
- Formula version
- Resulting custom score

Weights remain unrestricted finite numbers and may be negative or greater than `100`.

## 7. Missing and non-applicable data

These states must not be collapsed:

- `N/A`: model judged the facet not applicable
- `not_evaluated`: dimension/facet was outside the run profile
- `missing`: expected data absent
- `parse_failed`: response existed but could not be parsed
- `request_failed`: inference request failed

Charts and analysis code must be able to choose how to handle each state explicitly.

## 8. Forward compatibility

The first implementation may add fields, but it must not change existing field meanings without incrementing `schema_version`.

Later additions may include:

- EXIF/capture metadata
- Custom photographic facets
- Multiple rubric variants
- Inferred reference prompts
- Multi-run comparison reports
- Custom-score exports
- Additional analysis tables

These additions should extend the canonical identifiers and long-form observation model rather than replacing it.

## 9. Scope boundary

The first usable prototype does not need built-in comparison charts.

It does need to emit enough canonical, normalized, versioned data that custom visuals can be created without:

- Parsing HTML
- Reverse-engineering display state
- Re-running Q-Judger
- Guessing which prompt/profile/rubric variant produced a score
- Matching images by filename alone
