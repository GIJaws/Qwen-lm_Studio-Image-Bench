# Stateful LM Studio Branching and Bounded Concurrency

**Status:** Experimental optional path  
**Branch:** `chatgpt/stateful-concurrency`  
**Base:** `chatgpt/real-photo-runner`

## Purpose

Process the photograph and shared context once through LM Studio's native stateful
`POST /api/v1/chat` endpoint, then branch the selected L1 dimension evaluations
from the returned `response_id`.

This path is intentionally separate from the existing stateless runner until
live testing shows that:

1. LM Studio accepts concurrent branches from the same response ID.
2. The native MLX runtime overlaps those requests with Max Concurrent Predictions.
3. Stateful branching materially reduces repeated image/prompt processing.
4. The shared `READY` turn does not harm scoring behavior.

LM Studio documents stateful conversation branching. It does not explicitly
guarantee that this particular VLM/image prefix will reuse a vision or KV cache,
so the run metadata records that cache reuse is not assumed.

## Request topology

```text
Image + real-photo context
        |
        | native /api/v1/chat, store=true
        v
shared response_id
        |
        +-- Quality branch
        +-- Aesthetics branch
        +-- Creative Generation branch
        +-- optional additional dimensions
```

The base request asks the model to retain the image/context and respond `READY`.
That assistant response becomes part of every branch's history. The branch
therefore remains an experimental execution variant rather than an identical
implementation of the stock stateless harness.

## Bounded concurrency

When `--concurrency` is omitted, the CLI calls `GET /api/v1/models`, locates the
loaded model instance, and reads:

```text
loaded_instances[].config.parallel
```

For Jacob's current LM Studio configuration this should resolve to `4`.
The detected value is printed before inference starts.

An explicit override remains available:

```bash
--concurrency 4
```

No more than that number of branch HTTP requests run at once. Dimensions beyond
the limit remain queued in the local Python executor. They do not reach LM
Studio, and their HTTP timeout does not begin, until a worker slot becomes
available.

If model-list detection fails or the loaded instance does not expose a positive
`config.parallel`, the runner falls back safely to concurrency `1` and prints the
detection error. An explicit `--concurrency` bypasses detection.

The runner currently finishes one image's branch set before creating the shared
context for the next image. This keeps checkpointing and state ownership simple.
Global cross-image scheduling can be considered after the first measurements.

## Streaming

Streaming is enabled by default for the native endpoint.

The terminal displays concise SSE phase events:

- prompt processing start/progress/end
- reasoning start
- response generation start
- final token count and tokens/second when provided

The runner consumes the final `chat.end` event, which contains the same aggregate
result as a non-streaming native chat response.

Disable streaming/progress with:

```bash
--no-stream-progress
```

## Parameter comparison

The stateful native endpoint supports the parameters used by the judge except
for request-level `seed`.

| Judge setting | Stateless `/v1/chat/completions` | Stateful `/api/v1/chat` |
|---|---:|---:|
| temperature | yes | yes |
| top_p | yes | yes |
| top_k | yes | yes |
| repeat penalty | yes | yes |
| max output tokens | `max_tokens` | `max_output_tokens` |
| streaming | yes | yes, with prompt-processing events |
| reasoning mode | runtime/template dependent | explicit `reasoning` |
| context length per request | no | yes |
| seed | yes | **not documented/supported** |
| previous response/branching | no | yes |
| structured `response_format` | available on compatible OpenAI paths | not part of native chat schema |
| stop, presence/frequency penalties, logit bias | OpenAI path supports them | not part of native chat schema |

For this project:

- Structured output is not required because Qwen's JSON prompt plus parser is retained.
- Stop, presence/frequency penalties, and logit bias are not currently used.
- `seed` is the only current baseline judge setting that cannot be sent through
  the documented stateful request. Configure deterministic sampling in LM Studio
  if the loaded-model settings expose it.
- Image-sampling seed remains separate and is always recorded in the sample
  manifest.

## Test stateless concurrency first

Use one representative JPEG:

```bash
uv run --active python benchmark_lm_studio_concurrency.py \
  --image "/absolute/path/to/photo.jpg" \
  --model "qwen-image-bench-mlx" \
  --workers 1 \
  --workers 4
```

The script sends all five stock L1 requests in each test. It uses a locally
bounded executor, so a worker count of four creates at most four active HTTP
requests. Each worker receives its own Pillow image copy before serialization.

Compare the wall times:

```text
workers=1: ...
workers=4: ...
```

A lower four-worker wall time confirms that the server/runtime is overlapping
requests rather than processing them strictly one by one.

## Run the stateful experiment

First use a fixed image sample so stateless and stateful runs are comparable:

```bash
uv run --active python run_stateful_photos.py \
  --folder "/Users/jacobpeacock/Pictures/StackyPics/" \
  --sample-count 1 \
  --sample-seed 42 \
  --dimension "Quality" \
  --dimension "Aesthetics" \
  --model "qwen-image-bench-mlx" \
  --lm-studio-timeout 900
```

The CLI will normally detect the loaded model's configured parallel limit. Pass
`--concurrency 4` only when you want to override or bypass detection.

To run all five stock dimensions:

```bash
--all-dimensions
```

The stateful CLI does not expose `--lm-studio-seed`, because the documented
native request schema has no seed field.

## What to compare

Use the same photo/sample seed and dimensions for both paths.

Record:

- total wall time
- base-context prompt-processing time
- branch time-to-first-token
- branch input-token counts
- output scores and evidence
- parse failures
- whether four branches visibly overlap
- whether the same response ID can be used by concurrent branches reliably

The native endpoint returns per-request stats, which are stored in each
dimension's `inference_stats` and in the `stateful_context` record.

## Current limitations

- Cache reuse is not proven merely because a response ID is used.
- The base `READY` assistant turn changes the exact conversational history.
- A restarted LM Studio server may invalidate a saved response ID; the current
  runner creates a fresh shared context whenever unfinished dimensions are
  resumed.
- Only dimension branches for one image are concurrent.
- The native endpoint does not accept the stateless request-level seed.
- The stateful path remains optional and must not replace stateless baseline
  results until score and performance comparisons are reviewed.
