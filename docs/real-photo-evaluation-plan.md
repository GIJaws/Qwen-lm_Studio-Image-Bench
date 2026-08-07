# Qwen Image Bench: Real-Photo Sampling, Evaluation, and Static Report Plan

**Status:** Living requirements and phased implementation plan  
**Repository:** `GIJaws/Qwen-lm_Studio-Image-Bench`  
**Stacked feature branch:** `chatgpt/photo-sampling-report-mvp`  
**Base branch:** `chatgpt/lm-studio-backend`  
**Last updated:** 2026-08-07

This document is the source of truth for the real-photo prototype. It records accepted decisions, deferred ideas, experimental directions, and implementation phases so new ideas do not silently expand the first usable milestone.

## 1. Primary outcome

Build a local, CLI-driven prototype for evaluating real JPEG photographs with Qwen-Image-Bench through LM Studio, then review and re-rank the results in a static HTML report.

The prototype should let the user:

1. Point the CLI at an existing photo folder without moving or copying images.
2. Randomly sample up to `N` JPEGs, recursively by default.
3. Run the existing Qwen judge harness through the stateless LM Studio backend.
4. Preserve the stock Qwen scores and raw responses immutably.
5. Generate a static HTML report automatically.
6. Create custom rankings and filters without rerunning inference.
7. Reopen the report without losing local viewer settings.
8. Export/import ranking recipe JSON as the reliable persistence mechanism.

The prototype is deliberately independent of PhotoKin. A later PhotoKin integration is possible but is not required to validate the model.

## 2. Priority and scope boundary

### 2.1 Real photographs are the priority

The only new evaluation workflow required for the prototype is real-photo evaluation.

The existing upstream AI-generated-image workflow remains available through the original input-file path and should not receive new AI-specific features, UI, prompts, fixtures, or test suites unless a trivial shared implementation makes that unavoidable.

### 2.2 Fast usable result before complete feature set

Implementation should be staged so the user can begin generating real results before every viewer and benchmarking feature is finished.

The output format must preserve enough raw and normalized data that later HTML/report improvements can be applied by regenerating the report without rerunning the model.

### 2.3 Not PhotoKin

The prototype must not require:

- PhotoKin
- SQLite
- DINOv3
- A web server
- A frontend build step at report-viewing time
- Moving or duplicating source photos

## 3. Existing baseline to preserve

The fork already contains the upstream Qwen-Image-Bench harness plus an LM Studio backend.

The existing harness owns:

- Stock Qwen system/user prompt templates
- The five L1 dimensions
- The 23 L2 sub-capabilities
- The 56 L3 facets
- One independent request per image and active L1 dimension
- JSON extraction and repair
- `0 -> 0`, `1 -> 60`, `2 -> 100`, `N/A -> excluded`
- L3 -> L2 -> L1 -> aggregate scoring
- Raw response preservation

The LM Studio backend uses stateless `/v1/chat/completions` calls.

## 4. Terminology

### 4.1 Evaluation profile

Defines inference-time behavior:

- Evaluation mode
- Active L1 dimensions
- System-instruction source
- Presented image provenance
- Reference-text presence and role
- Rubric/checklist variant
- Model/runtime settings where relevant

Changing an evaluation profile requires inference to run again.

### 4.2 Evaluation run

An immutable record of:

- Sample manifest
- Evaluation profile
- Model/runtime
- Request settings
- Raw responses
- Parsed facet scores
- Official derived scores
- Errors and parse status

### 4.3 Filter preset

A reusable group of constraints that does not rerun inference.

Future filter presets may combine:

- Capture/EXIF conditions
- L1/L2/L3 score thresholds
- `N/A`/applicability conditions
- Custom-score thresholds

### 4.4 Ranking recipe

A post-inference view over one run:

- Facet weights
- Score filters
- Visible fields
- Sort key and direction
- Optional reference to a filter preset

Changing a ranking recipe must not alter immutable Qwen results or rerun inference.

## 5. LM Studio inference decisions

### 5.1 Stateless only for the prototype

Use only LM Studio's stateless `/v1/chat/completions` API.

Do not implement:

- `previous_response_id`
- Shared conversation history
- Stateful checklist chaining
- Stateful follow-up explanations
- Cache-control logic

Each image/L1 checklist is an independent request, matching the upstream harness.

### 5.2 Prompt caching is outside the implementation contract

