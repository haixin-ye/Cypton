import pandas as pd


def check(df):
    """
    MACD 顶背离与底背离识别策略
    """
    if len(df) < 50: return None

    # 只看最近 60 根
    df_slice = df.tail(60).copy().reset_index(drop=True)

    # 寻找波峰/波谷的窗口大小
    order = 5

    # === 寻找波峰 (Highs) ===
    peaks = []
    for i in range(order, len(df_slice) - order):
        current = df_slice.loc[i, 'high']
        if (df_slice.loc[i - order:i - 1, 'high'] < current).all() and \
                (df_slice.loc[i + 1:i + order, 'high'] < current).all():
            peaks.append(i)

    # === 寻找波谷 (Lows) ===
    valleys = []
    for i in range(order, len(df_slice) - order):
        current = df_slice.loc[i, 'low']
        if (df_slice.loc[i - order:i - 1, 'low'] > current).all() and \
                (df_slice.loc[i + 1:i + order, 'low'] > current).all():
            valleys.append(i)

    last_idx = len(df_slice) - 1
    signal = None

    # === 顶背离 (看跌) ===
    if len(peaks) >= 2:
        p2 = peaks[-1]
        p1 = peaks[-2]

        # 只看最近确认的信号
        if last_idx - p2 <= 7:
            price_p1 = df_slice.loc[p1, 'high']
            price_p2 = df_slice.loc[p2, 'high']
            macd_p1 = df_slice.loc[p1, 'MACD_12_26_9']
            macd_p2 = df_slice.loc[p2, 'MACD_12_26_9']

            # 价格新高，MACD没新高
            if price_p2 > price_p1 and macd_p2 < macd_p1 and macd_p1 > 0:
                signal = {
                    "type": "DIV_TOP",
                    "position": "MAIN",
                    "color": "#ff1744",  # 红色
                    "text": "顶背离",
                    # 【关键修改】直接传最高价，不加偏移，让前端决定箭头位置
                    "price": float(price_p2),
                    "timestamp": int(df_slice.loc[p2, 'timestamp'])
                }

    # === 底背离 (看涨) ===
    if len(valleys) >= 2:
        v2 = valleys[-1]
        v1 = valleys[-2]

        if last_idx - v2 <= 7:
            price_v1 = df_slice.loc[v1, 'low']
            price_v2 = df_slice.loc[v2, 'low']
            macd_v1 = df_slice.loc[v1, 'MACD_12_26_9']
            macd_v2 = df_slice.loc[v2, 'MACD_12_26_9']

            # 价格新低，MACD没新低
            if price_v2 < price_v1 and macd_v2 > macd_v1 and macd_v1 < 0:
                signal = {
                    "type": "DIV_BOTTOM",
                    "position": "MAIN",
                    "color": "#00e676",  # 绿色
                    "text": "底背离",
                    # 【关键修改】直接传最低价
                    "price": float(price_v2),
                    "timestamp": int(df_slice.loc[v2, 'timestamp'])
                }

    return signal