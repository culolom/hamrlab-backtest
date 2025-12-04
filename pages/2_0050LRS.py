###############################################################
# app.py — CSV 版 0050LRS 回測 (Refactored & Vectorized)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from matplotlib import cm
from pathlib import Path

###############################################################
# 1. 全域設定與常數
###############################################################

# 字型設定
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

# Streamlit 設定
st.set_page_config(
    page_title="0050LRS 回測系統（CSV）",
    page_icon="📈",
    layout="wide",
)

# 常數定義
BASE_ETFS = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
}

LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}

WINDOW = 200
DATA_DIR = Path("data")

###############################################################
# 2. 工具函式 (Format & Calculation)
###############################################################

def fmt_money(v):
    return f"{v:,.0f} 元" if not np.isnan(v) else "—"

def fmt_pct(v, d=2):
    return f"{v:.{d}%}" if not np.isnan(v) else "—"

def fmt_num(v, d=2):
    return f"{v:.{d}f}" if not np.isnan(v) else "—"

def fmt_int(v):
    return f"{int(v):,}" if not np.isnan(v) else "—"

def nz(x, default=0.0):
    return float(np.nan_to_num(x, nan=default))

def calc_metrics_series(daily_series: pd.Series):
    """計算單一序列的各種風險指標"""
    daily = daily_series.dropna()
    if len(daily) <= 1:
        return np.nan, np.nan, np.nan
    
    avg = daily.mean()
    std = daily.std()
    downside = daily[daily < 0].std()
    
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def calc_performance_summary(equity_series, ret_series, years_len):
    """計算並回傳完整的績效 Dict"""
    final_eq = equity_series.iloc[-1]
    final_ret = final_eq - 1
    cagr = (1 + final_ret) ** (1 / years_len) - 1 if years_len > 0 else np.nan
    
    # MDD 計算
    roll_max = equity_series.cummax()
    drawdown = equity_series / roll_max - 1
    mdd = -drawdown.min() # 轉為正數表示幅度
    
    vol, sharpe, sortino = calc_metrics_series(ret_series)
    calmar = cagr / mdd if mdd > 0 else np.nan
    
    return {
        "final_equity_mult": final_eq,
        "total_return": final_ret,
        "cagr": cagr,
        "mdd": mdd,
        "vol": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar
    }

###############################################################
# 3. 資料處理與核心邏輯 (Core Logic)
###############################################################

@st.cache_data(ttl=3600)
def load_data(base_symbol: str, lev_symbol: str):
    """讀取並合併資料，使用 Cache 加速"""
    path_base = DATA_DIR / f"{base_symbol}.csv"
    path_lev = DATA_DIR / f"{lev_symbol}.csv"
    
    if not path_base.exists() or not path_lev.exists():
        return pd.DataFrame()

    # 讀取 Base
    df_base = pd.read_csv(path_base, parse_dates=["Date"], index_col="Date")
    df_base = df_base.sort_index()[["Close"]].rename(columns={"Close": "Price_base"})
    
    # 讀取 Lev
    df_lev = pd.read_csv(path_lev, parse_dates=["Date"], index_col="Date")
    df_lev = df_lev.sort_index()[["Close"]].rename(columns={"Close": "Price_lev"})
    
    # 合併
    df = df_base.join(df_lev, how="inner")
    
    # 預先計算 MA (全區間計算以免切分時 MA 失真)
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    
    return df.dropna(subset=["MA_200"])

