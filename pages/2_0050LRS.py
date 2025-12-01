###############################################################
# 0050LRS 回測（0050 / 006208 + 正2 槓桿 ETF）auto_adjust版本
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
import yfinance as yf

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
# Streamlit 設定
###############################################################

st.set_page_config(page_title="0050LRS 回測系統（auto_adjust）", page_icon="📈", layout="wide")
st.markdown("<h1>📊 0050LRS 槓桿策略回測（auto_adjust）</h1>", unsafe_allow_html=True)

###############################################################
# ETF 選單（UI 顯示乾淨版本）
###############################################################

BASE_DISPLAY = ["0050", "006208"]
LEV_DISPLAY = ["00631L", "00663L", "00675L", "00685L"]

def to_symbol(x):  
    return f"{x}.TW"

###############################################################
# UI：選擇原型 / 槓桿 ETF
###############################################################

col1, col2 = st.columns(2)

with col1:
    base_display = st.selectbox("原型 ETF（訊號來源）", BASE_DISPLAY)
    base_symbol = to_symbol(base_display)

with col2:
    lev_display = st.selectbox("槓桿 ETF（出場標的）", LEV_DISPLAY)
    lev_symbol = to_symbol(lev_display)

st.markdown(f"### 使用原型：{base_display}　槓桿：{lev_display}")

###############################################################
# 自動下載（使用 auto_adjust=True）
###############################################################

@st.cache_data
def load_yf(symbol):
    df = yf.download(symbol, auto_adjust=True)
    if df.empty:
        st.error(f"⚠️ yfinance 無法下載：{symbol}")
        st.stop()
    df = df.rename(columns={"Close": "Price"})
    return df[["Price"]]

df_base = load_yf(base_symbol)
df_lev = load_yf(lev_symbol)

###############################################################
# 合併資料（以原型 ETF 時間為基準）
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
    default_start = max(available_start, available_end - dt.timedelta(days=365 * 5))
    start = st.date_input("開始日期", value=default_start,
                          min_value=available_start, max_value=available_end)
with col4:
    end = st.date_input("結束日期", value=available_end,
                        min_value=available_start, max_value=available_end)
with col5:
    capital = st.number_input("投入本金", 1000, 5_000_000, 100_000, step=10_000)

position_mode = st.radio("策略初始狀態", ["空手起跑（標準 LRS）", "起跑就進場"])

###############################################################
# 回測按鈕
###############################################################

if st.button("開始回測 🚀"):

    df = df.loc[pd.to_datetime(start): pd.to_datetime(end)].copy()

    ###############################################################
    # 計算 200SMA
    ###############################################################

    df["MA_200"] = df["Price_base"].rolling(200).mean()
    df = df.dropna(subset=["MA_200"])

    ###############################################################
    # 產生訊號：原型 ETF 觸發訊號
    ###############################################################

    df["Signal"] = 0
    df["base_shift"] = df["Price_base"].shift(1)
    df["ma_shift"] = df["MA_200"].shift(1)

    df.loc[(df["Price_base"] > df["MA_200"]) & (df["base_shift"] <= df["ma_shift"]), "Signal"] = 1  # 金叉
    df.loc[(df["Price_base"] < df["MA_200"]) & (df["base_shift"] >= df["ma_shift"]), "Signal"] = -1  # 死叉

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
    # 報酬計算（槓桿 ETF 實際進出）
    ###############################################################

    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    equity = [1.0]
    for i in range(1, len(df)):
        if df["Position"].iloc[i] == 1:
            equity.append(equity[-1] * (1 + df["Return_lev"].iloc[i]))
        else:
            equity.append(equity[-1])
    df["Equity_LRS"] = equity

    df["Equity_BH_Base"] = df["Price_base"] / df["Price_base"].iloc[0]
    df["Equity_BH_Lev"] = df["Price_lev"] / df["Price_lev"].iloc[0]

    ###############################################################
    # 三策略資金曲線圖
    ###############################################################

    st.subheader("📈 三策略資金曲線")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"], name="LRS"))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"], name=f"{lev_display} BH"))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"], name=f"{base_display} BH"))
    fig.update_layout(template="plotly_white", height=450)
    st.plotly_chart(fig, use_container_width=True)

    ###############################################################
    # 總結數字
    ###############################################################

    st.subheader("📘 回測總結")

    st.write(f"🔹 **LRS 最終資產：{df['Equity_LRS'].iloc[-1] * capital:,.0f} 元**")
    st.write(f"🔹 **槓桿 BH：{df['Equity_BH_Lev'].iloc[-1] * capital:,.0f} 元**")
    st.write(f"🔹 **原型 BH：{df['Equity_BH_Base'].iloc[-1] * capital:,.0f} 元**")
