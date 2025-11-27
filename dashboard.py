import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import os
import config

# 1. 页面配置
st.set_page_config(layout="wide", page_title=f"{config.SYMBOL_OKX} 智能盘口")
st.markdown("""
<style>
    .block-container {
        padding-top: 2rem !important; 
        padding-left: 1rem; 
        padding-right: 1rem;
    }
    header, footer, [data-testid="stElementToolbar"] {display: none;}
    [data-testid="stPlotlyChart"] > div {min-height: 900px;} 
</style>
""", unsafe_allow_html=True)

st.title(f"⚡ {config.SYMBOL_OKX} 智能分析")

# 初始化 Session State
if 'last_ts' not in st.session_state: st.session_state.last_ts = 0
if 'cached_fig' not in st.session_state: st.session_state.cached_fig = None


def load_json(filename):
    try:
        if not os.path.exists(filename): return None
        with open(filename, "r", encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def load_data_safe():
    data = load_json(config.JSON_FILENAME)
    if not data: return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty: return pd.DataFrame()
    df = df.fillna(0)
    df['dt'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai')
    return df


@st.fragment(run_every=config.POLLING_RATE)
def render_chart():
    df = load_data_safe()

    # 基础判空
    if df.empty or len(df) < 5:
        st.warning("⏳ 数据初始化中...")
        return

    # === 第一部分：无论图表刷不刷新，这些数字必须实时跳动 ===
    # 取最新的数据用于显示价格
    last_realtime = df.iloc[-1]
    prev_realtime = df.iloc[-2]

    c1, c2, c3, c4 = st.columns(4)
    # 计算涨跌
    change = last_realtime['close'] - prev_realtime['close']
    c1.metric("Price", f"{last_realtime['close']}", f"{change:.2f}")
    c2.metric("Vol", f"{last_realtime['volume']:.0f}")
    c3.metric("RSI", f"{last_realtime.get('RSI_14', 0):.1f}")
    c4.metric("KDJ (J)", f"{last_realtime.get('J_9_3', 0):.1f}")

    # === 第二部分：图表刷新逻辑 (防闪烁) ===
    current_ts = df.iloc[-1]['timestamp']

    # 如果时间戳没变，且缓存里有图，直接画缓存的图，然后结束函数
    if current_ts == st.session_state.last_ts and st.session_state.cached_fig is not None:
        st.plotly_chart(st.session_state.cached_fig, use_container_width=True, key="static_chart")
        st.caption(f"图表状态: 静态保持 | 价格源: 实时更新")
        return

    # === 第三部分：新K线生成，开始重绘图表 ===
    st.session_state.last_ts = current_ts

    # 截取显示范围
    n_display = min(len(df), config.DISPLAY_CANDLES)
    plot_df = df.tail(n_display).copy()
    signals = load_json(config.SIGNAL_FILENAME) or []

    def get_col(name):
        for col in df.columns:
            if col.startswith(name): return df[col].tail(n_display)
        return pd.Series([0] * n_display)

    # 创建画布
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.5, 0.15, 0.2, 0.15],
        subplot_titles=("Price & BOLL", "Volume", "MACD", "KDJ"),
        specs=[[{"secondary_y": False}]] * 4
    )

    # Row 1: K线
    fig.add_trace(go.Candlestick(
        x=plot_df['dt'], open=plot_df['open'], high=plot_df['high'], low=plot_df['low'], close=plot_df['close'],
        name='KLine', increasing_line_color='#00bfa5', increasing_fillcolor='#00bfa5', decreasing_line_color='#ff5252',
        decreasing_fillcolor='#ff5252'
    ), row=1, col=1)
    # 布林带
    fig.add_trace(
        go.Scatter(x=plot_df['dt'], y=get_col('BBU'), line=dict(color='rgba(255,255,255,0.4)', width=1), name='Upper',
                   showlegend=False), row=1, col=1)
    fig.add_trace(
        go.Scatter(x=plot_df['dt'], y=get_col('BBM'), line=dict(color='rgba(255,255,255,0.6)', width=1, dash='dash'),
                   name='Mid', showlegend=False), row=1, col=1)
    fig.add_trace(
        go.Scatter(x=plot_df['dt'], y=get_col('BBL'), line=dict(color='rgba(255,255,255,0.4)', width=1), name='Lower',
                   showlegend=False), row=1, col=1)

    # Row 2: Volume (清洗0值)
    vol_data = plot_df['volume'].replace(0, 1)
    vol_colors = ['#00bfa5' if c >= o else '#ff5252' for c, o in zip(plot_df['close'], plot_df['open'])]
    fig.add_trace(go.Bar(x=plot_df['dt'], y=vol_data, marker_color=vol_colors, name='Vol', showlegend=False), row=2,
                  col=1)

    # Row 3: MACD (独立坐标)
    hist = get_col('MACDh')
    dif = get_col('MACD')
    dea = get_col('MACDs')
    fig.add_trace(
        go.Bar(x=plot_df['dt'], y=hist, marker_color=['#00bfa5' if v >= 0 else '#ff5252' for v in hist], name='Hist',
               showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df['dt'], y=dif, line=dict(color='#ffeb3b', width=1), name='DIF', showlegend=False),
                  row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df['dt'], y=dea, line=dict(color='#00e5ff', width=1), name='DEA', showlegend=False),
                  row=3, col=1)

    # Row 4: KDJ
    fig.add_trace(
        go.Scatter(x=plot_df['dt'], y=get_col('K_'), line=dict(color='#ff9800', width=1), name='K', showlegend=False),
        row=4, col=1)
    fig.add_trace(
        go.Scatter(x=plot_df['dt'], y=get_col('D_'), line=dict(color='#00e5ff', width=1), name='D', showlegend=False),
        row=4, col=1)
    fig.add_trace(
        go.Scatter(x=plot_df['dt'], y=get_col('J_'), line=dict(color='#d500f9', width=1), name='J', showlegend=False),
        row=4, col=1)

    # 信号标注逻辑
    start_dt, end_dt = plot_df['dt'].min(), plot_df['dt'].max()
    ROW_MAP = {"MAIN": 1, "VOL": 2, "MACD": 3, "KDJ": 4}
    macd_cols = [c for c in plot_df.columns if c.startswith('MACD_') and 's' not in c and 'h' not in c]
    macd_col_name = macd_cols[0] if macd_cols else None

    for sig in signals:
        sig_dt = pd.to_datetime(sig['timestamp'], unit='ms').tz_localize('UTC').tz_convert('Asia/Shanghai')
        if start_dt <= sig_dt <= end_dt:
            pos_key = sig.get('position', 'MAIN')
            target_row = ROW_MAP.get(pos_key, 1)
            target_y = sig['price']

            if pos_key == 'MACD' and target_y == 0 and macd_col_name:
                try:
                    val = plot_df.loc[plot_df['timestamp'] == sig['timestamp'], macd_col_name]
                    if not val.empty: target_y = val.values[0]
                except:
                    pass

            is_bullish = any(x in sig['type'].upper() for x in ["GOLD", "BOTTOM", "UP", "LONG", "BUY"])
            fig.add_annotation(
                x=sig_dt, y=target_y, text=sig['text'],
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
                arrowcolor=sig['color'], bgcolor=sig['color'], bordercolor="white",
                font=dict(color="white", size=10), row=target_row, col=1, ay=30 if is_bullish else -30
            )

    # 布局设置 (剔除0值计算Range)
    valid_prices = plot_df[plot_df['close'] > 0]
    y1_range = None
    if not valid_prices.empty:
        y_min, y_max = valid_prices['low'].min(), valid_prices['high'].max()
        rng = y_max - y_min
        y1_range = [y_min - rng * 0.1, y_max + rng * 0.1]

    fig.update_layout(
        height=900, dragmode=False, xaxis_rangeslider_visible=False,
        plot_bgcolor='#131722', paper_bgcolor='#0e1117', font=dict(color='#b2b5be', size=11),
        margin=dict(l=10, r=50, t=50, b=20),
        legend=dict(orientation="h", yanchor="top", y=1.02, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
        yaxis=dict(range=y1_range, fixedrange=False) if y1_range else {},
        yaxis2=dict(autorange=True, fixedrange=False, matches=None),
        yaxis3=dict(autorange=True, fixedrange=False, matches=None),
        yaxis4=dict(autorange=True, fixedrange=False, matches=None)
    )

    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor='#2a2e39', side='right')

    st.session_state.cached_fig = fig
    st.plotly_chart(fig, use_container_width=True, key="static_chart")
    st.caption(f"图表重绘: {time.strftime('%H:%M:%S')}")


render_chart()