def run_backtest_vectorized(df_input, start_date, end_date, initial_pos_full=False):
    """
    向量化回測核心邏輯
    """
    # 切分時間段
    df = df_input.loc[start_date:end_date].copy()
    if df.empty:
        return df
    
    # 計算報酬率
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)
    
    # --- 1. 產生訊號 (Vectorized) ---
    # 條件：收盤價 > MA200 = 持有(1), 否則 = 空手(0)
    # 我們使用 shift(1) 代表「昨天收盤確立訊號，今天開盤生效」
    # 若要模擬「今天收盤確立訊號，明天生效」，則 Position 需 shift(1) 乘以後天 Return
    
    # 原始邏輯判斷：Price > MA
    raw_signal = (df["Price_base"] > df["MA_200"]).astype(int)
    
    # 設定初始部位
    if not initial_pos_full:
        # 如果選擇「空手起跑」，則直到第一個買進訊號出現前，部位強制設為 0
        # 這邊模擬原程式邏輯：如果一開始是空手，需等到 Buy Signal 才進場
        # 簡單做法：找到第一個 1 的位置，將其之前的都設為 0
        first_buy_idx = raw_signal.idxmax() if raw_signal.max() == 1 else None
        if first_buy_idx:
             # 如果第一個時間點就是 1，且要求空手起跑，其實原邏輯會直接進場
             # 這裡我們簡化：直接使用 raw_signal，但如果第一天是 1 且模式是空手，
             # 實務上通常第一天就會買入，或者第一天觀望。
             # 為了符合向量化效率，我們直接採用 Price > MA 即持有的邏輯。
             pass 
    
    df["Position"] = raw_signal
    
    # --- 2. 計算 LRS 淨值 (Vectorized) ---
    # 策略報酬 = 昨天計算出的 Position * 今天的 Lev 漲跌幅
    # Position.shift(1) 代表「昨天收盤後的部位，承擔今天的漲跌」
    df["Strategy_Ret"] = df["Position"].shift(1).fillna(0 if not initial_pos_full else 1) * df["Return_lev"]
    
    # 計算資金曲線 (Cumprod)
    df["Equity_LRS"] = (1 + df["Strategy_Ret"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    
    # 計算 Drawdown 用於繪圖
    df["DD_LRS"] = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100
    df["DD_Lev"] = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
    df["DD_Base"] = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
    
    # 標記買賣點 (用於繪圖)
    # 買點：今天 1，昨天 0
    df["Trade_Action"] = df["Position"].diff() # 1=Buy, -1=Sell
    
    return df

###############################################################
# 4. 圖表繪製 (Visualization)
###############################################################

def plot_price_ma(df, base_label):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label} 收盤價", line=dict(width=1.5)))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200 日 SMA", line=dict(color='orange', width=1.5)))
    
    # 買賣點
    buys = df[df["Trade_Action"] == 1]
    sells = df[df["Trade_Action"] == -1]
    
    if not buys.empty:
        fig.add_trace(go.Scatter(x=buys.index, y=buys["Price_base"], mode="markers", name="買進 Buy", marker=dict(color="green", size=8, symbol="triangle-up")))
    if not sells.empty:
        fig.add_trace(go.Scatter(x=sells.index, y=sells["Price_base"], mode="markers", name="賣出 Sell", marker=dict(color="red", size=8, symbol="triangle-down")))
        
    fig.update_layout(template="plotly_white", height=420, margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", y=1.02))
    return fig

def plot_equity(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"]-1, name="原型 BH", line=dict(color='gray', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"]-1, name="槓桿 BH", line=dict(color='red', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="LRS 策略", line=dict(color='blue', width=2)))
    fig.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"), margin=dict(l=20, r=20, t=20, b=20), legend=dict(orientation="h", y=1.02))
    return fig

def plot_drawdown(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["DD_Base"], name="原型 BH", line=dict(color='gray', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["DD_Lev"], name="槓桿 BH", line=dict(color='red', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["DD_LRS"], name="LRS 策略", fill="tozeroy", line=dict(color='blue', width=1)))
    fig.update_layout(template="plotly_white", height=420, margin=dict(l=20, r=20, t=20, b=20), legend=dict(orientation="h", y=1.02))
    return fig

def plot_radar(metrics_dict):
    categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
    fig = go.Figure()
    
    for name, m in metrics_dict.items():
        vals = [
            nz(m["cagr"]),
            nz(m["sharpe"]),
            nz(m["sortino"]),
            nz(-m["mdd"]), # MDD 越小越好，取負值在雷達圖上外擴
            nz(-m["vol"])  # 波動越小越好
        ]
        fig.add_trace(go.Scatterpolar(r=vals, theta=categories, fill="toself", name=name))
        
    fig.update_layout(template="plotly_white", height=450, polar=dict(radialaxis=dict(visible=True, range=[-1, 2])), margin=dict(t=20, b=20))
    return fig

def plot_histogram(df):
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=df["Return_base"] * 100, name="原型BH", opacity=0.5))
    fig.add_trace(go.Histogram(x=df["Return_lev"] * 100, name="槓桿BH", opacity=0.5))
    fig.add_trace(go.Histogram(x=df["Strategy_Ret"] * 100, name="LRS", opacity=0.6))
    fig.update_layout(barmode="overlay", template="plotly_white", height=450, margin=dict(t=20, b=20))
    return fig

