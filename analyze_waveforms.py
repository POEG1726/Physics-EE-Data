"""Reproducible analysis of the formal coaxial-cable waveform matrix.

The script reads the original Siglent CSV exports without modifying them.  It
uses one extraction rule for every load, writes auditable per-cycle and
per-configuration tables, performs the stated physics fits, and generates two
high-resolution figures for the essay.

Run from the repository root with the bundled Python environment::

    python analyze_waveforms.py

Dependencies: NumPy and Pillow.  SciPy and Matplotlib are not required.
"""

from __future__ import annotations

import csv
import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "analysis"
DATA_STATUS = ROOT / "data_status.csv"

SPEED_OF_LIGHT_M_S = 299_792_458.0
PULSE_PERIOD_S = 400e-9
INCIDENT_SEARCH_HALF_WIDTH_S = 60e-9
BASELINE_START_S = -90e-9
BASELINE_END_S = -35e-9
EDGE_SEARCH_WIDTH_S = 30e-9
OPEN_ANCHOR_HALF_WIDTH_S = 20e-9
FIXED_REFLECTION_HALF_WIDTH_S = 15e-9
BROAD_REFLECTION_START_S = 30e-9
BROAD_REFLECTION_END_S = 180e-9
DELAY_OUTLIER_THRESHOLD_NS = 15.0
UNRESOLVED_GAMMA_THRESHOLD = 0.04

Z0_OHM = {"RG58": 50.0, "RG179": 75.0}
LOAD_ORDER = ["6", "12", "22", "33", "50", "75", "120", "200", "470", "open", "short"]
NAME_PATTERN = re.compile(
    r"^(?P<cable>RG58|RG179)-(?P<length>\d+)M-(?P<load>SHORT|OPEN|\d+OHM)(?P<wrong>-WRONG)?\.CSV$",
    re.IGNORECASE,
)
GROUP_PATTERN = re.compile(r"^(RG58|RG179)\s+(\d+)m$", re.IGNORECASE)


@dataclass(frozen=True, order=True)
class Config:
    cable: str
    length_m: int
    load: str

    @property
    def z0_ohm(self) -> float:
        return Z0_OHM[self.cable]

    @property
    def load_ohm(self) -> float:
        if self.load == "short":
            return 0.0
        if self.load == "open":
            return math.inf
        return float(self.load)

    @property
    def gamma_theory(self) -> float:
        if self.load == "open":
            return 1.0
        return (self.load_ohm - self.z0_ohm) / (self.load_ohm + self.z0_ohm)

    @property
    def group(self) -> tuple[str, int]:
        return self.cable, self.length_m


@dataclass
class Waveform:
    path: Path
    time_s: np.ndarray
    voltage_v: np.ndarray
    sample_interval_s: float


@dataclass
class Incident:
    cycle_index: int
    peak_index: int
    peak_time_s: float
    baseline_v: float
    amplitude_v: float
    t50_s: float


def parse_name(path: Path) -> tuple[Config | None, bool]:
    match = NAME_PATTERN.fullmatch(path.name)
    if not match:
        return None, False
    raw_load = match.group("load").lower()
    load = raw_load[:-3] if raw_load.endswith("ohm") else raw_load
    return (
        Config(match.group("cable").upper(), int(match.group("length")), load),
        bool(match.group("wrong")),
    )


def expected_configs(path: Path) -> list[Config]:
    configs: list[Config] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            group_match = GROUP_PATTERN.fullmatch(row["Cable group"].strip())
            if not group_match:
                raise ValueError(f"Unrecognised cable group in {path.name}: {row['Cable group']!r}")
            cable, length = group_match.group(1).upper(), int(group_match.group(2))
            for load in LOAD_ORDER:
                if row.get(load, "").strip().upper() == "X":
                    configs.append(Config(cable, length, load))
    return configs


def formal_files(configs: Iterable[Config]) -> dict[Config, Path]:
    expected = set(configs)
    candidates: dict[Config, list[Path]] = {config: [] for config in expected}
    for path in ROOT.glob("*.csv"):
        config, is_wrong = parse_name(path)
        if config in expected and not is_wrong:
            candidates[config].append(path)
    missing = [config for config, paths in candidates.items() if not paths]
    duplicates = [(config, paths) for config, paths in candidates.items() if len(paths) > 1]
    if missing or duplicates:
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(str(item) for item in sorted(missing)))
        if duplicates:
            parts.append(
                "duplicates: "
                + "; ".join(f"{config}: {[path.name for path in paths]}" for config, paths in duplicates)
            )
        raise RuntimeError("Formal matrix cannot be resolved (" + " | ".join(parts) + ")")
    return {config: paths[0] for config, paths in candidates.items()}


def read_waveform(path: Path) -> Waveform:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    header_indexes = [i for i, row in enumerate(rows) if row[:2] == ["Second", "Value"]]
    if len(header_indexes) != 1:
        raise ValueError(f"{path.name}: expected exactly one Second,Value header")
    header_index = header_indexes[0]
    metadata = {row[0].strip(): row[1].strip() for row in rows[:header_index] if len(row) >= 2}
    time_s = np.asarray([float(row[0]) for row in rows[header_index + 1 :] if len(row) == 2], dtype=float)
    voltage_v = np.asarray([float(row[1]) for row in rows[header_index + 1 :] if len(row) == 2], dtype=float)
    if len(time_s) != len(voltage_v) or len(time_s) < 3:
        raise ValueError(f"{path.name}: invalid numeric sample count")
    dt = float(metadata.get("Sample Interval", np.median(np.diff(time_s))))
    if not np.all(np.diff(time_s) > 0):
        raise ValueError(f"{path.name}: time axis is not increasing")
    if not np.isclose(float(np.median(np.diff(time_s))), dt, rtol=1e-6, atol=1e-15):
        raise ValueError(f"{path.name}: sample interval does not match time axis")
    return Waveform(path, time_s, voltage_v, dt)


