"""Render publication-ready quantitative figures from the checked-in analysis CSVs.

This script is deliberately read-only with respect to raw waveforms and analysis
tables.  It writes only the three figures requested for the EE:
``gamma_exp_vs_theory.png``, ``ln_k_vs_length.png``, and
``delta_t_vs_length.png``.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ANALYSIS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ANALYSIS_DIR / "figures"
COLORS = {"RG58": "#0072B2", "RG179": "#D55E00"}
LENGTH_COLORS = {4: "#0072B2", 5: "#009E73", 10: "#E69F00", 15: "#CC79A7"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict[str, str], field: str) -> float:
    value = row.get(field, "")
    if value == "":
        raise ValueError(f"Missing {field!r} in {row.get('file', row)}")
    return float(value)


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "figure.titlesize": 14,
            "figure.titleweight": "bold",
            "legend.fontsize": 9,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "axes.edgecolor": "#34495E",
            "axes.linewidth": 0.9,
            "grid.color": "#DDE3EA",
            "grid.linewidth": 0.7,
            "grid.alpha": 0.9,
            "savefig.dpi": 300,
        }
    )


def gamma_figure(rows: list[dict[str, str]], fits: list[dict[str, str]], output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 5.1), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.075, right=0.99, bottom=0.17, top=0.85, wspace=0.27)
    domain = np.linspace(-1.05, 1.05, 300)

    for axis, cable in zip(axes, ("RG58", "RG179"), strict=True):
        axis.plot(domain, domain, color="#6C7A89", linestyle="--", linewidth=1.2, label="1:1 agreement")
        cable_rows = [row for row in rows if row["cable"] == cable]
        lengths = sorted({int(row["length_m"]) for row in cable_rows})

        for length in lengths:
            subset = [row for row in cable_rows if int(row["length_m"]) == length]
            color = LENGTH_COLORS[length]
            x = np.array([as_float(row, "gamma_theory") for row in subset])
            y = np.array([as_float(row, "gamma_exp_mean") for row in subset])
            yerr = np.array([as_float(row, "gamma_exp_sd") for row in subset])
            matched = np.array([row["qc_status"] == "matched_no_timing" for row in subset])
            ordinary = ~matched
            axis.errorbar(
                x[ordinary], y[ordinary], yerr=yerr[ordinary],
                fmt="o", markersize=5.2, capsize=2, color=color,
                markeredgecolor="white", markeredgewidth=0.7, linewidth=0.8, zorder=3,
            )
            if matched.any():
                axis.errorbar(
                    x[matched], y[matched], yerr=yerr[matched],
                    fmt="o", markersize=6.2, markerfacecolor="white", markeredgecolor=color,
                    markeredgewidth=1.5, capsize=2, color=color, linewidth=0.8, zorder=4,
                )

            fit = next(
                item for item in fits
                if item["fit_type"] == "gamma_through_origin"
                and item["cable"] == cable
                and int(item["length_m"]) == length
            )
            k = as_float(fit, "slope")
            r_squared = as_float(fit, "r_squared")
            axis.plot(
                domain,
                k * domain,
                color=color,
                linewidth=1.6,
                label=f"{length} m fit, k = {k:.3f}, R² = {r_squared:.4f}",
            )

        axis.set_title(cable)
        axis.set_xlabel(r"$\Gamma_{\mathrm{th}}$")
        axis.set_xlim(-1.08, 1.08)
        axis.set_ylim(-1.08, 1.08)
        axis.set_aspect("equal", adjustable="box")
        axis.grid(True)
        axis.legend(loc="upper left", frameon=False, handlelength=2.2)

    axes[0].set_ylabel(r"$\Gamma_{\mathrm{exp}}$")
    fig.suptitle("Experimental reflection coefficient versus transmission-line theory", y=0.975)
    fig.text(0.5, 0.035, "Points show configuration means; vertical bars show within-record pulse-cycle SD. Open circles are matched loads.", ha="center", fontsize=9)
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def ln_k_figure(fits: list[dict[str, str]], output: Path) -> None:
    fig, axis = plt.subplots(figsize=(7.5, 5.0))
    fig.subplots_adjust(left=0.11, right=0.98, bottom=0.19, top=0.88)
    gamma_fits = [row for row in fits if row["fit_type"] == "gamma_through_origin"]

    for cable in ("RG58", "RG179"):
        subset = sorted((row for row in gamma_fits if row["cable"] == cable), key=lambda row: as_float(row, "length_m"))
        x = np.array([as_float(row, "length_m") for row in subset])
        k = np.array([as_float(row, "slope") for row in subset])
        low = np.array([as_float(row, "slope_ci95_low") for row in subset])
        high = np.array([as_float(row, "slope_ci95_high") for row in subset])
        y = np.log(k)
        yerr = np.vstack((y - np.log(low), np.log(high) - y))
        slope, intercept = np.polyfit(x, y, 1)
        fitted_y = slope * x + intercept
        r_squared = 1 - np.sum((y - fitted_y) ** 2) / np.sum((y - np.mean(y)) ** 2)
        line_x = np.linspace(x.min(), x.max(), 100)
        color = COLORS[cable]
        axis.errorbar(x, y, yerr=yerr, fmt="o", color=color, capsize=3, markersize=6, label=cable, zorder=3)
        axis.plot(
            line_x,
            slope * line_x + intercept,
            color=color,
            linewidth=1.7,
            linestyle="-",
            label=rf"{cable}: $\ln k = {slope:.4f}L {intercept:+.4f}$, $R^2 = {r_squared:.4f}$",
        )

    axis.set_xlabel(r"Cable length, $L$ / m")
    axis.set_ylabel(r"$\ln(k)$")
    axis.set_title(r"ln(k) against cable length")
    axis.grid(True)
    axis.legend(frameon=False, loc="best")
    fig.text(
        0.5,
        0.04,
        r"$k$ is the zero-intercept fitted slope in $\Gamma_{\mathrm{exp}} = k\Gamma_{\mathrm{th}}$; error bars show its log-transformed 95% confidence interval.",
        ha="center",
        fontsize=9,
    )
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_effective_attenuation(fits: list[dict[str, str]], output: Path) -> None:
    """Write the full-precision ln(k) gradient and alpha_eff = -m/s.

    Here s=2 because the reflected wave travels approximately one cable length
    outward and one length back to the measurement plane.
    """
    rows = []
    for cable in ("RG58", "RG179"):
        subset = sorted(
            (row for row in fits if row["fit_type"] == "gamma_through_origin" and row["cable"] == cable),
            key=lambda row: as_float(row, "length_m"),
        )
        x = np.array([as_float(row, "length_m") for row in subset])
        y = np.log(np.array([as_float(row, "slope") for row in subset]))
        m, intercept = (float(value) for value in np.polyfit(x, y, 1))
        rows.append(
            {
                "cable": cable,
                "s": "2",
                "m_per_m": f"{m:.15g}",
                "intercept": f"{intercept:.15g}",
                "alpha_eff_per_m": f"{-m / 2.0:.15g}",
            }
        )
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['cable']}: m={row['m_per_m']}, alpha_eff=-m/s={row['alpha_eff_per_m']} m^-1 (s={row['s']})")


def delay_figure(
    rows: list[dict[str, str]], groups: list[dict[str, str]], fits: list[dict[str, str]], output: Path
) -> None:
    fig, axis = plt.subplots(figsize=(8.0, 5.2))
    fig.subplots_adjust(left=0.11, right=0.98, bottom=0.18, top=0.88)
    propagation_fits = [row for row in fits if row["fit_type"] == "round_trip_delay_linear"]

    for cable, offset in (("RG58", -0.08), ("RG179", 0.08)):
        color = COLORS[cable]
        cable_groups = sorted((row for row in groups if row["cable"] == cable), key=lambda row: as_float(row, "length_m"))
        x = np.array([as_float(row, "length_m") + offset for row in cable_groups])
        y = np.array([as_float(row, "delay_ns_median") for row in cable_groups])
        yerr = np.array([as_float(row, "delay_between_load_sd_ns") for row in cable_groups])
        axis.errorbar(
            x,
            y,
            yerr=yerr,
            fmt="none",
            color=color,
            elinewidth=1.5,
            capsize=5,
            capthick=1.5,
            zorder=5,
        )
        axis.scatter(x, y, s=32, marker="D", color=color, edgecolors="white", linewidths=0.7, zorder=6)

        fit = next(row for row in propagation_fits if row["cable"] == cable)
        slope = as_float(fit, "slope")
        intercept = as_float(fit, "intercept")
        r_squared = as_float(fit, "r_squared")
        line_x = np.linspace(x.min() - offset, x.max() - offset, 100)
        velocity = as_float(fit, "velocity_m_s") / 1e8
        axis.plot(
            line_x + offset,
            intercept + slope * line_x,
            color=color,
            linewidth=1.8,
            label=rf"{cable}: $b = {slope:.3f}$ ns m$^{{-1}}$, $v = {velocity:.3f}\times10^8$ m s$^{{-1}}$, $R^2 = {r_squared:.6f}$",
        )

    axis.set_xlabel(r"Cable length, $L$ / m")
    axis.set_ylabel(r"Round-trip delay, $\Delta t$ / ns")
    axis.set_title(r"Round-trip reflection delay versus cable length")
    axis.set_xlim(3.3, 15.7)
    axis.set_ylim(25, 160)
    axis.grid(True)
    axis.legend(frameon=False, loc="upper left")
    fig.text(0.5, 0.035, "Vertical bars show between-load SD; cable length has no uncertainty bar.", ha="center", fontsize=9)
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def validate(rows: list[dict[str, str]], groups: list[dict[str, str]], fits: list[dict[str, str]]) -> None:
    if len(rows) != 66:
        raise ValueError(f"Expected 66 processed configurations; found {len(rows)}")
    if len(groups) != 6:
        raise ValueError(f"Expected six cable-length delay groups; found {len(groups)}")
    if len(fits) != 8:
        raise ValueError(f"Expected six gamma fits and two delay fits; found {len(fits)}")
    if sum(row["qc_status"] == "matched_no_timing" for row in rows) != 6:
        raise ValueError("Expected exactly six matched-load rows with N/A timing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    rows = read_csv(ANALYSIS_DIR / "processed_results.csv")
    groups = read_csv(ANALYSIS_DIR / "group_delays.csv")
    fits = read_csv(ANALYSIS_DIR / "group_fits.csv")
    validate(rows, groups, fits)
    configure_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    gamma_figure(rows, fits, args.output_dir / "gamma_exp_vs_theory.png")
    ln_k_figure(fits, args.output_dir / "ln_k_vs_length.png")
    write_effective_attenuation(fits, args.output_dir / "effective_attenuation.csv")
    delay_figure(rows, groups, fits, args.output_dir / "delta_t_vs_length.png")
    print(f"Wrote figures to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
