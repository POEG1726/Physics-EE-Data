"""Render three point-based waveform figures for RG58 at 10 m.

Each figure uses exactly one saved oscilloscope record (matched, open, or
short).  The upper panel expands the central pulse cycle; the lower panel
retains the full acquisition and marks the source window of the expansion.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import ConnectionPatch, Rectangle


ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "analysis"
DEFAULT_OUTPUT_DIR = ANALYSIS_DIR / "figures"

PULSE_WINDOW_NS = (-40.0, 165.0)
SPECS = (
    ("matched", "rg58-10m-50ohm.csv", "50 Ω", "#6C757D"),
    ("open", "RG58-10M-open.csv", "∞ (open)", "#0072B2"),
    ("short", "RG58-10M-short.csv", "0 Ω (short)", "#D55E00"),
)


@dataclass(frozen=True)
class Cycle:
    index: int
    baseline_v: float
    incident_t50_ns: float
    reflection_t50_ns: float


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


def read_processed(path: Path, file_name: str) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    matches = [row for row in rows if row["file"] == file_name]
    if len(matches) != 1:
        raise ValueError(f"Expected one processed-results row for {file_name}; found {len(matches)}")
    return matches[0]


def central_cycle(cycles: list[Cycle]) -> Cycle:
    if len(cycles) != 5:
        raise ValueError(f"Expected five usable cycles; found {len(cycles)}")
    median_t50 = float(np.median([cycle.incident_t50_ns for cycle in cycles]))
    return min(cycles, key=lambda cycle: abs(cycle.incident_t50_ns - median_t50))


def format_annotation(kind: str, processed: dict[str, str]) -> str:
    gamma = float(processed["gamma_exp_mean"])
    if kind == "matched":
        return rf"$\Gamma_{{\mathrm{{exp}}}}$ = {gamma:+.4f}" + "\nNo reflection delay reported"
    delay = float(processed["delay_ns_median"])
    polarity = "positive" if kind == "open" else "negative"
    return rf"$\Gamma_{{\mathrm{{exp}}}}$ = {gamma:+.4f}" + f"\n{polarity} reflection; Δt = {delay:.3f} ns"


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 9.5,
            "axes.labelsize": 10.5,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "figure.titlesize": 13,
            "figure.titleweight": "bold",
            "axes.edgecolor": "#34495E",
            "axes.linewidth": 0.85,
            "grid.color": "#DDE3EA",
            "grid.linewidth": 0.65,
            "savefig.dpi": 300,
        }
    )


def render(kind: str, file_name: str, load_label: str, color: str, output: Path) -> None:
    raw_path = ROOT / file_name
    t_ns, voltage_v = read_scope_csv(raw_path)
    cycles = read_cycles_for_file(ANALYSIS_DIR / "per_cycle.csv", file_name)
    cycle = central_cycle(cycles)
    processed = read_processed(ANALYSIS_DIR / "processed_results.csv", file_name)
    corrected_v = voltage_v - cycle.baseline_v

    zoom_start = cycle.incident_t50_ns + PULSE_WINDOW_NS[0]
    zoom_end = cycle.incident_t50_ns + PULSE_WINDOW_NS[1]
    zoom_mask = (t_ns >= zoom_start) & (t_ns <= zoom_end)
    zoom_t = t_ns[zoom_mask] - cycle.incident_t50_ns
    zoom_v = corrected_v[zoom_mask]
    if len(zoom_t) < 100:
        raise ValueError(f"Zoom window is unexpectedly sparse for {file_name}")

    figure = plt.figure(figsize=(8.2, 7.2), constrained_layout=False)
    grid = figure.add_gridspec(2, 1, height_ratios=(1.28, 0.84), hspace=0.56)
    top = figure.add_subplot(grid[0])
    bottom = figure.add_subplot(grid[1])

    figure.suptitle(f"RG58, L = 10 m, R$_L$ = {load_label}", y=0.985)

    # Upper panel: every recorded sample is a marker. The line only helps the eye
    # follow sample order and is not a fit or interpolation.
    top.plot(zoom_t, zoom_v, color=color, alpha=0.38, linewidth=0.85, zorder=1)
    top.scatter(zoom_t, zoom_v, s=11, color=color, edgecolor="white", linewidth=0.22, zorder=2)
    top.axhline(0, color="#6C7A89", linewidth=0.75, zorder=0)
    top.axvline(0, color="#6C7A89", linewidth=0.75, linestyle="--", zorder=0)
    reflection_relative = cycle.reflection_t50_ns - cycle.incident_t50_ns
    if kind != "matched":
        top.axvline(reflection_relative, color=color, linewidth=0.85, linestyle=":", zorder=0)
    top.set_xlim(*PULSE_WINDOW_NS)
    top.set_ylabel("Baseline-corrected voltage / V")
    top.set_xlabel("Time relative to incident 50% crossing / ns")
    top.set_title("Expanded central pulse cycle", loc="left", pad=8)
    top.grid(True)
    top.text(
        0.985,
        0.95,
        format_annotation(kind, processed),
        transform=top.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.32", "facecolor": "white", "edgecolor": "#B8C2CC", "alpha": 0.94},
    )
    top.annotate(
        "incident\n50% crossing",
        xy=(0, np.interp(0, zoom_t, zoom_v)),
        xytext=(-26, top.get_ylim()[1] * 0.72),
        arrowprops={"arrowstyle": "->", "color": "#34495E", "lw": 0.8},
        ha="center",
        va="bottom",
        fontsize=8,
        color="#34495E",
    )
    if kind != "matched":
        top.text(
            reflection_relative,
            0.055,
            "reflected\n50% crossing",
            transform=top.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=8,
            color=color,
            bbox={"boxstyle": "round,pad=0.16", "facecolor": "white", "edgecolor": "none", "alpha": 0.82},
        )

    # Lower panel: retain every point in the saved record, but use small opaque
    # markers so the sampling density remains visible at the full-record scale.
    bottom.scatter(t_ns, corrected_v, s=1.5, color="#5E6D7E", alpha=0.72, linewidths=0, rasterized=True)
    y_min, y_max = np.quantile(corrected_v, [0.001, 0.999])
    padding = max(0.08, 0.12 * (y_max - y_min))
    bottom.set_ylim(y_min - padding, y_max + padding)
    bottom.axhline(0, color="#6C7A89", linewidth=0.7, zorder=0)
    highlight = Rectangle(
        (zoom_start, bottom.get_ylim()[0]),
        zoom_end - zoom_start,
        bottom.get_ylim()[1] - bottom.get_ylim()[0],
        facecolor="#F4A261",
        edgecolor="#C75B12",
        alpha=0.24,
        linewidth=1.2,
        zorder=2,
    )
    bottom.add_patch(highlight)
    bottom.text(
        zoom_start + 8,
        bottom.get_ylim()[1] - 0.06 * (bottom.get_ylim()[1] - bottom.get_ylim()[0]),
        "window expanded above",
        color="#93410A",
        fontsize=8,
        ha="left",
        va="top",
    )
    bottom.set_xlabel("Acquisition time / ns")
    bottom.set_ylabel("Baseline-corrected voltage / V")
    bottom.set_title("Full oscilloscope record", loc="left", pad=8)
    bottom.grid(True)

    for relative_x, absolute_x in ((PULSE_WINDOW_NS[0], zoom_start), (PULSE_WINDOW_NS[1], zoom_end)):
        connector = ConnectionPatch(
            xyA=(relative_x, top.get_ylim()[0]),
            coordsA=top.transData,
            xyB=(absolute_x, bottom.get_ylim()[1]),
            coordsB=bottom.transData,
            color="#C75B12",
            linewidth=0.7,
            alpha=0.72,
            clip_on=False,
        )
        figure.add_artist(connector)

    figure.text(
        0.5,
        0.017,
        "Markers are recorded 0.5 ns samples; thin connecting segments in the expanded panel are guides to the eye. "
        "Voltage is referenced to the central cycle's local pre-pulse baseline.",
        ha="center",
        fontsize=8.2,
        color="#425466",
    )
    figure.savefig(output, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(figure)


def read_cycles_for_file(path: Path, file_name: str) -> list[Cycle]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        Cycle(
            index=int(row["cycle_index"]),
            baseline_v=float(row["baseline_v"]),
            incident_t50_ns=float(row["incident_t50_s"]) * 1e9,
            reflection_t50_ns=float(row["reflection_t50_s"]) * 1e9,
        )
        for row in rows
        if row["file"] == file_name
    ]


def render_composite(output: Path) -> None:
    """Render the aligned three-condition figure intended as the main waveform plot."""
    loaded: list[tuple[str, str, str, str, np.ndarray, np.ndarray, Cycle, dict[str, str]]] = []
    for kind, file_name, load_label, color in SPECS:
        t_ns, voltage_v = read_scope_csv(ROOT / file_name)
        cycle = central_cycle(read_cycles_for_file(ANALYSIS_DIR / "per_cycle.csv", file_name))
        processed = read_processed(ANALYSIS_DIR / "processed_results.csv", file_name)
        loaded.append((kind, file_name, load_label, color, t_ns, voltage_v - cycle.baseline_v, cycle, processed))

    figure = plt.figure(figsize=(9.0, 7.25), constrained_layout=False)
    grid = figure.add_gridspec(2, 1, height_ratios=(1.28, 0.84), hspace=0.64)
    top = figure.add_subplot(grid[0])
    bottom = figure.add_subplot(grid[1])
    figure.suptitle("RG58, L = 10 m: matched, open, and short terminations", y=0.985)

    all_aligned_t: list[np.ndarray] = []
    all_corrected_v: list[np.ndarray] = []
    legend_handles = []
    legend_labels = []
    reflection_times = []
    for kind, _, load_label, color, t_ns, corrected_v, cycle, processed in loaded:
        aligned_t = t_ns - cycle.incident_t50_ns
        all_aligned_t.append(aligned_t)
        all_corrected_v.append(corrected_v)
        zoom_mask = (aligned_t >= PULSE_WINDOW_NS[0]) & (aligned_t <= PULSE_WINDOW_NS[1])
        top.plot(aligned_t[zoom_mask], corrected_v[zoom_mask], color=color, alpha=0.36, linewidth=0.85, zorder=1)
        handle = top.scatter(
            aligned_t[zoom_mask], corrected_v[zoom_mask], s=12, color=color,
            edgecolor="white", linewidth=0.22, zorder=3,
        )
        gamma = float(processed["gamma_exp_mean"])
        condition_label = {"matched": "Matched (50 Ω)", "open": "Open (∞)", "short": "Short (0 Ω)"}[kind]
        label = f"{condition_label}: Γexp = {gamma:+.4f}"
        legend_handles.append(handle)
        legend_labels.append(label)
        if kind != "matched":
            reflection_times.append(cycle.reflection_t50_ns - cycle.incident_t50_ns)

    reflected_t50 = float(np.mean(reflection_times))
    top.axhline(0, color="#6C7A89", linewidth=0.75, zorder=0)
    top.axvline(0, color="#34495E", linewidth=0.85, linestyle="--", zorder=0)
    top.axvline(reflected_t50, color="#34495E", linewidth=0.85, linestyle=":", zorder=0)
    top.set_xlim(*PULSE_WINDOW_NS)
    top.set_ylim(-1.06, 1.12)
    top.set_ylabel("Baseline-corrected voltage / V")
    top.set_xlabel("Time relative to incident 50% crossing / ns")
    top.set_title("Expanded central pulse cycle: common incident pulse, then different reflections", loc="left", pad=8)
    top.grid(True)
    top.annotate(
        "shared incident\n50% crossing",
        xy=(0, 0.5),
        xytext=(-27, 0.78),
        arrowprops={"arrowstyle": "->", "color": "#34495E", "lw": 0.8},
        ha="center",
        va="bottom",
        fontsize=8,
        color="#34495E",
    )
    top.text(
        reflected_t50,
        0.05,
        "reflected 50%\ncrossings ≈ 103 ns",
        transform=top.get_xaxis_transform(),
        ha="center",
        va="bottom",
        fontsize=8,
        color="#34495E",
        bbox={"boxstyle": "round,pad=0.16", "facecolor": "white", "edgecolor": "none", "alpha": 0.86},
    )

    for (_, _, _, color, _, corrected_v, _, _), aligned_t in zip(loaded, all_aligned_t, strict=True):
        bottom.scatter(aligned_t, corrected_v, s=1.5, color=color, alpha=0.32, linewidths=0, rasterized=True)
    y_min = min(float(np.quantile(values, 0.001)) for values in all_corrected_v)
    y_max = max(float(np.quantile(values, 0.999)) for values in all_corrected_v)
    padding = max(0.08, 0.11 * (y_max - y_min))
    bottom.set_xlim(
        min(float(values.min()) for values in all_aligned_t),
        max(float(values.max()) for values in all_aligned_t),
    )
    bottom.set_ylim(y_min - padding, y_max + padding)
    bottom.axhline(0, color="#6C7A89", linewidth=0.7, zorder=0)
    highlight = Rectangle(
        (PULSE_WINDOW_NS[0], bottom.get_ylim()[0]),
        PULSE_WINDOW_NS[1] - PULSE_WINDOW_NS[0],
        bottom.get_ylim()[1] - bottom.get_ylim()[0],
        facecolor="#F4A261",
        edgecolor="#C75B12",
        alpha=0.22,
        linewidth=1.2,
        zorder=2,
    )
    bottom.add_patch(highlight)
    bottom.text(
        5,
        bottom.get_ylim()[1] - 0.06 * (bottom.get_ylim()[1] - bottom.get_ylim()[0]),
        "window expanded above",
        color="#93410A",
        fontsize=8,
        ha="left",
        va="top",
    )
    bottom.set_xlabel("Time relative to central-cycle incident crossing / ns")
    bottom.set_ylabel("Baseline-corrected voltage / V")
    bottom.set_title("Full oscilloscope records after the same incident-pulse alignment", loc="left", pad=8)
    bottom.grid(True)

    for x_coord in PULSE_WINDOW_NS:
        figure.add_artist(
            ConnectionPatch(
                xyA=(x_coord, top.get_ylim()[0]), coordsA=top.transData,
                xyB=(x_coord, bottom.get_ylim()[1]), coordsB=bottom.transData,
                color="#C75B12", linewidth=0.7, alpha=0.72, clip_on=False,
            )
        )
    top.legend(
        legend_handles,
        legend_labels,
        loc="lower left",
        frameon=True,
        facecolor="white",
        framealpha=0.88,
        edgecolor="#B8C2CC",
        fontsize=8.2,
        handletextpad=0.35,
        labelspacing=0.35,
    )
    figure.text(
        0.5,
        0.017,
        "All traces are aligned to the central-cycle incident 50% crossing. Markers are recorded 0.5 ns samples; "
        "thin upper-panel segments are guides to the eye. Voltage uses each central cycle's local pre-pulse baseline.",
        ha="center",
        fontsize=8.2,
        color="#425466",
    )
    figure.savefig(output, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    configure_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for kind, file_name, load_label, color in SPECS:
        render(kind, file_name, load_label, color, args.output_dir / f"rg58_10m_{kind}_waveform.png")
    render_composite(args.output_dir / "rg58_10m_matched_open_short_composite.png")
    print(f"Wrote individual and composite RG58 10 m waveform figures to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