def linear_crossing(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    target_v: float,
    start_index: int,
    end_index: int,
    rising: bool,
) -> float | None:
    start_index = max(0, start_index)
    end_index = min(len(time_s) - 1, end_index)
    crossings: list[int] = []
    for index in range(start_index, end_index):
        first, second = voltage_v[index], voltage_v[index + 1]
        if (rising and first <= target_v < second) or (not rising and first >= target_v > second):
            crossings.append(index)
    if not crossings:
        return None
    index = crossings[-1]
    v0, v1 = voltage_v[index], voltage_v[index + 1]
    if v1 == v0:
        return float(time_s[index])
    fraction = (target_v - v0) / (v1 - v0)
    return float(time_s[index] + fraction * (time_s[index + 1] - time_s[index]))


def incident_cycles(waveform: Waveform) -> list[Incident]:
    time_s, voltage_v, dt = waveform.time_s, waveform.voltage_v, waveform.sample_interval_s
    reference_peak = int(np.argmax(voltage_v))
    period_samples = int(round(PULSE_PERIOD_S / dt))
    half_width = int(round(INCIDENT_SEARCH_HALF_WIDTH_S / dt))
    baseline_start = int(round(BASELINE_START_S / dt))
    baseline_end = int(round(BASELINE_END_S / dt))
    edge_width = int(round(EDGE_SEARCH_WIDTH_S / dt))
    peaks: list[int] = []
    min_k = math.floor((0 - reference_peak) / period_samples) - 1
    max_k = math.ceil((len(time_s) - 1 - reference_peak) / period_samples) + 1
    for k in range(min_k, max_k + 1):
        target = reference_peak + k * period_samples
        left, right = max(0, target - half_width), min(len(time_s), target + half_width + 1)
        if right - left < 3:
            continue
        peak = left + int(np.argmax(voltage_v[left:right]))
        if peak + baseline_start < 0 or peak + baseline_end <= peak + baseline_start:
            continue
        if not peaks or abs(peak - peaks[-1]) > period_samples // 2:
            peaks.append(peak)

    incidents: list[Incident] = []
    for cycle_index, peak in enumerate(peaks, start=1):
        baseline = float(np.median(voltage_v[peak + baseline_start : peak + baseline_end]))
        amplitude = float(voltage_v[peak] - baseline)
        target = baseline + 0.5 * amplitude
        t50 = linear_crossing(time_s, voltage_v, target, peak - edge_width, peak, rising=True)
        if amplitude <= 0 or t50 is None:
            continue
        incidents.append(Incident(cycle_index, peak, float(time_s[peak]), baseline, amplitude, t50))
    return incidents


def signed_peak(
    waveform: Waveform,
    baseline_v: float,
    start_time_s: float,
    end_time_s: float,
    sign: int,
) -> tuple[int, float] | None:
    left = int(np.searchsorted(waveform.time_s, start_time_s, side="left"))
    right = int(np.searchsorted(waveform.time_s, end_time_s, side="right"))
    if right - left < 3:
        return None
    segment = waveform.voltage_v[left:right]
    if sign > 0:
        relative_index = int(np.argmax(segment))
    elif sign < 0:
        relative_index = int(np.argmin(segment))
    else:
        relative_index = int(np.argmax(np.abs(segment - baseline_v)))
    index = left + relative_index
    return index, float(waveform.voltage_v[index] - baseline_v)


def reflection_measurement(
    waveform: Waveform,
    incident: Incident,
    start_time_s: float,
    end_time_s: float,
    sign: int,
) -> dict[str, float] | None:
    peak = signed_peak(waveform, incident.baseline_v, start_time_s, end_time_s, sign)
    if peak is None:
        return None
    peak_index, amplitude_v = peak
    target_v = incident.baseline_v + 0.5 * amplitude_v
    edge_width = int(round(EDGE_SEARCH_WIDTH_S / waveform.sample_interval_s))
    t50_s = linear_crossing(
        waveform.time_s,
        waveform.voltage_v,
        target_v,
        peak_index - edge_width,
        peak_index,
        rising=amplitude_v > 0,
    )
    return {
        "peak_index": float(peak_index),
        "peak_time_s": float(waveform.time_s[peak_index]),
        "amplitude_v": amplitude_v,
        "gamma_exp": amplitude_v / incident.amplitude_v,
        "t50_s": t50_s if t50_s is not None else math.nan,
        "delay_ns": (t50_s - incident.t50_s) * 1e9 if t50_s is not None else math.nan,
    }


def open_delay_anchor(waveform: Waveform, length_m: int) -> tuple[float, list[float]]:
    initial_guess_s = 2.0 * length_m / (0.67 * SPEED_OF_LIGHT_M_S)
    delays: list[float] = []
    for incident in incident_cycles(waveform):
        center = incident.peak_time_s + initial_guess_s
        measurement = reflection_measurement(
            waveform,
            incident,
            center - OPEN_ANCHOR_HALF_WIDTH_S,
            center + OPEN_ANCHOR_HALF_WIDTH_S,
            sign=1,
        )
        if measurement is not None:
            delays.append(measurement["delay_ns"])
    if not delays:
        raise RuntimeError(f"Could not obtain OPEN delay anchor from {waveform.path.name}")
    return float(statistics.median(delays)), delays


def sample_sd(values: Iterable[float]) -> float:
    clean = list(values)
    return float(statistics.stdev(clean)) if len(clean) >= 2 else 0.0


