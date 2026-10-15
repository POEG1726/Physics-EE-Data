# 变更记录

## 2026-10-07 — 恢复往返延迟图的误差棒

- 文件：`analysis/render_quantitative_figures.py`、`analysis/figures/delta_t_vs_length.png`
- 目的：在往返延迟图中显示各电缆长度组的测量离散程度。
- 变更：为延迟中位数增加纵向 between-load SD 误差棒，并注明电缆长度没有测量误差、不添加横向误差棒。
- 验证：从已保存的 `group_delays.csv` 和 `group_fits.csv` 渲染新图；目视确认误差棒、拟合线和图注均清晰。
- 提交：`3b6f380`

## 2026-08-30 — 上移完整记录图的 zoom 标注

- 文件：`analysis/render_aligned_full_record_composite.py`、`analysis/figures/rg58_10m_matched_open_short_full_aligned_no_notes.png`
- 目的：使 `zoomed region shown above` 不再落在 highlighted region 内。
- 变更：将该文字移至下方面板上边框外、与 `Complete aligned oscilloscope records` 标题同一水平带并略低几像素；高亮区域和连接线保持不变。
- 验证：运行 `python -m py_compile analysis/render_aligned_full_record_composite.py`；连续两次渲染 PNG SHA-256 均为 `08BEBFD34D091827A89B51C4843FB3CF3550218BCD2D4E9EBC0C852968ABE757`；目视确认文字位于高亮区外且与下方面板标题对齐。
- 提交：`ec5c925`

## 2026-08-30 — 新增完整 aligned 记录与放大区对应图

- 文件：`analysis/render_aligned_full_record_composite.py`、`analysis/figures/rg58_10m_matched_open_short_full_aligned_no_notes.png`
- 目的：满足 Figure 2 同时展示放大 waveform 与完整 acquisition record 的呈现要求。
- 变更：新增双面板无 note 图；上方面板显示 `−100…275 ns` aligned data points，下方面板显示三条经过相同 visualizer offset/baseline 变换的完整原始记录，并以半透明高亮区和连接线指示上方 zoom 的来源。导出区间仍逐点校验后才使用完整记录延伸。
- 验证：运行 `python -m py_compile analysis/render_aligned_full_record_composite.py`；连续两次渲染 PNG SHA-256 均为 `48C131C9CE17F58294B5F739A6C8348438A76729DA083ABEF6B7F29B181AA38C`；目视确认完整 aligned record、highlighted zoom region、连接线和无 note 要求均满足。
- 提交：`d15d7ce`

## 2026-08-30 — 直述波形对齐的非计算用途并简化图 5 图例

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/render_quantitative_figures.py`、`analysis/figures/rg58_10m_matched_open_short_aligned_export.png`、`analysis/figures/rg58_10m_matched_open_short_no_notes.png`、`analysis/figures/rg58_10m_matched_open_short_emphasized_note.png`、`analysis/figures/rg58_10m_matched_open_short_detail_175_250_no_notes.png`、`analysis/figures/rg58_10m_matched_open_short_detail_175_250_emphasized_note.png`、`analysis/figures/delta_t_vs_length.png`
- 目的：使 Figure 2 的 alignment 含义无歧义，并移除 Figure 5 中不再需要的 group-median 图例。
- 变更：Figure 2 bubble 改为 `Visualization-only alignment (not used for Δt calculation) / First peaks aligned at 0 ns`；Figure 5 legend 删除 `group median across resolvable loads`，仅保留 cable-specific fit labels。全部 waveform 版本同步更新。
- 验证：运行 `python -m py_compile analysis/render_aligned_waveform_composite.py analysis/render_quantitative_figures.py`；连续两次渲染 5 个 waveform PNG 与 `delta_t_vs_length.png` 的 SHA-256 均一致；目视确认 Figure 2 无计算歧义，Figure 5 无 group-median legend 项。
- 提交：`0a0c701`

## 2026-08-30 — 明确图 2、图 4 与图 5 的统计和展示角色

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/render_quantitative_figures.py`、`analysis/figures/rg58_10m_matched_open_short_aligned_export.png`、`analysis/figures/rg58_10m_matched_open_short_no_notes.png`、`analysis/figures/rg58_10m_matched_open_short_emphasized_note.png`、`analysis/figures/rg58_10m_matched_open_short_detail_175_250_no_notes.png`、`analysis/figures/rg58_10m_matched_open_short_detail_175_250_emphasized_note.png`、`analysis/figures/ln_k_vs_length.png`、`analysis/figures/delta_t_vs_length.png`
- 目的：防止将 Figure 2 的展示配准误解为 timing calculation，并让 Figure 4、Figure 5 只展示所需的统计信息。
- 变更：Figure 2 的 bubble 改为 `Visualization registration only / First peaks aligned at 0 ns` 并向左上移；Figure 4 note 改为 zero-intercept (k) 拟合斜率及其 log-transformed 95% confidence interval；Figure 5 删除 individual-load 灰点和 between-load SD error bars，仅保留 group-median diamonds 与拟合线。所有 waveform 备选版本同步更新。
- 验证：运行 `python -m py_compile analysis/render_aligned_waveform_composite.py analysis/render_quantitative_figures.py`；连续两次渲染 5 个 waveform PNG、`ln_k_vs_length.png` 和 `delta_t_vs_length.png` 的 SHA-256 均一致；目视确认三项文字、legend、marker 和图例符合要求。
- 提交：`2b468a6`

