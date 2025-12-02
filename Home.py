"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout for strategies.
"""

import streamlit as st
import os
import datetime

# 1. 頁面設定
st.set_page_config(
    page_title="倉鼠回測平台 | 會員專屬",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. 側邊欄：品牌與外部連結
with st.sidebar:
    # ✅ 修正：直接讀取您剛上傳的 logo.png，解決破圖問題
    if os.path.exists("logo.png"):
        st.image("logo.png", width=120)
    else:
        st.title("🐹") # 萬一圖片不見，至少顯示 emoji
        
    st.title("倉鼠實驗室")
    st.caption("v1.0.0 Beta | 白銀會員限定")
    
    st.divider()
    
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    
    st.divider()
    st.info("💡 **提示**\n本平台僅供策略研究與回測驗證，不代表投資建議。")

# 3. 主畫面：歡迎語 (Hero Section)
st.title("🚀 量化戰情室")

# ✅ 新增：動態檢查數據更新時間 (讀取 data 資料夾)
data_status = "檢查中..."
last_update = "N/A"

try:
    # 檢查 data 資料夾內最新的 CSV 檔案時間
    data_dir = "data"
    if os.path.exists(data_dir):
        files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".csv")]
        if files:
            latest_file = max(files, key=os.path.getmtime)
            timestamp = os.path.getmtime(latest_file)
            last_update = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            data_status = "✅ 系統數據正常"
        else:
            data_status = "⚠️ 無數據文件"
    else:
        data_status = "❌ 找不到數據資料夾"
except Exception as e:
    data_status = "⚠️ 狀態檢測異常"

st.caption(f"{data_status} | 📅 最後更新：{last_update}")

st.markdown("""
歡迎來到 **倉鼠回測平台**！這裡是鼠叔為白銀會員打造的專屬軍火庫。
不需要寫程式，直接點擊下方策略卡片，輸入參數即可驗證你的交易想法。
""")

st.divider()

# 4. 策略定義 (資料結構)
strategies = [
    {
        "name": "200SMA 趨勢策略 (基礎版)",
        "icon": "📈",
        "description": "經典的趨勢跟隨策略。使用 200 日移動平均線 (SMA) 判斷牛熊分界，適合用來測試大盤指數的長期持有績效。",
        "tags": ["趨勢", "均線", "長期"],
        "page_path": "pages/1_200SMA_basic.py",  # 對應檔案：pages/1_200SMA_basic.py
        "btn_label": "進入 SMA 回測"
    },
    {
        "name": "0050 LRS 動態槓桿策略",
        "icon": "⚡",
        "description": "進階的資金控管策略。以 0050/006208 為訊號，動態調整正2槓桿 ETF 的曝險比例，追求比大盤更高的報酬風險比。",
        "tags": ["槓桿", "動態調整", "波段"],
        "page_path": "pages/2_0050LRS.py",       # 對應檔案：pages/2_0050LRS.py
        "btn_label": "進入 LRS 回測"
    },
]

# 5. 策略展示區 (卡片式佈局)
st.subheader("🛠️ 選擇你的實驗策略")

# 使用 columns 排版，每行放 2 個策略
cols = st.columns(2)

for index, strategy in enumerate(strategies):
    col = cols[index % 2]
    
    with col:
        with st.container(border=True):
            st.markdown(f"### {strategy['icon']} {strategy['name']}")
            
            st.markdown(
                " ".join([f"`{tag}`" for tag in strategy['tags']])
            )
            
            st.write(strategy['description'])
            st.write("") 
            
            st.page_link(
                strategy['page_path'], 
                label=strategy['btn_label'], 
                icon="👉", 
                use_container_width=True
            )

# 6. 未來展望 / 預告區塊
st.markdown("---")
st.caption("🚧 更多策略正在開發中 (MACD 動能、RSI 逆勢交易...)，敬請期待！")