Do not verify, benchmark, depend on, or expose LM Studio prompt caching.

The application should work correctly whether LM Studio caches the system prompt or not. The image is expected to be processed for each independent request.

### 5.3 System instructions for the initial real-photo path

The initial real-photo profile should support no application-supplied system message, allowing the user to configure system instructions in the LM Studio model preset.

The profile/run metadata should record that the system-instruction source is `lm_studio_preset`.

The architecture may allow an application-supplied system prompt later, but the first real-photo workflow should not require one.

### 5.4 Existing AI-image path

The original `--input` workflow remains the upstream AI-generated-image path. It keeps the original Qwen prompts and benchmark metadata semantics.

No new AI-image implementation is required for the real-photo prototype.

## 6. Source-image and sampling requirements

### 6.1 Supported input format

The first version supports JPEG only:

- `.jpg`
- `.jpeg`
- Case-insensitive matching

HDR gain-map JPEGs are treated as ordinary backward-compatible JPEGs. No HDR detection, gain-map extraction, special tone mapping, or HDR-aware model path is required.

### 6.2 Folder traversal

- Recursive by default
- `--no-recursive` disables traversal into subfolders
- Source files remain in place
- No copies, moves, renames, or destructive operations

### 6.3 Sampling semantics

`--sample-count N` means **sample up to N eligible images**, not exactly N.

```text
selected_count = min(requested_maximum, eligible_count)
```

Requirements:

- Sampling without replacement
- No image can appear twice in one run
- Default sampling seed: `42`
- Explicit `--sample-seed` override
- Same folder/options/seed must produce the same ordered sample
- If no eligible JPEGs exist, fail clearly
- If fewer than `N` JPEGs exist, select all eligible JPEGs without treating it as an error
- No arbitrary maximum sample count; both tiny smoke tests and long overnight runs are valid

### 6.4 Durable sample manifest

Write the manifest before inference begins.

Minimum fields:

```json
{
  "source_folder": "/absolute/local/path",
  "recursive": true,
  "extensions": [".jpg", ".jpeg"],
  "sampling": "without_replacement",
  "sample_seed": 42,
  "requested_maximum": 100,
  "eligible_count": 63,
  "selected_count": 63,
  "selected_paths": ["/absolute/local/path/photo-001.jpg"],
  "selection_order": "stored_array_order",
  "created_at": "ISO-8601 timestamp"
}
```

The manifest and run outputs are local artifacts and must remain ignored by Git.

## 7. Real-photo evaluation profile

### 7.1 Default active dimensions

The built-in real-photo profile enables:

- Quality
- Aesthetics
- Creative Generation

It disables by default:

- Alignment
- Real-world Fidelity

The disabled dimensions must be recorded as `not_evaluated`, not as `0`, `100`, or `N/A`.

A custom profile may enable them later without a separate implementation path.

### 7.2 Initial rubric

Use the exact stock Qwen rubric/checklists for the first baseline.

The report must visibly distinguish:

- `Stock Qwen rubric`
- Future `Custom` or `Qwen-derived` rubric variants

Do not present a custom/adapted score as the official published Qwen benchmark score.

### 7.3 Aspect-ratio-preserving preprocessing

The real-photo path must not distort images to `1024 x 1024`.

Use a bounded resize that preserves the source aspect ratio and orientation. The exact bound may remain compatible with the current model path, but composition, body proportions, and framing must not be changed by a forced square resize.

### 7.4 Custom real-photo profiles

The first architecture should allow a JSON profile file, for example:

```bash
--profile profiles/real-photo-neutral.json
```

A visual profile editor, profile folders, and pinned-profile management are deferred.

## 8. Official Qwen results

The report must preserve simultaneously:

- Qwen aggregate over active dimensions
- Official L1 scores
- Official L2 scores
- Raw L3 values (`0`, `1`, `2`, `N/A`)
- Mapped L3 values (`0`, `60`, `100`, excluded)
- Raw response text/JSON
- Parse and repair status
- Current custom score

### 8.1 Aggregate label

For a real-photo run that evaluates only three pillars, label the aggregate clearly, for example:

```text
Qwen aggregate, active dimensions
```

It uses Qwen's official aggregation method but is not directly comparable to published benchmark totals that may use different prompts or active dimensions.

### 8.2 Prompt-dependent facets

