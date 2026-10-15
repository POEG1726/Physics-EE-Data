from __future__ import annotations

import csv
import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent

LOAD_ORDER = {
    "short": -math.inf,
    "open": math.inf,
}
COLORS = [
    "#2563eb",
    "#ea580c",
    "#16a34a",
    "#9333ea",
    "#dc2626",
    "#0891b2",
    "#ca8a04",
    "#4f46e5",
    "#be123c",
    "#0f766e",
    "#64748b",
    "#111827",
]
Z0_BY_CABLE = {
    "RG58": 50.0,
    "RG179": 75.0,
}


@dataclass(frozen=True)
class TraceId:
    cable: str
    length_m: int | None
    load_label: str
    load_ohm: float | None
    special_load: str | None
    path: Path
    is_wrong: bool = False
    is_direct: bool = False

    @property
    def group_key(self) -> tuple[str, int | None]:
        return self.cable, self.length_m

    @property
    def group_label(self) -> str:
        if self.is_direct:
            return "Direct connection"
        return f"{self.cable} {self.length_m}m"

    @property
    def sort_key(self) -> tuple[float, str]:
        if self.special_load:
            return LOAD_ORDER[self.special_load], self.load_label
        return float(self.load_ohm or 0), self.load_label


@dataclass
class Trace:
    ident: TraceId
    meta: dict[str, str]
    data: list[tuple[float, float]]
    color: str = "#2563eb"
    summary: dict[str, float | int | str | None] | None = None


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value or "trace"


def parse_trace_id(path: Path) -> TraceId | None:
    stem = path.stem
    if stem.lower() == "data_status":
        return None
    if stem.lower() == "direct-connection":
        return TraceId("DIRECT", None, "direct", None, None, path, is_direct=True)

    match = re.match(r"^(rg\d+)-(\d+)m-(.+)$", stem, flags=re.IGNORECASE)
    if not match:
        return None

    cable = match.group(1).upper()
    length_m = int(match.group(2))
    load_token = match.group(3).lower()
    is_wrong = "wrong" in load_token
    load_token = load_token.replace("-wrong", "").replace("_wrong", "").replace("wrong", "")
    load_token = load_token.strip("-_")

    if load_token in ("open", "short"):
        return TraceId(cable, length_m, load_token, None, load_token, path, is_wrong=is_wrong)

    ohm_match = re.match(r"^(\d+(?:\.\d+)?)ohm$", load_token)
    if ohm_match:
        load_ohm = float(ohm_match.group(1))
        label = f"{load_ohm:g} ohm"
        return TraceId(cable, length_m, label, load_ohm, None, path, is_wrong=is_wrong)

    return None


def discover_traces() -> tuple[list[TraceId], list[TraceId], list[Path]]:
    included: list[TraceId] = []
    excluded: list[TraceId] = []
    ignored: list[Path] = []
    for path in sorted(DATA_DIR.glob("*.csv"), key=lambda p: p.name.lower()):
        ident = parse_trace_id(path)
        if ident is None:
            if path.name.lower() != "data_status.csv":
                ignored.append(path)
            continue
        if ident.is_wrong:
            excluded.append(ident)
        else:
            included.append(ident)
    return included, excluded, ignored


def read_scope_csv(path: Path) -> tuple[dict[str, str], list[tuple[float, float]]]:
    rows = list(csv.reader(path.open(newline="", encoding="utf-8-sig")))
    meta: dict[str, str] = {}
    data_start = None
    for idx, row in enumerate(rows):
        if len(row) >= 2 and row[0] == "Second" and row[1] == "Value":
            data_start = idx + 1
            break
        if len(row) >= 2:
            meta[row[0]] = row[1]
    if data_start is None:
        raise ValueError(f"{path} does not contain a Second,Value header")
    data = [(float(row[0]) * 1e9, float(row[1])) for row in rows[data_start:] if len(row) >= 2]
    return meta, data


def load_traces(ids: Iterable[TraceId]) -> list[Trace]:
    traces: list[Trace] = []
    for ident in ids:
        meta, data = read_scope_csv(ident.path)
        traces.append(Trace(ident=ident, meta=meta, data=data))
    return traces


def first_n_average(data: list[tuple[float, float]], n: int = 100) -> float:
    count = min(n, len(data))
    return sum(y for _, y in data[:count]) / count


def get_window(data: list[tuple[float, float]], low: float, high: float) -> list[tuple[float, float]]:
    return [(x, y) for x, y in data if low <= x <= high]


def extremum_by_abs(points: list[tuple[float, float]]) -> tuple[float | None, float | None]:
    if not points:
        return None, None
    x, y = max(points, key=lambda p: abs(p[1]))
    return x, y


def reflection_prediction(ident: TraceId) -> float | None:
    z0 = Z0_BY_CABLE.get(ident.cable)
    if z0 is None:
        return None
    if ident.special_load == "short":
        return -1.0
    if ident.special_load == "open":
        return 1.0
    if ident.load_ohm is None:
        return None
    return (ident.load_ohm - z0) / (ident.load_ohm + z0)


def summarize_trace(trace: Trace) -> dict[str, float | int | str | None]:
    data = trace.data
    values = [y for _, y in data]
    baseline = first_n_average(data)
    corrected = [(x, y - baseline) for x, y in data]
    inc_x, inc_y = extremum_by_abs(get_window(corrected, -100, 80))

    refl_x = None
    refl_y = None
    if trace.ident.length_m is not None and inc_x is not None:
        expected_round_trip_ns = trace.ident.length_m * 10.3
        center = inc_x + expected_round_trip_ns
        half_width = max(25.0, expected_round_trip_ns * 0.25)
        refl_x, refl_y = extremum_by_abs(get_window(corrected, center - half_width, center + half_width))

    gamma_pred = reflection_prediction(trace.ident)
    ratio = None
    scale = None
    if inc_y not in (None, 0) and refl_y is not None:
        ratio = refl_y / inc_y
        if gamma_pred not in (None, 0):
            scale = ratio / gamma_pred

    return {
        "file": trace.ident.path.name,
        "group": trace.ident.group_label,
        "load": trace.ident.load_label,
        "points": len(data),
        "t_min_ns": min(x for x, _ in data),
        "t_max_ns": max(x for x, _ in data),
        "v_min": min(values),
        "v_max": max(values),
        "baseline_v": baseline,
        "tail_v": sum(values[-min(100, len(values)):]) / min(100, len(values)),
        "incident_t_ns": inc_x,
        "incident_v": inc_y,
        "reflection_t_ns": refl_x,
        "reflection_v": refl_y,
        "reflection_over_incident": ratio,
        "gamma_pred": gamma_pred,
        "scale_vs_gamma": scale,
    }


def assign_colors(traces: list[Trace]) -> None:
    for idx, trace in enumerate(sorted(traces, key=lambda t: (t.ident.cable, t.ident.length_m or -1, t.ident.sort_key))):
        trace.color = COLORS[idx % len(COLORS)]


