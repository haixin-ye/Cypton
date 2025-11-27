import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

# ================= ⚙️ 用户显示配置 =================
DISPLAY_CANDLES = 30  # 只显示最近多少根 (如 30)
REFRESH_RATE = 1  # 刷新间隔 (秒)

st.set_page_config(layout="wide", page_title="AI Trading Pro")
# 注入 CSS 去除默认边距，让图表尽可能大
st.markdown("""
<style>
    .block-container {padding-top: 0.5rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

st.title(f"⚡ ETH/USDT 实时盘口 (最近 {DISPLAY_CANDLES} 根)")

placeholder = st.empty()


def load_data():
    try:
        with open("market_data.json", "r", encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        # UTC -> 本地时间 (+8)
        df['dt'] = pd.to_datetime(df['dt']).dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai')
        return df
    except:
        return pd.DataFrame()


while True:
    df = load_data()

    if not df.empty:
        # === 核心切片逻辑：只取最近 N 根 ===
        # 如果数据不够，就取全部；如果够，就切片
        n = min(len(df), DISPLAY_CANDLES)
        plot_df = df.tail(n)

        last = plot_df.iloc[-1]
        prev = plot_df.iloc[-2]
        change = last['close'] - prev['close']
        color_code = "normal" if change == 0 else ("inverse" if change > 0 else "off")  # streamlit 颜色逻辑

        with placeholder.container():
            # 1. 顶部数据看板
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Price", f"{last['close']}", f"{change:.2f}")
            c2.metric("Vol", f"{last['volume']:.0f}")
            c3.metric("RSI (14)", f"{last.get('RSI_14', 0):.1f}")
            c4.metric("KDJ (J)", f"{last.get('J_9_3', 0):.1f}")
            c5.metric("ATR (波动)", f"{last.get('ATR_14', 0):.2f}")

            # 2. 绘制组合图 (4行布局)
            # 行高比例：K线图占最大 (50%)
            fig = make_subplots(
                rows=4, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.5, 0.15, 0.2, 0.15],
                specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": False}],
                       [{"secondary_y": False}]]
            )

            # --- Row 1: K线 + EMA + BOLL ---
            # 蜡烛图
            fig.add_trace(go.Candlestick(
                x=plot_df['dt'], open=plot_df['open'], high=plot_df['high'], low=plot_df['low'], close=plot_df['close'],
                name='K线', increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
            ), row=1, col=1)
            # EMA 均线 (7, 25, 99)
            fig.add_trace(
                go.Scatter(x=plot_df['dt'], y=plot_df['EMA_7'], line=dict(color='yellow', width=1), name='EMA7'), row=1,
                col=1)
            fig.add_trace(
                go.Scatter(x=plot_df['dt'], y=plot_df['EMA_25'], line=dict(color='cyan', width=1), name='EMA25'), row=1,
                col=1)
            fig.add_trace(
                go.Scatter(x=plot_df['dt'], y=plot_df['EMA_99'], line=dict(color='magenta', width=2), name='EMA99'),
                row=1, col=1)
            # 布林带 (只画线，去填充，防止遮挡K线)
            fig.add_trace(go.Scatter(x=plot_df['dt'], y=plot_df['BBU_20_2.0'],
                                     line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), name='BBU'), row=1,
                          col=1)
            fig.add_trace(go.Scatter(x=plot_df['dt'], y=plot_df['BBL_20_2.0'],
                                     line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), name='BBL'), row=1,
                          col=1)

            # --- Row 2: Volume ---
            # 颜色随涨跌变
            vol_colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(plot_df['close'], plot_df['open'])]
            fig.add_trace(go.Bar(x=plot_df['dt'], y=plot_df['volume'], marker_color=vol_colors, name='Vol'), row=2,
                          col=1)

            # --- Row 3: MACD ---
            hist_color = ['#26a69a' if v >= 0 else '#ef5350' for v in plot_df['MACDh_12_26_9']]
            fig.add_trace(go.Bar(x=plot_df['dt'], y=plot_df['MACDh_12_26_9'], marker_color=hist_color, name='Hist'),
                          row=3, col=1)
            fig.add_trace(
                go.Scatter(x=plot_df['dt'], y=plot_df['MACD_12_26_9'], line=dict(color='yellow', width=1), name='DIF'),
                row=3, col=1)
            fig.add_trace(
                go.Scatter(x=plot_df['dt'], y=plot_df['MACDs_12_26_9'], line=dict(color='blue', width=1), name='DEA'),
                row=3, col=1)

            # --- Row 4: KDJ ---
            fig.add_trace(go.Scatter(x=plot_df['dt'], y=plot_df['K_9_3'], line=dict(color='orange', width=1), name='K'),
                          row=4, col=1)
            fig.add_trace(go.Scatter(x=plot_df['dt'], y=plot_df['D_9_3'], line=dict(color='cyan', width=1), name='D'),
                          row=4, col=1)
            fig.add_trace(go.Scatter(x=plot_df['dt'], y=plot_df['J_9_3'], line=dict(color='purple', width=1), name='J'),
                          row=4, col=1)

            # === 专业的暗黑风格配置 ===
            fig.update_layout(
                height=900,
                dragmode=False,  # 禁止拖拽，锁定视图
                xaxis_rangeslider_visible=False,
                plot_bgcolor='#131722',
                paper_bgcolor='#0e1117',
                font=dict(color='#b2b5be'),
                margin=dict(l=0, r=60, t=0, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            # 隐藏多余的网格线
            fig.update_xaxes(showgrid=False, zeroline=False)
            fig.update_yaxes(showgrid=True, gridcolor='#2a2e39', zeroline=False, side='right')  # Y轴放右边，符合交易软件习惯

            st.plotly_chart(fig, use_container_width=True)

    time.sleep(REFRESH_RATE)