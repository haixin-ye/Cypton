# config.py

# ================= 🔧 基础设置 =================
SYMBOL_OKX = "ETH-USDT-SWAP"       # WebSocket 订阅ID
SYMBOL_CCXT = "ETH/USDT:USDT"      # REST API 请求ID
TIMEFRAME = "1m"              # 时间周期 (1m, 5m, 15m, 1h, 4h, 1d)

# ================= 📊 数据长度控制 =================
# 这是核心：后端内存维护长度 = 前端显示长度 = 策略回测长度
# 建议设为 1000~2000，既能保证指标精准，又包含足够长的历史趋势
MAX_DATA_LENGTH = 1000

# ================= 📡 网络设置 =================
PROXY_HOST = "127.0.0.1"      # 代理IP
PROXY_PORT = 7890             # 代理端口

# ================= 💾 文件路径 =================
JSON_FILENAME = "market_data.json"
SIGNAL_FILENAME = "signals.json"

# ================= 🎨 前端显示设置 =================
# 前端图表默认显示多少根K线？(必须 <= MAX_DATA_LENGTH)
# 通常我们不需要一次性在网页上画出2000根，太密了，画最近的200根即可
# 用户可以在网页上缩放查看更多
DISPLAY_CANDLES = 150

# 前端轮询文件的频率 (秒)
POLLING_RATE = 5