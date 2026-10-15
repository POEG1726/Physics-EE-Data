"""Check published sample integrity, statistical consistency and privacy.

Uses only the Python standard library. Run from any working directory.
--git-history also checks every reachable blob and commit identity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {'.py', '.ps1', '.md', '.csv', '.html', '.svg', '.drawio', '.txt', '.yml', '.yaml'}
PRIVATE_PATTERNS = [
    re.compile(r'[A-Za-z]:[\\/]+(?:Users|Downloads)[\\/]', re.I),
    re.compile(r'[A-Za-z]:[\\/]+Physics-EE', re.I),
    re.compile(r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b'),
    re.compile(r'\bSDS[A-Z0-9]{8,}\b'),
    re.compile(r'https?://docs\.google\.com/(?:document|spreadsheets|presentation)/d/[A-Za-z0-9_-]+'),
    re.compile(r'\bAIro[A-Za-z0-9_-]{30,}\b'),
    re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})'),
]
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
PUBLIC_EMAIL = 'maintainer@users.noreply.github.com'


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def near(actual: float, expected: float, label: str) -> None:
    check(math.isclose(actual, expected, rel_tol=2e-7, abs_tol=2e-7), f'{label}: {actual} != {expected}')


def sample_block(path: Path) -> bytes:
    lines = path.read_bytes().splitlines()
    start = lines.index(b'Second,Value')
    return b'\n'.join(lines[start + 1:]) + b'\n'


def privacy(text: str, label: str) -> None:
    for pattern in PRIVATE_PATTERNS:
        check(pattern.search(text) is None, f'Potential private identifier in {label} ({pattern.pattern})')
    check(all(value == PUBLIC_EMAIL for value in EMAIL.findall(text)), f'Personal email in {label}')
    for line in text.splitlines():
        if line.startswith('Serial Number,'):
            check(line == 'Serial Number,REDACTED', f'Unredacted instrument identity in {label}')


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def check_data() -> None:
    manifest = read_csv(ROOT / 'data_manifest.csv')
    roles = Counter(row['role'] for row in manifest)
    check(roles == {'formal': 66, 'calibration': 1, 'pilot': 2, 'excluded_superseded': 2}, 'Unexpected raw-data roles')
    names = {row['file'] for row in manifest}
    check(len(names) == len(manifest) == 71, 'Duplicate or missing manifest entries')
    observed = {p.name for p in ROOT.glob('*.csv') if p.name not in {'data_manifest.csv', 'data_status.csv'}}
    check(observed == names, 'Raw files and manifest differ')
    for row in manifest:
        block = sample_block(ROOT / row['file'])
        check(len(block.splitlines()) == int(row['samples']), f"Sample count: {row['file']}")
        check(hashlib.sha256(block).hexdigest() == row['sample_sha256'], f"Sample hash: {row['file']}")
    print('PASS: 71 raw sample blocks match published hashes and roles.')

    results = read_csv(ROOT / 'analysis/processed_results.csv')
    cycles = read_csv(ROOT / 'analysis/per_cycle.csv')
    groups = read_csv(ROOT / 'analysis/group_delays.csv')
    fits = read_csv(ROOT / 'analysis/group_fits.csv')
    check(len(results) == 66 and len(cycles) == 354 and len(groups) == 6 and len(fits) == 8, 'Unexpected table sizes')
    check(Counter(row['qc_status'] for row in results) == {'ok': 60, 'matched_no_timing': 6}, 'Unexpected QC status')
    check({r['file'] for r in results} == {r['file'] for r in manifest if r['role'] == 'formal'}, 'Formal routing differs')
    for row in results:
        selected = [r for r in cycles if r['file'] == row['file']]
        check(len(selected) == int(row['cycles']), f"Cycle count: {row['file']}")
        gamma = [float(r['gamma_exp']) for r in selected]
        near(float(row['gamma_exp_mean']), statistics.mean(gamma), 'Cycle gamma mean')
        near(float(row['gamma_exp_sd']), statistics.stdev(gamma), 'Cycle gamma SD')
        if row['qc_status'] == 'matched_no_timing':
            check(not row['delay_ns_median'] and not row['delay_cycle_sd_ns'], 'Matched delay must be N/A')
            check(row['usable_for_gamma_fit'] == row['usable_for_delay_fit'] == 'FALSE', 'Matched load used in fit')
    for group in groups:
        selected = [r for r in results if (r['cable'], r['length_m']) == (group['cable'], group['length_m']) and r['usable_for_delay_fit'] == 'TRUE']
        values = [float(r['delay_ns_median']) for r in selected]
        check(len(values) == int(group['configurations']) == 10, 'Unexpected load aggregation')
        near(float(group['delay_ns_median']), statistics.median(values), 'Group median')
        near(float(group['delay_between_load_sd_ns']), statistics.stdev(values), 'Between-load SD')
    for fit in fits:
        if fit['fit_type'] == 'gamma_through_origin':
            selected = [r for r in results if (r['cable'], r['length_m']) == (fit['cable'], fit['length_m']) and r['usable_for_gamma_fit'] == 'TRUE']
            x = [float(r['gamma_theory']) for r in selected]
            y = [float(r['gamma_exp_mean']) for r in selected]
            slope = sum(a * b for a, b in zip(x, y)) / sum(a * a for a in x)
            intercept = 0.0
        else:
            selected = [r for r in groups if r['cable'] == fit['cable']]
            x = [float(r['length_m']) for r in selected]
            y = [float(r['delay_ns_median']) for r in selected]
            mx, my = statistics.mean(x), statistics.mean(y)
            slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sum((a - mx) ** 2 for a in x)
            intercept = my - slope * mx
            near(float(fit['velocity_m_s']), 2e9 / slope, 'Propagation velocity')
        residual = sum((b - intercept - slope * a) ** 2 for a, b in zip(x, y))
        r_squared = 1 - residual / sum((b - statistics.mean(y)) ** 2 for b in y)
        near(float(fit['slope']), slope, 'Fit slope')
        near(float(fit['intercept']), intercept, 'Fit intercept')
        near(float(fit['r_squared']), r_squared, 'Centered R squared')
        check(int(fit['n']) == len(selected), 'Fit sample count differs')
    print('PASS: 66 configurations, 354 cycles, QC, aggregation and eight independent fits agree.')

    html = (ROOT / 'visualize/index.html').read_text(encoding='utf-8')
    match = re.search(r'<script id="traceData" type="application/json">(.*?)</script>', html, re.S)
    check(match is not None, 'Missing embedded waveform data')
    embedded = json.loads(match.group(1))
    check(embedded['generatedFrom'] == '.', 'Absolute HTML provenance path')
    traces = embedded['traces']
    check(len(traces) == 69 and sum(len(t['v']) for t in traces) == 300000, 'Unexpected HTML coverage')
    check({t['file'] for t in traces} == {r['file'] for r in manifest if r['role'] != 'excluded_superseded'}, 'HTML trace selection differs')
    for trace in traces:
        raw_rows = list(csv.reader(sample_block(ROOT / trace['file']).decode('utf-8').splitlines()))
        check(len(raw_rows) == len(trace['t']) == len(trace['v']), 'HTML array lengths differ')
        for row, time, value in zip(raw_rows, trace['t'], trace['v']):
            check(abs(float(row[0]) * 1e9 - time) < 2e-8 and abs(float(row[1]) - value) < 1e-9, 'HTML samples differ from CSV')
    check(not re.search(r'(?:src|href)=[\"\']https?://', html), 'HTML has external assets')
    print('PASS: offline HTML contains all 69 approved traces and 300,000 original samples.')

    alignment = read_csv(ROOT / 'visualize/alignment.csv')
    corrected = read_csv(ROOT / 'visualize/corrected_data.csv')
    check(len(alignment) == 11 and len(corrected) == 7711, 'Unexpected alignment export size')
    for transform in alignment:
        selected = [r for r in corrected if r['trace_id'] == transform['trace_id']]
        check(len(selected) == 701, 'Alignment window has missing samples')
        for row in selected:
            near(float(row['t_shifted_ns']), float(row['t_raw_ns']) + float(transform['global_time_shift_ns']) + float(transform['time_shift_ns']), 'Alignment time')
            near(float(row['v_shifted']), float(row['v_raw']) - float(transform['baseline_v']) + float(transform['global_voltage_shift_v']) + float(transform['voltage_shift_v']), 'Alignment voltage')
    print('PASS: eleven saved alignment transforms agree with all 7,711 exported rows.')


def check_privacy(history: bool) -> None:
    count = 0
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(p in {'.git', '.venv', '__pycache__'} for p in path.relative_to(ROOT).parts):
            continue
        check('essay' not in path.relative_to(ROOT).parts, 'Essay content present')
        if path.suffix.lower() in TEXT_EXTENSIONS or path.name.startswith('.git'):
            privacy(path.read_text(encoding='utf-8-sig'), str(path.relative_to(ROOT)))
            count += 1
    print(f'PASS: privacy patterns checked in {count} text files; no essay directory.')
    if history:
        identities = git('log', '--all', '--format=%aN <%aE> | %cN <%cE>').decode('utf-8')
        privacy(identities, 'commit identities')
        for line in identities.splitlines():
            check(line == f'Experiment Maintainer <{PUBLIC_EMAIL}> | Experiment Maintainer <{PUBLIC_EMAIL}>', 'Unexpected commit identity')
        objects = git('rev-list', '--objects', '--all').decode('utf-8').splitlines()
        blob_count = 0
        for entry in objects:
            object_id, _, name = entry.partition(' ')
            check(not name.startswith('essay/'), 'Essay exists in Git history')
            if git('cat-file', '-t', object_id).strip() != b'blob':
                continue
            if Path(name).suffix.lower() in TEXT_EXTENSIONS or Path(name).name.startswith('.git'):
                privacy(git('cat-file', 'blob', object_id).decode('utf-8-sig'), f'Git blob {object_id[:10]}')
                blob_count += 1
        print(f'PASS: all {blob_count} reachable text blobs and all commit identities checked.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--git-history', action='store_true')
    args = parser.parse_args()
    check_data()
    check_privacy(args.git_history)


if __name__ == '__main__':
    main()
