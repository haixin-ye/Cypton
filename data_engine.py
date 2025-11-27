import ssl
import ccxt
import websocket
import json
import pandas as pd
import pandas_ta as ta
import time
import threading
import os
import sys
from datetime import datetime, timedelta

# 引入配置
import config

# === 🔌 导入策略 ===
try:
    from strategies import macd_cross, boll_break, divergence

    STRATEGY_LIST = [macd_cross, boll_break, divergence]
except ImportError as e:
    print(f"❌ 策略加载失败: {e}")
    STRATEGY_LIST = []

global_df = pd.DataFrame()
global_signals = []


# ================= 🧮 指标计算 (必须全量算，保证精度) =================
def calculate_indicators(df):
    """
    注意：指标计算不能只算最近的，必须基于全量历史，
    否则 MACD/EMA 等依赖历史的指标会失真。
    """
    try:
        if df.empty: return df
        df.ta.macd(close='close', fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(close='close', length=20, std=2, append=True)
        df.ta.kdj(high='high', low='low', close='close', length=9, signal=3, append=True)
        df.ta.rsi(close='close', length=14, append=True)
        df.ta.ema(close='close', length=7, append=True)
        df.ta.ema(close='close', length=99, append=True)
        return df
    except:
        return df


# ================= 💾 文件存储 =================
def save_data_to_json(df):
    try:
        df_clean = df.fillna(0).tail(config.MAX_DATA_LENGTH).copy()
        json_str = df_clean.to_json(orient='records', date_format='iso', force_ascii=False)
        temp_file = config.JSON_FILENAME + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(json_str)
        os.replace(temp_file, config.JSON_FILENAME)
    except:
        pass


def save_signals_to_json():
    global global_signals
    try:
        # 既然只计算了最近的，这里直接存就行
        temp_file = config.SIGNAL_FILENAME + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(global_signals, f, indent=4, ensure_ascii=False)
        os.replace(temp_file, config.SIGNAL_FILENAME)
    except:
        pass


# ================= 🧠 核心：只重算可视范围内的策略 =================
def recalculate_recent_signals():
    """
    【性能优化版】
    只重新计算前端 config.DISPLAY_CANDLES 范围内的信号。
    """
    global global_df, global_signals

    # 1. 清空旧信号
    global_signals = []

    total = len(global_df)
    # 至少需要 50 根数据才能开始算策略
    if total < 50: return

    # 2. 确定计算范围 (只算最近 N 根)
    # 起点 = 总长度 - 显示长度
    # 但起点不能小于 50 (预热缓冲)
    display_range = config.DISPLAY_CANDLES
    start_idx = max(50, total - display_range)

    # 3. 循环回测 (范围大大缩小，速度极快)
    for i in range(start_idx, total + 1):

        # 切片：模拟当时的数据环境
        current_slice = global_df.iloc[:i]

        for strategy in STRATEGY_LIST:
            try:
                sig = strategy.check(current_slice)

                if sig:
                    dt_str = (pd.to_datetime(sig['timestamp'], unit='ms') + timedelta(hours=8)).strftime('%m-%d %H:%M')
                    sig['dt_str'] = dt_str

                    # 查重 (虽然清空了列表，但在同一时刻不同策略可能触发)
                    is_duplicate = False
                    if len(global_signals) > 0:
                        last = global_signals[-1]
                        if last['timestamp'] == sig['timestamp'] and last['type'] == sig['type']:
                            is_duplicate = True

                    if not is_duplicate:
                        global_signals.append(sig)
            except:
                pass

    # 4. 保存
    save_signals_to_json()


# ================= 📡 实时逻辑 =================
def process_realtime_kline(kline_data):
    global global_df
    try:
        ts = int(kline_data[0])
        close_p = float(kline_data[4])
        new_row = {
            'timestamp': ts,
            'open': float(kline_data[1]), 'high': float(kline_data[2]),
            'low': float(kline_data[3]), 'close': close_p,
            'volume': float(kline_data[7]),
            'dt': pd.to_datetime(ts, unit='ms')
        }

        if global_df.empty: return
        last_ts = global_df.iloc[-1]['timestamp']

        # === 情况 A: 换线时刻 ===
        if ts > last_ts:
            prev = global_df.iloc[-1]
            t_str = (prev['dt'] + timedelta(hours=8)).strftime('%H:%M')
            sys.stdout.write(f"\n✅ [{t_str}] 1m 结线 | 收: {prev['close']}\n")

            global_df = pd.concat([global_df, pd.DataFrame([new_row])], ignore_index=True)

            if len(global_df) > config.MAX_DATA_LENGTH:
                global_df = global_df.iloc[-config.MAX_DATA_LENGTH:].reset_index(drop=True)

            # 1. 计算指标 (全量，为了准)
            calculate_indicators(global_df)

            # 2. 计算策略 (只算最近的，为了快)
            # sys.stdout.write(f"    ⟳ 正在更新最近 {config.DISPLAY_CANDLES} 根K线的策略状态...")
            sys.stdout.flush()

            recalculate_recent_signals()

            # sys.stdout.write(" 完成\n")
            sys.stdout.flush()

        # === 情况 B: 实时跳动 ===
        elif ts == last_ts:
            idx = global_df.index[-1]
            global_df.loc[idx, ['high', 'low', 'close', 'volume']] = [new_row['high'], new_row['low'], close_p,
                                                                      new_row['volume']]

        save_data_to_json(global_df)

        now = datetime.now().strftime('%H:%M:%S')
        sys.stdout.write(f"\r🚀 [{now}] 监控中... P: {close_p:<8}   ")
        sys.stdout.flush()

    except Exception as e:
        print(f"\nErr: {e}")


# ================= 🚀 初始化 =================
def init_history_data():
    global global_df
    print(">>> [1/3] 初始化历史数据...", flush=True)
    try:
        okx = ccxt.okx({'proxies': {'http': f'http://{config.PROXY_HOST}:{config.PROXY_PORT}',
                                    'https': f'http://{config.PROXY_HOST}:{config.PROXY_PORT}'}, 'timeout': 20000})

        # 简单拉取
        bars = okx.fetch_ohlcv(config.SYMBOL_CCXT, timeframe=config.TIMEFRAME, limit=config.MAX_DATA_LENGTH)

        if not bars:
            print("❌ 获取数据失败", flush=True);
            os._exit(1)

        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = df.astype(float)
        df['dt'] = pd.to_datetime(df['timestamp'], unit='ms')

        calculate_indicators(df)
        global_df = df

        # 初始计算 (也只算可视范围的)
        print(f">>> [2/3] 初始计算 (最近 {config.DISPLAY_CANDLES} 根)...", flush=True)
        recalculate_recent_signals()

        save_data_to_json(global_df)
        print(">>> 初始化完成。", flush=True)
    except Exception as e:
        print(f"初始化失败: {e}", flush=True);
        os._exit(1)


def on_message(ws, msg):
    if msg == "pong": return
    try:
        data = json.loads(msg)
        if 'data' in data:
            for k in data['data']: process_realtime_kline(k)
    except:
        pass


if __name__ == "__main__":
    global_signals = []
    try:
        if os.path.exists(config.JSON_FILENAME): os.remove(config.JSON_FILENAME)
        if os.path.exists(config.SIGNAL_FILENAME): os.remove(config.SIGNAL_FILENAME)
    except:
        pass

    init_history_data()

    print("\n>>> WebSocket 连接中...", flush=True)

    ws = websocket.WebSocketApp("wss://ws.okx.com:8443/ws/v5/business",
                                on_open=lambda ws: (
                                    print(">>> 连接成功! 等待数据...", flush=True),
                                    ws.send(json.dumps({"op": "subscribe", "args": [
                                        {"channel": "candle" + config.TIMEFRAME, "instId": config.SYMBOL_OKX}]})),
                                    threading.Thread(
                                        target=lambda: [time.sleep(25) or ws.send("ping") for _ in iter(int, 1)],
                                        daemon=True).start()
                                ),
                                on_message=on_message)

    ws.run_forever(http_proxy_host=config.PROXY_HOST, http_proxy_port=config.PROXY_PORT, proxy_type="http",
                   sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=None)