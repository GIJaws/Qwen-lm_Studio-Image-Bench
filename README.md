# Qwen-Image-Bench

<p align="center">
  <a href="http://arxiv.org/abs/2605.28091"><img src="https://img.shields.io/badge/Paper-arXiv-b31b1b?logo=arxiv" alt="Paper"></a>
  <a href="https://huggingface.co/datasets/Qwen/Qwen-Image-Bench"><img src="https://img.shields.io/badge/Dataset-HuggingFace-ffd21e?logo=huggingface" alt="Dataset"></a>
  <a href="https://huggingface.co/Qwen/Qwen-Image-Bench"><img src="https://img.shields.io/badge/Judge_Model-HuggingFace-ffd21e?logo=huggingface" alt="Model"></a>
  <a href="https://www.modelscope.cn/datasets/Qwen/Qwen-Image-Bench"><img src="https://img.shields.io/badge/Dataset-ModelScope-624aff?logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjIyIiBoZWlnaHQ9IjIyMiIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNNzEuNTU2IDcyLjg4OGgzOC42Njd2MzguNjY3SDcxLjU1NnpNMTExLjU1NiAxMTIuODg4aDM4LjY2N3YzOC42NjdoLTM4LjY2N3pNNzEuNTU2IDExMi44ODhoMzguNjY3djM4LjY2N0g3MS41NTZ6IiBmaWxsPSIjNjI0QUZGIi8+PC9zdmc+" alt="ModelScope"></a>
  <a href="https://www.apache.org/licenses/LICENSE-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue" alt="License"></a>
</p>

An evaluation toolkit for text-to-image (T2I) generation models. It uses a fine-tuned **Q-Judger** (Qwen3.6-27B) to score generated images across **5 hierarchical dimensions** (Quality, Aesthetics, Alignment, Real-world Fidelity, Creative Generation) covering **56 fine-grained facets**.

<p align="center">
  <img src="assets/show_case.png" alt="Qwen-Image-Bench dimension framework and representative model outputs">
</p>

## Key Features

- **Evaluate any T2I model** — run the judge model on your own generated images and get structured, multi-dimensional scores
- **Compute scores from pre-generated responses** — reproduce the leaderboard from the released benchmark dataset
- **Powered by ms-swift** — uses the same inference setup that produced the benchmark responses
- **Optional LM Studio backend** — route the existing judge harness to a locally served MLX model through LM Studio's OpenAI-compatible `/v1/chat/completions` API

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/QwenLM/Qwen-Image-Bench.git
cd Qwen-Image-Bench

# 2. Install dependencies
uv venv myenv --python 3.11 && source myenv/bin/activate
# Install PyTorch first: https://pytorch.org/get-started/locally/
uv pip install -r requirements.txt

# 3. Run judge on your images with the upstream ms-swift backend
python judge.py \
  --input your_data.jsonl \
  --model Qwen/Qwen-Image-Bench
```

Your input file should be a CSV/JSON/JSONL with three columns:

| Column | Type | Description |
|--------|------|-------------|
| `ID` | int | Prompt identifier (1–1000), must match [benchmark metadata](metadata/bench_metadata.json) |
| `prompt` | str | The text prompt used to generate the image |
| `image_path` | str | Path to the generated image file |


## Installation


### Step-by-step

**1. Create and activate a virtual environment:**

```bash
uv venv myenv --python 3.11
source myenv/bin/activate
```

**2. Install PyTorch** (select the command matching your CUDA version):

See the official guide: [https://pytorch.org/get-started/locally/](https://pytorch.org/get-started/locally/)

**3. Install Python dependencies:**

```bash
uv pip install -r requirements.txt
```

This installs all required dependencies including ms-swift.


## Usage

### Evaluate Your Own T2I Model (`judge.py`)

#### Run Judge Inference with ms-swift

```bash
python judge.py \
  --input your_data.jsonl \
  --model Qwen/Qwen-Image-Bench