## 2026-08-30 — 扩展 post-reflection 局部放大范围

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/figures/rg58_10m_matched_open_short_detail_175_250_no_notes.png`、`analysis/figures/rg58_10m_matched_open_short_detail_175_250_emphasized_note.png`
- 目的：在同一 inset 中完整呈现反射后 175–250 ns 的微小结构。
- 变更：渲染器增加 `--detail-window START_NS END_NS` 参数，并新增 `175–250 ns` 局部放大版的无 note 与加粗 note PNG；inset 标题标明其实际时间范围。既有图文件未覆盖。
- 验证：运行 `python -m py_compile analysis/render_aligned_waveform_composite.py`；两种新 PNG 分别连续两次渲染 SHA-256 一致：`2BCD6E1CCE0E86DD4242029EAF8D38E9E9C4D5987FDA60C326C2042DCEB85767` 和 `BD8DEB72337DCB1CBB65EF99412C545FC07484DA82FE334B7F35EE747EE929ED`；目视确认 inset 覆盖 175–250 ns 并保留两种 note 样式。
- 提交：`ab2d225`

## 2026-08-30 — 增加波形图的两种底部说明版本

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/figures/rg58_10m_matched_open_short_no_notes.png`、`analysis/figures/rg58_10m_matched_open_short_emphasized_note.png`
- 目的：提供无 note 和更醒目 note 两种可选成图，同时保留既有主图。
- 变更：渲染脚本增加 `--note-mode`（`standard`、`none`、`emphasized`）；新增无底部说明 PNG，以及 note 为 `All markers are recorded 0.5 ns samples.`、9.5 pt 粗体且小于 x-axis label 的 PNG。
- 验证：运行 `python -m py_compile analysis/render_aligned_waveform_composite.py`；两种 PNG 分别连续两次渲染 SHA-256 一致：`8BCD0ACEA4C5B92A1EE3A6BC7B1FE64B44C1AA1D11D19198D4AADC8D4BDE1159` 和 `B97405F40EE668A8FA286DEB390C5D84720BD7DDAA23EB066FA956ECA35CEC5A`；目视检查无 note 版无底部文本、加粗版 note 清晰且小于 x-axis label。
- 提交：`42d3860`