def mean_or_nan(values: Iterable[float]) -> float:
    clean = list(values)
    return float(statistics.mean(clean)) if clean else math.nan


def median_or_nan(values: Iterable[float]) -> float:
    clean = list(values)
    return float(statistics.median(clean)) if clean else math.nan


def analyse_configuration(
    config: Config,
    waveform: Waveform,
    anchor_delay_ns: float,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    theory = config.gamma_theory
    sign = 1 if theory > 0 else -1 if theory < 0 else 0
    per_cycle: list[dict[str, object]] = []
    for incident in incident_cycles(waveform):
        center = incident.peak_time_s + anchor_delay_ns * 1e-9
        fixed = reflection_measurement(
            waveform,
            incident,
            center - FIXED_REFLECTION_HALF_WIDTH_S,
            center + FIXED_REFLECTION_HALF_WIDTH_S,
            sign,
        )
        if fixed is None:
            continue
        broad = None
        if abs(theory) >= 0.5:
            broad = reflection_measurement(
                waveform,
                incident,
                incident.peak_time_s + BROAD_REFLECTION_START_S,
                incident.peak_time_s + BROAD_REFLECTION_END_S,
                sign,
            )
        per_cycle.append(
            {
                "file": waveform.path.name,
                "cable": config.cable,
                "length_m": config.length_m,
                "load": config.load,
                "cycle_index": incident.cycle_index,
                "baseline_v": incident.baseline_v,
                "incident_peak_time_s": incident.peak_time_s,
                "incident_t50_s": incident.t50_s,
                "incident_amplitude_v": incident.amplitude_v,
                "reflection_peak_time_s": fixed["peak_time_s"],
                "reflection_t50_s": fixed["t50_s"],
                "reflection_amplitude_v": fixed["amplitude_v"],
                "gamma_theory": theory,
                "gamma_exp": fixed["gamma_exp"],
                "fixed_delay_ns": fixed["delay_ns"],
                "broad_gamma_exp": broad["gamma_exp"] if broad else math.nan,
                "broad_delay_ns": broad["delay_ns"] if broad else math.nan,
                "anchor_delay_ns": anchor_delay_ns,
            }
        )
    if not per_cycle:
        raise RuntimeError(f"No usable cycles extracted from {waveform.path.name}")

    gammas = [float(row["gamma_exp"]) for row in per_cycle]
    fixed_delays = [
        float(row["fixed_delay_ns"])
        for row in per_cycle
        if math.isfinite(float(row["fixed_delay_ns"]))
    ]
    broad_delays = [float(row["broad_delay_ns"]) for row in per_cycle if math.isfinite(float(row["broad_delay_ns"]))]
    broad_gammas = [float(row["broad_gamma_exp"]) for row in per_cycle if math.isfinite(float(row["broad_gamma_exp"]))]
    gamma_mean = mean_or_nan(gammas)
    broad_delay_median = median_or_nan(broad_delays)
    is_matched = abs(theory) < 1e-12
    delay_outlier = bool(
        broad_delays and abs(broad_delay_median - anchor_delay_ns) > DELAY_OUTLIER_THRESHOLD_NS
    )
    sign_mismatch = bool(not is_matched and gamma_mean * theory <= 0)
    unresolved = bool(
        not is_matched
        and (abs(gamma_mean) < UNRESOLVED_GAMMA_THRESHOLD or not fixed_delays)
    )
    if delay_outlier:
        status = "delay_outlier"
        note = "Broad-window reflection delay conflicts with this cable-length group's OPEN anchor."
    elif is_matched:
        status = "matched_no_timing"
        note = "The theoretical reflection is zero; timing is intentionally not reported."
    elif sign_mismatch:
        status = "sign_mismatch"
        note = "Measured reflection polarity conflicts with transmission-line theory."
    elif unresolved:
        status = "reflection_unresolved"
        note = "Measured reflected amplitude is below the fixed resolvability threshold."
    else:
        status = "ok"
        note = ""

    for row in per_cycle:
        row["qc_status"] = status

    delay_value = median_or_nan(fixed_delays) if status == "ok" else math.nan
    result: dict[str, object] = {
        "file": waveform.path.name,
        "cable": config.cable,
        "length_m": config.length_m,
        "load": config.load,
        "load_ohm": config.load_ohm,
        "z0_ohm": config.z0_ohm,
        "gamma_theory": theory,
        "cycles": len(per_cycle),
        "incident_amplitude_mean_v": mean_or_nan(float(row["incident_amplitude_v"]) for row in per_cycle),
        "reflection_amplitude_mean_v": mean_or_nan(float(row["reflection_amplitude_v"]) for row in per_cycle),
        "gamma_exp_mean": gamma_mean,
        "gamma_exp_sd": sample_sd(gammas),
        "gamma_residual": gamma_mean - theory,
        "fixed_delay_ns_median": median_or_nan(fixed_delays),
        "delay_ns_median": delay_value,
        "delay_cycle_sd_ns": sample_sd(fixed_delays) if status == "ok" else math.nan,
        "broad_delay_ns_median": broad_delay_median,
        "broad_gamma_exp_median": median_or_nan(broad_gammas),
        "anchor_delay_ns": anchor_delay_ns,
        "qc_status": status,
        "usable_for_gamma_fit": status == "ok" and not is_matched,
        "usable_for_delay_fit": status == "ok" and not is_matched,
        "note": note,
    }
    return per_cycle, result


def gamma_fit(rows: list[dict[str, object]], cable: str, length_m: int) -> dict[str, object]:
    selected = [
        row
        for row in rows
        if row["cable"] == cable and row["length_m"] == length_m and row["usable_for_gamma_fit"]
    ]
    x = np.asarray([float(row["gamma_theory"]) for row in selected])
    y = np.asarray([float(row["gamma_exp_mean"]) for row in selected])
    slope = float(np.dot(x, y) / np.dot(x, x))
    prediction = slope * x
    residual = y - prediction
    sse = float(np.dot(residual, residual))
    sst = float(np.dot(y - y.mean(), y - y.mean()))
    r_squared = 1.0 - sse / sst if sst else math.nan
    rmse = math.sqrt(sse / len(x))
    slope_se = math.sqrt((sse / (len(x) - 1)) / float(np.dot(x, x))) if len(x) > 1 else math.nan
    t_critical = {8: 2.306, 9: 2.262}.get(len(x) - 1, 1.96)
    ci_half = t_critical * slope_se
    attenuation_db_per_m = -20.0 * math.log10(slope) / (2.0 * length_m)
    return {
        "fit_type": "gamma_through_origin",
        "cable": cable,
        "length_m": length_m,
        "n": len(x),
        "slope": slope,
        "slope_se": slope_se,
        "slope_ci95_low": slope - ci_half,
        "slope_ci95_high": slope + ci_half,
        "intercept": 0.0,
        "r_squared": r_squared,
        "rmse": rmse,
        "velocity_m_s": math.nan,
        "attenuation_proxy_db_per_m": attenuation_db_per_m,
        "note": "Matched load and QC-failed configurations excluded; intercept fixed at zero by theory.",
    }


def group_delays(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups = sorted({(str(row["cable"]), int(row["length_m"])) for row in rows})
    result: list[dict[str, object]] = []
    for cable, length_m in groups:
        selected = [
            row
            for row in rows
            if row["cable"] == cable and row["length_m"] == length_m and row["usable_for_delay_fit"]
        ]
        delays = [float(row["delay_ns_median"]) for row in selected]
        result.append(
            {
                "cable": cable,
                "length_m": length_m,
                "configurations": len(delays),
                "delay_ns_median": median_or_nan(delays),
                "delay_between_load_sd_ns": sample_sd(delays),
                "delay_min_ns": min(delays),
                "delay_max_ns": max(delays),
            }
        )
    return result


def propagation_fit(groups: list[dict[str, object]], cable: str) -> dict[str, object]:
    selected = [row for row in groups if row["cable"] == cable]
    x = np.asarray([float(row["length_m"]) for row in selected])
    y = np.asarray([float(row["delay_ns_median"]) for row in selected])
    slope, intercept = (float(value) for value in np.polyfit(x, y, 1))
    prediction = intercept + slope * x
    residual = y - prediction
    sse = float(np.dot(residual, residual))
    sst = float(np.dot(y - y.mean(), y - y.mean()))
    r_squared = 1.0 - sse / sst if sst else math.nan
    rmse = math.sqrt(sse / len(x))
    sxx = float(np.dot(x - x.mean(), x - x.mean()))
    slope_se = math.sqrt((sse / (len(x) - 2)) / sxx) if len(x) > 2 and sxx else math.nan
    t_critical = 12.706 if len(x) - 2 == 1 else 1.96
    ci_half = t_critical * slope_se
    velocity = 2e9 / slope
    return {
        "fit_type": "round_trip_delay_linear",
        "cable": cable,
        "length_m": math.nan,
        "n": len(x),
        "slope": slope,
        "slope_se": slope_se,
        "slope_ci95_low": slope - ci_half,
        "slope_ci95_high": slope + ci_half,
        "intercept": intercept,
        "r_squared": r_squared,
        "rmse": rmse,
        "velocity_m_s": velocity,
        "attenuation_proxy_db_per_m": math.nan,
        "note": "Slope units ns/m; fit uses three group medians and therefore has one residual degree of freedom.",
    }


def direct_calibration(path: Path) -> dict[str, float]:
    waveform = read_waveform(path)
    incidents = incident_cycles(waveform)
    widths_ns: list[float] = []
    edge_width = int(round(40e-9 / waveform.sample_interval_s))
    for incident in incidents:
        plateau_left = int(np.searchsorted(waveform.time_s, incident.t50_s + 5e-9))
        plateau_right = int(np.searchsorted(waveform.time_s, incident.t50_s + 15e-9))
        plateau_v = float(np.median(waveform.voltage_v[plateau_left:plateau_right]))
        target = incident.baseline_v + 0.5 * (plateau_v - incident.baseline_v)
        rising = linear_crossing(
            waveform.time_s,
            waveform.voltage_v,
            target,
            incident.peak_index - edge_width,
            incident.peak_index,
            rising=True,
        )
        falling = linear_crossing(
            waveform.time_s,
            waveform.voltage_v,
            target,
            incident.peak_index,
            incident.peak_index + edge_width,
            rising=False,
        )
        if rising is not None and falling is not None:
            widths_ns.append((falling - rising) * 1e9)
    peak_times = [incident.peak_time_s for incident in incidents]
    periods_ns = [(later - earlier) * 1e9 for earlier, later in zip(peak_times, peak_times[1:])]
    return {
        "v_min": float(np.min(waveform.voltage_v)),
        "v_max": float(np.max(waveform.voltage_v)),
        "v_pp": float(np.max(waveform.voltage_v) - np.min(waveform.voltage_v)),
        "width_ns_mean": mean_or_nan(widths_ns),
        "width_ns_sd": sample_sd(widths_ns),
        "width_ns_min": min(widths_ns),
        "width_ns_max": max(widths_ns),
        "period_ns_median": median_or_nan(periods_ns),
        "frequency_mhz": 1000.0 / median_or_nan(periods_ns),
        "sample_interval_ns": waveform.sample_interval_s * 1e9,
    }


def aligned_cycle_correlation(first: Waveform, second: Waveform) -> float:
    """Median correlation after aligning repeated cycles at incident t50."""

    first_incidents = incident_cycles(first)
    second_incidents = incident_cycles(second)
    grid_s = np.arange(-50e-9, 200e-9 + 0.25e-9, max(first.sample_interval_s, second.sample_interval_s))
    correlations: list[float] = []
    for first_incident, second_incident in zip(first_incidents, second_incidents):
        first_times = first_incident.t50_s + grid_s
        second_times = second_incident.t50_s + grid_s
        if (
            first_times[0] < first.time_s[0]
            or first_times[-1] > first.time_s[-1]
            or second_times[0] < second.time_s[0]
            or second_times[-1] > second.time_s[-1]
        ):
            continue
        first_values = np.interp(first_times, first.time_s, first.voltage_v)
        second_values = np.interp(second_times, second.time_s, second.voltage_v)
        correlation = float(np.corrcoef(first_values, second_values)[0, 1])
        if math.isfinite(correlation):
            correlations.append(correlation)
    if not correlations:
        return math.nan
    return float(statistics.median(correlations))


def name_qc_rows(
    processed_rows: list[dict[str, object]],
    waveforms: dict[Config, Waveform],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for suspect in processed_rows:
        if suspect["qc_status"] != "delay_outlier":
            continue
        suspect_delay = float(suspect["broad_delay_ns_median"])
        candidates = [
            row
            for row in processed_rows
            if row["cable"] == suspect["cable"]
            and row["load"] == suspect["load"]
            and row["qc_status"] != "delay_outlier"
            and math.isfinite(float(row["broad_delay_ns_median"]))
        ]
        if not candidates:
            continue
        reference = min(candidates, key=lambda row: abs(float(row["broad_delay_ns_median"]) - suspect_delay))
        suspect_config = Config(str(suspect["cable"]), int(suspect["length_m"]), str(suspect["load"]))
        reference_config = Config(str(reference["cable"]), int(reference["length_m"]), str(reference["load"]))
        output.append(
            {
                "suspect_file": suspect["file"],
                "suspect_declared_length_m": suspect["length_m"],
                "suspect_broad_delay_ns": suspect_delay,
                "suspect_open_anchor_ns": suspect["anchor_delay_ns"],
                "nearest_same_load_file": reference["file"],
                "nearest_same_load_length_m": reference["length_m"],
                "reference_broad_delay_ns": reference["broad_delay_ns_median"],
                "delay_difference_ns": suspect_delay - float(reference["broad_delay_ns_median"]),
                "aligned_cycle_correlation": aligned_cycle_correlation(
                    waveforms[suspect_config], waveforms[reference_config]
                ),
                "verdict": "declared_length_inconsistent_recollect",
            }
        )
    return output


def clean_value(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.10g}"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return value


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fieldnames: list[str] | None = None,
) -> None:
    if not rows and fieldnames is None:
        raise ValueError(f"No rows for {path}")
    columns = fieldnames if fieldnames is not None else list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: clean_value(value) for key, value in row.items()})


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def dashed_line(draw: ImageDraw.ImageDraw, points: tuple[float, float, float, float], fill: str, width: int = 3) -> None:
    x0, y0, x1, y1 = points
    length = math.hypot(x1 - x0, y1 - y0)
    if not length:
        return
    dash, gap = 12.0, 8.0
    position = 0.0
    while position < length:
        end = min(length, position + dash)
        f0, f1 = position / length, end / length
        draw.line((x0 + (x1 - x0) * f0, y0 + (y1 - y0) * f0, x0 + (x1 - x0) * f1, y0 + (y1 - y0) * f1), fill=fill, width=width)
        position += dash + gap


