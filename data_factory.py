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
import platform
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import config

# ================= 🏗️ 全局内存数据库 =================
DATA_CACHE = {}
DATA_LOCK = threading.RLock()


# ================= 💾 核心功能：数据落盘 =================
def save_to_disk(reason="定时"):
    if not DATA_CACHE: return
    export_data = {}
    with DATA_LOCK:
        for tf, df in DATA_CACHE.items():
            clean_df = df.fillna(0)
            export_data[tf] = clean_df.to_dict(orient='records')
    if not export_data: return
    try:
        temp_file = config.JSON_FILENAME + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f)
        os.replace(temp_file, config.JSON_FILENAME)
        if reason != "定时":
            print(f"💾 [强行落盘] 触发原因: {reason} | 文件已更新!")
    except Exception as e:
        print(f"❌ 写入失败: {e}")


# ================= 🔔 高级预警模块 (矩阵极简版) =================
class AlertManager:
    def __init__(self, config_file='alerts.json', flush_callback=None):
        self.config_file = config_file
        self.last_mtime = 0

        # 规则存储结构：[[price, type, note], ...]
        self.rules = []

        # 内存中记录已触发的规则，防止重复弹窗
        # 格式: { "3500_above": True, ... }
        self.triggered_cache = set()

        self.enabled = True
        self.check_interval = 2
        self.last_check_time = 0
        self.flush_callback = flush_callback
        self.tolerance_pct = 0.0003

        self.load_config()

    def load_config(self):
        """热加载配置"""
        if not os.path.exists(self.config_file): return
        try:
            current_mtime = os.path.getmtime(self.config_file)
            if current_mtime > self.last_mtime:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.enabled = data.get('enable', True)

                    # ⬇️ 关键修改：读取简化版列表 ⬇️
                    raw_rules = data.get('rules', [])
                    self.rules = []

                    # 简单校验一下格式，防止写错
                    for r in raw_rules:
                        if isinstance(r, list) and len(r) >= 2:
                            # 格式化为标准结构 [价格(float), 类型(str), 备注(str)]
                            try:
                                p = float(r[0])
                                t = str(r[1]).strip()
                                n = str(r[2]) if len(r) > 2 else ""
                                self.rules.append([p, t, n])
                            except:
                                print(f"⚠️ 跳过格式错误的规则: {r}")

                # 如果文件被修改了，我们清空触发缓存，这样你可以重新利用已触发的价格
                self.triggered_cache.clear()
                self.last_mtime = current_mtime
                print(f"🔔 [系统] 预警配置已刷新！加载 {len(self.rules)} 条规则 (矩阵模式)")
        except Exception as e:
            print(f"⚠️ 读取配置出错: {e}")

    def play_sound(self):
        try:
            sys_plat = platform.system()
            if sys_plat == "Windows":
                import winsound
                for _ in range(3):
                    winsound.Beep(800, 150)
                    winsound.Beep(1200, 150)
            elif sys_plat == "Darwin":
                os.system('afplay /System/Library/Sounds/Glass.aiff')
            else:
                print('\a')
        except:
            pass

    def show_popup(self, price, note, rule_type):
        def _popup():
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            self.play_sound()

            titles = {
                'reach': "🎯 目标击中 (Touch)!",
                'above': "🚀 向上突破 (Breakout)!",
                'below': "📉 向下跌破 (Breakdown)!"
            }
            title = titles.get(rule_type, "行情预警")

            msg = f"{title}\n\n触发价格: {price}\n预警设定: {note}\n\n(已强行保存数据)"
            messagebox.showwarning(title, msg)
            root.destroy()

        threading.Thread(target=_popup, daemon=True).start()

    def check_price(self, current_price):
        """检查逻辑"""
        now = time.time()
        if now - self.last_check_time > self.check_interval:
            self.load_config()
            self.last_check_time = now

        if not self.enabled: return

        is_triggered_any = False

        # 遍历所有规则
        for rule in self.rules:
            # rule 结构: [price, type, note]
            target = rule[0]
            r_type = rule[1]
            note = rule[2]

            # 生成一个唯一ID，防止重复触发
            # 例如: "3500.0_above"
            rule_id = f"{target}_{r_type}"

            if rule_id in self.triggered_cache:
                continue

            triggered = False

            # === 判定逻辑 ===
            if r_type == 'above':
                if current_price >= target:
                    print(f"🚀 [预警] 突破 {target}! (现价: {current_price})")
                    triggered = True

            elif r_type == 'below':
                if current_price <= target:
                    print(f"🔻 [预警] 跌破 {target}! (现价: {current_price})")
                    triggered = True

            elif r_type == 'reach':
                diff = abs(current_price - target)
                if diff <= (target * self.tolerance_pct):
                    print(f"🎯 [预警] 触碰 {target}! (现价: {current_price})")
                    triggered = True

            if triggered:
                self.triggered_cache.add(rule_id)
                is_triggered_any = True
                self.show_popup(current_price, note, r_type)

        if is_triggered_any and self.flush_callback:
            self.flush_callback(reason=f"预警触发")


# 初始化全局报警器
alert_bot = AlertManager(flush_callback=save_to_disk)


# ================= 🧮 下面代码保持不变 =================
# 为了节省篇幅，下面的 calculate_indicators, init_history,
# process_message, on_message... 等函数完全不需要动。
# 请确保你的文件中包含它们。