## 2026-08-30 — 精简对齐波形的底部说明

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/figures/rg58_10m_matched_open_short_aligned_export.png`
- 目的：仅保留图中必要的采样间隔说明。
- 变更：底部 note 改为 `All markers are recorded 0.5 ns samples.`，移除其余处理与显示范围文字。
- 验证：运行 `python -m py_compile analysis/render_aligned_waveform_composite.py`；连续两次渲染 PNG SHA-256 均为 `37300778DD5289448DCB5BC52D1C491913AEB8E9BCC2F90DDA45A1ED9106E79C`。
- 提交：`7679b0a`

## 2026-08-30 — 补入 HTML 导出窗口后的真实波形点

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/figures/rg58_10m_matched_open_short_aligned_export.png`
- 目的：填补横轴 250–275 ns 的空白，且只使用能由原始示波器记录验证的真实采样点。
- 变更：读取原始 Siglent trace，并应用 `visualize\alignment.csv` 保存的 global/trace time offsets、baseline 和 voltage offsets；以 `corrected_data.csv` 的 `−100…250 ns` 701 点为逐点参照，验证通过后加入每条 250–275 ns 的 50 个 0.5 ns 原始点。未重新拟合或插值。
- 验证：三条 trace 的导出区间与重建区间均为 701 点；最大时间差为 `2.84×10⁻¹⁴ ns`（浮点舍入），最大电压差为 `0 V`；连续两次渲染 PNG SHA-256 均为 `C9A415685EA23D7040F6E67F7D02A04366067F312F54557617F3A2188CD3D89A`；目视确认 250–275 ns 已显示连续的实际采样点。
- 提交：`abb1184`

## 2026-08-30 — 扩大对齐波形主图并细化时间网格

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/figures/rg58_10m_matched_open_short_aligned_export.png`
- 目的：减少成图左右视觉留白，使主坐标轴更易阅读，并按指定时间分度呈现完整的比较范围。
- 变更：画布由 `10.0×6.25 in` 加宽至 `11.8×6.25 in`，压缩 subplot 左右边距；横轴显示范围改为 `−100…275 ns`，主刻度间隔改为 `25 ns`。250–275 ns 保留为空白边距，未外推数据。
- 验证：运行 `python -m py_compile analysis/render_aligned_waveform_composite.py`；连续两次渲染 PNG SHA-256 均为 `73418F875CBE8440933B1F527393B3DF657C9C965F41F045EE801280054FA4DA`；目视检查主图面积、25 ns 网格、inset 和各数据点均清晰。
- 提交：`06833c8`

## 2026-08-30 — 调整对齐波形的留白与局部放大位置

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/figures/rg58_10m_matched_open_short_aligned_export.png`
- 目的：避免左上 legend 遮挡入射 pulse，并使 post-reflection 弱小峰的局部放大更紧凑且不遮挡主反射。
- 变更：主图显示范围改为 `−95…255 ns`，以左侧留白为主、右侧只增加少量留白（无样本外推）；将 post-reflection inset 移至右上角，并由主图的 32%×31% 缩小为 27%×26%。
- 验证：运行 `python -m py_compile analysis/render_aligned_waveform_composite.py`；连续两次渲染 PNG SHA-256 均为 `9FFDDC9A93E98204C5298C49C845855BBBB875EE89B921EB11068836F45DD78B`；目视确认 legend 未覆盖入射 peak、inset 未覆盖反射 pulse 且弱小峰仍可辨。
- 提交：`9d20993`

## 2026-08-30 — 以 visualizer 导出数据重绘 RG58 10 m 叠加波形

- 文件：`analysis/render_aligned_waveform_composite.py`、`analysis/figures/rg58_10m_matched_open_short_aligned_export.png`
- 目的：直接采用 HTML visualizer 已保存的 baseline 和 time offset，生成三种负载条件的高对比对齐数据点图，并保留反射后的弱小峰。
- 变更：从 `visualize` 的 `alignment.csv` 和 `corrected_data.csv` 读取三条 corrected trace，使用已导出的 `t_shifted_ns`、`v_shifted` 而不重新估计任何偏移；采用蓝（matched）、橙（open）、洋红（short）曲线，将显示窗口由 fit default 的 `−100…250 ns` 缩短为 `−66.7…250 ns`，并增加 `195…240 ns` 的 post-reflection detail inset。
- 验证：运行 `python -m py_compile analysis/render_aligned_waveform_composite.py`；连续两次运行渲染脚本的 PNG SHA-256 均为 `9006092889D810B9D564CD9DFB95DAEEEA821C291959FBD5F686FC26E89DB68F`；目视检查三条首个 pulse 在 0 ns 对齐、反射极性正确、后续小峰在 inset 中可辨。
- 提交：`34bf5d5`

