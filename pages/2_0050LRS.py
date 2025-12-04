###############################################################
    # Tabs 區塊 (已新增 Heatmap)
    ###############################################################

    st.markdown("<h3>📊 三策略資金曲線與風險解析</h3>", unsafe_allow_html=True)
    
    # 1. 增加第五個 Tab
    tab_equity, tab_dd, tab_radar, tab_hist, tab_heat = st.tabs([
        "📈 資金曲線", 
        "🌊 回撤比較", 
        "🕸️ 風險雷達", 
        "📊 日報酬分佈", 
        "🗓️ 月報酬熱力圖"  # <--- 新增這個
    ])

    # --- 1. 資金曲線 ---
    with tab_equity:
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], mode="lines", name="原型BH"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], mode="lines", name="槓桿BH"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS", line=dict(width=2.5)))
        fig_equity.update_layout(template="plotly_white", height=450, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_equity, use_container_width=True)

    # --- 2. 回撤 ---
    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) 
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) 
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) 

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="原型BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name="槓桿BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS", fill="tozeroy"))
        fig_dd.update_layout(template="plotly_white", height=450, yaxis=dict(tickformat=".1%"))
        st.plotly_chart(fig_dd, use_container_width=True)

    # --- 3. 雷達 ---
    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
        radar_lrs_vals  = [nz(cagr_lrs),  nz(sharpe_lrs),  nz(sortino_lrs),  nz(-mdd_lrs),  nz(-vol_lrs)]
        radar_lev_vals  = [nz(cagr_lev),  nz(sharpe_lev),  nz(sortino_lev),  nz(-mdd_lev),  nz(-vol_lev)]
        radar_base_vals = [nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)]

        # 簡單縮放一下雷達圖數值以便顯示 (Demo用，正規做法應Normalize)
        # 這裡直接繪製原始數值
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_lrs_vals, theta=radar_categories, fill="toself", name="LRS"))
        fig_radar.add_trace(go.Scatterpolar(r=radar_lev_vals, theta=radar_categories, fill="toself", name="槓桿BH"))
        fig_radar.add_trace(go.Scatterpolar(r=radar_base_vals, theta=radar_categories, fill="toself", name="原型BH"))
        fig_radar.update_layout(template="plotly_white", height=480)
        st.plotly_chart(fig_radar, use_container_width=True)

    # --- 4. 日報酬分佈 ---
    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return_base"], name="原型BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_lev"], name="槓桿BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_LRS"], name="LRS", opacity=0.7))
        fig_hist.update_layout(barmode="overlay", template="plotly_white", height=480, xaxis=dict(tickformat=".1%"))
        st.plotly_chart(fig_hist, use_container_width=True)

    # --- 5. 月報酬熱力圖 (新功能) ---
    with tab_heat:
        # 讓使用者選擇要看哪一個策略
        hm_mode = st.radio("選擇要檢視的策略", ["LRS 策略", "槓桿 ETF (Buy & Hold)", "原型 ETF (Buy & Hold)"], horizontal=True)
        
        if hm_mode == "LRS 策略":
            target_series = df["Return_LRS"]
            target_name = "LRS 策略"
        elif hm_mode == "槓桿 ETF (Buy & Hold)":
            target_series = df["Return_lev"]
            target_name = "槓桿 Buy&Hold"
        else:
            target_series = df["Return_base"]
            target_name = "原型 Buy&Hold"
            
        fig_hm = plot_monthly_heatmap(target_series, target_name)
        st.plotly_chart(fig_hm, use_container_width=True)
