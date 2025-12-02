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


# ================= 🔔 高级预警模块 =================
class AlertManager:
    def __init__(self, config_file='alerts.json', flush_callback=None):
        self.config_file = config_file
        self.last_mtime = 0
        self.rules = []
        self.triggered_cache = set()
        self.enabled = True
        self.check_interval = 2
        self.last_check_time = 0
        self.flush_callback = flush_callback
        self.tolerance_pct = 0.001
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_file): return
        try:
            current_mtime = os.path.getmtime(self.config_file)
            if current_mtime > self.last_mtime:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.enabled = data.get('enable', True)
                    raw_rules = data.get('rules', [])
                    self.rules = []
                    for r in raw_rules:
                        if isinstance(r, list) and len(r) >= 2:
                            try:
                                p = float(r[0])
                                t = str(r[1]).strip()
                                n = str(r[2]) if len(r) > 2 else ""
                                # 第4个参数是指标类型，没写就是 price
                                i = str(r[3]).strip() if len(r) > 3 else "price"
                                self.rules.append([p, t, n, i])
                            except:
                                pass
                self.triggered_cache.clear()
                self.last_mtime = current_mtime
                print(f"🔔 [系统] 配置已热重载！规则数: {len(self.rules)}")
        except Exception as e:
            print(f"⚠️ 读取配置出错: {e}")

    def play_sound(self):
        try:
            sys_plat = platform.system()
            if sys_plat == "Windows":
                import winsound
                # 警报音：急促的三连响
                for _ in range(3):
                    winsound.Beep(2000, 100)
                    winsound.Beep(2500, 100)
            elif sys_plat == "Darwin":
                os.system('afplay /System/Library/Sounds/Glass.aiff')
            else:
                print('\a')
        except:
            pass

    def show_popup(self, value_text, note, rule_type):
        def _popup():
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            self.play_sound()

            titles = {
                'reach': "🎯 目标击中 (Touch)",
                'above': "🚀 向上突破 (Breakout)",
                'below': "📉 向下跌破 (Breakdown)",
                'volatility': "🌊 巨浪预警 (Volatility)"
            }
            title = titles.get(rule_type, "行情预警")

            msg = f"{title}\n\n当前数值: {value_text}\n备注: {note}\n\n(已记录并落盘)"
            messagebox.showwarning(title, msg)
            root.destroy()

        threading.Thread(target=_popup, daemon=True).start()

    # 🔥 修改点：接收三个参数 (Price, RSI, VolRatio)
    def check_market(self, price, rsi, vol_ratio):
        now = time.time()
        if now - self.last_check_time > self.check_interval:
            self.load_config()
            self.last_check_time = now

        if not self.enabled: return
        is_triggered_any = False

        for rule in self.rules:
            # 格式: [Target, Type, Note, Indicator]
            target = rule[0]
            r_type = rule[1]
            note = rule[2]
            indicator = rule[3]

            rule_id = f"{target}_{r_type}_{indicator}"
            if rule_id in self.triggered_cache: continue

            triggered = False
            current_val = 0

            # === 根据指标类型取值 ===
            if r_type == 'volatility':
                current_val = vol_ratio
                # 逻辑：当前波动倍数 >= 设定的倍数
                if vol_ratio >= target:
                    print(f"🌊 [异动] 波动率放大 {vol_ratio:.1f}倍 (阈值: {target}x)")
                    triggered = True

            elif indicator == 'rsi':
                current_val = rsi
                if r_type == 'above' and rsi >= target:
                    triggered = True
                elif r_type == 'below' and rsi <= target:
                    triggered = True
                elif r_type == 'reach' and abs(rsi - target) <= 1.0:
                    triggered = True

            else:  # 默认是 price
                current_val = price
                if r_type == 'above' and price >= target:
                    triggered = True
                elif r_type == 'below' and price <= target:
                    triggered = True
                elif r_type == 'reach' and abs(price - target) <= (target * self.tolerance_pct):
                    triggered = True

            if triggered:
                # 控制台打印
                if r_type != 'volatility':  # 波动率上面打印过了
                    print(f"🔔 [触发] {indicator}:{current_val:.2f} 满足 {r_type} {target}")

                self.triggered_cache.add(rule_id)
                is_triggered_any = True

                # 弹窗显示的内容稍微区分一下
                val_text = f"{current_val:.2f}"
                if r_type == 'volatility':
                    val_text = f"{current_val:.1f} 倍于平均"

                self.show_popup(val_text, note, r_type)

        if is_triggered_any and self.flush_callback:
            self.flush_callback(reason="预警触发")


alert_bot = AlertManager(flush_callback=save_to_disk)


# ================= 🧮 核心算法 (新增波动率计算) =================
def calculate_indicators(df):
    if df.empty: return df
    try:
        # 1. 基础指标
        df.ta.macd(close='close', fast=12, slow=26, signal=9, append=True)
        df.ta.rsi(close='close', length=14, append=True)
        df.ta.kdj(high='high', low='low', close='close', length=9, signal=3, append=True)
        df.ta.bbands(close='close', length=20, std=2, append=True)

        # 🔥 2. 新增：波动率异动计算
        # 计算当前K线震幅 (High - Low)
        df['range'] = df['high'] - df['low']
        # 计算过去20根K线的平均震幅 (作为基准)
        df['avg_range'] = ta.sma(df['range'], length=20)
        # 计算异动倍数 (防止除以0)
        df['vol_ratio'] = df['range'] / df['avg_range'].replace(0, 1)

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


# ================= 📡 实时处理 (传入 VolRatio) =================
def process_message(channel, kline):
    tf = channel.replace("candle", "")
    try:
        ts, open_p, high, low, close_p, vol = int(kline[0]), float(kline[1]), float(kline[2]), float(kline[3]), float(
            kline[4]), float(kline[6])

        # 1. 这里不能先 check，因为波动率需要先把这一行加进去跟历史比，才能算出来
        # 所以我们将 check 逻辑后移

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

            # 重算指标（包含波动率）
            df = calculate_indicators(df)
            DATA_CACHE[tf] = df

            # 提取需要的数值
            current_rsi = df.iloc[-1].get('RSI_14', 50)
            current_vol_ratio = df.iloc[-1].get('vol_ratio', 0)

        # 🔥 2. 只有 1m 周期负责检查报警
        if tf == "1m":
            # 传入三个参数：价格, RSI, 波动率倍数
            alert_bot.check_market(close_p, current_rsi, current_vol_ratio)

        # 🔥 3. 打印日志 (只打 1m)
        if tf == "1m":
            now = datetime.now().strftime('%H:%M:%S')
            # 这里的 VR = Volatility Ratio
            print(f"⚡ [{now}] {tf:<3} | 💰 {close_p:<8} | RSI: {current_rsi:.1f} | VR: {current_vol_ratio:.1f}x")

    except Exception as e:
        print(f"❌ 处理异常: {e}")


# ... (剩下的 on_message, on_open, main 等保持不变，确保包含在文件末尾) ...
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
            time.sleep(25)
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
        time.sleep(2)


def writer_loop():
    print("💾 定时落盘服务启动...")
    while True:
        time.sleep(config.WRITE_INTERVAL)
        save_to_disk(reason="定时")


if __name__ == "__main__":
    init_history()
    threading.Thread(target=writer_loop, daemon=True).start()
    start_ws_loop()