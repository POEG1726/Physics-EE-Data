# Waveform analysis summary

## Scope

The formal analysis uses RG58 at 4 m, 5 m, and 10 m and RG179 at 5 m, 10 m, and 15 m, with the eleven loads listed in `data_status.csv`. RG58 15 m pilot traces and every `*-WRONG.csv` file are excluded. Raw waveform CSVs are read-only.

## Extraction rule

For every pulse cycle, the baseline is the median voltage from 90 ns to 35 ns before the incident peak. Incident and reflected amplitudes are measured relative to that baseline. The incident and reflected arrival times are obtained by linear interpolation at 50% of their respective amplitudes. Each cable-length group's OPEN trace supplies one fixed reflection-delay anchor; every other load is measured in the same +/-15 ns window around that anchor. A separate 30-180 ns broad-window check is applied only to strong theoretical reflections (|Gamma| >= 0.5) to detect delay/length inconsistencies. Repeated cycles quantify within-record repeatability but are not independent experimental repeats.

## Calibration

- Direct-connection extrema: -1.0146 V to 0.9927 V; Vpp = 2.0073 V.
- 50% pulse width from the stable high- and low-level midpoint: 20.007 +/- 0.017 ns across detected cycles (range 19.989-20.030 ns), supporting a nominal 20 ns setting.
- Pulse period: 400.000 ns, corresponding to 2.500000 MHz.
- Sampling interval: 0.500 ns.

## Reflection-coefficient fits

The fit is Gamma_exp = k Gamma_theory with the intercept constrained to zero. The exactly matched load and any QC-failed trace are excluded.

| Cable | Length / m | n | k | 95% CI | R2 | RMSE |
|---|---:|---:|---:|---:|---:|---:|
| RG58 | 4 | 10 | 0.959 | 0.942 to 0.975 | 0.9995 | 0.0147 |
| RG58 | 5 | 10 | 0.944 | 0.929 to 0.959 | 0.9996 | 0.0130 |
| RG58 | 10 | 10 | 0.892 | 0.883 to 0.902 | 0.9998 | 0.0084 |
| RG179 | 5 | 10 | 0.714 | 0.707 to 0.721 | 0.9998 | 0.0064 |
| RG179 | 10 | 10 | 0.662 | 0.641 to 0.683 | 0.9982 | 0.0186 |
| RG179 | 15 | 10 | 0.597 | 0.584 to 0.610 | 0.9991 | 0.0116 |

All six matched-load residuals are small (maximum |Gamma_exp| = 0.025), consistent with the predicted near-zero reflection. The fitted scale k falls with length, which is consistent with attenuation over the outward and return paths. At the directly comparable 5 m and 10 m lengths, RG179 has a smaller measured reflection scale than RG58. This is an empirical system response; it should not be attributed to characteristic impedance alone because the cables differ in construction and attenuation.

## Propagation-delay fits

Each length point is the median of all resolvable non-matched loads that passed QC. The linear model is Delta t = a + bL, and propagation speed is v = 2/b.

| Cable | Group delays / ns | b / ns m^-1 | a / ns | R2 | v / m s^-1 | v/c |
|---|---|---:|---:|---:|---:|---:|
| RG58 | 4 m: 41.822, 5 m: 52.131, 10 m: 103.038 | 10.196 | 1.091 | 1.00000 | 1.9616e+08 | 0.654 |
| RG179 | 5 m: 48.814, 10 m: 96.216, 15 m: 143.127 | 9.431 | 1.739 | 0.99999 | 2.1206e+08 | 0.707 |

Only three lengths are available for each cable, leaving one residual degree of freedom. The very high R2 values demonstrate consistency with a linear relation but do not by themselves establish a precise uncertainty on velocity. Cable-length uncertainty was not recorded and must not be invented.

## Data-quality result

No cable-length/load configuration was rejected by the automated delay-consistency check. The formal RG179 15 m short trace gives a round-trip delay of 143.069 ns and Gamma_exp = -0.5917, consistent with the rest of the 15 m group.

## Files

- `per_cycle.csv`: every extracted pulse cycle and its QC status.
- `processed_results.csv`: one row per formal cable-length-load configuration.
- `group_delays.csv`: delay aggregation across valid loads.
- `group_fits.csv`: reflection and propagation fit coefficients.
- `name_qc.csv`: delay and waveform-similarity evidence for any physical-label outlier.
- `figure_gamma_vs_theory.png`: reflection-response figure.
- `figure_delay_vs_length.png`: propagation-delay figure.
