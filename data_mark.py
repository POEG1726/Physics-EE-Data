from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent
OUT_CSV = DATA_DIR / "data_status.csv"

CABLE_GROUPS = [
    ("RG58 4m", "rg58", "4m"),
    ("RG58 5m", "rg58", "5m"),
    ("RG58 10m", "rg58", "10m"),
    ("RG179 5m", "rg179", "5m"),
    ("RG179 10m", "rg179", "10m"),
    ("RG179 15m", "rg179", "15m"),
]

IMPEDANCES = ["6", "12", "22", "33", "50", "75", "120", "200", "470", "open", "short"]


def normalize_name(path: Path) -> str:
    return path.stem.lower()


def parse_waveform_filename(path: Path) -> tuple[str, str, str] | None:
    """
    Expected format examples:
      RG58-10M-12OHM.csv
      rg179-15m-12ohm.csv
      RG58-4M-open.csv
      RG58-10M-short.csv
    """
    name = normalize_name(path)
    match = re.fullmatch(r"(rg58|rg179)-(\d+m)-(open|short|\d+)(?:ohm)?", name)
    if not match:
        return None

    cable, length, impedance = match.groups()
    return cable, length, impedance


def build_status(data_dir: Path) -> dict[tuple[str, str], list[Path]]:
    status: dict[tuple[str, str], list[Path]] = {}
    valid_groups = {(cable, length) for _, cable, length in CABLE_GROUPS}

    for csv_file in sorted(data_dir.glob("*.csv")):
        parsed = parse_waveform_filename(csv_file)
        if parsed is None:
            continue

        cable, length, impedance = parsed
        if (cable, length) not in valid_groups:
            continue
        if impedance not in IMPEDANCES:
            continue

        status.setdefault((f"{cable}-{length}", impedance), []).append(csv_file)

    return status


def write_status_csv(data_dir: Path, out_csv: Path) -> None:
    status = build_status(data_dir)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Cable group", *IMPEDANCES])

        for label, cable, length in CABLE_GROUPS:
            group_key = f"{cable}-{length}"
            row = [label]
            for impedance in IMPEDANCES:
                row.append("X" if status.get((group_key, impedance)) else "")
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate waveform data collection status CSV.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out", type=Path, default=OUT_CSV)
    args = parser.parse_args()

    write_status_csv(args.data_dir, args.out)
    print(args.out)


if __name__ == "__main__":
    main()
