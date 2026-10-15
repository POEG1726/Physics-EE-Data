"""Render a two-panel, aligned waveform figure with a full-record context panel.

The lower panel uses the complete original records after applying the exact
baseline and time offsets saved by the HTML visualizer.  The upper panel is the
same aligned data restricted to the highlighted comparison window.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import ConnectionPatch, Rectangle
from matplotlib.ticker import MultipleLocator
from mpl_toolkits.axes_grid1.inset_locator import inset_axes, mark_inset

from render_aligned_waveform_composite import (
    DEFAULT_INPUT_DIR,
    DISPLAY_WINDOW_NS,
    ROOT,
    TRACES,
    Trace,
    configure_style,
    plot_points,
    read_alignment,
    read_scope_csv,
)


OUTPUT = ROOT / "analysis" / "figures" / "rg58_10m_matched_open_short_full_aligned_no_notes.png"
POST_REFLECTION_DETAIL_NS = (175.0, 250.0)


def read_full_traces(input_dir: Path) -> list[Trace]:
    alignment = read_alignment(input_dir / "alignment.csv")
    with (input_dir / "corrected_data.csv").open(encoding="utf-8", newline="") as handle:
        exported = {}
        for row in csv.DictReader(handle):
            exported.setdefault(row["trace_id"], []).append(row)

    traces: list[Trace] = []
    for trace_id, label, color in TRACES:
        metadata = alignment[trace_id]
        exported_rows = exported.get(trace_id, [])
        if not exported_rows:
            raise ValueError(f"corrected_data.csv is missing {trace_id}")
        raw_t, raw_v = read_scope_csv(ROOT / metadata["file"])
        time_ns = raw_t + float(metadata["global_time_shift_ns"]) + float(metadata["time_shift_ns"])
        voltage_v = (
            raw_v
            - float(metadata["baseline_v"])
            + float(metadata["global_voltage_shift_v"])
            + float(metadata["voltage_shift_v"])
        )

        # Prove that the source reconstruction is the same transform as the
        # HTML export before using the continuation outside its 250 ns cutoff.
        export_mask = (time_ns >= -100.0) & (time_ns <= 250.0)
        exported_t = np.array([float(row["t_shifted_ns"]) for row in exported_rows])
        exported_v = np.array([float(row["v_shifted"]) for row in exported_rows])
        if len(time_ns[export_mask]) != len(exported_t):
            raise ValueError(f"Export/source point-count mismatch for {trace_id}")
        if not np.allclose(time_ns[export_mask], exported_t, rtol=0.0, atol=1e-9):
            raise ValueError(f"Export/source time mismatch for {trace_id}")
        if not np.allclose(voltage_v[export_mask], exported_v, rtol=0.0, atol=1e-12):
            raise ValueError(f"Export/source voltage mismatch for {trace_id}")
        traces.append(Trace(trace_id, label, color, time_ns, voltage_v, float(metadata["baseline_v"]), float(metadata["time_shift_ns"])))
    return traces


def render(input_dir: Path = DEFAULT_INPUT_DIR, output: Path = OUTPUT) -> None:
    traces = read_full_traces(input_dir)
    configure_style()
    figure = plt.figure(figsize=(11.8, 8.3), constrained_layout=False)
    figure.subplots_adjust(left=0.085, right=0.992, bottom=0.10, top=0.90, hspace=0.44)
    grid = figure.add_gridspec(2, 1, height_ratios=(1.28, 0.82))
    top = figure.add_subplot(grid[0])
    bottom = figure.add_subplot(grid[1])
    figure.suptitle("RG58, L = 10 m: aligned waveforms for three terminations", y=0.967)

    zoom_traces = [
        Trace(t.trace_id, t.label, t.color, t.time_ns[(t.time_ns >= DISPLAY_WINDOW_NS[0]) & (t.time_ns <= DISPLAY_WINDOW_NS[1])], t.voltage_v[(t.time_ns >= DISPLAY_WINDOW_NS[0]) & (t.time_ns <= DISPLAY_WINDOW_NS[1])], t.baseline_v, t.time_shift_ns)
        for t in traces
    ]
    plot_points(top, zoom_traces, marker_size=15.0, line_width=0.8)
    top.axhline(0.0, color="#52677D", linewidth=0.8, zorder=1)
    top.axvline(0.0, color="#52677D", linewidth=0.8, linestyle="--", zorder=1)
    top.set_xlim(*DISPLAY_WINDOW_NS)
    top.set_ylim(-1.14, 1.00)
    top.xaxis.set_major_locator(MultipleLocator(25.0))
    top.set_ylabel("Voltage / V")
    top.set_title("Expanded aligned data points", loc="left", pad=8)
    top.grid(True)
    top.legend(loc="upper left", frameon=True, framealpha=0.96, edgecolor="#B7C4D0", markerscale=1.25)
    top.text(
        0.73,
        0.13,
        "First peaks aligned at 0 ns\nVisualization-only alignment\n(not used for Δt calculation)",
        transform=top.transAxes,
        ha="left",
        va="bottom",
        fontsize=9,
        color="#30475E",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "#B7C4D0", "alpha": 0.95},
    )

    detail = inset_axes(top, width="27%", height="26%", loc="upper right", borderpad=1.35)
    plot_points(detail, zoom_traces, marker_size=10.0, line_width=0.65)
    detail.set_xlim(*POST_REFLECTION_DETAIL_NS)
    detail_values = np.concatenate(
        [trace.voltage_v[(trace.time_ns >= POST_REFLECTION_DETAIL_NS[0]) & (trace.time_ns <= POST_REFLECTION_DETAIL_NS[1])] for trace in zoom_traces]
    )
    detail_low, detail_high = np.quantile(detail_values, [0.01, 0.99])
    detail_pad = max(0.025, 0.14 * (detail_high - detail_low))
    detail.set_ylim(detail_low - detail_pad, detail_high + detail_pad)
    detail.axhline(0.0, color="#52677D", linewidth=0.55, zorder=1)
    detail.xaxis.set_major_locator(MultipleLocator(25.0))
    detail.tick_params(labelsize=7, pad=1)
    detail.grid(True, linewidth=0.45, alpha=0.8)
    detail.set_title("Post-reflection detail: 175–250 ns", fontsize=8, pad=4)
    mark_inset(top, detail, loc1=2, loc2=4, fc="none", ec="#52677D", alpha=0.58, linewidth=0.65)

    full_x = np.concatenate([trace.time_ns for trace in traces])
    full_y = np.concatenate([trace.voltage_v for trace in traces])
    y_low, y_high = np.quantile(full_y, [0.001, 0.999])
    y_pad = max(0.10, 0.10 * (y_high - y_low))
    bottom.set_xlim(float(full_x.min()), float(full_x.max()))
    bottom.set_ylim(y_low - y_pad, y_high + y_pad)
    bottom.xaxis.set_major_locator(MultipleLocator(400.0))
    for trace in traces:
        bottom.scatter(trace.time_ns, trace.voltage_v, s=1.8, color=trace.color, alpha=0.62, linewidths=0, rasterized=True)
    bottom.axhline(0.0, color="#52677D", linewidth=0.7, zorder=0)
    highlight = Rectangle(
        (DISPLAY_WINDOW_NS[0], bottom.get_ylim()[0]),
        DISPLAY_WINDOW_NS[1] - DISPLAY_WINDOW_NS[0],
        bottom.get_ylim()[1] - bottom.get_ylim()[0],
        facecolor="#F4A261",
        edgecolor="#C75B12",
        alpha=0.24,
        linewidth=1.2,
        zorder=2,
    )
    bottom.add_patch(highlight)
    bottom.text(
        (DISPLAY_WINDOW_NS[0] + DISPLAY_WINDOW_NS[1]) / 2.0,
        1.015,
        "zoomed region shown above",
        transform=bottom.get_xaxis_transform(),
        color="#93410A",
        fontsize=8.5,
        ha="center",
        va="bottom",
        clip_on=False,
    )
    bottom.set_xlabel("Aligned acquisition time / ns")
    bottom.set_ylabel("Voltage / V")
    bottom.set_title("Complete aligned oscilloscope records", loc="left", pad=8)
    bottom.grid(True)

    for relative_x, absolute_x in ((DISPLAY_WINDOW_NS[0], DISPLAY_WINDOW_NS[0]), (DISPLAY_WINDOW_NS[1], DISPLAY_WINDOW_NS[1])):
        connector = ConnectionPatch(
            xyA=(relative_x, top.get_ylim()[0]),
            coordsA=top.transData,
            xyB=(absolute_x, bottom.get_ylim()[1]),
            coordsB=bottom.transData,
            color="#C75B12",
            linewidth=0.75,
            alpha=0.72,
            clip_on=False,
        )
        figure.add_artist(connector)

    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(figure)


if __name__ == "__main__":
    render()
