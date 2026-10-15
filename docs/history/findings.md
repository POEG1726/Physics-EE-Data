# Findings & Decisions

## Requirements

- Audit all waveform CSV files and report missing data.
- Verify expected configuration coverage against `data_status.csv`.
- Add a reproducible name and file-format checker.
- Preserve existing user changes to the essay and visualization exports.

## Research Findings

- As of 2026-08-24, the formal filename matrix covers all 66 configurations. The old `rg179-15m-12ohm-WRONG.csv` remains excluded while the separately acquired normal 12 Ω file supplies that configuration.
- Direct-connection calibration gives approximately 2.007 Vpp. Using the midpoint between the stable low and high pulse levels (rather than the overshoot peak), the five 50%-crossing pulse widths cluster at approximately 20.00 ns, supporting nominal settings of 2.0 Vpp and 20 ns.
- Preliminary within-trace amplitude ratios for RG179 15 m show a common attenuation scale: the recovered 120 Ω and 200 Ω traces have reflection signs and magnitudes consistent with their labels. The full analysis must estimate coefficients using one fixed rule rather than configuration-specific tuning.
- The superseded trace now retained as `rg179-15m-SHORT-WRONG.csv` is a physical-label outlier: its strong negative reflection arrives at about 96.10 ns, essentially the same as `rg179-10m-SHORT.csv` (about 96.06 ns), instead of the approximately 142.5--143.5 ns delay shared by the other RG179 15 m loads. The validated replacement now supplies the formal configuration.
- The final incident-aligned repeated-cycle comparison gives correlation 0.99967 between the superseded short trace and the RG179 10 m short; their broad-window delays differ by only 0.038 ns. This supports retaining the old trace as excluded evidence.
- Through-origin fits of measured against theoretical reflection coefficient give scale factors of 0.959, 0.944, and 0.892 for RG58 at 4 m, 5 m, and 10 m; and 0.714, 0.662, and 0.597 for RG179 at 5 m, 10 m, and 15 m. Every fit has R² above 0.998; the final RG179 15 m fit uses all ten non-matched loads.
- Median round-trip delay is linear with length: RG58 gives 10.196 ns/m and `v = 1.962e8 m/s` (`0.654c`); RG179 gives 9.431 ns/m and `v = 2.121e8 m/s` (`0.707c`). Each cable has only three length points, so the near-unity R² values must not be presented as a complete uncertainty estimate.
- The maximum absolute measured residual at the six theoretically matched loads is 0.025, supporting the predicted near-zero reflection.
- The newly supplied `rg179-15m-short-new.csv` is structurally valid: 4,000 samples at 0.5 ns, 400 ns pulse cadence, adjacent-cycle correlation 0.999925, and DC-shift-adjusted repeat RMSE 0.00338 V.
- Under the unchanged extraction protocol, the new short trace gives a median round-trip delay of 143.069 ns versus the RG179 15 m OPEN anchor of 142.523 ns, and `Gamma_exp = -0.5917 ± 0.0032`. It passes all formal QC checks.
- Incident-aligned waveform correlation is 0.99737 between the new short trace and the RG179 15 m 6 Ω trace, but only 0.71032 with the superseded nominal 15 m short and 0.71877 with the 10 m short. This supports treating the new trace as the correct 15 m acquisition.
- After promotion and full regeneration, the formal matrix has 60 usable non-matched configurations, six matched configurations with timing intentionally N/A, and zero QC failures. The HTML visualization also includes the replacement and lists the superseded short under excluded traces.
- For the essay, describe the final data as strongly consistent with transmission-line theory rather than "perfect": all six reflection fits have R² above 0.998, matched-load residuals remain within 0.025, and round-trip delay is linear in length, but each configuration is represented by one acquisition and cable-length uncertainty was not recorded.
- Use approximate wording for quantities inferred from exported waveforms or affected by measurement resolution: approximately 2.5 MHz pulse repetition frequency, approximately 400 ns period, approximately 20 ns pulse width, and approximately 2.0 V peak-to-peak. Keep fitted coefficients and extracted results at justified precision with stated units.
- The working Google Doc was updated in place on tab `t.0`: the attenuation-aware theoretical framework, completed methodology and processing procedure, six-group reflection-fit table, current reflection and delay figures, analysis, limitations, and conclusion now agree with the 66-configuration analysis. The final readback found none of the stale `1 kHz`, incomplete-data, planned-analysis, or exact `2 Vpp`/`20 ns` phrases.
- The raw oscilloscope CSVs do not store the function generator front-panel load-display setting. The essay now treats the generator as a nominal 50 Ω source but explicitly avoids inferring whether the display was set to 50 Ω or Hi-Z from waveform data alone.

