# Waveform Alignment Lab

## 使用

直接用浏览器打开 `index.html`，无需服务器。页面内嵌 69 条实测/校准/试测波形，共 300,000 个采样点；不包含两个 WRONG 文件。

从仓库根目录重新生成：

```sh
python visualize/visualize.py
```

生成器会读取仓库根目录的 Siglent CSV，更新 `index.html` 和 `summary.csv`。不要直接维护生成的 HTML；维护 `visualize.py` 后重新生成。

## 操作

- Data Selection：按电缆、长度、负载及文件名筛选、多选。
- Display Window：选择显示窗口、原始/扣 baseline 模式、参考波形及 Y 范围。
- Global Shift / Per-Curve Shift Controls：全局或逐条调整时间、电压和 baseline。
- Auto Align：平滑显示窗口内的曲线并定位第一个满足阈值的正峰，将其平移至 0 ns；默认平滑 7 点、阈值 25%。
- Recalculate selected baselines：使用可见峰前至少 10 个原始样本的均值；不足时回退到前 100 个原始样本的均值。
- Match Metrics：相对参考波形计算 RMS、MAE 和 correlation。
- Export：导出 alignment JSON/CSV、当前窗口 corrected CSV、Canvas PNG。
- CSV import：在浏览器中读入自己的 Siglent CSV。

## 变换

```text
t_display = t_raw_ns + global_time_shift + curve_time_shift
v_display = v_raw - baseline + global_voltage_shift + curve_voltage_shift
```

Raw voltage 模式不扣 baseline。手动和自动对齐不会改变原始 CSV，也不会更新正式分析表。

## 随仓库保留的导出

`alignment.csv`：RG58 10 m 十一个负载的对齐、baseline 和电压偏移参数。
`corrected_data.csv`：对应的 −100…250 ns 窗口，每条 701 点，共 7,711 行，含原始及变换后的坐标。

对齐绘图脚本默认读取此目录。它们验证导出点和原始样本经过存储参数变换后逐点一致，再使用原始样本扩展显示范围；不重新拟合偏移。

## 解释边界

`summary.csv` 和页面的峰值指标用于波形浏览，不等同于 `analyze_waveforms.py` 的逐周期固定窗口算法。正式统计与不确定度定义见 `../docs/DATA.md`。

SVG 和 `rg58_10m_load_visualization.html` 是保留的历史静态导出；当前交互工具以 `index.html` 为准。