## 2026-08-30 — 增加 RG58 10 m 对齐叠加波形主图

- 文件：`analysis/render_rg58_10m_waveform_figures.py`、`analysis/figures/rg58_10m_matched_open_short_composite.png`
- 目的：落实三种终端条件使用一张叠加主图的呈现方式，使相同入射条件与随后反射差异能直接比较。
- 变更：将 matched、open、short 的 central-cycle 入射 50% crossing 全部对齐至 0 ns；上方面板叠加 0.5 ns 采样点，显示共用入射 pulse 与约 103 ns 后的近零、正、负反射；下方面板叠加完整记录，并以同一高亮窗口与连接线说明放大来源。
- 验证：运行 `python -m py_compile analysis/render_rg58_10m_waveform_figures.py`；连续两次渲染的 composite PNG SHA-256 一致；目视检查入射 pulse 重合、反射极性、legend、放大窗口和连接线均清晰且不重叠。
- 提交：`85e4cec`

## 2026-08-30 — 渲染 RG58 10 m 原始采样点波形图

- 文件：`analysis/render_rg58_10m_waveform_figures.py`、`analysis/figures/rg58_10m_matched_waveform.png`、`analysis/figures/rg58_10m_open_waveform.png`、`analysis/figures/rg58_10m_short_waveform.png`
- 目的：为 matched、open、short 三种终端条件提供可审阅的原始采样点波形图，清楚显示局部放大区与其在完整记录中的位置。
- 变更：从三个原始 Siglent CSV 与 `per_cycle.csv`、`processed_results.csv` 生成三张两面板 PNG；上方按 central cycle 的 local pre-pulse baseline 显示 0.5 ns 样本点，下方保留完整 acquisition，并以高亮窗口和连接线指向放大区。open/short 标注记录平均 `Γ_exp` 与中位反射延迟；matched 明确不报告反射延迟。
- 验证：运行 `python -m py_compile analysis/render_rg58_10m_waveform_figures.py`；连续两次渲染的三张 PNG SHA-256 一致；目视检查三张图的采样点、放大窗口、连接线、波形极性与文字布局。
- 提交：`d5440e2`

## 2026-08-30 — 填充 Google Docs 原始数据表

- 文件：Google Docs `[private-document-id-redacted]`（`t.0` tab）、`CHANGELOG.md`
- 目的：用完整的正式 66 配置处理结果替换 EE 文档中的空白原始数据表，并使周期内统计量的定义明确。
- 变更：将原 20×8 占位表扩展为 67×8，并填入 `Cable`、`L / m`、`R_L / Ω`、`Γ_th`、`Γ_exp`、`σ_Γ`、`Δt / ns`、`σ_Δt / ns`；在相邻说明中明确两项 σ 为同一波形记录内 pulse cycles 的标准差，且 matched load 的两项 timing 统计为 `N/A`。
- 验证：Docs connector 读回确认目标文档、`t.0` tab 和 67×8 表结构；逐单元格比对 `analysis/processed_results.csv` 的 66 行格式化结果，0 处不一致；6 个 matched-load 行均为 `N/A`；表头均为粗体且占位黄色高亮已清除。
- 提交：`a7aa4dc`

## 2026-08-30 — 新增实验连接示意图

- 文件：`analysis/render_experimental_setup_schematic.py`、`analysis/figures/experimental_setup_schematic.drawio`、`analysis/figures/experimental_setup_schematic.png`
- 目的：以可编辑的 draw.io 图和本地预览清晰记录反射测量连接、时间测量参考平面与 cable length 的定义。
- 变更：绘制 Signal generator（50 Ω source）→ 20 cm RG316 → BNC T-junction → test cable（`L`、`Z₀`）→ `R_L` 的主路径；标出 CH4（1 MΩ）分支、T-junction/test-cable input reference plane、`L` 的测量端点及入射/反射脉冲方向。
- 验证：使用 XML parser 验证原生 `.drawio`；运行渲染脚本与 `python -m py_compile`；连续两次生成的 `.drawio` 与 PNG SHA-256 一致，并目视检查 PNG 布局与标签。
- 提交：`924802f`