Enabling an L1 dimension currently requests all stock L3 facets inside it. Some Aesthetics and Creative Generation facets are prompt-dependent or context-dependent.

The first baseline should preserve whatever the model returns, including `N/A`. The custom ranking layer decides whether those facets affect the user's ranking.

Future viewer metadata may tag facets as:

- Image-intrinsic
- Context-dependent
- Prompt-dependent
- Usually irrelevant to real-photo ranking

These tags must not mutate the Qwen result.

## 9. Custom scoring and filtering

### 9.1 Immutable official result

Official Qwen raw and derived scores are never edited by viewer controls.

### 9.2 Unrestricted custom weights

Weights are arbitrary finite numbers, not percentages constrained to `0..100`.

Valid examples:

```text
-100
-40
0
85
100
250
```

Reject only non-finite values such as `NaN` and infinity.

The UI label is `Weight`, not `Weight %`.

### 9.3 Initial custom-score formula

For applicable facets:

```text
facet contribution = mapped facet score * weight / 100
custom score = sum(all facet contributions)
```

`N/A` contributes nothing.

Do not clamp or normalize the final custom score to `0..100`. Negative totals and totals above `100` are valid.

Do not divide by the signed sum of weights, because positive and negative weights may cancel and create unstable results.

### 9.4 Ranking and filtering are independent

A facet can simultaneously:

- Contribute to ranking
- Be used as a minimum/maximum filter
- Be visible in the report

For example:

```text
Edge Clarity >= Pass      filter
Edge Clarity weight = 0   no ranking contribution
```

This supports using sharpness as a search condition without asserting that sharper ICM is always better.

### 9.5 Supported filter conditions

The long-term filter model should support:

- `>=`
- `<=`
- `=`
- Between/range
- Is applicable
- Is `N/A`

Filters may target available L1, L2, L3, official aggregate, or custom score fields.

## 10. Ranking recipes and presets

### 10.1 Built-in recipe candidates

- Official aggregate
- Quality-first
- Aesthetics-first
- Creative-first
- ICM shortlist using relevant stock facets
- Blank custom recipe

### 10.2 Recipe operations

The report should ultimately support:

- Create
- Duplicate
- Rename
- Delete
- Reset
- Export JSON
- Import JSON

### 10.3 Persistence

`localStorage` should automatically restore the local viewer state when possible.

Persist per report/run:

- Active recipe
- Custom weights
- Score filters
- Rank/show/ignore choices
- Sort key and direction
- Search text
- Page size and current page
- Expanded/collapsed panels
- Theme
- Selected image when still available
- Locally created/duplicated recipes

Namespace by schema version and run/report ID, for example:

```text
qwen-image-bench-report:v1:<run-id>:viewer-state
```

Because `file://` localStorage behavior can vary, JSON export/import is the reliable persistence mechanism.

Provide:

- `Reset saved view`
- `Export recipe JSON`
- `Import recipe JSON`

## 11. Static HTML report

### 11.1 Packaging

The report is a static HTML file that opens directly in a browser.

It embeds its CSS, JavaScript, run metadata, and score data, but references source JPEGs by local file URL instead of embedding image bytes.

Consequences accepted for the prototype:

- Report is intended for the same Mac and source folder layout
- Moving source images or the report to another machine may break image links
- No thumbnail generation initially

### 11.2 Image layout

- Preserve natural image aspect ratios
- Support portrait, landscape, square, and panoramic images
- Use order-preserving justified rows to fill available width
- Avoid a masonry layout that makes sorted order visually ambiguous
- Do not force landscape crops

### 11.3 Pagination and performance

- Paginate results
- Render/load only the current page's source images
- Provide a page-size selector
- Use a modest default page size, such as 24
- Support very large overnight runs without decoding every original at once

If full-resolution source loading is too slow in practice, generated thumbnails are a later optimization rather than a prerequisite.

### 11.4 Viewer features

Minimum direction:

- System, light, and dark appearance modes
- Search
- Sort ascending/descending
- Sort by official aggregate, L1, L2, L3, or custom score
- Filter by Fail, Pass, Excel, `N/A`, or mapped numeric score
- Natural-aspect gallery
- Selected-photo inspector
- Full official hierarchy
- Raw L3 values
- Current custom score
- Raw JSON and raw judge-response panels
- Run metadata
- Model identifier and runtime
- Evaluation profile/rubric label
- Sampling seed and counts
- Source filename/path
- Parse/error status
- Open-original file link

