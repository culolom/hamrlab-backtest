"""
Auto-update adjusted-price CSVs (Smart Append & Split Detection)
- Automatically detects Stock Splits (like 00663L in 2025)
- Fixes yfinance MultiIndex column issues
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
import re
import pandas as pd
import yfinance as yf

# -----------------------------------------------------
# Paths & Config
# -----------------------------------------------------
DATA_DIR = Path("data")
SYMBOLS_FILE = Path("symbols.txt")

# -----------------------------------------------------
# Normalize symbol
# -----------------------------------------------------
def normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if s.endswith(".TW"):
        return s
    if re.match(r"^\d+[A-Z]*$", s):
        return s + ".TW"
    return s

# -----------------------------------------------------
# Helper: Fix yfinance MultiIndex columns
# -----------------------------------------------------
def clean_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    # 如果是多層索引 (Price, Ticker)，只保留第一層 (Price)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

# -----------------------------------------------------
# Load existing CSV
# -----------------------------------------------------
def load_existing(symbol: str) -> pd.DataFrame | None:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return None

    try:
        # 嘗試讀取，處理可能的多行 Header 問題
        # 假設標準格式只有一行 header，如果是亂掉的格式可能需要更複雜的清洗
        # 這裡簡單讀取，如果出錯就回傳 None 讓它重建
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        
        # 簡單驗證是否有需要的欄位
        if "Close" not in df.columns:
            # 可能是因為之前的 MultiIndex 存檔導致 header 錯亂，視為損壞
            return None
            
        df = df.sort_index()
        return df
    except Exception as e:
        print(f"⚠ CSV corrupted for {symbol} ({e}), rebuilding...")
        return None

# -----------------------------------------------------
# Download Full History (Overwrite)
# -----------------------------------------------------
def download_full_history(symbol: str):
    print(f"📦 Downloading FULL history for {symbol}...")
    df = yf.download(symbol, period="max", auto_adjust=True, progress=False)
    df = clean_yfinance_columns(df)
    
    if df.empty:
        print(f"❌ FAILED: no data for {symbol}")
        return

    df = df[["Close", "Volume"]]
    df.index.name = "Date"
    df.to_csv(DATA_DIR / f"{symbol}.csv")
    print(f"✅ Saved fresh CSV for {symbol} ({len(df)} rows)")

# -----------------------------------------------------
# Update single symbol CSV (Smart Update)
# -----------------------------------------------------
def update_symbol(symbol: str):
    DATA_DIR.mkdir(exist_ok=True)
    existing = load_existing(symbol)

    # 1. 如果沒有舊檔，直接下載全量
    if existing is None or existing.empty:
        download_full_history(symbol)
        return

    # 2. 檢查價格一致性 (Split Detection)
    last_date = existing.index[-1]
    
    # 下載這幾天的資料 (包含 last_date) 用來比對
    # 往回多抓 5 天確保有重疊資料
    check_start = last_date - timedelta(days=5)
    
    print(f"🔍 Checking {symbol} consistency since {last_date.date()}...")
    
    new_data = yf.download(
        symbol, 
        start=check_start.strftime("%Y-%m-%d"), 
        end=None, # 到最新
        auto_adjust=True, 
        progress=False
    )
    new_data = clean_yfinance_columns(new_data)
    
    if new_data.empty:
        print(f"⏭ No new data found for {symbol}")
        return

    # 比對 last_date 當天的價格
    if last_date in new_data.index:
        old_close = existing.loc[last_date, "Close"]
        new_close = new_data.loc[last_date, "Close"]
        
        # 處理可能的 Series (如果有重複 index)
        if isinstance(old_close, pd.Series): old_close = old_close.iloc[-1]
        if isinstance(new_close, pd.Series): new_close = new_close.iloc[-1]

        # 計算價格差異比例
        ratio = abs(new_close - old_close) / old_close
        
        # 如果差異超過 10%，視為發生拆股/除權息，觸發全量更新
        if ratio > 0.1:
            print(f"⚠ Split/Adjustment detected! ({old_close:.2f} vs {new_close:.2f})")
            print("♻ Triggering FULL re-download to fix history...")
            download_full_history(symbol)
            return
    
    # 3. 如果價格一致，執行 Append
    # 只取 last_date 之後的新資料
    new_rows = new_data[new_data.index > last_date].copy()
    
    if new_rows.empty:
        print(f"⏭ {symbol} already up-to-date")
        return

    new_rows = new_rows[["Close", "Volume"]]
    new_rows.index.name = "Date"

    merged = pd.concat([existing, new_rows])
    merged = merged[~merged.index.duplicated(keep="last")]
    merged = merged.sort_index()

    merged.to_csv(DATA_DIR / f"{symbol}.csv")
    print(f"✅ Appended {len(new_rows)} rows to {symbol}")

# -----------------------------------------------------
# Read symbols.txt
# -----------------------------------------------------
def load_symbols() -> list[str]:
    if not SYMBOLS_FILE.exists():
        # Fallback for demo
        return ["00663L.TW"]

    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        return [normalize_symbol(line.strip()) for line in f if line.strip() and not line.startswith("#")]

# -----------------------------------------------------
# Main
# -----------------------------------------------------
def main():
    symbols = load_symbols()
    for sym in symbols:
        print("\n" + "="*30)
        try:
            update_symbol(sym)
        except Exception as e:
            print(f"⚠ ERROR updating {sym}: {e}")

if __name__ == "__main__":
    main()
