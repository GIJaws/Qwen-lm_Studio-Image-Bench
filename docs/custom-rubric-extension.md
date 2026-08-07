# Custom Rubric and Dimension Extension Plan

**Status:** Deferred design, with easy stock-dimension controls implemented now  
**Branch:** `chatgpt/real-photo-runner`

## 1. Official scope

Qwen-Image-Bench defines and validates a fixed taxonomy:

- 5 L1 dimensions
- 23 L2 sub-capabilities
- 56 L3 facets

The paper, model card, dataset card, and released harness describe Q-Judger as a judge for that taxonomy. They do not document an official API for arbitrary new dimensions, recommend user-authored facets, or claim human-agreement results for rubrics outside those 56 facets.

The paper itself expands earlier evaluation practice by introducing Real-world Fidelity and Creative Generation, but that is part of the benchmark authors' designed and annotated taxonomy. It is not evidence that any user-authored checklist inherits the benchmark's validation.

## 2. Removing or selecting stock dimensions

Selecting only relevant stock dimensions is consistent with the released harness design:

- Benchmark metadata identifies the dimensions relevant to each prompt.
- The harness creates independent requests only for selected L1 dimensions.
- Disabled dimensions are absent/not evaluated rather than assigned zero.

The real-photo runner now exposes this directly:

```bash
--dimension "Quality"
--dimension "Aesthetics"
```

or:

```bash
--all-dimensions
```

This changes request selection, not the stock rubric wording.

## 3. Adding custom dimensions is technically plausible but experimental

Q-Judger remains a capable vision-language model based on Qwen3.6-27B, and its inference behavior is driven by explicit checklist text. It can therefore be asked to assess new photographic properties.

However, custom outputs must be treated as:

- Prompted experimental judgments
- Not official Qwen-Image-Bench scores
- Not covered by the reported human-agreement figures
- Potentially less calibrated than the trained stock facets

A custom dimension may still be useful if it is validated against Jacob's selections and produces stable, interpretable evidence.

## 4. Naming and versioning

Do not call custom facets simply "V2 dimensions" without identifying what they extend.

Use immutable, explicit rubric identities:

```text
qwen_stock_v1
birds_of_stone_real_photo_v1
birds_of_stone_icm_v1
```

A profile may select:

1. Only the stock pack
2. Only a custom pack
3. A clearly identified composite bundle containing unchanged stock dimensions plus wholly new custom dimensions

Example composite identity:

```text
qwen_stock_v1_plus_birds_of_stone_photo_v1
```

Stock and custom results must remain distinguishable per dimension and facet.

## 5. When to adapt versus add

### Adapt an existing facet only when

- The underlying concept remains intentionally comparable
- The wording changes to remove T2I-specific assumptions
- The result is labelled Qwen-derived/custom, not official

Example:

```text
Stock: Camera / Lens Style matches the requested prompt
Adapted: Visible camera/lens treatment is coherent and intentionally executed
```

### Add a new facet when

The property is genuinely different, for example:

- Motion Structure
- Subject Anchor Sharpness
- Motion-Sharpness Contrast
- Flash Freeze Presence
- Intentionality of Movement
- Set Utility

New concepts receive new stable `facet_concept_id` values.

## 6. Run consistency

A normal run uses one coherent rubric bundle and version for every selected image.

Do not silently combine:

```text
stock Quality
adapted Aesthetics
ICM Creative Generation
```

unless that exact mixture is declared as a named, versioned composite bundle.

Each L1 request remains logically isolated and stateless. Adding a custom L1 dimension adds another independent request; it does not alter the stock dimension responses.

## 7. Required refactor before arbitrary dimensions

The current prototype still has fixed stock-taxonomy assumptions in:

- `DIM_TO_CHECKLIST`
- `CHECKLIST_L3_TO_L2`
- `ALL_DIMENSIONS`
- Facet ID generation
- Analysis CSV row generation
- Official aggregation labels

A proper custom-dimension implementation should introduce a generic rubric registry, conceptually:

```python
RubricBundle
  id
  version
  classification
  dimensions

DimensionDefinition
  id
  label
  checklist
  l2_groups
  facets
```

Then:

1. Profiles select a rubric bundle and active dimensions.
2. Prompt construction reads the selected dimension definition.
3. Parsing preserves arbitrary nested L2/L3 output.
4. Aggregation follows the selected hierarchy.
5. Exports carry exact rubric/dimension/facet identities.
6. The report labels stock and custom results distinctly.

This is a contained refactor, but it is more than copying another checklist string because the current normalization and export code assumes the stock mapping.

## 8. Recommended sequence

1. Use stock dimensions with evidence on several photographs.
2. Inspect score variation and evidence quality.
3. Build the generic rubric registry only after identifying the first small custom dimension worth testing.
4. Add one narrow custom photography dimension.
5. Compare it against Jacob's manual ranking before expanding the custom taxonomy.

The first custom pack should remain small enough to reveal whether Q-Judger generalizes beyond its trained taxonomy.