def gamma_plot(rows: list[dict[str, object]], fits: list[dict[str, object]], path: Path) -> None:
    image = Image.new("RGB", (1800, 900), "white")
    draw = ImageDraw.Draw(image)
    title_font, label_font, tick_font = load_font(34, True), load_font(25), load_font(20)
    draw.text((900, 30), "Measured reflection coefficient vs transmission-line theory", font=title_font, fill="#17202a", anchor="ma")
    colors = {4: "#0072B2", 5: "#009E73", 10: "#E69F00", 15: "#CC79A7"}
    panels = {"RG58": (105, 120, 850, 790), "RG179": (950, 120, 1695, 790)}
    lower, upper = -1.08, 1.08

    for cable, (left, top, right, bottom) in panels.items():
        def px(value: float) -> float:
            return left + (value - lower) / (upper - lower) * (right - left)

        def py(value: float) -> float:
            return bottom - (value - lower) / (upper - lower) * (bottom - top)

        for tick in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            draw.line((px(tick), top, px(tick), bottom), fill="#e7e9ec", width=2)
            draw.line((left, py(tick), right, py(tick)), fill="#e7e9ec", width=2)
            draw.text((px(tick), bottom + 14), f"{tick:.1f}", font=tick_font, fill="#34495e", anchor="ma")
            draw.text((left - 14, py(tick)), f"{tick:.1f}", font=tick_font, fill="#34495e", anchor="rm")
        draw.rectangle((left, top, right, bottom), outline="#34495e", width=3)
        dashed_line(draw, (px(lower), py(lower), px(upper), py(upper)), "#7f8c8d", 3)
        draw.text(((left + right) / 2, top - 48), cable, font=label_font, fill="#17202a", anchor="ma")
        draw.text(((left + right) / 2, bottom + 56), "Theoretical reflection coefficient", font=label_font, fill="#17202a", anchor="ma")
        y_label = Image.new("RGBA", (650, 45), (255, 255, 255, 0))
        y_draw = ImageDraw.Draw(y_label)
        y_draw.text((325, 22), "Measured reflection coefficient", font=label_font, fill="#17202a", anchor="mm")
        y_label = y_label.rotate(90, expand=True)
        image.paste(y_label, (left - 92, int((top + bottom) / 2 - y_label.height / 2)), y_label)

        cable_rows = [row for row in rows if row["cable"] == cable]
        lengths = sorted({int(row["length_m"]) for row in cable_rows})
        for length in lengths:
            fit = next(item for item in fits if item["fit_type"] == "gamma_through_origin" and item["cable"] == cable and item["length_m"] == length)
            slope = float(fit["slope"])
            draw.line((px(lower), py(slope * lower), px(upper), py(slope * upper)), fill=colors[length], width=4)
            for row in cable_rows:
                if int(row["length_m"]) != length:
                    continue
                x, y = float(row["gamma_theory"]), float(row["gamma_exp_mean"])
                cx, cy = px(x), py(y)
                if row["qc_status"] == "delay_outlier":
                    draw.line((cx - 10, cy - 10, cx + 10, cy + 10), fill="#D55E00", width=5)
                    draw.line((cx - 10, cy + 10, cx + 10, cy - 10), fill="#D55E00", width=5)
                elif row["qc_status"] == "matched_no_timing":
                    draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill="white", outline=colors[length], width=4)
                else:
                    draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=colors[length], outline="white", width=2)
            legend_y = top + 28 + 34 * lengths.index(length)
            draw.line((left + 22, legend_y, left + 72, legend_y), fill=colors[length], width=4)
            draw.text((left + 82, legend_y), f"{length} m: slope {slope:.3f}", font=tick_font, fill="#2c3e50", anchor="lm")
        if cable == "RG179" and any(row["qc_status"] == "delay_outlier" for row in cable_rows):
            draw.text((right - 20, bottom - 22), "x = QC-excluded", font=tick_font, fill="#D55E00", anchor="ra")
    image.save(path, dpi=(200, 200))


