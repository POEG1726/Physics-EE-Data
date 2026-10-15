"""Audit the Siglent waveform CSV files used by the transmission-line EE.

The raw scope files do not store the cable, length, or termination value in
their metadata.  Filename checks therefore verify naming syntax and coverage,
but cannot prove the physical setup.  For a physical name check, generate and
complete a manifest from contemporaneous lab notes, PCB labels, and (for
resistors) DMM readings, then validate it with ``--manifest``.

Examples
--------
python verify_waveform_data.py
python verify_waveform_data.py --allow-incomplete
python verify_waveform_data.py --write-manifest-template measurement_manifest.csv
python verify_waveform_data.py --manifest measurement_manifest.csv --require-manifest
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


WAVEFORM_NAME = re.compile(
    r"^(?P<cable>RG58|RG179)-(?P<length>\d+)M-"
    r"(?P<load>SHORT|OPEN|\d+OHM)(?P<wrong>-WRONG)?\.CSV$",
    re.IGNORECASE,
)
GROUP_NAME = re.compile(r"^(?P<cable>RG58|RG179)\s+(?P<length>\d+)m$", re.IGNORECASE)
YES = {"yes", "y", "true", "1"}


@dataclass(frozen=True, order=True)
class Configuration:
    cable: str
    length_m: int
    load: str

    def label(self) -> str:
        load = self.load if self.load in {"short", "open"} else f"{self.load} ohm"
        return f"{self.cable} {self.length_m} m, {load}"


@dataclass
class Waveform:
    path: Path
    configuration: Configuration | None
    is_wrong: bool
    record_length: int | None = None
    sample_interval_s: float | None = None
    vertical_units: str | None = None
    horizontal_units: str | None = None
    model: str | None = None
    source: str | None = None
    samples: int = 0
    t_start_s: float | None = None
    t_end_s: float | None = None
    pulse_period_s: float | None = None
    repeat_correlation: float | None = None
    repeat_rmse_v: float | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def structural_ok(self) -> bool:
        return not self.errors


def normalize_load(value: str) -> str:
    token = value.strip().lower()
    if token in {"short", "open"}:
        return token
    match = re.fullmatch(r"(\d+)(?:ohm)?", token)
    if not match:
        raise ValueError(f"unrecognised load label: {value!r}")
    return match.group(1)


def parse_configuration(filename: str) -> tuple[Configuration | None, bool]:
    match = WAVEFORM_NAME.fullmatch(filename)
    if not match:
        return None, False
    return (
        Configuration(
            cable=match.group("cable").upper(),
            length_m=int(match.group("length")),
            load=normalize_load(match.group("load")),
        ),
        bool(match.group("wrong")),
    )


def parse_record_length(value: str) -> int | None:
    match = re.search(r"(\d+)\s*$", value)
    return int(match.group(1)) if match else None


def cluster_positive_edges(times: list[float], voltages: list[float]) -> list[float]:
    """Return representative times for large positive transition clusters.

    This deliberately estimates periodic source cadence only; it is not used to
    extract reflection amplitudes or arrival times.
    """

    steps = [(times[index + 1], voltages[index + 1] - voltages[index]) for index in range(len(times) - 1)]
    largest = max((step for _, step in steps), default=0.0)
    if largest <= 0:
        return []
    threshold = max(0.010, largest * 0.35)
    candidates = [(time, step) for time, step in steps if step >= threshold]
    if not candidates:
        return []

    clusters: list[list[tuple[float, float]]] = [[candidates[0]]]
    for candidate in candidates[1:]:
        if candidate[0] - clusters[-1][-1][0] <= 12e-9:
            clusters[-1].append(candidate)
        else:
            clusters.append([candidate])
    return [max(cluster, key=lambda item: item[1])[0] for cluster in clusters]


def estimate_pulse_period(times: list[float], voltages: list[float]) -> float | None:
    edges = cluster_positive_edges(times, voltages)
    candidate_gaps = [
        later - earlier
        for index, earlier in enumerate(edges)
        for later in edges[index + 1 :]
        if 300e-9 <= later - earlier <= 500e-9
    ]
    if len(candidate_gaps) < 2:
        return None
    return statistics.median(candidate_gaps)


def cycle_repeatability(
    times: list[float], voltages: list[float], period_s: float | None
) -> tuple[float | None, float | None]:
    """Compare a waveform to itself one estimated pulse period later.

    The correlation is insensitive to a constant DC shift between cycles.  The
    RMSE is calculated after removing that shift, so it describes shape
    repeatability rather than baseline placement.
    """

    if period_s is None or len(times) < 3:
        return None, None
    sample_interval = statistics.median(later - earlier for earlier, later in zip(times, times[1:]))
    shift = round(period_s / sample_interval)
    if shift < 1 or shift >= len(voltages):
        return None, None
    earlier = voltages[:-shift]
    later = voltages[shift:]
    mean_earlier = statistics.mean(earlier)
    mean_later = statistics.mean(later)
    centered_earlier = [value - mean_earlier for value in earlier]
    centered_later = [value - mean_later for value in later]
    denominator = math.sqrt(
        sum(value * value for value in centered_earlier)
        * sum(value * value for value in centered_later)
    )
    correlation = (
        sum(first * second for first, second in zip(centered_earlier, centered_later)) / denominator
        if denominator
        else None
    )
    differences = [second - first for first, second in zip(earlier, later)]
    mean_difference = statistics.mean(differences)
    rmse_v = math.sqrt(statistics.mean((value - mean_difference) ** 2 for value in differences))
    return correlation, rmse_v


def parse_waveform(path: Path, configuration: Configuration | None, is_wrong: bool) -> Waveform:
    report = Waveform(path=path, configuration=configuration, is_wrong=is_wrong)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as error:
        report.errors.append(f"cannot read CSV: {error}")
        return report

    header_indexes = [index for index, row in enumerate(rows) if [item.strip() for item in row[:2]] == ["Second", "Value"]]
    if len(header_indexes) != 1:
        report.errors.append(f"expected exactly one 'Second,Value' header; found {len(header_indexes)}")
        return report

    data_start = header_indexes[0] + 1
    metadata = {
        row[0].strip(): row[1].strip()
        for row in rows[:data_start]
        if len(row) >= 2 and row[0].strip() not in {"Second", ""}
    }
    report.record_length = parse_record_length(metadata.get("Record Length", ""))
    try:
        report.sample_interval_s = float(metadata["Sample Interval"])
    except (KeyError, ValueError):
        report.errors.append("missing or invalid Sample Interval")
    report.vertical_units = metadata.get("Vertical Units")
    report.horizontal_units = metadata.get("Horizontal Units")
    report.model = metadata.get("Model")
    report.source = metadata.get("Source")

    if report.vertical_units != "V":
        report.errors.append(f"expected Vertical Units 'V'; found {report.vertical_units!r}")
    if report.horizontal_units != "s":
        report.errors.append(f"expected Horizontal Units 's'; found {report.horizontal_units!r}")

    times: list[float] = []
    voltages: list[float] = []
    for row_number, row in enumerate(rows[data_start:], start=data_start + 1):
        if len(row) != 2:
            report.errors.append(f"row {row_number} has {len(row)} fields instead of 2")
            continue
        try:
            time_s, voltage_v = float(row[0]), float(row[1])
        except ValueError:
            report.errors.append(f"row {row_number} has non-numeric time or voltage")
            continue
        if not math.isfinite(time_s) or not math.isfinite(voltage_v):
            report.errors.append(f"row {row_number} has non-finite time or voltage")
            continue
        times.append(time_s)
        voltages.append(voltage_v)

    report.samples = len(times)
    if report.samples < 2:
        report.errors.append("fewer than two numeric samples")
        return report
    report.t_start_s, report.t_end_s = times[0], times[-1]
    if report.record_length is not None and report.record_length != report.samples:
        report.errors.append(f"Record Length declares {report.record_length}, but {report.samples} samples were parsed")
    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        report.errors.append("time values are not strictly increasing")
    intervals = [later - earlier for earlier, later in zip(times, times[1:])]
    reference_interval = statistics.median(intervals)
    tolerance = max(abs(reference_interval) * 1e-6, 1e-15)
    if max(intervals) - min(intervals) > tolerance:
        report.errors.append("time interval is not uniform")
    if report.sample_interval_s is not None and abs(report.sample_interval_s - reference_interval) > tolerance:
        report.errors.append(
            f"Sample Interval declares {report.sample_interval_s:g} s, but data interval is {reference_interval:g} s"
        )
    report.pulse_period_s = estimate_pulse_period(times, voltages)
    if report.pulse_period_s is None:
        report.warnings.append("could not estimate repeated-pulse cadence from positive edges")
    else:
        report.repeat_correlation, report.repeat_rmse_v = cycle_repeatability(times, voltages, report.pulse_period_s)
        if report.repeat_correlation is None or report.repeat_rmse_v is None:
            report.warnings.append("could not compare adjacent pulse cycles")
    return report


def read_expected_matrix(path: Path) -> tuple[set[Configuration], list[str]]:
    errors: list[str] = []
    expected: set[Configuration] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as error:
        return expected, [f"cannot read expected matrix {path}: {error}"]
    if not rows or not rows[0] or rows[0][0].strip().lower() != "cable group":
        return expected, ["data_status.csv must begin with a 'Cable group' column"]
    try:
        loads = [normalize_load(item) for item in rows[0][1:]]
    except ValueError as error:
        return expected, [str(error)]
    if len(loads) != len(set(loads)):
        errors.append("data_status.csv contains duplicate load columns")
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not row[0].strip():
            continue
        match = GROUP_NAME.fullmatch(row[0].strip())
        if not match:
            errors.append(f"data_status.csv row {row_number} has invalid cable group {row[0]!r}")
            continue
        for load in loads:
            expected.add(Configuration(match.group("cable").upper(), int(match.group("length")), load))
    return expected, errors


def load_manifest(path: Path, valid_reports: Iterable[Waveform]) -> tuple[list[str], list[str]]:
    """Return errors and warnings from a user-confirmed acquisition manifest."""

    errors: list[str] = []
    warnings: list[str] = []
    required = {"file", "cable", "length_m", "load", "acquisition_verified"}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or [])
            if not required.issubset(headers):
                return [f"manifest lacks required columns: {', '.join(sorted(required - headers))}"], warnings
            entries = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        return [f"cannot read manifest: {error}"], warnings

    by_file = {entry["file"].strip().lower(): entry for entry in entries if entry.get("file")}
    if len(by_file) != len(entries):
        errors.append("manifest contains blank or duplicate file rows")
    for report in valid_reports:
        entry = by_file.get(report.path.name.lower())
        if entry is None:
            errors.append(f"manifest has no row for {report.path.name}")
            continue
        assert report.configuration is not None
        try:
            manifest_config = Configuration(
                entry["cable"].strip().upper(), int(entry["length_m"]), normalize_load(entry["load"])
            )
        except (ValueError, KeyError) as error:
            errors.append(f"manifest row for {report.path.name} is invalid: {error}")
            continue
        if manifest_config != report.configuration:
            errors.append(
                f"manifest/name mismatch for {report.path.name}: manifest says {manifest_config.label()}, "
                f"filename says {report.configuration.label()}"
            )
        if entry["acquisition_verified"].strip().lower() not in YES:
            warnings.append(f"physical setup not yet confirmed for {report.path.name}")
    return errors, warnings


def write_manifest_template(path: Path, reports: Iterable[Waveform]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "file",
                "cable",
                "length_m",
                "load",
                "acquisition_verified",
                "resistance_measured_ohm",
                "notes",
            ]
        )
        for report in sorted(reports, key=lambda item: item.path.name.lower()):
            assert report.configuration is not None
            config = report.configuration
            writer.writerow([report.path.name, config.cable, config.length_m, config.load, "", "", ""])


def print_list(title: str, values: Iterable[str], indent: str = "  ") -> None:
    items = list(values)
    print(f"{title}: {len(items)}")
    for item in items:
        print(f"{indent}{item}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent, help="directory containing raw waveform CSVs")
    parser.add_argument("--status", type=Path, default=None, help="expected configuration matrix (default: ROOT/data_status.csv)")
    parser.add_argument("--manifest", type=Path, help="user-confirmed acquisition manifest")
    parser.add_argument("--require-manifest", action="store_true", help="fail if physical setup confirmation is absent or incomplete")
    parser.add_argument("--write-manifest-template", type=Path, help="write a manifest template for valid, named waveforms")
    parser.add_argument("--allow-incomplete", action="store_true", help="return success despite missing expected configurations")
    args = parser.parse_args()

    root = args.root.resolve()
    status_path = (args.status or root / "data_status.csv").resolve()
    expected, matrix_errors = read_expected_matrix(status_path)
    structural_errors = list(matrix_errors)
    warnings: list[str] = []

    reports: list[Waveform] = []
    unrecognised_csv: list[str] = []
    direct_path = root / "DIRECT-CONNECTION.csv"
    for path in sorted(root.glob("*.csv"), key=lambda item: item.name.lower()):
        if path.name.lower() in {"data_status.csv", "data_manifest.csv"}:
            continue
        if path.name.lower() == direct_path.name.lower():
            reports.append(parse_waveform(path, None, False))
            continue
        configuration, is_wrong = parse_configuration(path.name)
        if configuration is None:
            unrecognised_csv.append(path.name)
            continue
        reports.append(parse_waveform(path, configuration, is_wrong))

    named = [report for report in reports if report.configuration is not None]
    valid_named = [report for report in named if not report.is_wrong]
    wrong_named = [report for report in named if report.is_wrong]
    for report in reports:
        structural_errors.extend(f"{report.path.name}: {error}" for error in report.errors)
        warnings.extend(f"{report.path.name}: {warning}" for warning in report.warnings)

    duplicates: list[str] = []
    seen: dict[Configuration, Waveform] = {}
    for report in valid_named:
        assert report.configuration is not None
        previous = seen.get(report.configuration)
        if previous is not None:
            duplicates.append(
                f"{report.configuration.label()}: {previous.path.name} and {report.path.name}"
            )
        else:
            seen[report.configuration] = report
    structural_errors.extend(f"duplicate valid configuration: {item}" for item in duplicates)

    found_core = set(seen) & expected
    missing = sorted(expected - found_core)
    pilot = sorted(set(seen) - expected)
    excluded_expected = sorted(
        report.configuration for report in wrong_named if report.configuration is not None and report.configuration in expected
    )

    manifest_errors: list[str] = []
    manifest_warnings: list[str] = []
    if args.manifest:
        manifest_errors, manifest_warnings = load_manifest(args.manifest.resolve(), valid_named)
        structural_errors.extend(manifest_errors)
        warnings.extend(manifest_warnings)
        if args.require_manifest:
            structural_errors.extend(
                warning.replace("physical setup not yet confirmed", "required physical setup confirmation is absent")
                for warning in manifest_warnings
            )
    elif args.require_manifest:
        structural_errors.append("--require-manifest was set, but no manifest was supplied")

    if args.write_manifest_template:
        output = args.write_manifest_template.resolve()
        write_manifest_template(output, valid_named)
        print(f"Wrote manifest template: {output}")

    print("Waveform data verification")
    print(f"Root: {root}")
    print(f"Expected matrix: {len(expected)} configurations from {status_path.name}")
    print(f"Named waveform files: {len(named)} ({len(valid_named)} valid names, {len(wrong_named)} explicitly excluded)")
    print(f"Direct-reference files: {sum(report.configuration is None for report in reports)}")
    print(f"Structurally valid CSVs: {sum(report.structural_ok for report in reports)}/{len(reports)}")
    if unrecognised_csv:
        print_list("Unrecognised root CSV files", unrecognised_csv)
    print(f"Core coverage: {len(found_core)}/{len(expected)}")
    print_list("Missing expected configurations", (item.label() for item in missing))
    print_list("Explicitly excluded expected configurations", (item.label() for item in excluded_expected))
    print_list("Named pilot configurations outside data_status.csv", (item.label() for item in pilot))

    cadence = [report.pulse_period_s for report in reports if report.pulse_period_s is not None]
    if cadence:
        median_period = statistics.median(cadence)
        print(
            "Repeated-pulse cadence: "
            f"estimated for {len(cadence)}/{len(reports)} files; "
            f"median {median_period * 1e9:.2f} ns ({1 / median_period / 1e6:.3f} MHz)"
        )
    else:
        warnings.append("no repeated-pulse cadence could be estimated")
    correlations = [report.repeat_correlation for report in reports if report.repeat_correlation is not None]
    rmses = [report.repeat_rmse_v for report in reports if report.repeat_rmse_v is not None]
    if correlations and rmses:
        repeat_reports = [report for report in reports if report.repeat_correlation is not None and report.repeat_rmse_v is not None]
        least_repeatable = min(repeat_reports, key=lambda report: report.repeat_correlation or -math.inf)
        print(
            "Adjacent-cycle consistency: "
            f"correlation range {min(correlations):.6f} to {max(correlations):.6f}; "
            f"median {statistics.median(correlations):.6f}; "
            f"median shape RMSE {statistics.median(rmses):.5f} V"
        )
        print(
            "Lowest adjacent-cycle correlation: "
            f"{least_repeatable.path.name} ({least_repeatable.repeat_correlation:.6f}; "
            f"shape RMSE {least_repeatable.repeat_rmse_v:.5f} V)"
        )

    if structural_errors:
        print_list("ERRORS", structural_errors)
    if warnings:
        print_list("WARNINGS", warnings)
    print(
        "Name-verification boundary: the scope CSV metadata does not contain cable, length, or load. "
        "This check verifies syntax, uniqueness, coverage, and structural integrity; physical setup confirmation requires a manifest."
    )

    if structural_errors:
        return 2
    if missing and not args.allow_incomplete:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