def calculate_indicators(df):
    if df.empty: return df
    try:
        df.ta.macd(close='close', fast=12, slow=26, signal=9, append=True)
        df.ta.rsi(close='close', length=14, append=True)
        df.ta.kdj(high='high', low='low', close='close', length=9, signal=3, append=True)
        df.ta.bbands(close='close', length=20, std=2, append=True)
        df['VOL_MA_20'] = ta.sma(df['volume'], length=20)
    except:
        pass
    return df


def init_history():
    print(f"⏳ 正在初始化历史数据 (目标: {config.LIMIT} 条)...")
    okx = ccxt.okx({
        'proxies': {'http': f'http://{config.PROXY_HOST}:{config.PROXY_PORT}',
                    'https': f'http://{config.PROXY_HOST}:{config.PROXY_PORT}'},
        'timeout': 20000
    })
    for tf in config.TIMEFRAMES:
        print(f"   -> 拉取 {tf} ... ", end="")
        try:
            duration_seconds = okx.parse_timeframe(tf)
            lookback_count = int(config.LIMIT * 1.5)
            start_timestamp = okx.milliseconds() - (duration_seconds * 1000 * lookback_count)
            all_ohlcv = []
            current_since = start_timestamp
            while True:
                candles = okx.fetch_ohlcv(config.SYMBOL_REST, timeframe=tf, since=current_since, limit=100)
                if not candles: break
                if not all_ohlcv:
                    all_ohlcv = candles
                else:
                    last_ts = all_ohlcv[-1][0]
                    new_candles = [c for c in candles if c[0] > last_ts]
                    if not new_candles: break
                    all_ohlcv.extend(new_candles)
                if len(candles) < 100: break
                current_since = all_ohlcv[-1][0] + 1
                time.sleep(0.05)
            if len(all_ohlcv) > config.LIMIT: all_ohlcv = all_ohlcv[-config.LIMIT:]
            df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = calculate_indicators(df)
            with DATA_LOCK:
                DATA_CACHE[tf] = df
            print(f"✅ 完成 ({len(df)} 根)")
        except Exception as e:
            print(f"❌ 失败: {e}")
    print("🚀 预热完毕")


def process_message(channel, kline):
    tf = channel.replace("candle", "")
    try:
        ts, open_p, high, low, close_p, vol = int(kline[0]), float(kline[1]), float(kline[2]), float(kline[3]), float(
            kline[4]), float(kline[6])

        # 1. 检查报警 (1m 数据最灵敏，适合做触发源)
        if tf == "1m":
            alert_bot.check_price(close_p)

        # 2. 更新内存 (所有周期都必须更新，不能跳过)
        with DATA_LOCK:
            if tf not in DATA_CACHE: return
            df = DATA_CACHE[tf]
            last_ts = df.iloc[-1]['timestamp'] if not df.empty else 0
            new_row = {'timestamp': ts, 'open': open_p, 'high': high, 'low': low, 'close': close_p, 'volume': vol}

            if ts > last_ts:
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                if len(df) > config.LIMIT: df = df.iloc[-config.LIMIT:].reset_index(drop=True)
            elif ts == last_ts:
                if not df.empty:
                    df.iloc[-1] = new_row
                else:
                    df = pd.DataFrame([new_row])

            df = calculate_indicators(df)
            DATA_CACHE[tf] = df

        # 🔥 3. 优化日志打印：只打印 1m 的数据 🔥
        # 解释：其他周期的价格和 1m 是一样的，重复打印没有意义。
        # 只要看到 1m 在跳动，就证明连接正常。
        if tf == "1m":
            now = datetime.now().strftime('%H:%M:%S')
            rsi_val = df.iloc[-1].get('RSI_14', 0) if not df.empty else 0

            # 这里我稍微优化了一下格式，让它看起来更像一个仪表盘
            # \r 可以让某些终端实现原地刷新，但为了兼容性还是用普通 print
            print(f"⚡ [{now}] {tf:<3} | 💰 {close_p:<8} | RSI: {rsi_val:.1f}")

    except Exception as e:
        print(f"❌ 处理异常: {e}")


def on_message(ws, msg):
    if msg == "pong": return
    try:
        data = json.loads(msg)
        if 'data' in data:
            channel = data['arg']['channel']
            for kline in data['data']: process_message(channel, kline)
    except:
        pass


def on_open(ws):
    print("\n>>> 🟢 连接成功！订阅中...")
    args = [{"channel": f"candle{tf}", "instId": config.SYMBOL_WS} for tf in config.TIMEFRAMES]
    ws.send(json.dumps({"op": "subscribe", "args": args}))

    def heartbeat():
        while ws.sock and ws.sock.connected:
            time.sleep(5)
            try:
                ws.send("ping")
            except:
                break

    threading.Thread(target=heartbeat, daemon=True).start()


def start_ws_loop():
    while True:
        try:
            ws = websocket.WebSocketApp(config.WS_URL, on_open=on_open, on_message=on_message)
            ws.run_forever(http_proxy_host=config.PROXY_HOST, http_proxy_port=config.PROXY_PORT, proxy_type="http",
                           sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=None)
        except Exception:
            pass
        time.sleep(1)


def writer_loop():
    print("💾 定时落盘服务启动...")
    while True:
        time.sleep(config.WRITE_INTERVAL)
        save_to_disk(reason="定时")


if __name__ == "__main__":
    init_history()
    threading.Thread(target=writer_loop, daemon=True).start()
    start_ws_loop()