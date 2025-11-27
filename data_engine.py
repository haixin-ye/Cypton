import ssl
import ccxt
import websocket
import json
import pandas as pd
import pandas_ta as ta
import time
import threading
import os
from datetime import datetime

# ================= ⚙️ 用户配置区域 =================
SYMBOL_OKX = "ETH-USDT"
SYMBOL_CCXT = "ETH/USDT"
TIMEFRAME = "1m"
HISTORY_LIMIT = 1000
JSON_FILENAME = "market_data.json"
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 7890

# 【新】在这里定义你想要在控制台看到的指标 (即使没写在这里，后台也会计算并保存到JSON)
# 可选值: 'MACD', 'KDJ', 'RSI', 'BOLL', 'CCI', 'ATR', 'EMA'
LOG_INDICATORS = ['MACD', 'KDJ', 'RSI']

global_df = pd.DataFrame()


# ================= 🧮 全指标计算工厂 =================
def calculate_indicators(df):
    """
    计算所有常见指标，但只打印用户选中的
    """
    # 1. MACD (12, 26, 9) -> 结果列: MACD_12_26_9, MACDs_..., MACDh_...
    df.ta.macd(close='close', fast=12, slow=26, signal=9, append=True)

    # 2. 布林带 BOLL (20, 2) -> BBL, BBM, BBU
    df.ta.bbands(close='close', length=20, std=2, append=True)

    # 3. KDJ (9, 3) -> K_9_3, D_9_3, J_9_3
    df.ta.kdj(high='high', low='low', close='close', length=9, signal=3, append=True)

    # 4. RSI 相对强弱 (14) -> RSI_14
    df.ta.rsi(close='close', length=14, append=True)

    # 5. CCI 顺势指标 (14) -> CCI_14_0.015
    df.ta.cci(high='high', low='low', close='close', length=14, append=True)

    # 6. ATR 真实波幅 (14) -> ATR_14
    df.ta.atr(high='high', low='low', close='close', length=14, append=True)

    # 7. EMA 均线组 (7, 25, 99) -> EMA_7, EMA_25, EMA_99
    df.ta.ema(close='close', length=7, append=True)
    df.ta.ema(close='close', length=25, append=True)
    df.ta.ema(close='close', length=99, append=True)

    return df


def save_to_json(df):
    try:
        # 为了前端绘图流畅，我们只保存最近 100 条即可 (虽然前端只画30条，多存点以防万一)
        df_export = df.copy()
        json_str = df_export.tail(100).to_json(orient='records', date_format='iso', force_ascii=False)
        with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(json.loads(json_str), f, indent=4)
    except Exception as e:
        print(f"写入JSON失败: {e}")


# ================= 📡 实时处理逻辑 =================
def process_realtime_kline(kline_data):
    global global_df
    try:
        ts = int(kline_data[0])
        close_p = float(kline_data[4])
        # 构造新行
        new_row = {
            'timestamp': ts,
            'open': float(kline_data[1]), 'high': float(kline_data[2]),
            'low': float(kline_data[3]), 'close': close_p, 'volume': float(kline_data[5]),
            'dt': pd.to_datetime(ts, unit='ms')
        }

        if global_df.empty: return

        last_ts = global_df.iloc[-1]['timestamp']
        action = ""

        # === 分钟切换检测 ===
        if ts > last_ts:
            # 结算上一分钟
            prev = global_df.iloc[-1]
            t_str = (prev['dt'] + pd.Timedelta(hours=8)).strftime('%H:%M')
            print(f"\n======== {t_str} 结算 | 收: {prev['close']} | Vol: {prev['volume']:.1f} ========\n")

            # 新增一行
            global_df = pd.concat([global_df, pd.DataFrame([new_row])], ignore_index=True)
            if len(global_df) > 1500: global_df = global_df.iloc[-1500:].reset_index(drop=True)
            action = "New"
        elif ts == last_ts:
            # 更新当前
            idx = global_df.index[-1]
            global_df.loc[idx, ['high', 'low', 'close', 'volume']] = [new_row['high'], new_row['low'], close_p,
                                                                      new_row['volume']]
            action = "Upd"
        else:
            return

        # === 实时计算 ===
        calculate_indicators(global_df)
        save_to_json(global_df)

        # === 动态构建打印信息 ===
        # 根据 LOG_INDICATORS 配置生成打印字符串
        cur = global_df.iloc[-1]
        log_parts = [f"\r[{datetime.now().strftime('%H:%M:%S')}] {action} Price:{close_p}"]

        if 'MACD' in LOG_INDICATORS:
            macd = cur.get('MACD_12_26_9', 0)
            log_parts.append(f"MACD:{macd:.3f}")
        if 'RSI' in LOG_INDICATORS:
            rsi = cur.get('RSI_14', 0)
            log_parts.append(f"RSI:{rsi:.1f}")
        if 'KDJ' in LOG_INDICATORS:
            j = cur.get('J_9_3', 0)
            log_parts.append(f"KDJ_J:{j:.1f}")
        if 'BOLL' in LOG_INDICATORS:
            up = cur.get('BBU_20_2.0', 0)
            log_parts.append(f"Top:{up:.1f}")

        print(" | ".join(log_parts), end="", flush=True)

    except Exception as e:
        print(f"处理出错: {e}")


# ================= 🚀 基础连接 (保持不变) =================
def init_history_data():
    global global_df
    print(f">>> [1/3] 正在加载过去 {HISTORY_LIMIT} 根 K 线以校准指标...")
    try:
        okx = ccxt.okx(
            {'proxies': {'http': f'http://{PROXY_HOST}:{PROXY_PORT}', 'https': f'http://{PROXY_HOST}:{PROXY_PORT}'}})
        bars = okx.fetch_ohlcv(SYMBOL_CCXT, timeframe=TIMEFRAME, limit=HISTORY_LIMIT)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['dt'] = pd.to_datetime(df['timestamp'], unit='ms')
        calculate_indicators(df)
        global_df = df
        save_to_json(global_df)
        print(f">>> 初始化完成。")
    except Exception as e:
        print(f"初始化失败: {e}")
        os._exit(1)


def on_message(ws, message):
    if message == "pong": return
    try:
        data = json.loads(message)
        if 'data' in data:
            for kline in data['data']:
                process_realtime_kline(kline)
    except:
        pass


def on_open(ws):
    print("\n>>> [2/3] 连接成功，数据流已建立！")
    sub_param = {"op": "subscribe", "args": [{"channel": "candle" + TIMEFRAME, "instId": SYMBOL_OKX}]}
    ws.send(json.dumps(sub_param))
    threading.Thread(target=keep_alive, args=(ws,), daemon=True).start()


def keep_alive(ws):
    while True:
        time.sleep(25)
        if ws.sock and ws.sock.connected:
            try:
                ws.send("ping")
            except:
                break
        else:
            break


if __name__ == "__main__":
    init_history_data()
    ws = websocket.WebSocketApp(
        "wss://ws.okx.com:8443/ws/v5/business",
        on_open=on_open, on_message=on_message,
        on_error=lambda ws, err: print(f"Error: {err}"),
        on_close=lambda ws, *args: print("Closed")
    )
    ws.run_forever(http_proxy_host=PROXY_HOST, http_proxy_port=PROXY_PORT, proxy_type="http", ping_interval=None,
                   sslopt={"cert_reqs": ssl.CERT_NONE})