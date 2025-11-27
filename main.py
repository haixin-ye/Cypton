import subprocess
import sys
import time
import os
import signal

# 定义文件名称
BACKEND_SCRIPT = "data_engine.py"
FRONTEND_SCRIPT = "dashboard.py"


def run_system():
    print(f"🚀 正在启动 AI 交易全栈系统...")
    print(f"📂 当前解释器路径: {sys.executable}")

    # 1. 启动后端 (数据引擎)
    # 使用 sys.executable 确保用的是当前 conda 环境的 python
    print(f" -> 正在启动后端引擎 ({BACKEND_SCRIPT})...")
    backend_process = subprocess.Popen(
        [sys.executable, BACKEND_SCRIPT],
        cwd=os.path.dirname(os.path.abspath(__file__)),  # 确保在当前目录运行
        shell=False
    )

    # 给后端一点时间先跑起来 (防止前端读取时 JSON 还没生成)
    time.sleep(2)

    # 2. 启动前端 (Streamlit)
    # 相当于在命令行执行: python -m streamlit run dashboard.py
    print(f" -> 正在启动可视化看板 ({FRONTEND_SCRIPT})...")
    frontend_process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", FRONTEND_SCRIPT],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        shell=False
    )

    print("\n✅ 系统启动成功！")
    print("   后端正在后台搬砖...")
    print("   前端网页即将自动弹出...")
    print("\n[按 Ctrl+C 可以一键关闭所有程序]")

    try:
        # 主进程进入死循环，等待用户按 Ctrl+C
        # 同时监测两个子进程是否意外挂了
        while True:
            time.sleep(1)
            if backend_process.poll() is not None:
                print("❌ 警告：后端引擎意外退出了！")
                break
            if frontend_process.poll() is not None:
                print("❌ 警告：前端页面意外退出了！")
                break

    except KeyboardInterrupt:
        print("\n\n🛑 正在停止所有服务...")
    finally:
        # 3. 优雅地杀掉子进程
        backend_process.terminate()
        frontend_process.terminate()
        # 确保它们死透了
        backend_process.wait()
        frontend_process.wait()
        print("👋 再见！")


if __name__ == "__main__":
    run_system()