```

#### Run Judge Inference with LM Studio

Start LM Studio as a local server, load the Qwen-Image-Bench-compatible model in LM Studio, then use the model identifier shown by LM Studio:

```bash
python judge.py \
  --backend lm-studio \
  --input your_data.jsonl \
  --model "your-lm-studio-model-identifier" \
  --lm-studio-base-url http://localhost:1234/v1
```

The LM Studio backend preserves the upstream harness semantics: every `(image, level-1 dimension)` task is sent as an independent single-turn `/v1/chat/completions` request. It does not reuse conversation state across Quality, Aesthetics, Alignment, Real-world Fidelity, or Creative Generation passes.

By default, the backend sends image inputs as inline PNG data URLs and uses the same deterministic sampling values as the upstream harness where LM Studio exposes matching request fields: `temperature=0`, `top_k=1`, `top_p=1.0`, `repeat_penalty=1.05`, `seed=42`, and `max_tokens=4096`.

For LM Studio-specific request fields that are not first-class CLI arguments, pass a JSON object that will be merged into every request body:

```bash
python judge.py \
  --backend lm-studio \
  --input your_data.jsonl \
  --model "your-lm-studio-model-identifier" \
  --lm-studio-extra-body-json '{"response_format":{"type":"json_object"}}'
```

That option is intentionally explicit so the default path remains close to Qwen's original prompt-and-parse workflow.

#### CLI Options

| Argument | Default | Description |
|----------|---------|-------------|
| `--input` | *(required)* | Input CSV/JSON/JSONL with `ID`, `prompt`, `image_path` |
| `--model` | *(required)* | HuggingFace/local model path for `ms-swift`, or LM Studio model identifier for `lm-studio` |
| `--backend` | `ms-swift` | Inference backend: `ms-swift` or `lm-studio` |
| `--hf-bench-repo` | — | HF dataset repo for bench metadata |
| `--local-metadata` | — | Local metadata file path (overrides default) |
| `--max-batch-size` | 24 | Harness batch size; also ms-swift `PtEngine` max_batch_size |
| `--max-new-tokens` | 4096 | Max generation tokens |
| `--lm-studio-base-url` | `http://localhost:1234/v1` | LM Studio OpenAI-compatible base URL |
| `--lm-studio-timeout` | 300 | Per-request timeout in seconds |
| `--lm-studio-temperature` | 0 | LM Studio temperature |
| `--lm-studio-top-k` | 1 | LM Studio top_k |
| `--lm-studio-top-p` | 1.0 | LM Studio top_p |
| `--lm-studio-repeat-penalty` | 1.05 | LM Studio repeat_penalty |
| `--lm-studio-seed` | 42 | LM Studio seed when supported |
| `--lm-studio-no-seed` | false | Omit the `seed` field from LM Studio requests |
| `--lm-studio-image-format` | `PNG` | Inline image payload format: `PNG`, `JPEG`, or `WEBP` |
| `--lm-studio-extra-body-json` | — | JSON object merged into each LM Studio request body |

#### Output Files

After running `judge.py`, three files are written next to your input:

| File | Contents |
|------|----------|
| `<input>_judged.{jsonl,csv}` | Per-row results: original fields + `judge_model_output` (combined raw scores JSON) + `<dim>_judge_output` (raw judge text per L1 dimension) |
| `<input>_bench_scores.json` | Aggregated scores: `level1`, `level2`, `total` |
| `<input>_bench_scores.xlsx` | Same scores in Excel: `Level-1 Summary` sheet + one sheet per L1 dimension with L2 detail |

### Compute Scores from Pre-generated Responses (`compute_scores.py`)


```bash
# From local file
python compute_scores.py --input qwen_image_bench_hf_v0518.jsonl

# Or download from HuggingFace
python compute_scores.py --hf-repo Qwen/Qwen-Image-Bench
```

Output: `scores_result.xlsx` + `scores_detail.json`


## Top-5 Models

