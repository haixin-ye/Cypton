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
from datetime import datetime
import config

# ================= 🏗️ 全局内存数据库 =================
# 格式: { "1m": DataFrame, "5m": DataFrame ... }
DATA_CACHE = {}
DATA_LOCK = threading.RLock()  # 读写锁


# ================= 🧮 核心算法：特征工程 =================
def calculate_indicators(df):
    """
    对传入的 K 线数据进行全量指标计算
    """
    if df.empty: return df
    try:
        # 1. MACD
        df.ta.macd(close='close', fast=12, slow=26, signal=9, append=True)
        # 2. RSI
        df.ta.rsi(close='close', length=14, append=True)
        # 3. KDJ
        df.ta.kdj(high='high', low='low', close='close', length=9, signal=3, append=True)
        # 4. 布林带
        df.ta.bbands(close='close', length=20, std=2, append=True)
        # 5. 成交量均线
        df['VOL_MA_20'] = ta.sma(df['volume'], length=20)

    except Exception as e:
        # 指标计算偶尔报错不应中断主程序
        pass
    return df


# ================= 🔌 第一步：历史数据预热 =================
def init_history():
    """
    策略：过量预取 + 尾部截断
    确保拿到的一定是【包含当前最新K线】的最后 LIMIT 条数据
    """
    print(f"⏳ 正在初始化历史数据 (目标: {config.LIMIT} 条, 确保最新)...")

    okx = ccxt.okx({
        'proxies': {
            'http': f'http://{config.PROXY_HOST}:{config.PROXY_PORT}',
            'https': f'http://{config.PROXY_HOST}:{config.PROXY_PORT}'
        },
        'timeout': 20000
    })

    for tf in config.TIMEFRAMES:
        print(f"   -> 拉取 {tf} ... ", end="")
        try:
            # 1. 计算【超量】起始时间
            # 我们多预留 50% 的时间缓冲，防止中间有停盘/缺数据导致拉不到最新
            duration_seconds = okx.parse_timeframe(tf)
            # 比如要1000根，我们按1500根的时间跨度去请求
            lookback_count = int(config.LIMIT * 1.5)
            time_span_ms = duration_seconds * 1000 * lookback_count

            start_timestamp = okx.milliseconds() - time_span_ms

            all_ohlcv = []
            current_since = start_timestamp

            # 2. 循环拉取，直到【没有新数据】为止
            while True:
                # 每次请求 100 条 (OKX 某些接口限制较严，用 100 比较稳，反正循环很快)
                limit_per_req = 100

                candles = okx.fetch_ohlcv(config.SYMBOL_REST, timeframe=tf, since=current_since, limit=limit_per_req)

                if not candles:
                    break  # 真的没数据了，退出

                # 数据拼接
                if not all_ohlcv:
                    all_ohlcv = candles
                else:
                    last_ts = all_ohlcv[-1][0]
                    # 过滤掉时间戳重复或旧的数据
                    new_candles = [c for c in candles if c[0] > last_ts]
                    if not new_candles:
                        break  # 虽然有返回，但都是旧数据，说明到头了
                    all_ohlcv.extend(new_candles)

                # 3. 核心判断：是否已经拉到了"未来"或"现在"？
                # 如果这次拉回来的数量少于 limit_per_req，说明已经是最后一页了
                if len(candles) < limit_per_req:
                    break

                # 更新下次起点
                current_since = all_ohlcv[-1][0] + 1
                time.sleep(0.05)  # 极短休眠避免触发频率限制

            # 4. 【尾部截断】：只保留最后(最新)的 LIMIT 条
            if len(all_ohlcv) > config.LIMIT:
                all_ohlcv = all_ohlcv[-config.LIMIT:]

            if not all_ohlcv:
                print("❌ 空数据")
                continue

            # 5. 【时效性校验】：检查最后一条数据的时间是否新鲜
            last_candle_time = datetime.fromtimestamp(all_ohlcv[-1][0] / 1000)
            now_time = datetime.now()
            # 简单打印一下最后一条K线的时间，让你放心
            time_str = last_candle_time.strftime('%H:%M:%S')

            # 转 DataFrame
            df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = calculate_indicators(df)

            with DATA_LOCK:
                DATA_CACHE[tf] = df

            print(f"✅ 完成 (获 {len(df)} 根 | 最新: {time_str})")

        except Exception as e:
            print(f"❌ 失败: {e}")

    print("🚀 历史数据预热完毕，准备接入实时流...")

# ================= 📡 第二步：WebSocket 实时处理 =================

