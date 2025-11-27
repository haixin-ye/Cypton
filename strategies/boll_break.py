def check(df):
    """
    布林带突破策略 (确认线逻辑)
    """
    # 至少需要 4-5 根数据来对比 -2 和 -3
    if len(df) < 5: return None

    # 获取【刚走完】的两根K线
    # curr = 刚刚确定的那根 (倒数第2根)
    # prev = 再前一根 (倒数第3根)
    curr = df.iloc[-2]
    prev = df.iloc[-3]

    signal = None

    # 尝试获取布林带列名 (pandas_ta 默认通常是 BBU_20_2.0)
    # 为了防止列名报错，建议检查一下 keys，或者使用 try-except
    try:
        up_curr = curr['BBU_20_2.0']
        low_curr = curr['BBL_20_2.0']
        up_prev = prev['BBU_20_2.0']
        low_prev = prev['BBL_20_2.0']
    except KeyError:
        # 如果还没计算出布林带指标，直接返回
        return None

    # === 向上突破逻辑 ===
    # 逻辑：前一根收盘 <= 上轨，当前根收盘 > 上轨 (这就叫"突破瞬间")
    if prev['close'] <= up_prev and curr['close'] > up_curr:
        signal = {
            "type": "BOLL_UP",
            "position": "MAIN",
            "color": "#ff9100", # 橙色
            "marker": "star",
            "text": "破上轨",
            "price": curr['high'],
            "timestamp": int(curr['timestamp'])
        }

    # === 向下突破逻辑 ===
    # 逻辑：前一根收盘 >= 下轨，当前根收盘 < 下轨
    elif prev['close'] >= low_prev and curr['close'] < low_curr:
        signal = {
            "type": "BOLL_DOWN",
            "position": "MAIN",
            "color": "#2979ff", # 蓝色
            "marker": "star",
            "text": "破下轨",
            "price": curr['low'],
            "timestamp": int(curr['timestamp'])
        }

    return signal