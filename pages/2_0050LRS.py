###############################################################
# 0050LRS 回測（auto_adjust 版本）
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go

import yfinance as yf   # 直接改用 auto_adjust 下載

###############################################################
# 字型設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft JhengHei",
        "PingFang TC",
        "Heiti TC",
    ]
matplotlib.rcParams["axes.unicode_minus"] = False

###############################################################
# Streamlit 頁面設定
###############################################################

st.set_page_config(
    page_title="0050LRS 回測系統（auto_adjust）",
    page_icon="📈",
    layout="wide",
)
st.markdown("<h1>📊 0050LRS 槓桿策略回測（auto_adjust）</h1>", unsafe_allow_html=True)

###############################################################
# ETF 清單（無 .TW，UI 更乾淨）
###############################################################

BASE_LIST = ["0050", "006208"]
LEV_LIST = ["00631L", "00663L", "00675L", "00685L"]

def to_symbol(x):
    """UI: 0050 → yfinance: 0050.TW"""
    return f"{x}.TW"

###############################################################
# UI
###############################################################

col1, col2 = st.columns(2)

with col1:
    base_display = st.selectbox("原型 ETF（訊號來源）", BASE_LIST)
    base_symbol = to_symbol(base_display)

with col2:
    lev_display = st.selectbox("槓桿 ETF（實際進出場標的）", LEV_LIST)
    lev_symbol = to_symbol(lev_display)

st.markdown(f"### 使用原型：{base_display}　槓桿：{lev_display}")

###############################################################
# 自動下載（auto_adjust）
###############################################################

@st.cache_data
def load_yf_price(symbol: str) -> pd.DataFrame:
    """
    下載自動調整後價格（內含股息/拆股調整）
    """
    df = yf.download(symbol, auto_adjust=True)
    if df.empty:
        raise ValueError(f"⚠️ 無法下載 {symbol}")
    df = df[["Close"]]  # 使用調整後收盤價
    df = df.rename(columns={"Close": "Price"})
    return df

# 下載資料
try:
    df_base = load_yf_price(base_symbol)
    df_lev = load_yf_price(lev_symbol)
except Exception as e:
    st.error(str(e))
    st.stop()

###############################################################
# 合併資料
###############################################################

df = pd.DataFrame(index=df_base.index)
df["Price_base"] = df_base["Price"]
df = df.join(df_lev["Price"].rename("Price_lev"), how="inner")
df = df.sort_index()

###############################################################
# 日期區間
###############################################################

available_start = df.index.min().date()
available_end = df.index.max().date()
st.info(f"📌 可回測區間：{available_start} ~ {available_end}")

col3, col4, col5 = st.columns(3)

with col3:
    default_start = max(available_start, available_end - dt.timedelta(days=5*365))
    start = st.date_input("開始日期", value=default_start,
                          min_value=available_start, max_value=available_end)

with col4:
    end = st.date_input("結束日期", value=available_end,
                        min_value=available_start, max_value=available_end)

with col5:
    capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)

position_mode = st.radio("策略初始狀態", ["空手起跑（標準 LRS）", "一開始就全倉槓桿 ETF"])

###############################################################
# 主回測（按下按鈕）
###############################################################

if st.button("開始回測 🚀"):

    if start >= end:
        st.error("⚠️ 開始日期需小於結束日期")
        st.stop()

    df = df.loc[pd.to_datetime(start): pd.to_datetime(end)].copy()

    # 計算 200SMA（來自原型 ETF）
    df["MA_200"] = df["Price_base"].rolling(200).mean()
    df = df.dropna(subset=["MA_200"])

    if df.empty:
        st.error("⚠️ 沒有足夠資料計算 200SMA")
        st.stop()

    ###############################################################
    # 訊號產生（原型 ETF）
    ###############################################################

    df["Price_base_shift"] = df["Price_base"].shift(1)
    df["MA_shift"] = df["MA_200"].shift(1)

    df["Signal"] = 0
    df.loc[(df["Price_base"] > df["MA_200"]) & (df["Price_base_shift"] <= df["MA_shift"]), "Signal"] = 1
    df.loc[(df["Price_base"] < df["MA_200"]) & (df["Price_base_shift"] >= df["MA_shift"]), "Signal"] = -1

    # 初始持倉
    if "空手" in position_mode:
        pos = 1 if df["Price_base"].iloc[0] > df["MA_200"].iloc[0] else 0
    else:
        pos = 1

    positions = [pos]

    for sig in df["Signal"].iloc[1:]:
        if sig == 1:
            pos = 1
        elif sig == -1:
            pos = 0
        positions.append(pos)

    df["Position"] = positions

    ###############################################################
    # 報酬計算（槓桿 ETF）
    ###############################################################

    df["Ret_lev"] = df["Price_lev"].pct_change().fillna(0)

    equity = [1.0]
    for i in range(1, len(df)):
        if df["Position"].iloc[i] == 1:
            equity.append(equity[-1] * (1 + df["Ret_lev"].iloc[i]))
        else:
            equity.append(equity[-1])
    df["Equity_LRS"] = equity

    df["Equity_BH_Base"] = (df["Price_base"] / df["Price_base"].iloc[0])
    df["Equity_BH_Lev"] = (df["Price_lev"] / df["Price_lev"].iloc[0])

    ###############################################################
    # 三策略比較圖
    ###############################################################

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"], name="LRS"))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"], name=f"{lev_display} BH"))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"], name=f"{base_display} BH"))
    fig.update_layout(template="plotly_white", height=450)
    st.plotly_chart(fig, use_container_width=True)

    ###############################################################
    # 最終數字
    ###############################################################

    st.subheader("📌 回測結果")

    st.write(f"🔹 LRS 最終資產：{equity[-1] * capital:,.0f} 元")
    st.write(f"🔹 槓桿 BH：{df['Equity_BH_Lev'].iloc[-1] * capital:,.0f} 元")
    st.write(f"🔹 原型 BH：{df['Equity_BH_Base'].iloc[-1] * capital:,.0f} 元")