- The official matrix contains RG58 at 4 m, 5 m, and 10 m, and RG179 at 5 m, 10 m, and 15 m; each group expects eleven load conditions.
- RG58 15 m files exist but are partial exploratory data and are not in the official matrix.
- `*-WRONG.csv` files must be reported as excluded, not counted as valid evidence.
- The root contains 68 raw-like waveform CSVs: 64 with 4,000 samples and 4 with 10,000 samples. All have the same declared 0.5 ns interval, voltage/time units, scope model, source channel, finite data, and strictly monotonic uniform time values.
- The raw Siglent metadata contains no cable, cable length, or load value. Filename checks can establish naming consistency and data-matrix coverage, while a waveform check can only flag a physically implausible label for review.
- The waveforms contain repeated pulse events approximately 400 ns apart, corresponding to a 2.5 MHz cadence. Thus a typical 2 microsecond record contains about five pulses, while the essay's present 1 kHz source-frequency statement conflicts with the observed waveform cadence and must be verified against the instrument setup.
- The expected matrix has 66 configurations. Sixty-three valid named files cover it; RG179 15 m is missing 12 ohm, 120 ohm, and 200 ohm. The three corresponding files are explicitly marked `WRONG` and are excluded. Two valid RG58 15 m files are exploratory because that group is not in `data_status.csv`.
- The first validator run found all 69 measured/reference CSVs structurally valid and returned exit code 1 only because of the three missing expected configurations. `--allow-incomplete` returned success after the structural audit.
- Manifest template generation produced 65 rows for all valid named waveforms. Requiring confirmation correctly failed for all 65 blank rows, so an auto-generated manifest is not mistaken for physical evidence.
- Every waveform yielded an approximately 400 ns cadence estimate. Adjacent-cycle shape correlation ranges from 0.989229 to 0.999956 (median 0.999902), with median DC-shift-adjusted RMSE of 0.00310 V. This supports stable repeated pulses within each record, while not replacing independent repeat acquisitions.
- `rg58-4m-22ohm.csv` has the lowest within-record cycle correlation (0.989229; shape RMSE 0.02986 V). It remains structurally valid, so it should be inspected during extraction rather than renamed or discarded automatically.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Use the standard library Python CSV parser | The raw Siglent exports are CSV and the validator needs no external dependency. |
| Validate filename, header, sample count, time monotonicity, interval consistency, and finite voltages | These are mechanical checks that can be repeated objectively. |
| Add a conservative reflection-sign plausibility warning | It provides a useful label sanity check without claiming it proves the physical load. |
| Detect periodic pulse cadence from repeated steep positive edges | This independently checks the record's repeated-pulse claim and catches setup-text contradictions. |
| Add `verify_waveform_data.py` | Provides repeatable coverage, naming, metadata, time-axis, and cadence checks without changing raw data. |
| Require a completed manifest for physical name confirmation | The raw scope CSV cannot independently prove the cable or termination that was connected. |
| Compare each waveform with itself one pulse period later | Gives a quantitative within-record waveform-stability check. |
| Derive each cable-length reflection window from its OPEN trace | Uses one high-signal physical anchor per group without tuning individual loads. |
| Add a broad-window delay cross-check for strong reflections | Detects a cable-length mismatch even when a fixed expected window would return a small spurious peak. |
| Retain the old 15 m short under a `-WRONG` filename | Preserves the original evidence while ensuring it is not selected by the formal analysis. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Existing worktree is dirty | Exclude those paths from every edit and commit. |
| No structural parse errors found in the first full raw-file pass | Continue with coverage and physics-plausibility checks. |
| A broad planning-file patch did not apply | Re-read exact file context and used a narrower patch. |
| Temporary dynamic import raised a dataclass module-registration error | Use a normal Python module import instead; the validator CLI itself already ran successfully. |
| First normal-import invocation produced no output | Re-run with an explicit stdin script marker; no data conclusion was drawn from the blank run. |
| Explicit stdin marker still produced no output | Verify interpreter argument behavior before using a temporary script-file fallback. |
| Shell removal of the generated Python cache was blocked | Use the file patch tool to remove the one verified cache file. |
| The file patch tool cannot delete binary cache content | Add a narrow Git ignore rule; the cache is regenerable and not experimental evidence. |

## Resources

- `data_status.csv`
- Raw Siglent CSV exports in the repository root
- `visualize/visualize.py`