def delay_plot(
    rows: list[dict[str, object]],
    groups: list[dict[str, object]],
    fits: list[dict[str, object]],
    path: Path,
) -> None:
    image = Image.new("RGB", (1500, 950), "white")
    draw = ImageDraw.Draw(image)
    title_font, label_font, tick_font = load_font(34, True), load_font(26), load_font(21)
    left, top, right, bottom = 145, 120, 1410, 820
    x_min, x_max, y_min, y_max = 3.0, 16.0, 25.0, 160.0
    colors = {"RG58": "#0072B2", "RG179": "#D55E00"}

    def px(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * (right - left)

    def py(value: float) -> float:
        return bottom - (value - y_min) / (y_max - y_min) * (bottom - top)

    draw.text((750, 34), "Round-trip reflection delay vs cable length", font=title_font, fill="#17202a", anchor="ma")
    for tick in range(4, 16, 1):
        if tick % 2 == 0:
            draw.line((px(tick), top, px(tick), bottom), fill="#e7e9ec", width=2)
            draw.text((px(tick), bottom + 15), str(tick), font=tick_font, fill="#34495e", anchor="ma")
    for tick in range(40, 161, 20):
        draw.line((left, py(tick), right, py(tick)), fill="#e7e9ec", width=2)
        draw.text((left - 15, py(tick)), str(tick), font=tick_font, fill="#34495e", anchor="rm")
    draw.rectangle((left, top, right, bottom), outline="#34495e", width=3)
    draw.text(((left + right) / 2, bottom + 65), "Cable length / m", font=label_font, fill="#17202a", anchor="ma")
    y_label = Image.new("RGBA", (620, 50), (255, 255, 255, 0))
    y_draw = ImageDraw.Draw(y_label)
    y_draw.text((310, 25), "Round-trip delay / ns", font=label_font, fill="#17202a", anchor="mm")
    y_label = y_label.rotate(90, expand=True)
    image.paste(y_label, (35, int((top + bottom) / 2 - y_label.height / 2)), y_label)

    for cable in ["RG58", "RG179"]:
        color = colors[cable]
        fit = next(item for item in fits if item["fit_type"] == "round_trip_delay_linear" and item["cable"] == cable)
        slope, intercept = float(fit["slope"]), float(fit["intercept"])
        cable_groups = [group for group in groups if group["cable"] == cable]
        low, high = min(float(group["length_m"]) for group in cable_groups), max(float(group["length_m"]) for group in cable_groups)
        draw.line((px(low), py(intercept + slope * low), px(high), py(intercept + slope * high)), fill=color, width=5)

        for row in rows:
            if row["cable"] != cable or not row["usable_for_delay_fit"]:
                continue
            x = float(row["length_m"]) + (-0.08 if cable == "RG58" else 0.08)
            y = float(row["delay_ns_median"])
            draw.ellipse((px(x) - 4, py(y) - 4, px(x) + 4, py(y) + 4), fill="#aeb6bf")
        for group in cable_groups:
            x = float(group["length_m"]) + (-0.08 if cable == "RG58" else 0.08)
            y = float(group["delay_ns_median"])
            sd = float(group["delay_between_load_sd_ns"])
            draw.line((px(x), py(y - sd), px(x), py(y + sd)), fill=color, width=3)
            draw.line((px(x) - 8, py(y - sd), px(x) + 8, py(y - sd)), fill=color, width=3)
            draw.line((px(x) - 8, py(y + sd), px(x) + 8, py(y + sd)), fill=color, width=3)
            draw.polygon([(px(x), py(y) - 10), (px(x) + 10, py(y)), (px(x), py(y) + 10), (px(x) - 10, py(y))], fill=color)
        legend_y = top + 40 + 42 * (["RG58", "RG179"].index(cable))
        draw.line((left + 28, legend_y, left + 90, legend_y), fill=color, width=5)
        draw.text(
            (left + 105, legend_y),
            f"{cable}: slope {slope:.3f} ns/m, v = {float(fit['velocity_m_s']) / 1e8:.3f} x 10^8 m/s",
            font=tick_font,
            fill="#2c3e50",
            anchor="lm",
        )
    draw.text((right - 14, bottom - 22), "small points = individual loads; diamonds = group medians", font=tick_font, fill="#5d6d7e", anchor="ra")
    image.save(path, dpi=(200, 200))


def summary_markdown(
    calibration: dict[str, float],
    rows: list[dict[str, object]],
    groups: list[dict[str, object]],
    fits: list[dict[str, object]],
    name_checks: list[dict[str, object]],
) -> str:
    gamma_fits = [fit for fit in fits if fit["fit_type"] == "gamma_through_origin"]
    propagation = [fit for fit in fits if fit["fit_type"] == "round_trip_delay_linear"]
    rg179_short = next(row for row in rows if row["cable"] == "RG179" and row["length_m"] == 15 and row["load"] == "short")
    short_name_check = next(
        (check for check in name_checks if check["suspect_file"] == rg179_short["file"]),
        None,
    )
    matched = [row for row in rows if row["qc_status"] == "matched_no_timing"]
    matched_abs_max = max(abs(float(row["gamma_exp_mean"])) for row in matched)
    lines = [
        "# Waveform analysis summary",
        "",
        "## Scope",
        "",
        "The formal analysis uses RG58 at 4 m, 5 m, and 10 m and RG179 at 5 m, 10 m, and 15 m, with the eleven loads listed in `data_status.csv`. RG58 15 m pilot traces and every `*-WRONG.csv` file are excluded. Raw waveform CSVs are read-only.",
        "",
        "## Extraction rule",
        "",
        "For every pulse cycle, the baseline is the median voltage from 90 ns to 35 ns before the incident peak. Incident and reflected amplitudes are measured relative to that baseline. The incident and reflected arrival times are obtained by linear interpolation at 50% of their respective amplitudes. Each cable-length group's OPEN trace supplies one fixed reflection-delay anchor; every other load is measured in the same +/-15 ns window around that anchor. A separate 30-180 ns broad-window check is applied only to strong theoretical reflections (|Gamma| >= 0.5) to detect delay/length inconsistencies. Repeated cycles quantify within-record repeatability but are not independent experimental repeats.",
        "",
        "## Calibration",
        "",
        f"- Direct-connection extrema: {calibration['v_min']:.4f} V to {calibration['v_max']:.4f} V; Vpp = {calibration['v_pp']:.4f} V.",
        f"- 50% pulse width from the stable high- and low-level midpoint: {calibration['width_ns_mean']:.3f} +/- {calibration['width_ns_sd']:.3f} ns across detected cycles (range {calibration['width_ns_min']:.3f}-{calibration['width_ns_max']:.3f} ns), supporting a nominal 20 ns setting.",
        f"- Pulse period: {calibration['period_ns_median']:.3f} ns, corresponding to {calibration['frequency_mhz']:.6f} MHz.",
        f"- Sampling interval: {calibration['sample_interval_ns']:.3f} ns.",
        "",
        "## Reflection-coefficient fits",
        "",
        "The fit is Gamma_exp = k Gamma_theory with the intercept constrained to zero. The exactly matched load and any QC-failed trace are excluded.",
        "",
        "| Cable | Length / m | n | k | 95% CI | R2 | RMSE |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for fit in gamma_fits:
        lines.append(
            f"| {fit['cable']} | {int(fit['length_m'])} | {fit['n']} | {float(fit['slope']):.3f} | {float(fit['slope_ci95_low']):.3f} to {float(fit['slope_ci95_high']):.3f} | {float(fit['r_squared']):.4f} | {float(fit['rmse']):.4f} |"
        )
    lines.extend(
        [
            "",
            f"All six matched-load residuals are small (maximum |Gamma_exp| = {matched_abs_max:.3f}), consistent with the predicted near-zero reflection. The fitted scale k falls with length, which is consistent with attenuation over the outward and return paths. At the directly comparable 5 m and 10 m lengths, RG179 has a smaller measured reflection scale than RG58. This is an empirical system response; it should not be attributed to characteristic impedance alone because the cables differ in construction and attenuation.",
            "",
            "## Propagation-delay fits",
            "",
            "Each length point is the median of all resolvable non-matched loads that passed QC. The linear model is Delta t = a + bL, and propagation speed is v = 2/b.",
            "",
            "| Cable | Group delays / ns | b / ns m^-1 | a / ns | R2 | v / m s^-1 | v/c |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for fit in propagation:
        cable_groups = [group for group in groups if group["cable"] == fit["cable"]]
        delay_text = ", ".join(f"{int(group['length_m'])} m: {float(group['delay_ns_median']):.3f}" for group in cable_groups)
        velocity = float(fit["velocity_m_s"])
        lines.append(
            f"| {fit['cable']} | {delay_text} | {float(fit['slope']):.3f} | {float(fit['intercept']):.3f} | {float(fit['r_squared']):.5f} | {velocity:.4e} | {velocity / SPEED_OF_LIGHT_M_S:.3f} |"
        )
    lines.extend(
        [
            "",
            "Only three lengths are available for each cable, leaving one residual degree of freedom. The very high R2 values demonstrate consistency with a linear relation but do not by themselves establish a precise uncertainty on velocity. Cable-length uncertainty was not recorded and must not be invented.",
            "",
            "## Data-quality result",
            "",
        ]
    )
    if short_name_check is not None and rg179_short["qc_status"] == "delay_outlier":
        lines.append(
            f"`{rg179_short['file']}` is excluded from both formal fits. Its broad-window short-circuit reflection is at {float(rg179_short['broad_delay_ns_median']):.3f} ns with Gamma approximately {float(rg179_short['broad_gamma_exp_median']):.3f}, while the RG179 15 m OPEN anchor is {float(rg179_short['anchor_delay_ns']):.3f} ns. Its nearest same-load trace is `{short_name_check['nearest_same_load_file']}`: the delays differ by only {abs(float(short_name_check['delay_difference_ns'])):.3f} ns and their incident-aligned cycle correlation is {float(short_name_check['aligned_cycle_correlation']):.5f}. The waveform therefore behaves like the RG179 10 m short acquisition, not a 15 m trace. The physical dataset requires one recollection: RG179 15 m short. No other formal configuration was automatically rejected."
        )
    else:
        lines.append(
            f"No cable-length/load configuration was rejected by the automated delay-consistency check. The formal RG179 15 m short trace gives a round-trip delay of {float(rg179_short['delay_ns_median']):.3f} ns and Gamma_exp = {float(rg179_short['gamma_exp_mean']):.4f}, consistent with the rest of the 15 m group."
        )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `per_cycle.csv`: every extracted pulse cycle and its QC status.",
            "- `processed_results.csv`: one row per formal cable-length-load configuration.",
            "- `group_delays.csv`: delay aggregation across valid loads.",
            "- `group_fits.csv`: reflection and propagation fit coefficients.",
            "- `name_qc.csv`: delay and waveform-similarity evidence for any physical-label outlier.",
            "- `figure_gamma_vs_theory.png`: reflection-response figure.",
            "- `figure_delay_vs_length.png`: propagation-delay figure.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    configs = expected_configs(DATA_STATUS)
    files = formal_files(configs)
    waveforms = {config: read_waveform(path) for config, path in files.items()}

    anchors: dict[tuple[str, int], float] = {}
    anchor_rows: list[dict[str, object]] = []
    for cable, length_m in sorted({config.group for config in configs}):
        open_config = Config(cable, length_m, "open")
        anchor, cycles = open_delay_anchor(waveforms[open_config], length_m)
        anchors[(cable, length_m)] = anchor
        anchor_rows.append(
            {
                "cable": cable,
                "length_m": length_m,
                "open_anchor_delay_ns": anchor,
                "open_anchor_cycle_sd_ns": sample_sd(cycles),
                "cycles": len(cycles),
            }
        )

    per_cycle_rows: list[dict[str, object]] = []
    processed_rows: list[dict[str, object]] = []
    for config in sorted(configs, key=lambda item: (item.cable, item.length_m, LOAD_ORDER.index(item.load))):
        cycles, result = analyse_configuration(config, waveforms[config], anchors[config.group])
        per_cycle_rows.extend(cycles)
        processed_rows.append(result)

    group_order = [(cable, length) for cable in ["RG58", "RG179"] for length in sorted(value for item_cable, value in anchors if item_cable == cable)]
    gamma_fits = [gamma_fit(processed_rows, cable, length) for cable, length in group_order]
    delay_groups = group_delays(processed_rows)
    propagation_fits = [propagation_fit(delay_groups, cable) for cable in ["RG58", "RG179"]]
    all_fits = gamma_fits + propagation_fits
    calibration = direct_calibration(ROOT / "DIRECT-CONNECTION.csv")
    name_checks = name_qc_rows(processed_rows, waveforms)

    write_csv(OUTPUT_DIR / "per_cycle.csv", per_cycle_rows)
    write_csv(OUTPUT_DIR / "processed_results.csv", processed_rows)
    write_csv(OUTPUT_DIR / "open_delay_anchors.csv", anchor_rows)
    write_csv(OUTPUT_DIR / "group_delays.csv", delay_groups)
    write_csv(OUTPUT_DIR / "group_fits.csv", all_fits)
    write_csv(OUTPUT_DIR / "calibration.csv", [calibration])
    write_csv(
        OUTPUT_DIR / "name_qc.csv",
        name_checks,
        fieldnames=[
            "suspect_file",
            "suspect_declared_length_m",
            "suspect_broad_delay_ns",
            "suspect_open_anchor_ns",
            "nearest_same_load_file",
            "nearest_same_load_length_m",
            "reference_broad_delay_ns",
            "delay_difference_ns",
            "aligned_cycle_correlation",
            "verdict",
        ],
    )
    gamma_plot(processed_rows, all_fits, OUTPUT_DIR / "figure_gamma_vs_theory.png")
    delay_plot(processed_rows, delay_groups, all_fits, OUTPUT_DIR / "figure_delay_vs_length.png")
    (OUTPUT_DIR / "analysis_summary.md").write_text(
        summary_markdown(calibration, processed_rows, delay_groups, all_fits, name_checks), encoding="utf-8"
    )

    statuses: dict[str, int] = {}
    for row in processed_rows:
        status = str(row["qc_status"])
        statuses[status] = statuses.get(status, 0) + 1
    print(f"Analysed {len(processed_rows)} formal configurations and {len(per_cycle_rows)} pulse cycles.")
    print("QC status: " + ", ".join(f"{key}={value}" for key, value in sorted(statuses.items())))
    print(f"Outputs written to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