`Reveal in Finder` is not a guaranteed static-browser capability and should not be promised in the MVP.

### 11.5 Report generation workflow

Use `uv` for project setup and commands.

Generate HTML by default after a real-photo run.

Provide an opt-out such as:

```bash
--no-html-report
```

Also support regenerating the report from stored judged output without rerunning inference, for example:

```bash
uv run python render_report.py path/to/run_judged.jsonl
```

This separation allows the user to start long inference runs while report features continue to improve.

## 12. Capture/EXIF filters

These were part of the earlier interface direction and must remain documented even if deferred from the first usable report.

Future capture filters should include:

- Shutter speed, highest priority
- Aperture
- ISO
- Focal length
- Flash status

Filter presets should eventually combine capture filters and score filters so a reusable preset can express conditions such as:

```text
shutter <= 1/15 s
flash = any
Edge Clarity >= Pass
Motion Structure >= threshold
```

EXIF extraction and reusable capture-filter presets are not required to block the first real-photo inference/report milestone.

## 13. Future prompt and provenance benchmarking

The run schema should support these experiments later without implementing the full matrix now.

### 13.1 Independent experimental axes

#### Actual provenance

- Real
- AI-generated

For the current corpus, actual provenance is real.

#### Presented provenance

- Explicitly real
- Explicitly AI-generated
- Explicitly uncertain/may be either
- Omitted/not stated

#### Reference text presence and role

- None
- Actual generation prompt
- Candidate/possible generation prompt
- Literal image description
- Photographic intent/context

#### Reference-text source

- Manual
- Q-Judger inferred
- Another model inferred
- Original source metadata

#### Presented role versus actual role

The same text may be presented as:

- Actual generation prompt
- Possible generation prompt
- Description
- Photographic intent

Store both the text's actual source/role and how it was presented to the judge.

#### Rubric variant

- Exact stock Qwen
- Real-photo-adapted
- ICM-aware
- Other custom variants

### 13.2 Experimental conditions are not facets

Do not create duplicated L3 facets such as:

```text
Social Bias when told real
Social Bias when told AI
```

Instead, store separate runs of the same stable facet under different profile conditions.

Add a new facet only when measuring a genuinely different property.

### 13.3 Inferred prompt generation

A future prompt-inference step should:

1. Generate one candidate prompt per image.
2. Save it as immutable run input.
3. Reuse the exact same prompt across controlled conditions.

Do not regenerate the prompt independently for every condition, because that would introduce another uncontrolled variable.

### 13.4 Suggested staged benchmark

1. Real photo, stock rubric, no reference text.
2. Provenance framing comparison: omitted vs real vs AI vs uncertain.
3. Same frozen reference text presented as description vs possible prompt vs actual prompt.
4. Stock rubric versus real-photo-adapted wording.
5. Add genuinely new ICM/photo facets.

The complete factorial matrix is explicitly deferred because it would create excessive inference volume and difficult interpretation.

## 14. Future custom photographic facets

Potential new facets include:

- Motion Structure
- Subject Anchor Sharpness
- Motion-Sharpness Contrast
- Flash Freeze Presence
- Repeated Frozen Structure
- Intentionality of Movement
- Subject Recognisability
- Composition and Flow
- Light and Colour Structure
- Energy and Emotional Impact
- Technical Failure
- Distinctiveness
- Set Utility

These must be labelled custom and must not overwrite stock Qwen facet identities.

## 15. Useful tests only

Tests should protect real behavior, not exist for test-count inflation.

### 15.1 Required tests

- Seed 42 produces deterministic sampling
- Sampling is without replacement
- Sample count means up to `N`
- Recursive and non-recursive traversal
- JPEG extension filtering is case-insensitive
- Empty eligible set fails clearly
- Default real-photo dimensions are correct
- Disabled dimensions are recorded as not evaluated
- Aspect ratio is preserved in preprocessing
- Manifest is written before inference
- Report data/path serialization is safe
- Official score values remain immutable
- Custom-score formula supports negative and >100 weights
- `N/A` contributes nothing
- Filters and ranking are independent
- Recipe import/export round-trips
- `localStorage` failure does not break the viewer

### 15.2 Minimal upstream regression test

Verify that the existing `--input` path still routes to the original upstream workflow.

Do not build a separate AI-image test suite or live output-equivalence benchmark merely to support this real-photo prototype.