## 2026-08-30 — 标注定量图的拟合优度

- 文件：`analysis/render_quantitative_figures.py`、`analysis/figures/gamma_exp_vs_theory.png`、`analysis/figures/ln_k_vs_length.png`、`analysis/figures/delta_t_vs_length.png`
- 目的：让三张定量图直接报告各自线性拟合的 R²，并采用用户指定的 `ln(k) against cable length` 标题。
- 变更：反射系数图的每条长度拟合线、`ln(k)` 图的两条电缆趋势线和延迟图的两条传播拟合线均显示 R²；保留原 `ln(k)` 图底部注释。
- 验证：运行渲染脚本与 `python -m py_compile`；连续两次渲染的 PNG SHA-256 一致；目视检查 R²、标题、图例和底部注释均未重叠。
- 提交：`10a71ba`

## 2026-08-30 — 新增定量分析图

- 文件：`analysis/render_quantitative_figures.py`、`analysis/figures/gamma_exp_vs_theory.png`、`analysis/figures/ln_k_vs_length.png`、`analysis/figures/delta_t_vs_length.png`
- 目的：从已验证的 66 配置处理结果生成三张可用于 EE 的定量图，且不改动原始波形、分析 CSV 或 essay 文档。
- 变更：新增可重复渲染脚本；生成实验/理论反射系数图、`ln(k)` 对电缆长度图，以及往返延迟对电缆长度图。图中明确区分 matched load、同一记录内 pulse-cycle 标准差、95% k 置信区间和跨负载延迟标准差。
- 验证：运行渲染脚本与 `python -m py_compile`；连续两次渲染的三张 PNG SHA-256 一致；逐张目视检查坐标轴、图例、误差棒和无重叠的文字布局。
- 提交：`6b9b8c3`

## 2026-08-24 — 完成 Google Docs essay 的理论、方法与分析更新

- 文件：`task_plan.md`、`findings.md`、`progress.md`
- 目的：记录完整 66 配置数据纳入用户指定 Google Docs essay 后的写作决策、证据边界与验证结果。
- 变更：在原 Google Doc 的 `t.0` tab 中补入衰减理论、修订 methodology 和 data processing、增加 6 组拟合表与两张最新图，并完成 analysis、limitations 和 conclusion；将波形推断量统一写为 approximately，不从 CSV 猜测 function-generator load-display 设置。
- 验证：Google Docs 最终读回确认无 `1 kHz`、缺数据、planned analysis 或过度精确的 `2 Vpp`/`20 ns` 旧表述；确认两个内嵌图像、一个 7×5 结果表及标题样式存在。
- 提交：`219a3e8`

## 2026-08-24 — 纳入替换后的 RG179 15 m short 数据

- 文件：`rg179-15m-SHORT.csv`、`rg179-15m-SHORT-WRONG.csv`
- 目的：以新采集且通过物理一致性检查的 short trace 替换错误的 10 m-like 记录，同时保留原始错误记录供审计。
- 变更：新 trace 接替正式文件名；旧 trace 原内容保留并增加 `-WRONG` 标记。两份文件的 SHA-256 与操作前各自内容一致。
- 文件：`analyze_waveforms.py`、`analysis/analysis_summary.md`、`analysis/per_cycle.csv`、`analysis/processed_results.csv`、`analysis/group_delays.csv`、`analysis/group_fits.csv`、`analysis/name_qc.csv`、`analysis/figure_gamma_vs_theory.png`、`analysis/figure_delay_vs_length.png`
- 目的：把有效的 RG179 15 m short 纳入正式分析并移除过时的 QC rejection。
- 变更：正式 short 得到 143.069 ns 往返延迟和 `Gamma_exp = -0.5917`；RG179 15 m 拟合使用全部 10 个非匹配负载，斜率 0.5971、R² 0.99915；图中仅在存在异常点时显示 QC-excluded 图例。
- 文件：`visualize/index.html`、`visualize/summary.csv`
- 目的：同步交互式波形可视化与正式数据选择。
- 变更：内嵌新的正式 short，并把旧 short 列入 excluded 数据。
- 文件：`task_plan.md`、`findings.md`、`progress.md`
- 目的：记录替换依据、最终结果和验证证据。
- 变更：新增 Phase 8 并更新数据完整性结论为无正式 QC failure。
- 验证：`verify_waveform_data.py` 得到 71/71 CSV 结构有效及正式矩阵 66/66；分析 354 个脉冲周期，状态为 60 `ok`、6 `matched_no_timing`；12 个分析/可视化输出确定性重跑哈希一致；独立断言验证原始文件哈希、配置唯一性、拟合、HTML included/excluded 路由和零 name-QC 记录；目视检查更新后的图。
- 提交：`263ee5a`