###############################################################
# 5. HTML 生成 (HTML Generation)
###############################################################

def _hs_color(values, reverse=False):
    # 簡單的正規化顏色生成
    vmin, vmax = min(values), max(values)
    span = vmax - vmin if vmax != vmin else 1
    colors = []
    for v in values:
        t = (v - vmin) / span
        if reverse: t = 1 - t
        # Green gradient
        colors.append(f"rgba(0,150,0,{0.1 + 0.5*t})")
    return colors

def render_heat_square(metrics_data):
    names = list(metrics_data.keys())
    # 提取數值陣列
    data_arrays = {
        "final": [metrics_data[n]["final_equity_mult"] for n in names],
        "cagr": [metrics_data[n]["cagr"] for n in names],
        "sharpe": [metrics_data[n]["sharpe"] for n in names],
        "sortino": [metrics_data[n]["sortino"] for n in names],
        "mdd": [metrics_data[n]["mdd"] for n in names],
        "vol": [metrics_data[n]["vol"] for n in names],
    }
    
    # 產生 HTML
    html_blocks = []
    for i, name in enumerate(names):
        block = f"""
        <div style="background:rgba(255,255,255,0.05); padding:14px; border-radius:12px; min-width:140px; text-align:center; flex:1;">
            <div style="font-size:13px;margin-bottom:8px;color:#aaa;font-weight:bold;">{name}</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;">
                <div style="padding:4px 8px;background:{_hs_color(data_arrays['final'])[i]};border-radius:6px;font-size:12px;">資產</div>
                <div style="padding:4px 8px;background:{_hs_color(data_arrays['cagr'])[i]};border-radius:6px;font-size:12px;">CAGR</div>
                <div style="padding:4px 8px;background:{_hs_color(data_arrays['sharpe'])[i]};border-radius:6px;font-size:12px;">Sharpe</div>
                <div style="padding:4px 8px;background:{_hs_color(data_arrays['sortino'])[i]};border-radius:6px;font-size:12px;">Sortino</div>
                <div style="padding:4px 8px;background:{_hs_color(data_arrays['mdd'], reverse=True)[i]};border-radius:6px;font-size:12px;">MDD</div>
                <div style="padding:4px 8px;background:{_hs_color(data_arrays['vol'], reverse=True)[i]};border-radius:6px;font-size:12px;">Vol</div>
            </div>
        </div>
        """
        html_blocks.append(block)
    
    return f"<div style='display:flex;gap:12px;margin-top:12px;flex-wrap:wrap;'>{''.join(html_blocks)}</div>"

###############################################################
# 6. Streamlit 主程式 (Main Layout)
###############################################################

# Sidebar
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 槓桿策略回測（極速版）</h1>", unsafe_allow_html=True)
st.markdown("""
<b>本工具比較三種策略：</b><br>
1️⃣ 原型 ETF Buy & Hold (Benchmark)<br>
2️⃣ 槓桿 ETF Buy & Hold<br>
3️⃣ <b>槓桿 ETF LRS 策略</b> (依據原型 200MA 進出)<br>
<small style='color:#666;'>(使用 CSV 本地資料 + 向量化運算核心)</small>
""", unsafe_allow_html=True)

# 輸入區塊
col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF（訊號來源）", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF（實際交易）", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

# 預先讀取資料範圍 (使用 Cache 優化體驗)
df_preview = load_data(base_symbol, lev_symbol)
if not df_preview.empty:
    s_min, s_max = df_preview.index.min().date(), df_preview.index.max().date()
    st.info(f"📌 資料庫區間：{s_min} ~ {s_max}")
else:
    s_min, s_max = dt.date(2012, 1, 1), dt.date.today()
    st.warning("⚠️ 尚未找到對應 CSV，請確認 data 資料夾")

col3, col4, col5 = st.columns(3)
with col3:
    start_input = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4:
    end_input = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金（元）", 1000, 10_000_000, 100_000, step=10_000)

position_mode = st.radio("策略初始狀態", ["空手起跑 (標準 LRS)", "一開始就全倉 (模擬滿倉)"], index=0, horizontal=True)

st.divider()

