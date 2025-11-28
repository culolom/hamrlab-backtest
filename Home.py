"""
HamrLab Backtest Platform main entry.
Main page: shows strategy list and navigation; backtests implemented on sub-pages.
"""

import streamlit as st

st.set_page_config(page_title="倉鼠回測平台", page_icon="🐹", layout="wide")

st.title("🐹 倉鼠回測平台")
st.caption("左側為策略清單，右側顯示所選策略介紹；回測功能請至各策略頁面操作。")

# Strategy definitions
strategies = {
    "200SMA 回測基礎版": {
        "description": "以 200 日 SMA 產生進出場訊號，對單一標的回測並提供價格/均線與資金曲線圖。",
        "page": "pages/1_200SMA_basic.py",
    },
    "0050 LRS 槓桿策略": {
        "description": "以 0050/006208 為訊號來源，實際進出正2 槓桿 ETF，提供三種策略績效比較。",
        "page": "pages/2_LRS_leveraged.py",
    },
}

left, right = st.columns([1, 2])

with left:
    choice = st.radio("策略清單", list(strategies.keys()))
    st.markdown("""
    **提示**
    - 點選策略後於右側查看說明。
    - 進入策略頁面後再執行回測，方便未來增減策略。""")

with right:
    info = strategies[choice]
    st.subheader(choice)
    st.write(info["description"])
    st.markdown(
        "在策略頁面中可設定回測區間、本金與參數，並觀看圖表與績效指標。"
    )
    

st.divider()
st.markdown(
    """
    🧭 **使用方式**
    1. 在左側選擇策略並點擊右側的「前往策略頁面」。
    2. 於策略頁面輸入回測參數並執行回測。
    3. 圖表與績效報表均位於策略頁面，主畫面僅負責策略列表與說明。"""
)