## 2026-08-24 — 新增可复现的完整波形分析

- 文件：`analyze_waveforms.py`
- 目的：用统一且可审计的规则分析正式 66 配置数据，同时保持原始示波器 CSV 只读。
- 变更：新增局部基线、反射峰值、50% crossing、OPEN 延迟锚点、强反射宽窗 QC、反射系数拟合、传播速度拟合、校准和绘图流程。
- 文件：`analysis/analysis_summary.md`、`analysis/calibration.csv`、`analysis/per_cycle.csv`、`analysis/processed_results.csv`、`analysis/open_delay_anchors.csv`、`analysis/group_delays.csv`、`analysis/group_fits.csv`、`analysis/name_qc.csv`
- 目的：保留从单周期测量到配置汇总、拟合和物理名称检查的完整证据链。
- 变更：分析 66 个正式配置与 355 个脉冲周期；将匹配负载 timing 记为 N/A，并将 `rg179-15m-SHORT.csv` 标为 96.102 ns 的长度异常、排除于正式拟合。
- 文件：`analysis/figure_gamma_vs_theory.png`、`analysis/figure_delay_vs_length.png`
- 目的：生成可直接用于 essay 的高分辨率结果图。
- 变更：展示理论/实验反射系数关系、长度衰减趋势和往返延迟线性拟合。
- 文件：`task_plan.md`、`findings.md`、`progress.md`
- 目的：记录提取规则、错误处理、质检结果和结论边界。
- 变更：记录 RG179 15 m short 的名称异常、2.5 MHz cadence、20.007 ns pulse width、拟合系数与传播速度。
- 验证：`verify_waveform_data.py` 得到 70/70 CSV 结构有效及正式矩阵 66/66；完整分析连续重跑的 10 个输出 SHA-256 全部一致；独立断言验证 66 个唯一配置、355 个周期、QC 状态 59/6/1、反射极性和拟合 R²；目视检查两张图。
- 提交：`c8b4cd7`

## 2026-08-24 — 恢复已验证的 RG179 15 m 终端数据

- 文件：`rg179-15m-120ohm-WRONG.csv`、`rg179-15m-120ohm.csv`、`rg179-15m-200ohm-WRONG.csv`、`rg179-15m-200ohm.csv`
- 目的：将波形反推结果与文件名一致的 120 Ω、200 Ω RG179 15 m 数据恢复为正式配置。
- 变更：移除两个文件名中的 `-WRONG` 标记；保留 `rg179-15m-12ohm-WRONG.csv` 作为排除的旧重复记录。
- 文件：`data_status.csv`
- 目的：反映完整的正式配置矩阵。
- 变更：将 RG179 15 m 的 12 Ω、120 Ω、200 Ω 状态标为已覆盖。
- 文件：`visualize/index.html`、`visualize/summary.csv`
- 目的：同步可视化的嵌入数据和摘要。
- 变更：重新生成，纳入两个恢复的文件，并显示完整 RG179 15 m 状态行。
- 验证：运行 `visualize/visualize.py` 与 `verify_waveform_data.py`；正式矩阵覆盖 66/66，HTML 内嵌 RG179 15 m 的全部 11 个 load。
- 提交：`e5dd9ac`

## 2026-08-04 — 建立仓库编辑规范

- 文件：`agents.md`、`CHANGELOG.md`
- 目的：定义每次编辑的变更记录、独立提交和安全回退要求。
- 变更：新增仓库级协作规范与本变更记录文件。
- 验证：检查文件内容，并确认 Git 工作区状态。
- 提交：使用 `git log --oneline -- agents.md CHANGELOG.md` 查看对应提交。