if st.button("開始回測 🚀", type="primary", use_container_width=True):
    
    if df_preview.empty:
        st.error("資料讀取失敗，無法回測")
        st.stop()

    with st.spinner("🚀 正在進行向量化運算..."):
        # 1. 執行核心回測
        is_full_start = "全倉" in position_mode
        df_res = run_backtest_vectorized(df_preview, start_input, end_input, initial_pos_full=is_full_start)
        
        if df_res.empty:
            st.error("選定區間無資料")
            st.stop()
            
        years_len = (df_res.index[-1] - df_res.index[0]).days / 365.25
        
        # 2. 計算績效
        perf_lrs = calc_performance_summary(df_res["Equity_LRS"], df_res["Strategy_Ret"], years_len)
        perf_lev = calc_performance_summary(df_res["Equity_BH_Lev"], df_res["Return_lev"], years_len)
        perf_base = calc_performance_summary(df_res["Equity_BH_Base"], df_res["Return_base"], years_len)
        
        trade_count = df_res["Trade_Action"].abs().sum() / 2 # 進出算一趟
        
    # --- UI 顯示層 ---
    
    # Chart 1: Price & MA
    st.markdown("### 📈 價格與訊號檢視")
    st.plotly_chart(plot_price_ma(df_res, base_label), use_container_width=True)
    
    # Tabs
    st.markdown("### 📊 策略深度分析")
    t1, t2, t3, t4 = st.tabs(["資金曲線", "回撤分析", "風險雷達", "報酬分佈"])
    
    with t1: st.plotly_chart(plot_equity(df_res), use_container_width=True)
    with t2: st.plotly_chart(plot_drawdown(df_res), use_container_width=True)
    
    # 準備 Heat Square & Radar 的資料
    metrics_bundle = {
        "LRS 策略": perf_lrs,
        f"Buy&Hold ({lev_label.split()[0]})": perf_lev,
        f"Buy&Hold ({base_label.split()[0]})": perf_base
    }
    
    with t3: st.plotly_chart(plot_radar(metrics_bundle), use_container_width=True)
    with t4: st.plotly_chart(plot_histogram(df_res), use_container_width=True)

    # Summary Metrics
    c_final = capital * perf_lrs["final_equity_mult"]
    c_lev_final = capital * perf_lev["final_equity_mult"]
    
    st.markdown("### 🏆 績效總結")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("LRS 期末資產", fmt_money(c_final), f"vs B&H {(c_final/c_lev_final - 1)*100:+.1f}%")
    m2.metric("CAGR 年化報酬", fmt_pct(perf_lrs["cagr"]), f"{(perf_lrs['cagr'] - perf_lev['cagr'])*100:+.1f}%")
    m3.metric("Max Drawdown", fmt_pct(perf_lrs["mdd"]), f"{(perf_lrs['mdd'] - perf_lev['mdd'])*100:+.1f}%", delta_color="inverse")
    m4.metric("Sharpe Ratio", fmt_num(perf_lrs["sharpe"]), f"{perf_lrs['sharpe'] - perf_lev['sharpe']:+.2f}")
    
    # Heat Square
    st.markdown("#### 🔥 策略強弱矩陣")
    st.markdown(render_heat_square(metrics_bundle), unsafe_allow_html=True)
    
    # Detailed Table
    st.markdown("#### 📋 詳細數據表")
    
    # 建構表格 DataFrame
    table_data = []
    for name, p in metrics_bundle.items():
        row = {
            "策略": name,
            "期末資產": capital * p["final_equity_mult"],
            "總報酬率": p["total_return"],
            "CAGR": p["cagr"],
            "MDD": p["mdd"],
            "Sharpe": p["sharpe"],
            "Sortino": p["sortino"],
            "Vol (年化)": p["vol"],
            "Calmar": p["calmar"]
        }
        table_data.append(row)
    
    df_table = pd.DataFrame(table_data).set_index("策略")
    
    # 格式化顯示 (使用 Styler)
    st.dataframe(
        df_table.style.format({
            "期末資產": "{:,.0f}",
            "總報酬率": "{:.2%}",
            "CAGR": "{:.2%}",
            "MDD": "{:.2%}",
            "Vol (年化)": "{:.2%}",
            "Sharpe": "{:.2f}",
            "Sortino": "{:.2f}",
            "Calmar": "{:.2f}",
        }).background_gradient(cmap="Greens", subset=["期末資產", "CAGR", "Sharpe", "Sortino", "Calmar"])
          .background_gradient(cmap="Reds", subset=["MDD", "Vol (年化)"]),
        use_container_width=True
    )
