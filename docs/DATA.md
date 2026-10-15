# 数据字典与处理方法

## 原始波形

根目录的 71 个波形 CSV 为 Siglent 导出。`Second,Value` 之前为元数据，之后两列分别为时间 / s 和电压 / V。`Serial Number` 值替换为 `REDACTED`；型号、软件版本、通道、采样间隔、幅度刻度等非唯一标识元数据保留。数值采样行未改写、重采样或插值。

`data_manifest.csv` 包含文件名、用途、采样数、采样块 SHA-256。哈希对象为 `Second,Value` 后全部行，用 LF 连接并以 LF 结束；因此不受文本换行平台差异影响，不覆盖已脱敏的头部。

| role | 数量 | 用途 |
|---|---:|---|
| formal | 66 | 正式矩阵 |
| calibration | 1 | DIRECT-CONNECTION.csv 直连校准 |
| pilot | 2 | RG58 15 m 试测，不参与正式拟合 |
| excluded_superseded | 2 | WRONG 标签的旧记录，不参与默认可视化及正式拟合 |

`data_status.csv` 是预期正式矩阵，而不是物理接线证明；`data_mark.py` 可从现存文件重新生成覆盖表。仅凭示波器元数据无法确认负载或电缆标签。

## 固定提取规则

以每个入射峰前 −90…−35 ns 的电压中位数为 baseline；入射和反射幅度都相对此 baseline 计算。时刻由各自幅度的 50% 线性插值交点确定。每组开路波形提供统一的反射延迟锚点，其他负载使用该锚点 ±15 ns 窗口。对强理论反射（|Γ_th| ≥ 0.5）另作 30…180 ns 宽窗口检查，识别明显的延迟/长度不一致。

Γ_th = (R_L − Z₀)/(R_L + Z₀)，开路取 +1、短路取 −1。Γ_exp 是每周期反射幅度与入射幅度的比；每配置报告这些比值的均值和样本标准差。Δt 报告各有效周期的中位数，离散程度另用样本标准差表示。

## 正式处理结果

### analysis/processed_results.csv（66 行）

| 字段 | 含义与单位 |
|---|---|
| file, cable, length_m, load | 来源文件、电缆、标称长度 / m、负载标签 |
| load_ohm, z0_ohm | 负载电阻与标称特征阻抗 / Ω；开路用 inf |
| gamma_theory, gamma_exp_mean, gamma_exp_sd | 理论值、实测周期比值均值及周期内样本 SD，无量纲 |
| cycles | 本记录提取的脉冲周期数 |
| incident_amplitude_mean_v, reflection_amplitude_mean_v | baseline 校正后的幅度均值 / V |
| gamma_residual | Γ_exp_mean − Γ_th（不是衰减拟合残差） |
| fixed_delay_ns_median | 固定窗口得到的中位延迟 / ns，可能仅作诊断 |
| delay_ns_median, delay_cycle_sd_ns | 正式有效延迟中位数及同记录周期样本 SD / ns |
| broad_delay_ns_median, broad_gamma_exp_median | 宽窗口诊断指标 |
| anchor_delay_ns | 所属组的开路延迟锚点 / ns |
| qc_status | ok 或 matched_no_timing；被拒记录若存在会另有标记 |
| usable_for_gamma_fit, usable_for_delay_fit | 是否参与相应拟合 |
| note | 数据解释或排除原因 |

### 其他表

- `per_cycle.csv`：354 行；每周期 baseline / V、入射/反射峰值和 50% 时刻 / s、幅度 / V、Γ、延迟 / ns 和 QC。
- `group_delays.csv`：6 行；每组有效负载数、延迟中位数、不同负载间的样本 SD、最小/最大延迟，单位 ns。
- `group_fits.csv`：8 行；6 个反射拟合与 2 个传播拟合。包含样本量、斜率/标准误/95% CI、截距、centered R²、RMSE、速度及衰减代理。
- `calibration.csv`：1 行；直连极值、Vpp / V、脉宽均值/SD/范围 / ns、周期 / ns、频率 / MHz、采样间隔 / ns。
- `open_delay_anchors.csv`：6 行；每组开路延迟锚点、其周期 SD / ns 及周期数。
- `name_qc.csv`：潜在物理标签异常的诊断表；本发布版只有表头，表示自动检查没有新增标记，不能证明所有物理标签。
- `figures/effective_attenuation.csv`：2 行；对 ln(k) 与 L 作线性拟合，`s = 2` 为往返路径因子，`m_per_m` 为 ln(k) 对长度的拟合斜率 / m⁻¹，`intercept` 为截距，`alpha_eff_per_m = -m_per_m/s`。

空白数值字段表示不可用，不应当作零。六个匹配负载保留残余 Γ，但正式延迟及其 SD 为 N/A。

## 拟合与误差棒

反射拟合为 Γ_exp = k Γ_th，固定零截距，排除匹配负载，每组 10 个配置。k = Σ(xy)/Σ(x²)。R² 使用 centered 定义：1 − SSE/Σ(y−ȳ)²。95% CI 使用残差估计的斜率标准误和 9 自由度 t 临界值 2.262。

传播拟合为 Δt = a + bL，各点为同组有效非匹配负载延迟的中位数；b 单位 ns/m，v = 2×10⁹/b，单位 m/s。每电缆只有三个长度，残差自由度为 1。`attenuation_proxy_db_per_m = -20 log10(k)/(2L)` 是系统响应代理。

反射图误差棒是同记录周期 Γ 的样本 SD；ln(k) 图使用 k 的 95% CI 经对数变换的上下界；延迟图使用不同负载间延迟的样本 SD。长度未记录测量误差，因此无横向误差棒。不同层次的 SD 和 CI 不能混同为统一的测量不确定度预算。

## 可视化与对齐导出

`visualize/summary.csv` 的 69 行覆盖正式、直连、试测记录；其峰值和 baseline 是浏览工具的启发式统计，不替代正式算法。HTML 嵌入每条波形完整的 t / ns 和 v / V 数组。

`alignment.csv` 保存 11 条 RG58 10 m 波形的 reference、显示窗口、baseline mode、全局及单条时间偏移 / ns、电压偏移 / V、baseline / V。`corrected_data.csv` 的 7,711 行保存 `trace_id,file,t_raw_ns,v_raw,baseline_v,t_shifted_ns,v_shifted`。这些是人工浏览/对齐的导出，不是新的实验重复。

## 设置记录的证据范围

`waveform.txt` 是保留的仪器设置笔记，包含 1.0 Vpp 显示值和 19.4 ns 脉宽；直连波形测得约 2.007 Vpp 和 20.007 ns。不同显示负载约定、设置记录和实测值应分开理解。CSV 本身不能证明函数发生器所有菜单设置，不能据此强行消除笔记与测量的差异。