## 2026-08-04 — 建立项目初始基线

- 文件：仓库当前全部既有文件（CSV 数据、脚本、`essay/`、`visualize/` 及规范文件）
- 目的：将当前项目状态纳入 Git，作为后续修改的可回退起点。
- 变更：首次提交现有项目文件；不删除、不改写数据内容。
- 验证：提交前检查 Git 状态与文件清单；提交后确认工作区干净。
- 提交：使用 `git log --oneline --all` 查看对应提交。

## 2026-08-21 — 新增波形数据验证器

- 文件：`.gitignore`、`verify_waveform_data.py`、`task_plan.md`、`findings.md`、`progress.md`
- 目的：可重复检查示波器 CSV 的文件名、预期配置覆盖、元数据结构、时间轴和记录内脉冲一致性，并明确物理接线验证所需的独立证据。
- 变更：新增验证 CLI、可选 acquisition manifest 检查、审计计划与结果记录；忽略可再生的 Python 缓存文件。
- 验证：运行 `verify_waveform_data.py` 和 `verify_waveform_data.py --allow-incomplete`；69/69 CSV 结构有效，正式矩阵覆盖 63/66，并验证 manifest 严格模式会拒绝未确认记录。
- 提交：`e73d38d`
## 2026-08-30 — 补回 Figure 2 反射后细节窗口

- 文件：`analysis/render_aligned_full_record_composite.py`、`analysis/figures/rg58_10m_matched_open_short_full_aligned_no_notes.png`
- 目的：恢复双面板 Figure 2 上方 zoomed graph 右上角的 post-reflection detail，并按要求整理对齐说明气泡。
- 变更：新增 175–250 ns 放大 inset 及连接标记；气泡文字左对齐，并将 “First peaks aligned at 0 ns” 移至第一行。
- 验证：运行 `python -m py_compile analysis/render_aligned_full_record_composite.py`；重复渲染 SHA-256 一致（`3F53906427AFC58394A5497149BC1B214E59BEED15B176EACE3C5FE58DB6FF0E`）。
- 提交：`54dd43d`
## 2026-08-30 — 统一 Figure 2 电压轴标签

- 文件：`analysis/render_aligned_full_record_composite.py`、`analysis/figures/rg58_10m_matched_open_short_full_aligned_no_notes.png`
- 目的：使上下两个波形面板的纵轴标注简洁且一致。
- 变更：将两个 y-axis 标签改为 `Voltage / V`。
- 验证：运行 `python -m py_compile analysis/render_aligned_full_record_composite.py` 并重新渲染图像，目视确认上下轴标签均已更新。
- 提交：`35df8a5`
## 2026-08-30 — 统一 F4 有效衰减系数精度

- 文件：`analysis/render_quantitative_figures.py`、`analysis/figures/effective_attenuation.csv`、Google Doc `IB_Physics_EE`
- 目的：避免正文误用 Table 2 四舍五入后的 k，并使 F4 note 与用户指定表述一致。
- 变更：脚本从 full-precision k 回归得到梯度 m，并输出 `α_eff = −m/s`（s=2）；正文更新为 RG58 `0.00586261350739799 m⁻¹`、RG179 `0.00891787456845251 m⁻¹`，同时保留 R² = 0.9979、0.9918。
- 验证：运行 `python -m py_compile analysis/render_quantitative_figures.py` 与绘图脚本；确认 `effective_attenuation.csv` 数值；重新读取 Google Doc 段落确认正文已替换。
- 提交：`61b6f0c`
## 2026-08-30 — Figure 5 显示六位 R²

- 文件：`analysis/render_quantitative_figures.py`、`analysis/figures/delta_t_vs_length.png`
- 目的：提高 Figure 5 拟合优度数值的显示精度。
- 变更：将图例中的两个 R² 从 5 位小数改为 6 位小数（0.999997、0.999991）。
- 验证：运行 `python -m py_compile analysis/render_quantitative_figures.py` 和绘图脚本；目视确认图例显示六位小数。
- 提交：`18b7341`
