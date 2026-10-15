"""Render the RG58 10 m comparison using the visualizer's stored alignment.

The HTML visualizer exports its fitted baseline and time offsets, but its
``corrected_data.csv`` stops at the fit-default window end (250 ns).  The
script applies those stored values to the original scope records and verifies
that the reconstructed export window exactly reproduces the exported points.
It therefore extends the view with real samples, without re-fitting anything.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.axes_grid1.inset_locator import inset_axes, mark_inset
from matplotlib.ticker import MultipleLocator


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = ROOT / "visualize"
DEFAULT_OUTPUT = ROOT / "analysis" / "figures" / "rg58_10m_matched_open_short_aligned_export.png"

# Extend the visualizer's default fit window with real source samples.  The
# left margin keeps the legend clear of the incident pulse; the right segment
# shows the continuation past the HTML export's 250 ns cutoff.
DISPLAY_WINDOW_NS = (-100.0, 275.0)
DETAIL_WINDOW_NS = (195.0, 240.0)

TRACES = (
    ("rg58_10_50_ohm_rg58_10m_50ohm", "Matched (50 Ω)", "#0072B2"),
    ("rg58_10_open_rg58_10m_open", "Open (∞)", "#E69F00"),
    ("rg58_10_short_rg58_10m_short", "Short (0 Ω)", "#CC1F4A"),
)


@dataclass(frozen=True)
class Trace:
    trace_id: str
    label: str
    color: str
    time_ns: np.ndarray
    voltage_v: np.ndarray
    baseline_v: float
    time_shift_ns: float


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 10,
            "axes.labelsize": 10.5,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "figure.titlesize": 14,
            "figure.titleweight": "bold",
            "axes.edgecolor": "#30475E",
            "axes.linewidth": 0.85,
            "grid.color": "#D9E2EC",
            "grid.linewidth": 0.7,
            "savefig.dpi": 300,
        }
    )


def read_alignment(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {row["trace_id"]: row for row in rows}
    expected = {trace_id for trace_id, _, _ in TRACES}
    missing = expected - result.keys()
    if missing:
        raise ValueError(f"alignment.csv is missing trace IDs: {sorted(missing)}")
    for trace_id in expected:
        row = result[trace_id]
        if row["baseline_mode"] != "corrected":
            raise ValueError(f"{trace_id} is not an exported corrected trace")
        if float(row["window_start_ns"]) != -100.0 or float(row["window_end_ns"]) != 250.0:
            raise ValueError(f"{trace_id} does not use the visualizer fit default window")
    return result


def read_scope_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.reader(path.open(encoding="utf-8-sig", newline="")))
    for index, row in enumerate(rows):
        if len(row) >= 2 and row[0] == "Second" and row[1] == "Value":
            data = rows[index + 1 :]
            return (
                np.array([float(row[0]) * 1e9 for row in data], dtype=float),
                np.array([float(row[1]) for row in data], dtype=float),
            )
    raise ValueError(f"No Siglent Second,Value data block in {path.name}")


def read_traces(input_dir: Path) -> list[Trace]:
    alignment = read_alignment(input_dir / "alignment.csv")
    rows_by_id: dict[str, list[dict[str, str]]] = {}
    with (input_dir / "corrected_data.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows_by_id.setdefault(row["trace_id"], []).append(row)

    traces: list[Trace] = []
    for trace_id, label, color in TRACES:
        exported_rows = rows_by_id.get(trace_id, [])
        if not exported_rows:
            raise ValueError(f"corrected_data.csv is missing {trace_id}")
        exported_time_ns = np.array([float(row["t_shifted_ns"]) for row in exported_rows])
        exported_voltage_v = np.array([float(row["v_shifted"]) for row in exported_rows])
        metadata = alignment[trace_id]
        raw_time_ns, raw_voltage_v = read_scope_csv(ROOT / metadata["file"])
        time_ns = raw_time_ns + float(metadata["global_time_shift_ns"]) + float(metadata["time_shift_ns"])
        voltage_v = (
            raw_voltage_v
            - float(metadata["baseline_v"])
            + float(metadata["global_voltage_shift_v"])
            + float(metadata["voltage_shift_v"])
        )

        # The exported interval is the reference implementation of the
        # visualizer's transform.  Do not use the source continuation unless it
        # reproduces every exported point within numerical precision.
        export_mask = (time_ns >= -100.0) & (time_ns <= 250.0)
        if len(time_ns[export_mask]) != len(exported_time_ns):
            raise ValueError(f"Export/source point-count mismatch for {trace_id}")
        if not np.allclose(time_ns[export_mask], exported_time_ns, rtol=0.0, atol=1e-9):
            raise ValueError(f"Export/source time-coordinate mismatch for {trace_id}")
        if not np.allclose(voltage_v[export_mask], exported_voltage_v, rtol=0.0, atol=1e-12):
            raise ValueError(f"Export/source voltage-coordinate mismatch for {trace_id}")

        in_window = (time_ns >= DISPLAY_WINDOW_NS[0]) & (time_ns <= DISPLAY_WINDOW_NS[1])
        if in_window.sum() < 500:
            raise ValueError(f"Unexpectedly sparse displayed range for {trace_id}")
        traces.append(
            Trace(
                trace_id,
                label,
                color,
                time_ns[in_window],
                voltage_v[in_window],
                float(metadata["baseline_v"]),
                float(metadata["time_shift_ns"]),
            )
        )
    return traces


def plot_points(axis: plt.Axes, traces: list[Trace], marker_size: float, line_width: float) -> None:
    for trace in traces:
        axis.plot(trace.time_ns, trace.voltage_v, color=trace.color, linewidth=line_width, alpha=0.62, zorder=2)
        axis.scatter(
            trace.time_ns,
            trace.voltage_v,
            s=marker_size,
            color=trace.color,
            edgecolors="white",
            linewidths=0.22,
            label=trace.label,
            zorder=3,
        )


def render(
    input_dir: Path,
    output: Path,
    note_mode: str = "standard",
    detail_window_ns: tuple[float, float] = DETAIL_WINDOW_NS,
) -> None:
    traces = read_traces(input_dir)
    configure_style()
    figure, axis = plt.subplots(figsize=(11.8, 6.25), constrained_layout=False)
    figure.subplots_adjust(left=0.085, right=0.992, bottom=0.145, top=0.875)
    figure.suptitle("RG58, L = 10 m: aligned waveforms for three terminations", y=0.975)

    plot_points(axis, traces, marker_size=15.0, line_width=0.8)
    axis.axhline(0.0, color="#52677D", linewidth=0.8, zorder=1)
    axis.axvline(0.0, color="#52677D", linewidth=0.8, linestyle="--", zorder=1)
    axis.set_xlim(*DISPLAY_WINDOW_NS)
    axis.xaxis.set_major_locator(MultipleLocator(25.0))
    axis.set_ylim(-1.14, 1.00)
    axis.set_xlabel("Time relative to aligned first-peak position / ns")
    axis.set_ylabel("Baseline-corrected voltage / V")
    axis.set_title("Visualizer-aligned data points", loc="left", pad=9)
    axis.grid(True)
    axis.legend(loc="upper left", frameon=True, framealpha=0.96, edgecolor="#B7C4D0", markerscale=1.25)
    axis.text(
        0.90,
        0.13,
        "Visualization-only alignment\n(not used for Δt calculation)\nFirst peaks aligned at 0 ns",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="#30475E",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "#B7C4D0", "alpha": 0.95},
    )

    # A magnified inset ensures the small post-reflection feature remains a
    # visible data feature rather than a claim made only in the caption.
    detail = inset_axes(axis, width="27%", height="26%", loc="upper right", borderpad=1.35)
    plot_points(detail, traces, marker_size=10.0, line_width=0.65)
    detail.set_xlim(*detail_window_ns)
    detail_values = np.concatenate(
        [trace.voltage_v[(trace.time_ns >= detail_window_ns[0]) & (trace.time_ns <= detail_window_ns[1])] for trace in traces]
    )
    y_min, y_max = float(detail_values.min()), float(detail_values.max())
    pad = max(0.012, (y_max - y_min) * 0.14)
    detail.set_ylim(y_min - pad, y_max + pad)
    detail.axhline(0.0, color="#52677D", linewidth=0.55, zorder=1)
    detail.grid(True, linewidth=0.5)
    detail.tick_params(labelsize=7)
    detail.set_title(
        f"Post-reflection detail: {detail_window_ns[0]:.0f}–{detail_window_ns[1]:.0f} ns",
        fontsize=8,
        pad=4,
    )
    mark_inset(axis, detail, loc1=2, loc2=4, fc="none", ec="#52677D", alpha=0.58, linewidth=0.65)

    if note_mode != "none":
        figure.text(
            0.5,
            0.018,
            "All markers are recorded 0.5 ns samples.",
            ha="center",
            fontsize=9.5 if note_mode == "emphasized" else 8.35,
            fontweight="bold" if note_mode == "emphasized" else "normal",
            color="#30475E" if note_mode == "emphasized" else "#425466",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--note-mode", choices=("standard", "none", "emphasized"), default="standard")
    parser.add_argument("--detail-window", type=float, nargs=2, metavar=("START_NS", "END_NS"), default=DETAIL_WINDOW_NS)
    args = parser.parse_args()
    detail_window_ns = tuple(args.detail_window)
    if detail_window_ns[0] >= detail_window_ns[1]:
        parser.error("DETAIL_WINDOW start must be less than its end")
    render(args.input_dir, args.output, args.note_mode, detail_window_ns)


if __name__ == "__main__":
    main()