def write_summary_csv(traces: list[Trace]) -> None:
    fieldnames = [
        "group",
        "load",
        "file",
        "points",
        "t_min_ns",
        "t_max_ns",
        "v_min",
        "v_max",
        "baseline_v",
        "tail_v",
        "incident_t_ns",
        "incident_v",
        "reflection_t_ns",
        "reflection_v",
        "reflection_over_incident",
        "gamma_pred",
        "scale_vs_gamma",
    ]
    with (SCRIPT_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trace in sorted(traces, key=lambda t: (t.ident.cable, t.ident.length_m or -1, t.ident.sort_key)):
            writer.writerow({key: trace.summary.get(key) if trace.summary else "" for key in fieldnames})


def status_table_html() -> str:
    status_path = DATA_DIR / "data_status.csv"
    if not status_path.exists():
        return ""
    rows = list(csv.reader(status_path.open(newline="", encoding="utf-8-sig")))
    if not rows:
        return ""
    header, body = rows[0], rows[1:]
    head = "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
    body_rows = []
    for row in body:
        cells = []
        for cell in row:
            cls = "ok" if cell == "X" else "missing" if cell == "" else ""
            cells.append(f'<td class="{cls}">{html.escape(cell)}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
      <details class="status-panel">
        <summary>Data status</summary>
        <table class="status-table"><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>
      </details>
"""


def trace_to_json(trace: Trace) -> dict[str, object]:
    ident = trace.ident
    trace_id = slug(f"{ident.cable}_{ident.length_m}_{ident.load_label}_{ident.path.stem}")
    if ident.is_direct:
        trace_id = "direct_connection"
    return {
        "id": trace_id,
        "label": f"{ident.group_label} {ident.load_label}",
        "group": ident.group_label,
        "cable": ident.cable,
        "lengthM": ident.length_m,
        "loadLabel": ident.load_label,
        "loadOhm": ident.load_ohm,
        "specialLoad": ident.special_load,
        "file": ident.path.name,
        "isDirect": ident.is_direct,
        "color": trace.color,
        "summary": trace.summary,
        "t": [round(x, 10) for x, _ in trace.data],
        "v": [round(y, 10) for _, y in trace.data],
    }


def default_window(traces: list[Trace]) -> dict[str, float]:
    candidates = [trace for trace in traces if trace.ident.cable == "RG58" and trace.ident.length_m == 10]
    if not candidates:
        candidates = [trace for trace in traces if not trace.ident.is_direct]
    if not candidates:
        candidates = traces
    all_t = [x for trace in candidates for x, _ in trace.data]
    if not all_t:
        return {"start": -100.0, "end": 250.0}
    return {"start": max(-100.0, min(all_t)), "end": min(250.0, max(all_t))}


def build_html(traces: list[Trace], excluded: list[TraceId], ignored: list[Path]) -> str:
    trace_json = {
        "generatedFrom": ".",
        "units": {"time": "ns", "voltage": "V"},
        "defaultWindow": default_window(traces),
        "statusHtml": status_table_html(),
        "excluded": [
            {"group": item.group_label, "load": item.load_label, "file": item.path.name}
            for item in excluded
        ],
        "ignored": [path.name for path in ignored],
        "traces": [trace_to_json(trace) for trace in traces],
    }
    data_json = json.dumps(trace_json, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")
    html_text = HTML_TEMPLATE.replace("__TRACE_DATA_JSON__", data_json)
    return html_text


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>Waveform Alignment Lab</title>
<style>
  :root {
    --bg: #f7f8fb;
    --panel: #ffffff;
    --line: #d7dde8;
    --text: #121826;
    --muted: #526070;
    --accent: #2563eb;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: Arial, Helvetica, sans-serif;
  }
  header {
    padding: 14px 18px;
    border-bottom: 1px solid var(--line);
    background: #fff;
  }
  h1 {
    font-size: 22px;
    margin: 0;
    letter-spacing: 0;
  }
  .subhead {
    margin-top: 4px;
    color: var(--muted);
    font-size: 13px;
  }
  .app {
    display: grid;
    grid-template-columns: minmax(330px, 390px) minmax(0, 1fr);
    min-height: calc(100vh - 65px);
  }
  aside {
    border-right: 1px solid var(--line);
    background: #fff;
    padding: 14px;
    overflow: auto;
    max-height: calc(100vh - 65px);
  }
  main {
    padding: 14px;
    overflow: auto;
  }
  section {
    border: 1px solid var(--line);
    background: var(--panel);
    margin-bottom: 12px;
  }
  section > h2 {
    font-size: 14px;
    margin: 0;
    padding: 10px 12px;
    border-bottom: 1px solid var(--line);
    background: #f1f4f9;
  }
  .section-body { padding: 10px 12px; }
  label {
    display: block;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 4px;
  }
  input, select, button {
    font: inherit;
  }
  input[type="number"], input[type="text"], select {
    width: 100%;
    min-height: 30px;
    border: 1px solid #cbd3df;
    background: #fff;
    color: var(--text);
    padding: 4px 7px;
  }
  input[type="range"] {
    width: 100%;
  }
  button {
    min-height: 30px;
    border: 1px solid #bcc6d6;
    background: #fff;
    color: var(--text);
    padding: 4px 9px;
    cursor: pointer;
  }
  button.primary {
    border-color: var(--accent);
    background: var(--accent);
    color: #fff;
  }
  button:disabled {
    color: #94a3b8;
    cursor: default;
  }
  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .grid-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
  }
  .button-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }
  .trace-list {
    max-height: 290px;
    overflow: auto;
    border: 1px solid var(--line);
  }
  .trace-row {
    display: grid;
    grid-template-columns: 24px 14px minmax(0, 1fr);
    gap: 7px;
    align-items: center;
    padding: 6px 8px;
    border-bottom: 1px solid #edf0f5;
    font-size: 13px;
  }
  .trace-row:last-child { border-bottom: 0; }
  .trace-row input { width: 16px; height: 16px; }
  .swatch {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 1px solid rgba(0, 0, 0, 0.2);
  }
  .trace-meta {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .plot-shell {
    border: 1px solid var(--line);
    background: #fff;
    padding: 10px;
  }
  canvas {
    width: 100%;
    height: 590px;
    display: block;
    background: #fff;
  }
  .stats {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 8px 0 0;
    color: var(--muted);
    font-size: 13px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    font-size: 12px;
  }
  th, td {
    border-bottom: 1px solid #e3e8f0;
    padding: 6px 7px;
    text-align: right;
    white-space: nowrap;
  }
  th:first-child, td:first-child,
  th:nth-child(2), td:nth-child(2) {
    text-align: left;
  }
  th {
    background: #f1f4f9;
    color: #273142;
    position: sticky;
    top: 0;
  }
  .table-wrap {
    max-height: 310px;
    overflow: auto;
    border: 1px solid var(--line);
    background: #fff;
  }
  .curve-controls input[type="number"] {
    min-width: 86px;
  }
  .curve-controls input[type="range"] {
    min-width: 120px;
  }
  .pill {
    display: inline-block;
    padding: 1px 6px;
    border: 1px solid var(--line);
    background: #f8fafc;
    color: var(--muted);
    font-size: 12px;
  }
  details.status-panel {
    margin-top: 8px;
  }
  .status-table td.ok {
    color: #166534;
    font-weight: 700;
    text-align: center;
  }
  .status-table td.missing {
    background: #f8fafc;
  }
  .small-note {
    color: var(--muted);
    font-size: 12px;
    line-height: 1.35;
  }
  @media (max-width: 980px) {
    .app { grid-template-columns: 1fr; }
    aside { max-height: none; border-right: 0; border-bottom: 1px solid var(--line); }
    canvas { height: 430px; }
  }
</style>
</head>
<body>
<header>
  <h1>Waveform Alignment Lab</h1>
  <div class="subhead">Select traces, shift time/voltage, override baseline, and quantify waveform match in the current window.</div>
</header>
<div class="app">
  <aside>
    <section>
      <h2>Data Selection</h2>
      <div class="section-body">
        <div class="grid-3">
          <div><label for="cableFilter">Cable</label><select id="cableFilter"></select></div>
          <div><label for="lengthFilter">Length</label><select id="lengthFilter"></select></div>
          <div><label for="loadFilter">Load</label><select id="loadFilter"></select></div>
        </div>
        <div style="margin-top:8px;">
          <label for="searchFilter">Search</label>
          <input id="searchFilter" type="text" placeholder="file, group, load">
        </div>
        <div class="button-row">
          <button id="selectVisible" class="primary">Select visible</button>
          <button id="clearSelection">Clear</button>
          <button id="selectRg58">RG58 10m</button>
        </div>
        <div class="trace-list" id="traceList" style="margin-top:10px;"></div>
        <div style="margin-top:8px;">
          <label for="csvImport">Import CSV</label>
          <input id="csvImport" type="file" accept=".csv,text/csv" multiple>
        </div>
      </div>
    </section>

    <section>
      <h2>Display Window</h2>
      <div class="section-body">
        <div class="grid-2">
          <div><label for="windowStart">Start ns</label><input id="windowStart" type="number" step="0.5"></div>
          <div><label for="windowEnd">End ns</label><input id="windowEnd" type="number" step="0.5"></div>
        </div>
        <div class="grid-2" style="margin-top:8px;">
          <div><label for="baselineMode">Voltage mode</label><select id="baselineMode"><option value="corrected">Baseline corrected</option><option value="raw">Raw voltage</option></select></div>
          <div><label for="referenceSelect">Reference</label><select id="referenceSelect"></select></div>
        </div>
        <div class="grid-2" style="margin-top:8px;">
          <div><label for="maxPoints">Max draw points / trace</label><input id="maxPoints" type="number" min="100" max="20000" step="100"></div>
          <div><label for="autoY">Y range</label><select id="autoY"><option value="auto">Auto</option><option value="manual">Manual</option></select></div>
        </div>
        <div class="grid-2" style="margin-top:8px;">
          <div><label for="yMin">Y min V</label><input id="yMin" type="number" step="0.01"></div>
          <div><label for="yMax">Y max V</label><input id="yMax" type="number" step="0.01"></div>
        </div>
        <div class="button-row">
          <button id="fitSelected">Fit selected</button>
          <button id="fitWindow">Fit default window</button>
          <button id="recalculateBaseline">Recalculate selected baselines</button>
        </div>
        <p class="small-note" id="baselineStatus" style="margin:8px 0 0;">Baseline recalculation uses visible pre-peak samples when available.</p>
      </div>
    </section>

    <section>
      <h2>Global Shift</h2>
      <div class="section-body">
        <label for="globalTime">Time shift ns</label>
        <input id="globalTimeRange" type="range" min="-200" max="200" step="0.1">
        <input id="globalTime" type="number" step="0.1">
        <label for="globalVoltage" style="margin-top:8px;">Voltage shift V</label>
        <input id="globalVoltageRange" type="range" min="-2" max="2" step="0.001">
        <input id="globalVoltage" type="number" step="0.001">
        <div class="button-row">
          <button id="resetGlobal">Reset global</button>
          <button id="resetCurves">Reset curves</button>
        </div>
      </div>
    </section>

    <section>
      <h2>Auto Align</h2>
      <div class="section-body">
        <div class="grid-2">
          <div><label for="peakThreshold">Peak threshold %</label><input id="peakThreshold" type="number" min="1" max="100" step="1"></div>
          <div><label for="smoothingSamples">Smoothing samples</label><input id="smoothingSamples" type="number" min="1" max="101" step="2"></div>
        </div>
        <div class="button-row">
          <button id="autoAlignButton" class="primary">Align first positive peaks</button>
        </div>
        <p class="small-note" id="autoAlignStatus" style="margin:8px 0 0;">Uses currently displayed selected curves and moves each detected first peak to 0 ns.</p>
        <div class="table-wrap" style="max-height:190px; margin-top:8px;">
          <table>
            <thead><tr><th>Trace</th><th>Peak ns</th><th>Peak V</th><th>Delta ns</th><th>Status</th></tr></thead>
            <tbody id="autoAlignBody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section>
      <h2>Export</h2>
      <div class="section-body">
        <div class="button-row">
          <button id="exportJson">Alignment JSON</button>
          <button id="exportCsv">Alignment CSV</button>
          <button id="exportData">Corrected data CSV</button>
          <button id="exportPng">Screenshot PNG</button>
        </div>
        <p class="small-note" style="margin:8px 0 0;">Corrected data export uses the current time window and current baseline/shift values.</p>
      </div>
    </section>

    <section>
      <h2>Source Status</h2>
      <div class="section-body" id="statusSlot"></div>
    </section>
  </aside>

  <main>
    <div class="plot-shell">
      <canvas id="plotCanvas"></canvas>
      <div class="stats" id="plotStats"></div>
    </div>

    <section style="margin-top:12px;">
      <h2>Per-Curve Shift Controls</h2>
      <div class="section-body">
        <div class="table-wrap">
          <table class="curve-controls">
            <thead>
              <tr><th>Trace</th><th>File</th><th>Time ns</th><th></th><th>Voltage V</th><th></th><th>Baseline V</th><th>Visible pts</th></tr>
            </thead>
            <tbody id="curveControls"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section>
      <h2>Match Metrics</h2>
      <div class="section-body">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Trace</th><th>Reference</th><th>Samples</th><th>RMS V</th><th>MAE V</th><th>Correlation</th></tr></thead>
            <tbody id="metricsBody"></tbody>
          </table>
        </div>
      </div>
    </section>
  </main>
</div>

<script id="traceData" type="application/json">__TRACE_DATA_JSON__</script>
<script>
const embedded = JSON.parse(document.getElementById('traceData').textContent);
const palette = ['#2563eb','#ea580c','#16a34a','#9333ea','#dc2626','#0891b2','#ca8a04','#4f46e5','#be123c','#0f766e','#64748b','#111827'];
let traces = embedded.traces.map((trace, index) => normalizeTrace(trace, index));
let state = {
  selected: new Set(),
  filters: { cable: 'all', length: 'all', load: 'all', search: '' },
  transforms: {},
  baselineMode: 'corrected',
  referenceId: '',
  windowStart: embedded.defaultWindow.start,
  windowEnd: embedded.defaultWindow.end,
  autoY: true,
  yMin: -1.2,
  yMax: 1.2,
  globalTime: 0,
  globalVoltage: 0,
  maxPoints: 6000,
  peakThreshold: 25,
  smoothingSamples: 7,
  lastAutoAlign: null,
};

const els = {};
for (const id of [
  'cableFilter','lengthFilter','loadFilter','searchFilter','traceList','csvImport',
  'windowStart','windowEnd','baselineMode','referenceSelect','maxPoints','autoY','yMin','yMax',
  'globalTimeRange','globalTime','globalVoltageRange','globalVoltage','peakThreshold','smoothingSamples',
  'autoAlignButton','autoAlignStatus','autoAlignBody','plotCanvas','plotStats',
  'curveControls','metricsBody','statusSlot','recalculateBaseline','baselineStatus'
]) {
  els[id] = document.getElementById(id);
}

function normalizeTrace(trace, index) {
  trace.t = trace.t.map(Number);
  trace.v = trace.v.map(Number);
  trace.color = trace.color || palette[index % palette.length];
  trace.summary = trace.summary || {};
  if (trace.summary.baseline_v == null) {
    trace.summary.baseline_v = average(trace.v.slice(0, 100));
  }
  trace.sortKey = [
    trace.cable || '',
    trace.lengthM == null ? -1 : Number(trace.lengthM),
    loadSortValue(trace),
    trace.file || trace.id,
  ];
  return trace;
}

function initTransforms() {
  for (const trace of traces) {
    if (!state.transforms[trace.id]) {
      state.transforms[trace.id] = {
        time: 0,
        voltage: 0,
        baseline: Number(trace.summary.baseline_v || 0),
      };
    }
  }
}

function chooseDefaultSelection() {
  const preferred = traces.filter(t => t.cable === 'RG58' && t.lengthM === 10);
  const fallback = traces.filter(t => !t.isDirect);
  const chosen = preferred.length ? preferred : fallback.slice(0, 8);
  state.selected = new Set(chosen.map(t => t.id));
  state.referenceId = chosen[0]?.id || traces[0]?.id || '';
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function loadSortValue(trace) {
  if (trace.specialLoad === 'short') return -Infinity;
  if (trace.specialLoad === 'open') return Infinity;
  return trace.loadOhm == null ? 0 : Number(trace.loadOhm);
}

function sortTraces(items) {
  return [...items].sort((a, b) => {
    for (let i = 0; i < a.sortKey.length; i++) {
      if (a.sortKey[i] < b.sortKey[i]) return -1;
      if (a.sortKey[i] > b.sortKey[i]) return 1;
    }
    return 0;
  });
}

function rebuildFilters() {
  setOptions(els.cableFilter, uniqueValues(traces.map(t => t.cable || 'UNKNOWN')), state.filters.cable);
  setOptions(els.lengthFilter, uniqueValues(traces.map(t => t.lengthM == null ? 'direct' : `${t.lengthM}m`)), state.filters.length);
  setOptions(els.loadFilter, uniqueValues(traces.map(t => t.loadLabel || 'unknown')), state.filters.load);
}

function uniqueValues(values) {
  return [...new Set(values)].sort((a, b) => naturalCompare(a, b));
}

function naturalCompare(a, b) {
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

function setOptions(select, values, current) {
  select.innerHTML = '<option value="all">All</option>' + values.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
  select.value = [...values, 'all'].includes(current) ? current : 'all';
}

function visibleTracesByFilter() {
  const search = state.filters.search.trim().toLowerCase();
  return sortTraces(traces.filter(trace => {
    const cableOk = state.filters.cable === 'all' || trace.cable === state.filters.cable;
    const lengthLabel = trace.lengthM == null ? 'direct' : `${trace.lengthM}m`;
    const lengthOk = state.filters.length === 'all' || lengthLabel === state.filters.length;
    const loadOk = state.filters.load === 'all' || trace.loadLabel === state.filters.load;
    const haystack = `${trace.label} ${trace.file} ${trace.group} ${trace.loadLabel}`.toLowerCase();
    const searchOk = !search || haystack.includes(search);
    return cableOk && lengthOk && loadOk && searchOk;
  }));
}

function selectedTraces() {
  return sortTraces(traces.filter(trace => state.selected.has(trace.id)));
}

function renderTraceList() {
  const visible = visibleTracesByFilter();
  els.traceList.innerHTML = visible.map(trace => `
    <label class="trace-row" title="${escapeHtml(trace.file)}">
      <input type="checkbox" data-trace-check="${escapeHtml(trace.id)}" ${state.selected.has(trace.id) ? 'checked' : ''}>
      <span class="swatch" style="background:${trace.color}"></span>
      <span class="trace-meta">${escapeHtml(trace.group)} <strong>${escapeHtml(trace.loadLabel)}</strong> <span class="pill">${trace.v.length}</span></span>
    </label>
  `).join('');
  for (const input of els.traceList.querySelectorAll('input[data-trace-check]')) {
    input.addEventListener('change', () => {
      if (input.checked) state.selected.add(input.dataset.traceCheck);
      else state.selected.delete(input.dataset.traceCheck);
      ensureReference();
      syncInputs();
      renderAll();
    });
  }
}

function ensureReference() {
  const selected = selectedTraces();
  if (!selected.length) {
    state.referenceId = '';
    return;
  }
  if (!state.referenceId || !state.selected.has(state.referenceId)) {
    state.referenceId = selected[0].id;
  }
}

function renderReferenceOptions() {
  const selected = selectedTraces();
  els.referenceSelect.innerHTML = selected.map(trace => `<option value="${escapeHtml(trace.id)}">${escapeHtml(trace.label)}</option>`).join('');
  els.referenceSelect.value = state.referenceId;
}

function renderCurveControls() {
  const selected = selectedTraces();
  els.curveControls.innerHTML = selected.map(trace => {
    const tr = state.transforms[trace.id];
    const count = visiblePointCount(trace);
    return `
      <tr>
        <td><span class="swatch" style="background:${trace.color}"></span> ${escapeHtml(trace.label)}</td>
        <td>${escapeHtml(trace.file)}</td>
        <td><input type="number" step="0.1" value="${formatInput(tr.time)}" data-shift-time="${escapeHtml(trace.id)}"></td>
        <td><input type="range" min="-200" max="200" step="0.1" value="${formatInput(tr.time)}" data-shift-time-range="${escapeHtml(trace.id)}"></td>
        <td><input type="number" step="0.001" value="${formatInput(tr.voltage)}" data-shift-voltage="${escapeHtml(trace.id)}"></td>
        <td><input type="range" min="-2" max="2" step="0.001" value="${formatInput(tr.voltage)}" data-shift-voltage-range="${escapeHtml(trace.id)}"></td>
        <td><input type="number" step="0.0001" value="${formatInput(tr.baseline)}" data-baseline="${escapeHtml(trace.id)}"></td>
        <td data-visible-count="${escapeHtml(trace.id)}">${count}</td>
      </tr>
    `;
  }).join('');

  bindCurveInput('data-shift-time', 'time');
  bindCurveInput('data-shift-time-range', 'time');
  bindCurveInput('data-shift-voltage', 'voltage');
  bindCurveInput('data-shift-voltage-range', 'voltage');
  bindCurveInput('data-baseline', 'baseline');
}

function bindCurveInput(attribute, key) {
  for (const input of els.curveControls.querySelectorAll(`input[${attribute}]`)) {
    const id = input.getAttribute(attribute);
    input.addEventListener('input', () => {
      state.transforms[id][key] = Number(input.value) || 0;
      syncMatchingCurveInputs(id, key);
      renderPlotAndMetrics();
    });
  }
}

function syncMatchingCurveInputs(id, key) {
  const selectors = {
    time: [`input[data-shift-time="${cssEscape(id)}"]`, `input[data-shift-time-range="${cssEscape(id)}"]`],
    voltage: [`input[data-shift-voltage="${cssEscape(id)}"]`, `input[data-shift-voltage-range="${cssEscape(id)}"]`],
    baseline: [`input[data-baseline="${cssEscape(id)}"]`],
  };
  for (const selector of selectors[key]) {
    const el = els.curveControls.querySelector(selector);
    if (el) el.value = formatInput(state.transforms[id][key]);
  }
}

function updateVisibleCounts() {
  for (const trace of selectedTraces()) {
    const cell = els.curveControls.querySelector(`td[data-visible-count="${cssEscape(trace.id)}"]`);
    if (cell) cell.textContent = visiblePointCount(trace);
  }
}

function cssEscape(value) {
  if (window.CSS && CSS.escape) return CSS.escape(value);
  return String(value).replace(/["\\]/g, '\\$&');
}

function syncInputs() {
  els.windowStart.value = formatInput(state.windowStart);
  els.windowEnd.value = formatInput(state.windowEnd);
  els.baselineMode.value = state.baselineMode;
  els.maxPoints.value = state.maxPoints;
  els.autoY.value = state.autoY ? 'auto' : 'manual';
  els.yMin.value = formatInput(state.yMin);
  els.yMax.value = formatInput(state.yMax);
  els.yMin.disabled = state.autoY;
  els.yMax.disabled = state.autoY;
  els.globalTime.value = formatInput(state.globalTime);
  els.globalTimeRange.value = formatInput(clamp(state.globalTime, -200, 200));
  els.globalVoltage.value = formatInput(state.globalVoltage);
  els.globalVoltageRange.value = formatInput(clamp(state.globalVoltage, -2, 2));
  els.peakThreshold.value = state.peakThreshold;
  els.smoothingSamples.value = state.smoothingSamples;
  renderReferenceOptions();
}

function renderAll() {
  renderTraceList();
  syncInputs();
  renderCurveControls();
  renderPlotAndMetrics();
}

function renderPlotAndMetrics() {
  drawPlot();
  renderMetrics();
  updateVisibleCounts();
  renderAutoAlignResults();
}

function transformedX(trace, index) {
  return trace.t[index] + state.globalTime + state.transforms[trace.id].time;
}

function transformedY(trace, index) {
  const tr = state.transforms[trace.id];
  const base = state.baselineMode === 'corrected' ? tr.baseline : 0;
  return trace.v[index] - base + state.globalVoltage + tr.voltage;
}

function visiblePointCount(trace) {
  let count = 0;
  for (let i = 0; i < trace.t.length; i++) {
    const x = transformedX(trace, i);
    if (x >= state.windowStart && x <= state.windowEnd) count++;
  }
  return count;
}

function visiblePoints(trace, forDrawing = false) {
  const points = [];
  for (let i = 0; i < trace.t.length; i++) {
    const x = transformedX(trace, i);
    if (x >= state.windowStart && x <= state.windowEnd) {
      points.push([x, transformedY(trace, i), i]);
    }
  }
  if (forDrawing && points.length > state.maxPoints) {
    const step = Math.ceil(points.length / state.maxPoints);
    return points.filter((_, index) => index % step === 0);
  }
  return points;
}

function normalizedSmoothingSamples() {
  let samples = Math.round(Number(state.smoothingSamples) || 1);
  samples = clamp(samples, 1, 101);
  if (samples % 2 === 0) samples += 1;
  return Math.min(samples, 101);
}

function detectFirstPositivePeak(trace, thresholdPercent = state.peakThreshold, smoothingSamples = state.smoothingSamples) {
  const points = visiblePoints(trace, false);
  if (points.length < 3) {
    return { ok: false, traceId: trace.id, reason: 'not enough visible points' };
  }
  const smoothWindow = normalizedSmoothingSamplesFor(smoothingSamples);
  const half = Math.floor(smoothWindow / 2);
  const smoothed = points.map((_, index) => {
    const start = Math.max(0, index - half);
    const end = Math.min(points.length - 1, index + half);
    let sum = 0;
    for (let i = start; i <= end; i++) sum += points[i][1];
    return sum / (end - start + 1);
  });
  const positiveMax = Math.max(...smoothed);
  if (!Number.isFinite(positiveMax) || positiveMax <= 0) {
    return { ok: false, traceId: trace.id, reason: 'no positive signal' };
  }
  const threshold = positiveMax * clamp(Number(thresholdPercent) || 0, 1, 100) / 100;
  let peakIndex = -1;
  for (let i = 1; i < smoothed.length - 1; i++) {
    if (smoothed[i] > 0 && smoothed[i] >= threshold && smoothed[i] >= smoothed[i - 1] && smoothed[i] >= smoothed[i + 1]) {
      peakIndex = i;
      break;
    }
  }
  if (peakIndex < 0) {
    return { ok: false, traceId: trace.id, reason: 'no local peak above threshold' };
  }

  const refineStart = Math.max(0, peakIndex - half);
  const refineEnd = Math.min(points.length - 1, peakIndex + half);
  let refinedIndex = peakIndex;
  for (let i = refineStart; i <= refineEnd; i++) {
    if (points[i][1] > points[refinedIndex][1]) refinedIndex = i;
  }
  return {
    ok: true,
    traceId: trace.id,
    peakX: points[refinedIndex][0],
    peakY: points[refinedIndex][1],
    rawIndex: points[refinedIndex][2],
    threshold,
    positiveMax,
    smoothingSamples: smoothWindow,
  };
}

function normalizedSmoothingSamplesFor(value) {
  let samples = Math.round(Number(value) || 1);
  samples = Math.max(1, Math.min(101, samples));
  if (samples % 2 === 0) samples += 1;
  return Math.min(samples, 101);
}

function alignFirstPositivePeaks() {
  ensureReference();
  const selected = selectedTraces();
  const reference = selected.find(trace => trace.id === state.referenceId);
  if (!selected.length) {
    state.lastAutoAlign = {
      ok: false,
      message: 'Select at least one trace.',
      results: [],
      thresholdPercent: state.peakThreshold,
      smoothingSamples: state.smoothingSamples,
      referenceId: state.referenceId,
      targetPeakNs: 0,
      timestamp: new Date().toISOString(),
    };
    renderPlotAndMetrics();
    return;
  }

  state.smoothingSamples = normalizedSmoothingSamplesFor(state.smoothingSamples);
  const thresholdPercent = clamp(Number(state.peakThreshold) || 25, 1, 100);
  state.peakThreshold = thresholdPercent;
  const smoothingSamples = state.smoothingSamples;
  const detections = new Map();
  for (const trace of selected) {
    detections.set(trace.id, detectFirstPositivePeak(trace, thresholdPercent, smoothingSamples));
  }

  const targetPeakNs = 0;
  const results = [];
  for (const trace of selected) {
    const detection = detections.get(trace.id);
    let delta = 0;
    let applied = false;
    if (detection && detection.ok) {
      delta = targetPeakNs - detection.peakX;
      state.transforms[trace.id].time = state.transforms[trace.id].time + delta;
      applied = true;
    }
    results.push(autoAlignResult(trace, detection, delta, applied));
  }
  state.lastAutoAlign = {
    ok: true,
    message: `Moved ${results.filter(r => r.status === 'aligned').length} detected first peaks to 0 ns.`,
    thresholdPercent,
    smoothingSamples,
    referenceId: reference?.id || '',
    targetPeakNs,
    results,
    timestamp: new Date().toISOString(),
  };
  syncInputs();
  renderCurveControls();
  renderPlotAndMetrics();
}

function autoAlignResult(trace, detection, delta, applied) {
  if (!detection || !detection.ok) {
    return {
      traceId: trace.id,
      label: trace.label,
      file: trace.file,
      ok: false,
      status: detection?.reason || 'not detected',
      peakNs: null,
      peakV: null,
      rawIndex: null,
      appliedDeltaNs: 0,
      finalTimeShiftNs: state.transforms[trace.id].time,
    };
  }
  return {
    traceId: trace.id,
    label: trace.label,
    file: trace.file,
    ok: true,
    status: applied ? 'aligned' : 'detected',
    peakNs: detection.peakX,
    peakV: detection.peakY,
    rawIndex: detection.rawIndex,
    appliedDeltaNs: delta,
    finalTimeShiftNs: state.transforms[trace.id].time,
  };
}

function renderAutoAlignResults() {
  const result = state.lastAutoAlign;
  if (!result) {
    els.autoAlignStatus.textContent = 'Uses currently displayed selected curves and moves each detected first peak to 0 ns.';
    els.autoAlignBody.innerHTML = '<tr><td colspan="5">No auto-align run yet.</td></tr>';
    return;
  }
  els.autoAlignStatus.textContent = result.message;
  els.autoAlignBody.innerHTML = result.results.map(row => `
    <tr>
      <td>${escapeHtml(row.label)}</td>
      <td>${row.peakNs == null ? '' : formatMetric(row.peakNs)}</td>
      <td>${row.peakV == null ? '' : formatMetric(row.peakV)}</td>
      <td>${formatMetric(row.appliedDeltaNs)}</td>
      <td>${escapeHtml(row.status)}</td>
    </tr>
  `).join('');
}

function recalculateSelectedBaselines() {
  const selected = selectedTraces();
  if (!selected.length) {
    els.baselineStatus.textContent = 'Select at least one trace before recalculating baseline.';
    return;
  }
  const thresholdPercent = clamp(Number(state.peakThreshold) || 25, 1, 100);
  const smoothingSamples = normalizedSmoothingSamplesFor(state.smoothingSamples);
  let visiblePrePeakCount = 0;
  let fallbackCount = 0;

  for (const trace of selected) {
    const detection = detectFirstPositivePeak(trace, thresholdPercent, smoothingSamples);
    const baselineSamples = [];
    if (detection.ok) {
      for (let i = 0; i < trace.t.length; i++) {
        const x = transformedX(trace, i);
        if (x >= state.windowStart && x < detection.peakX) {
          baselineSamples.push(trace.v[i]);
        }
      }
    }
    if (baselineSamples.length >= 10) {
      state.transforms[trace.id].baseline = average(baselineSamples);
      visiblePrePeakCount++;
    } else {
      state.transforms[trace.id].baseline = average(trace.v.slice(0, 100));
      fallbackCount++;
    }
  }
  els.baselineStatus.textContent = `Recalculated ${selected.length} baselines (${visiblePrePeakCount} from visible pre-peak samples, ${fallbackCount} from first 100 raw samples).`;
  renderCurveControls();
  renderPlotAndMetrics();
}

function drawPlot() {
  const canvas = els.plotCanvas;
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(640, Math.floor(rect.width * dpr));
  const height = Math.max(360, Math.floor(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.scale(dpr, dpr);
  const cssWidth = width / dpr;
  const cssHeight = height / dpr;
  const pad = { left: 64, right: 18, top: 22, bottom: 46 };
  const plotW = cssWidth - pad.left - pad.right;
  const plotH = cssHeight - pad.top - pad.bottom;
  const selected = selectedTraces();
  const allVisible = selected.flatMap(trace => visiblePoints(trace, true).map(p => p[1]));
  let yMin = state.yMin;
  let yMax = state.yMax;
  if (state.autoY) {
    if (allVisible.length) {
      yMin = Math.min(...allVisible);
      yMax = Math.max(...allVisible);
    } else {
      yMin = -1;
      yMax = 1;
    }
    const padY = (yMax - yMin) * 0.08 || 0.1;
    yMin -= padY;
    yMax += padY;
    state.yMin = yMin;
    state.yMax = yMax;
  }
  if (Math.abs(yMax - yMin) < 1e-12) {
    yMin -= 0.5;
    yMax += 0.5;
  }
  const xMin = state.windowStart;
  const xMax = state.windowEnd;
  const sx = x => pad.left + (x - xMin) / (xMax - xMin) * plotW;
  const sy = y => pad.top + (yMax - y) / (yMax - yMin) * plotH;

  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, cssWidth, cssHeight);
  ctx.strokeStyle = '#cbd5e1';
  ctx.strokeRect(pad.left, pad.top, plotW, plotH);

  ctx.font = '12px Arial';
  ctx.fillStyle = '#64748b';
  ctx.strokeStyle = '#e2e8f0';
  ctx.lineWidth = 1;
  for (const tick of ticks(xMin, xMax, 7)) {
    const x = sx(tick);
    ctx.beginPath();
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + plotH);
    ctx.stroke();
    ctx.fillText(formatTick(tick), x - 14, pad.top + plotH + 22);
  }
  for (const tick of ticks(yMin, yMax, 7)) {
    const y = sy(tick);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
    ctx.fillText(formatTick(tick), 8, y + 4);
  }
  if (yMin < 0 && yMax > 0) {
    ctx.strokeStyle = '#94a3b8';
    ctx.beginPath();
    ctx.moveTo(pad.left, sy(0));
    ctx.lineTo(pad.left + plotW, sy(0));
    ctx.stroke();
  }

  for (const trace of selected) {
    const points = visiblePoints(trace, true);
    if (points.length < 2) continue;
    ctx.strokeStyle = trace.color;
    ctx.lineWidth = trace.id === state.referenceId ? 2.3 : 1.6;
    ctx.beginPath();
    points.forEach(([x, y], index) => {
      const px = sx(x);
      const py = sy(y);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
  }

  if (state.lastAutoAlign?.results?.length) {
    for (const row of state.lastAutoAlign.results) {
      if (!row.ok || row.rawIndex == null) continue;
      const trace = traces.find(item => item.id === row.traceId);
      if (!trace || !state.selected.has(trace.id)) continue;
      const x = transformedX(trace, row.rawIndex);
      const y = transformedY(trace, row.rawIndex);
      if (x < xMin || x > xMax || y < yMin || y > yMax) continue;
      const px = sx(x);
      const py = sy(y);
      ctx.save();
      ctx.fillStyle = trace.id === state.referenceId ? '#111827' : trace.color;
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(px, py, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }
  }

  const legendX = pad.left + 8;
  let legendY = pad.top + 18;
  ctx.font = '12px Arial';
  for (const trace of selected.slice(0, 14)) {
    ctx.fillStyle = trace.color;
    ctx.fillRect(legendX, legendY - 9, 12, 8);
    ctx.fillStyle = '#1f2937';
    const ref = trace.id === state.referenceId ? ' [ref]' : '';
    ctx.fillText(`${trace.group} ${trace.loadLabel}${ref}`, legendX + 18, legendY);
    legendY += 16;
  }

  ctx.fillStyle = '#334155';
  ctx.font = '13px Arial';
  ctx.fillText('Time (ns)', pad.left + plotW / 2 - 28, cssHeight - 12);
  ctx.save();
  ctx.translate(16, pad.top + plotH / 2 + 35);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(state.baselineMode === 'corrected' ? 'Voltage - baseline (V)' : 'Voltage (V)', 0, 0);
  ctx.restore();

  const visibleCounts = selected.map(trace => visiblePointCount(trace));
  const totalVisible = visibleCounts.reduce((sum, value) => sum + value, 0);
  els.plotStats.innerHTML = [
    `<span>Selected: <strong>${selected.length}</strong></span>`,
    `<span>Visible points: <strong>${totalVisible}</strong></span>`,
    `<span>Window: <strong>${formatTick(xMin)} to ${formatTick(xMax)} ns</strong></span>`,
    `<span>Y: <strong>${formatTick(yMin)} to ${formatTick(yMax)} V</strong></span>`,
    `<span>Mode: <strong>${state.baselineMode}</strong></span>`,
  ].join('');
  if (state.autoY) {
    els.yMin.value = formatInput(yMin);
    els.yMax.value = formatInput(yMax);
  }
}

function ticks(min, max, count) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || count <= 1) return [0];
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, index) => min + step * index);
}

function formatTick(value) {
  if (!Number.isFinite(value)) return '';
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
}

function formatInput(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '0';
  const text = number.toFixed(6).replace(/\.?0+$/, '');
  return text === '' || text === '-' ? '0' : text;
}

function renderMetrics() {
  const selected = selectedTraces();
  const reference = traces.find(trace => trace.id === state.referenceId);
  if (!reference || !selected.length) {
    els.metricsBody.innerHTML = '<tr><td colspan="6">No selected traces.</td></tr>';
    return;
  }
  const refPoints = visiblePoints(reference, false);
  const sampledRef = downsample(refPoints, 4000);
  els.metricsBody.innerHTML = selected.map(trace => {
    const metric = trace.id === reference.id
      ? { samples: sampledRef.length, rms: 0, mae: 0, corr: 1 }
      : compareTrace(reference, trace, sampledRef);
    return `<tr>
      <td><span class="swatch" style="background:${trace.color}"></span> ${escapeHtml(trace.label)}</td>
      <td>${trace.id === reference.id ? 'yes' : ''}</td>
      <td>${metric.samples}</td>
      <td>${formatMetric(metric.rms)}</td>
      <td>${formatMetric(metric.mae)}</td>
      <td>${formatMetric(metric.corr)}</td>
    </tr>`;
  }).join('');
}

function compareTrace(reference, trace, refPoints) {
  const valuesA = [];
  const valuesB = [];
  for (const [x, yRef] of refPoints) {
    const rawTime = x - state.globalTime - state.transforms[trace.id].time;
    const rawV = interpolate(trace.t, trace.v, rawTime);
    if (rawV == null) continue;
    const tr = state.transforms[trace.id];
    const base = state.baselineMode === 'corrected' ? tr.baseline : 0;
    const y = rawV - base + state.globalVoltage + tr.voltage;
    valuesA.push(yRef);
    valuesB.push(y);
  }
  if (!valuesA.length) return { samples: 0, rms: NaN, mae: NaN, corr: NaN };
  let sumSq = 0;
  let sumAbs = 0;
  for (let i = 0; i < valuesA.length; i++) {
    const diff = valuesB[i] - valuesA[i];
    sumSq += diff * diff;
    sumAbs += Math.abs(diff);
  }
  return {
    samples: valuesA.length,
    rms: Math.sqrt(sumSq / valuesA.length),
    mae: sumAbs / valuesA.length,
    corr: correlation(valuesA, valuesB),
  };
}

function interpolate(xs, ys, x) {
  if (x < xs[0] || x > xs[xs.length - 1]) return null;
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (xs[mid] <= x) lo = mid;
    else hi = mid;
  }
  const x0 = xs[lo], x1 = xs[hi];
  const y0 = ys[lo], y1 = ys[hi];
  if (x1 === x0) return y0;
  const ratio = (x - x0) / (x1 - x0);
  return y0 + (y1 - y0) * ratio;
}

function correlation(a, b) {
  const n = a.length;
  if (n < 2) return NaN;
  const meanA = average(a);
  const meanB = average(b);
  let num = 0, denA = 0, denB = 0;
  for (let i = 0; i < n; i++) {
    const da = a[i] - meanA;
    const db = b[i] - meanB;
    num += da * db;
    denA += da * da;
    denB += db * db;
  }
  const den = Math.sqrt(denA * denB);
  return den === 0 ? NaN : num / den;
}

function downsample(points, maxCount) {
  if (points.length <= maxCount) return points;
  const step = Math.ceil(points.length / maxCount);
  return points.filter((_, index) => index % step === 0);
}

function formatMetric(value) {
  if (!Number.isFinite(value)) return '';
  return value.toFixed(5).replace(/0+$/, '').replace(/\.$/, '');
}

function fitSelectedWindow() {
  const selected = selectedTraces();
  const xs = [];
  for (const trace of selected) {
    for (let i = 0; i < trace.t.length; i++) xs.push(transformedX(trace, i));
  }
  if (!xs.length) return;
  state.windowStart = Math.min(...xs);
  state.windowEnd = Math.max(...xs);
  syncInputs();
  renderPlotAndMetrics();
}

function resetDefaultWindow() {
  state.windowStart = embedded.defaultWindow.start;
  state.windowEnd = embedded.defaultWindow.end;
  syncInputs();
  renderPlotAndMetrics();
}

function resetGlobal() {
  state.globalTime = 0;
  state.globalVoltage = 0;
  syncInputs();
  renderPlotAndMetrics();
}

function resetCurves() {
  for (const trace of traces) {
    state.transforms[trace.id] = {
      time: 0,
      voltage: 0,
      baseline: Number(trace.summary.baseline_v || 0),
    };
  }
  state.lastAutoAlign = null;
  renderAll();
}

function alignmentState() {
  return {
    generatedAt: new Date().toISOString(),
    source: embedded.generatedFrom,
    units: embedded.units,
    baselineMode: state.baselineMode,
    referenceId: state.referenceId,
    window: { startNs: state.windowStart, endNs: state.windowEnd },
    globalShift: { timeNs: state.globalTime, voltageV: state.globalVoltage },
    lastAutoAlign: state.lastAutoAlign,
    selected: selectedTraces().map(trace => ({
      id: trace.id,
      label: trace.label,
      file: trace.file,
      group: trace.group,
      load: trace.loadLabel,
      timeShiftNs: state.transforms[trace.id].time,
      voltageShiftV: state.transforms[trace.id].voltage,
      baselineV: state.transforms[trace.id].baseline,
    })),
  };
}

function exportJson() {
  downloadBlob('alignment.json', JSON.stringify(alignmentState(), null, 2), 'application/json');
}

function exportAlignmentCsv() {
  const rows = [[
    'trace_id','label','file','group','load','reference_id','baseline_mode','window_start_ns','window_end_ns',
    'global_time_shift_ns','global_voltage_shift_v','time_shift_ns','voltage_shift_v','baseline_v'
  ]];
  for (const trace of selectedTraces()) {
    const tr = state.transforms[trace.id];
    rows.push([
      trace.id, trace.label, trace.file, trace.group, trace.loadLabel, state.referenceId, state.baselineMode,
      state.windowStart, state.windowEnd, state.globalTime, state.globalVoltage, tr.time, tr.voltage, tr.baseline
    ]);
  }
  downloadBlob('alignment.csv', rows.map(row => row.map(csvCell).join(',')).join('\n'), 'text/csv');
}

function exportCorrectedData() {
  const rows = [['trace_id','file','t_raw_ns','v_raw','baseline_v','t_shifted_ns','v_shifted']];
  for (const trace of selectedTraces()) {
    const tr = state.transforms[trace.id];
    for (let i = 0; i < trace.t.length; i++) {
      const tShifted = transformedX(trace, i);
      if (tShifted < state.windowStart || tShifted > state.windowEnd) continue;
      const vShifted = trace.v[i] - tr.baseline + state.globalVoltage + tr.voltage;
      rows.push([trace.id, trace.file, trace.t[i], trace.v[i], tr.baseline, tShifted, vShifted]);
    }
  }
  downloadBlob('corrected_data.csv', rows.map(row => row.map(csvCell).join(',')).join('\n'), 'text/csv');
}

function exportPng() {
  els.plotCanvas.toBlob(blob => {
    if (blob) downloadBlob('waveform_alignment.png', blob, 'image/png');
  });
}

function downloadBlob(filename, content, type) {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  const text = value == null ? '' : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function parseImportedTrace(fileName, text, index) {
  const rows = text.split(/\r?\n/).map(line => line.split(','));
  const dataStart = rows.findIndex(row => row[0] === 'Second' && row[1] === 'Value');
  if (dataStart < 0) throw new Error(`${fileName} does not contain Second,Value`);
  const t = [];
  const v = [];
  for (const row of rows.slice(dataStart + 1)) {
    if (row.length < 2) continue;
    const seconds = Number(row[0]);
    const volts = Number(row[1]);
    if (Number.isFinite(seconds) && Number.isFinite(volts)) {
      t.push(seconds * 1e9);
      v.push(volts);
    }
  }
  const parsed = parseFileName(fileName);
  const id = `import_${Date.now()}_${index}_${slugClient(fileName)}`;
  return normalizeTrace({
    id,
    label: `${parsed.group} ${parsed.loadLabel}`,
    group: parsed.group,
    cable: parsed.cable,
    lengthM: parsed.lengthM,
    loadLabel: parsed.loadLabel,
    loadOhm: parsed.loadOhm,
    specialLoad: parsed.specialLoad,
    file: fileName,
    isDirect: parsed.isDirect,
    color: palette[(traces.length + index) % palette.length],
    summary: {
      file: fileName,
      group: parsed.group,
      load: parsed.loadLabel,
      points: t.length,
      t_min_ns: Math.min(...t),
      t_max_ns: Math.max(...t),
      v_min: Math.min(...v),
      v_max: Math.max(...v),
      baseline_v: average(v.slice(0, 100)),
    },
    t,
    v,
  }, traces.length + index);
}

function parseFileName(fileName) {
  const stem = fileName.replace(/\.csv$/i, '');
  if (/^direct-connection$/i.test(stem)) {
    return { cable: 'DIRECT', lengthM: null, loadLabel: 'direct', loadOhm: null, specialLoad: null, group: 'Direct connection', isDirect: true };
  }
  const match = stem.match(/^(rg\d+)-(\d+)m-(.+)$/i);
  if (!match) {
    return { cable: 'IMPORT', lengthM: null, loadLabel: 'unknown', loadOhm: null, specialLoad: null, group: 'Imported', isDirect: false };
  }
  const cable = match[1].toUpperCase();
  const lengthM = Number(match[2]);
  let loadToken = match[3].toLowerCase().replace(/[-_]?wrong/g, '');
  if (loadToken === 'open' || loadToken === 'short') {
    return { cable, lengthM, loadLabel: loadToken, loadOhm: null, specialLoad: loadToken, group: `${cable} ${lengthM}m`, isDirect: false };
  }
  const ohm = loadToken.match(/^(\d+(?:\.\d+)?)ohm$/);
  if (ohm) {
    const loadOhm = Number(ohm[1]);
    return { cable, lengthM, loadLabel: `${loadOhm} ohm`, loadOhm, specialLoad: null, group: `${cable} ${lengthM}m`, isDirect: false };
  }
  return { cable, lengthM, loadLabel: loadToken, loadOhm: null, specialLoad: null, group: `${cable} ${lengthM}m`, isDirect: false };
}

function slugClient(text) {
  return String(text).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'trace';
}

function bindEvents() {
  els.cableFilter.addEventListener('change', () => { state.filters.cable = els.cableFilter.value; renderTraceList(); });
  els.lengthFilter.addEventListener('change', () => { state.filters.length = els.lengthFilter.value; renderTraceList(); });
  els.loadFilter.addEventListener('change', () => { state.filters.load = els.loadFilter.value; renderTraceList(); });
  els.searchFilter.addEventListener('input', () => { state.filters.search = els.searchFilter.value; renderTraceList(); });
  document.getElementById('selectVisible').addEventListener('click', () => {
    state.selected = new Set(visibleTracesByFilter().map(trace => trace.id));
    ensureReference();
    renderAll();
  });
  document.getElementById('clearSelection').addEventListener('click', () => {
    state.selected.clear();
    ensureReference();
    renderAll();
  });
  document.getElementById('selectRg58').addEventListener('click', () => {
    const rg58 = traces.filter(trace => trace.cable === 'RG58' && trace.lengthM === 10);
    state.selected = new Set(rg58.map(trace => trace.id));
    ensureReference();
    renderAll();
  });

  els.windowStart.addEventListener('input', () => updateWindow('start', Number(els.windowStart.value)));
  els.windowEnd.addEventListener('input', () => updateWindow('end', Number(els.windowEnd.value)));
  els.baselineMode.addEventListener('change', () => { state.baselineMode = els.baselineMode.value; renderPlotAndMetrics(); });
  els.referenceSelect.addEventListener('change', () => { state.referenceId = els.referenceSelect.value; renderPlotAndMetrics(); });
  els.maxPoints.addEventListener('input', () => { state.maxPoints = Math.max(100, Number(els.maxPoints.value) || 100); renderPlotAndMetrics(); });
  els.autoY.addEventListener('change', () => { state.autoY = els.autoY.value === 'auto'; syncInputs(); renderPlotAndMetrics(); });
  els.yMin.addEventListener('input', () => { state.yMin = Number(els.yMin.value); state.autoY = false; syncInputs(); renderPlotAndMetrics(); });
  els.yMax.addEventListener('input', () => { state.yMax = Number(els.yMax.value); state.autoY = false; syncInputs(); renderPlotAndMetrics(); });
  document.getElementById('fitSelected').addEventListener('click', fitSelectedWindow);
  document.getElementById('fitWindow').addEventListener('click', resetDefaultWindow);
  els.recalculateBaseline.addEventListener('click', recalculateSelectedBaselines);

  bindGlobalShift(els.globalTime, els.globalTimeRange, 'globalTime');
  bindGlobalShift(els.globalTimeRange, els.globalTime, 'globalTime');
  bindGlobalShift(els.globalVoltage, els.globalVoltageRange, 'globalVoltage');
  bindGlobalShift(els.globalVoltageRange, els.globalVoltage, 'globalVoltage');
  els.peakThreshold.addEventListener('input', () => {
    state.peakThreshold = clamp(Number(els.peakThreshold.value) || 25, 1, 100);
    els.peakThreshold.value = state.peakThreshold;
  });
  els.smoothingSamples.addEventListener('input', () => {
    state.smoothingSamples = normalizedSmoothingSamplesFor(els.smoothingSamples.value);
    els.smoothingSamples.value = state.smoothingSamples;
  });
  els.autoAlignButton.addEventListener('click', alignFirstPositivePeaks);
  document.getElementById('resetGlobal').addEventListener('click', resetGlobal);
  document.getElementById('resetCurves').addEventListener('click', resetCurves);

  document.getElementById('exportJson').addEventListener('click', exportJson);
  document.getElementById('exportCsv').addEventListener('click', exportAlignmentCsv);
  document.getElementById('exportData').addEventListener('click', exportCorrectedData);
  document.getElementById('exportPng').addEventListener('click', exportPng);

  els.csvImport.addEventListener('change', async () => {
    const files = [...els.csvImport.files];
    const added = [];
    for (let i = 0; i < files.length; i++) {
      const text = await files[i].text();
      added.push(parseImportedTrace(files[i].name, text, i));
    }
    traces = sortTraces([...traces, ...added]);
    initTransforms();
    for (const trace of added) state.selected.add(trace.id);
    ensureReference();
    rebuildFilters();
    renderAll();
  });
  window.addEventListener('resize', drawPlot);
}

function bindGlobalShift(input, peer, key) {
  input.addEventListener('input', () => {
    state[key] = Number(input.value) || 0;
    peer.value = formatInput(key === 'globalTime' ? clamp(state[key], -200, 200) : clamp(state[key], -2, 2));
    renderPlotAndMetrics();
  });
}

function updateWindow(which, value) {
  if (!Number.isFinite(value)) return;
  if (which === 'start') state.windowStart = value;
  else state.windowEnd = value;
  if (state.windowEnd <= state.windowStart) state.windowEnd = state.windowStart + 1;
  syncInputs();
  renderPlotAndMetrics();
}

initTransforms();
chooseDefaultSelection();
rebuildFilters();
bindEvents();
els.statusSlot.innerHTML = embedded.statusHtml || '<p class="small-note">No data_status.csv found.</p>';
renderAll();
</script>
</body>
</html>
"""


def main() -> None:
    included_ids, excluded_ids, ignored_paths = discover_traces()
    traces = load_traces(included_ids)
    assign_colors(traces)
    for trace in traces:
        trace.summary = summarize_trace(trace)

    write_summary_csv(traces)
    html_text = build_html(traces, excluded_ids, ignored_paths)
    (SCRIPT_DIR / "index.html").write_text(html_text, encoding="utf-8")


if __name__ == "__main__":
    main()
