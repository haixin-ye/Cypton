# config.py

# ================= 🌍 交易所配置 =================
# 注意：OKX 合约叫 "ETH-USDT-SWAP"，现货叫 "ETH-USDT"
# WebSocket 订阅 ID
SYMBOL_WS = "ETH-USDT-SWAP"
# REST API 请求 ID (用于初始化历史)
SYMBOL_REST = "ETH/USDT:USDT"

# 需要监听的周期
TIMEFRAMES = ["1m", "5m", "15m", "1h"]

# 保留的数据长度
LIMIT = 800

# ================= ⚙️ 网络配置 =================
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 7890   # 请确保你的代理端口是这个
WS_URL = "wss://ws.okx.com:8443/ws/v5/business"

# ================= 💾 输出 =================
JSON_FILENAME = "market_factory.json"
WRITE_INTERVAL = 30 # 每5秒强制落盘一次（不管有没有更新，保底）