| Model | Quality | Aesthetics | Alignment | Real-world Fidelity | Creative Generation | **Overall** |
|-------|:-------:|:----------:|:---------:|:-------------------:|:-------------------:|:-----------:|
| GPT Image 2 | **58.65** | **67.53** | **65.85** | **57.38** | **75.23** | **64.69** |
| Nano Banana 2.0 | 54.77 | 61.08 | 62.40 | 54.28 | 67.05 | 59.82 |
| GPT Image 1.5 | 55.14 | 60.88 | 61.72 | 53.95 | 66.35 | 59.65 |
| Nano Banana Pro | 55.67 | 60.26 | 61.25 | 54.07 | 66.23 | 59.45 |
| Qwen Image 2.0 Pro | 54.39 | 58.67 | 59.28 | 51.83 | 64.94 | 57.84 |

Full results for all 18 models are available in the paper.


## Inference Parameters

The upstream judge model uses fixed inference parameters for reproducibility:

| Parameter | Value |
|-----------|-------|
| `seed` | 42 |
| `temperature` | 0 |
| `top_k` | 1 |
| `top_p` | 1.0 |
| `repetition_penalty` | 1.05 |
| `max_new_tokens` | 4096 |
| `enable_thinking` | True |
| `max_batch_size` | 24 |

The LM Studio backend sends the matching OpenAI-compatible fields exposed by LM Studio. Runtime-specific fields that are not standardized for `/v1/chat/completions` can be supplied with `--lm-studio-extra-body-json`.


## Project Structure

```
.
├── judge.py                     # Run judge model inference on new images
├── compute_scores.py            # Compute scores from pre-generated responses
├── score_utils.py               # Score extraction, mapping, correction, aggregation
├── checklists.py                # Evaluation prompts and dimension definitions
├── backends/
│   ├── ms_swift_backend.py      # ms-swift inference engine
│   └── lm_studio_backend.py     # LM Studio OpenAI-compatible inference backend
├── metadata/
│   └── bench_metadata.json      # ID → dims_en metadata for judge inference
├── tests/
│   └── test_lm_studio_backend.py
├── requirements.txt
└── assets/                      # Figures for documentation
```


## Evaluation Framework

The benchmark uses a **3-level hierarchical scoring system** with 5 L1 dimensions, 23 L2 sub-capabilities, and 56 L3 facets:

| L1 Dimension | L2 Sub-capabilities |
|--------------|---------------------|
| **Quality** | Realism, Detail, Resolution |
| **Aesthetics** | Composition, Color Harmony, Lighting, Anatomical Portraiture, Emotional Expression, Style Control |
| **Alignment** | Attributes, Actions, Layout, Relations, Scene |
| **Real-world Fidelity** | Fairness, Safety & Compliance, World Knowledge |
| **Creative Generation** | Imagination, Feature Matching, Logical Resolution, Text Rendering, Design Applications, Visual Storytelling |

**Scoring**: Each L3 facet is rated 0 (Fail → 0), 1 (Pass → 60), or 2 (Excel → 100), with N/A excluded. Scores aggregate bottom-up: L3 → L2 → L1 → Overall.

For the complete dimension hierarchy and detailed analysis, see the [benchmark dataset card](https://huggingface.co/datasets/Qwen/Qwen-Image-Bench).


## Citation

If you find this benchmark useful, please cite our paper:

```bibtex
@misc{li2026qwenimagebenchgenerationcreationtexttoimage,
      title={Qwen-Image-Bench: From Generation to Creation in Text-to-Image Evaluation}, 
      author={Niantong Li and Guangzheng Hu and Weixu Qiao and Ying Ba and Qichen Hong and Shijun Shen and Jinlin Wang and Fan Zhou and Jianye Kang and Xin Shang and Ziyi He and Wei Wang and Dalin Li and Jiahao Li and Jie Zhang and Kaiyuan Gao and Kun Yan and Lihan Jiang and Ningyuan Tang and Shengming Yin and Tianhe Wu and Xiao Xu and Xiaoyue Chen and Yuxiang Chen and Yan Shu and Yanran Zhang and Yilei Chen and Yixian Xu and Zekai Zhang and Zhendong Wang and Zihao Liu and Zikai Zhou and Hongzhu Shi and Yi Wang and Bing Zhao and Hu Wei and Lin Qu and Chenfei Wu},
      year={2026},
      eprint={2605.28091},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2605.28091}, 
}
```

## License

This project is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
