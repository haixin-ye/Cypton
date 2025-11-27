
# MACD 金叉/死叉
def check(df):
    """
    输入: 包含完整指标的 DataFrame
    输出: 信号字典 or None
    """
    if len(df) < 5: return None

    # 获取最后两行
    curr = df.iloc[-2]
    prev = df.iloc[-3]

    # 提取 MACD 值 (注意做容错处理)
    # 假设列名是标准名，如果有变化可以用 get
    try:
        dif_now = curr['MACD_12_26_9']
        dea_now = curr['MACDs_12_26_9']
        dif_prev = prev['MACD_12_26_9']
        dea_prev = prev['MACDs_12_26_9']
    except KeyError:
        return None

    signal = None

    # 金叉逻辑: 昨天 DIF < DEA，今天 DIF > DEA
    if dif_prev < dea_prev and dif_now > dea_now:
        signal = {
            "type": "GOLD",
            "position": "MACD",  # 标记画在哪里
            "color": "#00e676",
            "marker": "triangle-up",
            "text": "金叉",
            "price": curr['close'],
            "timestamp": int(curr['timestamp'])
        }

    # 死叉逻辑: 昨天 DIF > DEA，今天 DIF < DEA
    elif dif_prev > dea_prev and dif_now < dea_now:
        signal = {
            "type": "DEATH",
            "position": "MACD",
            "color": "#ff1744",
            "marker": "triangle-down",
            "text": "死叉",
            "price": curr['close'],
            "timestamp": int(curr['timestamp'])
        }

    return signal