## 16. Public-repository safety

Never commit:

- Real photographs
- Private photo filenames or manifests
- Absolute local paths
- LM Studio logs
- Model weights
- API tokens or credentials
- Private PhotoKin details
- Event/client datasets
- Generated local reports or result files

Use synthetic fixtures and generic example paths in tests and documentation.

The existing `.gitignore` remains part of the safety boundary, but diffs must still be inspected before every push.

## 17. Phased implementation plan

### Phase 0: Validate the existing LM Studio backend

**Purpose:** Confirm PR #1 can call the local model and parse a stock Qwen response.

- Clone `chatgpt/lm-studio-backend`
- Install via `uv`
- Run unit tests
- Run one-image stock harness smoke test

This can happen while Phase 1 is developed.

### Phase 1A: Earliest usable real-photo run

**Goal:** Let the user begin evaluating real photographs as soon as possible.

Implement:

- `--folder`
- JPEG-only discovery
- Recursive default and `--no-recursive`
- Sample up to `N`
- Seed 42
- Sampling without replacement
- Durable sample manifest
- Built-in stock-rubric real-photo profile
- Quality, Aesthetics, Creative Generation active
- Alignment and Real-world Fidelity not evaluated
- Optional/no application system prompt
- Aspect-ratio-preserving preprocessing
- Existing stateless LM Studio backend
- Complete raw and normalized run output
- Basic automatic static report showing official scores and originals

The Phase 1A output schema must be final enough that later report improvements do not require re-inference.

### Phase 1B: Useful ranking report

Add without changing inference results:

- Custom score editor
- Unrestricted signed weights
- Score filters
- Official-versus-custom score display
- Ranking recipes
- LocalStorage persistence
- Recipe export/import JSON
- Search, sort, pagination, themes
- Full inspector and raw outputs
- Regenerate-report command

This is the minimum feature set needed to judge whether the model's dimensions are genuinely useful for photography ranking.

### Phase 2: Profiles and capture filters

- Custom profile JSON loading
- More explicit profile metadata
- Optional L1-dimension selection
- Facet applicability labels
- EXIF extraction
- Shutter/aperture/ISO/focal/flash filters
- Reusable filter presets
- Simple profile creation/duplication

Profile folders and pinned-profile UI are optional late Phase 2 items, not blockers.

### Phase 3: Prompt/provenance experiment runner

- Presented-provenance variants
- Reference-text variants
- Frozen inferred-prompt generation
- Multiple runs over the same sample manifest
- Multi-run comparison report
- Controlled delta views by facet

### Phase 4: Adapted rubrics and custom ICM facets

- Real-photo-adapted stock facets
- ICM-aware rubric
- New photographic facets
- Clear stock/custom provenance
- Recipe presets for different photographic roles

### Phase 5: Optional integrations

- PhotoKin integration
- SQLite-backed run library
- Stateful LM Studio option
- Follow-up/explanation conversations
- Thumbnail cache if direct originals are too slow
- More durable profile library and folders

## 18. Phase 1 acceptance criteria

A user can run one command against a local JPEG folder and receive:

1. A deterministic, duplicate-free sample of up to `N` images.
2. A manifest written before inference.
3. Independent stateless LM Studio requests using the stock Qwen rubric.
4. Real-photo default dimensions only.
5. Aspect-ratio-preserving model input.
6. Immutable raw and official score outputs.
7. A static HTML report opened without a server.
8. Direct references to original JPEGs.
9. A custom ranking/filter view that does not mutate official results.
10. Local state restoration plus reliable recipe JSON export/import.

## 19. Explicitly deferred from the first usable milestone

- AI-image-specific development beyond preserving upstream behavior
- Full profile manager with folders and pins
- Full prompt/provenance factorial benchmark
- Inferred-prompt generation
- Real-photo rubric rewrites
- Custom ICM facets
- EXIF capture filtering if it delays Phase 1A
- Multi-run comparison
- Stateful LM Studio
- PhotoKin integration
- Database/server architecture
- Embedded thumbnails

## 20. Change-control rule

New ideas should be added to this document first and assigned to a phase before implementation.

A feature may move earlier only when:

1. It is required for correctness or data compatibility, or
2. It is small enough to add without delaying the earliest usable real-photo run.

Otherwise it remains documented and deferred rather than silently expanding Phase 1.
