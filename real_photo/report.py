"""Minimal static HTML report for the first durable real-photo runner."""

from __future__ import annotations

import html
import json
from typing import Any, Iterable


def render_minimal_report(
    run_data: dict[str, Any],
    manifest: dict[str, Any],
    results: Iterable[dict[str, Any]],
) -> str:
    ordered = sorted(results, key=lambda record: record["sample_index"])
    payload = {
        "run": run_data,
        "manifest": manifest,
        "results": ordered,
    }
    serialized = _safe_script_json(payload)
    title = html.escape(f"Qwen Image Bench · {run_data['run_id']}")

    return f"""<!doctype html>
<html lang="en" data-theme="system">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light dark; --bg:#f5f6f8; --panel:#fff; --text:#17191d; --muted:#68707c; --border:#d9dde4; --accent:#315ee7; }}
html[data-theme="dark"] {{ color-scheme:dark; --bg:#111317; --panel:#1a1d23; --text:#f1f3f6; --muted:#a2a9b4; --border:#343a45; --accent:#84a2ff; }}
html[data-theme="light"] {{ color-scheme:light; }}
@media (prefers-color-scheme:dark) {{ html[data-theme="system"] {{ --bg:#111317; --panel:#1a1d23; --text:#f1f3f6; --muted:#a2a9b4; --border:#343a45; --accent:#84a2ff; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
header {{ position:sticky; top:0; z-index:3; background:color-mix(in srgb,var(--bg) 92%, transparent); backdrop-filter:blur(14px); border-bottom:1px solid var(--border); padding:16px 22px; }}
.header-row {{ display:flex; align-items:center; gap:14px; justify-content:space-between; }}
h1 {{ font-size:18px; margin:0; }}
.meta {{ color:var(--muted); margin-top:6px; display:flex; flex-wrap:wrap; gap:8px 18px; }}
.controls {{ display:flex; align-items:center; gap:8px; }}
button,select {{ font:inherit; color:inherit; background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:7px 10px; }}
main {{ padding:20px 22px 48px; max-width:1800px; margin:auto; }}
.status {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:16px; color:var(--muted); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px; align-items:start; }}
.card {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; overflow:hidden; min-width:0; }}
.card img {{ width:100%; height:auto; max-height:520px; object-fit:contain; display:block; background:#090a0c; }}
.card-body {{ padding:12px; }}
.card-title {{ display:flex; gap:10px; align-items:flex-start; justify-content:space-between; }}
.filename {{ font-weight:650; overflow-wrap:anywhere; }}
.score {{ font-variant-numeric:tabular-nums; font-size:16px; font-weight:700; color:var(--accent); white-space:nowrap; }}
.path {{ color:var(--muted); font-size:12px; margin:5px 0 10px; overflow-wrap:anywhere; }}
.pills {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }}
.pill {{ border:1px solid var(--border); border-radius:999px; padding:3px 7px; font-size:12px; }}
details {{ border-top:1px solid var(--border); padding-top:9px; margin-top:9px; }}
summary {{ cursor:pointer; font-weight:600; }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:9px; font-size:11px; max-height:320px; overflow:auto; }}
a {{ color:var(--accent); }}
.pager {{ display:flex; align-items:center; justify-content:center; gap:10px; margin:22px 0 0; }}
.empty {{ padding:40px; text-align:center; color:var(--muted); }}
</style>
</head>
<body>
<header>
  <div class="header-row">
    <div>
      <h1>Qwen Image Bench · Real-photo run</h1>
      <div class="meta" id="run-meta"></div>
    </div>
    <div class="controls">
      <label>Theme <select id="theme"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
      <label>Page <select id="page-size"><option>12</option><option selected>24</option><option>48</option><option>96</option></select></label>
    </div>
  </div>
</header>
<main>
  <div class="status" id="status"></div>
  <div class="grid" id="grid"></div>
  <div class="pager"><button id="previous">Previous</button><span id="page-label"></span><button id="next">Next</button></div>
</main>
<script id="report-data" type="application/json">{serialized}</script>
<script>
const data = JSON.parse(document.getElementById('report-data').textContent);
let page = 0;
let pageSize = 24;
const scoreText = value => value == null ? 'N/A' : Number(value).toFixed(2);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function render() {{
  const results = data.results;
  const pageCount = Math.max(1, Math.ceil(results.length / pageSize));
  page = Math.min(page, pageCount - 1);
  const shown = results.slice(page * pageSize, (page + 1) * pageSize);
  document.getElementById('grid').innerHTML = shown.length ? shown.map(card).join('') : '<div class="empty">No completed results yet.</div>';
  document.getElementById('page-label').textContent = `Page ${{page + 1}} of ${{pageCount}}`;
  document.getElementById('previous').disabled = page === 0;
  document.getElementById('next').disabled = page + 1 >= pageCount;
}}
function card(result) {{
  const official = result.official_scores || {{}};
  const l1 = official.level1 || {{}};
  const pills = Object.entries(l1).map(([name,score]) => `<span class="pill">${{escapeHtml(name)}} ${{scoreText(score)}}</span>`).join('');
  const responseBlocks = Object.entries(result.dimensions || {{}}).filter(([,state]) => state.request_status !== 'not_evaluated').map(([dimension,state]) => `<h4>${{escapeHtml(dimension)}} · ${{escapeHtml(state.parse_status)}}</h4><pre>${{escapeHtml(state.raw_response || state.error || '')}}</pre>`).join('');
  return `<article class="card">
    <a href="${{escapeHtml(result.source_uri)}}"><img loading="lazy" src="${{escapeHtml(result.source_uri)}}" alt="${{escapeHtml(result.source_relative_path)}}"></a>
    <div class="card-body">
      <div class="card-title"><div class="filename">${{escapeHtml(result.source_relative_path)}}</div><div class="score">${{scoreText(official.active_dimension_aggregate)}}</div></div>
      <div class="path">${{escapeHtml(result.source_path)}}</div>
      <div class="pills">${{pills}}</div>
      <a href="${{escapeHtml(result.source_uri)}}">Open original</a>
      <details><summary>Official hierarchy</summary><pre>${{escapeHtml(JSON.stringify(official,null,2))}}</pre></details>
      <details><summary>Raw judge responses</summary>${{responseBlocks}}</details>
    </div>
  </article>`;
}}
const run = data.run;
const manifest = data.manifest;
document.getElementById('run-meta').innerHTML = [
  `Run <strong>${{escapeHtml(run.run_id)}}</strong>`,
  `Profile ${{escapeHtml(run.evaluation_profile.name)}}`,
  `Model ${{escapeHtml(run.model.id)}}`,
  `Seed ${{manifest.sample_seed}}`
].map(item => `<span>${{item}}</span>`).join('');
document.getElementById('status').innerHTML = [
  `Status: ${{escapeHtml(run.status)}}`,
  `Completed: ${{data.results.length}} / ${{manifest.selected_count}}`,
  `Eligible: ${{manifest.eligible_count}}`,
  `Requested maximum: ${{manifest.requested_maximum}}`
].map(item => `<span>${{item}}</span>`).join('');
const theme = document.getElementById('theme');
try {{ theme.value = localStorage.getItem('qwen-report-theme') || 'system'; }} catch {{ theme.value = 'system'; }}
document.documentElement.dataset.theme = theme.value;
theme.addEventListener('change', () => {{ document.documentElement.dataset.theme = theme.value; try {{ localStorage.setItem('qwen-report-theme',theme.value); }} catch {{}} }});
document.getElementById('page-size').addEventListener('change', event => {{ pageSize = Number(event.target.value); page = 0; render(); }});
document.getElementById('previous').addEventListener('click', () => {{ page--; render(); window.scrollTo(0,0); }});
document.getElementById('next').addEventListener('click', () => {{ page++; render(); window.scrollTo(0,0); }});
render();
</script>
</body>
</html>
"""


def _safe_script_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