def process_message(channel, kline):
    """
    处理单条推送数据
    """
    # channel 示例: "candle1m" -> "1m"
    tf = channel.replace("candle", "")

    try:
        # OKX 推送格式解析
        ts = int(kline[0])
        open_p = float(kline[1])
        high = float(kline[2])
        low = float(kline[3])
        close_p = float(kline[4])
        vol = float(kline[6])  # 6 是基础货币数量(ETH), 7 是计价货币(USDT)

        with DATA_LOCK:
            if tf not in DATA_CACHE: return
            df = DATA_CACHE[tf]

            last_ts = df.iloc[-1]['timestamp']

            new_row = {
                'timestamp': ts, 'open': open_p, 'high': high, 'low': low,
                'close': close_p, 'volume': vol
            }

            # 逻辑：如果是新的一根K线（时间戳变大），append；如果是同一根，update
            if ts > last_ts:
                # 必须转成 DataFrame 才能 concat
                new_df_row = pd.DataFrame([new_row])
                df = pd.concat([df, new_df_row], ignore_index=True)
                # 保持长度，防止内存溢出
                if len(df) > config.LIMIT:
                    df = df.iloc[-config.LIMIT:].reset_index(drop=True)
            elif ts == last_ts:
                # 更新最后一行
                df.iloc[-1] = new_row

            # 🔥 核心：每次更新数据后，立即重算指标
            # (虽然计算量大，但能保证 AI 拿到的是毫秒级最新的指标)
            df = calculate_indicators(df)
            DATA_CACHE[tf] = df

        # ✅ 实时日志：打印到控制台
        now = datetime.now().strftime('%H:%M:%S')
        # \r 让光标回到行首，实现原地刷新效果，看起来像跳动
        # 但既然你有多个周期，原地刷新会互相覆盖，所以这里用换行打印更清晰
        # 或者只打印特定周期的
        print(f"⚡ [{now}] {tf:<4} | P: {close_p:<8} | V: {int(vol):<5} | RSI: {df.iloc[-1].get('RSI_14', 0):.1f}")

    except Exception as e:
        print(f"❌ 处理异常: {e}")


def on_message(ws, msg):
    """收到消息的回调"""
    if msg == "pong": return  # 忽略心跳包
    try:
        data = json.loads(msg)
        # 检查是否是 K 线数据
        if 'data' in data and 'arg' in data:
            channel = data['arg']['channel']
            for kline in data['data']:
                process_message(channel, kline)
    except:
        pass


def on_open(ws):
    print("\n>>> 🟢 连接成功！发送订阅请求...", flush=True)
    # 构造订阅参数
    args = [{"channel": f"candle{tf}", "instId": config.SYMBOL_WS} for tf in config.TIMEFRAMES]
    ws.send(json.dumps({"op": "subscribe", "args": args}))

    # 启动心跳子线程 (OKX 要求每 25s 发一次 ping)
    def heartbeat():
        while ws.sock and ws.sock.connected:
            time.sleep(25)
            try:
                ws.send("ping")
            except:
                break

    threading.Thread(target=heartbeat, daemon=True).start()


def on_error(ws, error):
    print(f"⚠️ 连接错误: {error}")


def on_close(ws, *args):
    print("🔌 连接断开")


def start_ws_loop():
    """
    死循环维护 WebSocket 连接
    """
    while True:
        try:
            print(f"\n>>> 正在连接 OKX ({config.WS_URL})...")
            ws = websocket.WebSocketApp(
                config.WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            # 阻塞运行
            ws.run_forever(
                http_proxy_host=config.PROXY_HOST,
                http_proxy_port=config.PROXY_PORT,
                proxy_type="http",
                sslopt={"cert_reqs": ssl.CERT_NONE},
                ping_interval=None
            )
        except Exception as e:
            print(f"❌ 启动失败: {e}")

        print("🔁 2秒后尝试重连...")
        time.sleep(2)


# ================= 💾 第三步：定时落盘 =================
def writer_loop():
    """
    独立线程：不管 WebSocket 推送多快，我只按固定频率写磁盘。
    避免 IO 占用过多 CPU。
    """
    print("💾 磁盘写入服务启动...")
    while True:
        time.sleep(config.WRITE_INTERVAL)

        if not DATA_CACHE: continue

        export_data = {}
        with DATA_LOCK:
            for tf, df in DATA_CACHE.items():
                # 转换前做一下清洗，去掉指标计算产生的 NaN
                clean_df = df.fillna(0)
                export_data[tf] = clean_df.to_dict(orient='records')

        if not export_data: continue

        try:
            temp_file = config.JSON_FILENAME + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f)
            os.replace(temp_file, config.JSON_FILENAME)
            # print(f"💾 JSON 已更新 ({len(export_data)} timeframes)")
        except Exception as e:
            print(f"❌ 写入失败: {e}")


# ================= 🚀 主入口 =================
if __name__ == "__main__":
    # 1. 预热
    init_history()

    # 2. 启动写入线程 (Daemon守护线程，主程序挂了它也挂)
    threading.Thread(target=writer_loop, daemon=True).start()

    # 3. 启动采集主循环 (阻塞)
    start_ws_loop()