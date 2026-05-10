#!/usr/bin/env python3
"""
A股量化交易系统 - 统一启动入口
"""

import os
import sys
import argparse
from dotenv import load_dotenv

load_dotenv()

DINGTALK_TOKEN = os.getenv('DINGTALK_ACCESS_TOKEN', '')
DINGTALK_WEBHOOK = f'https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}' if DINGTALK_TOKEN and DINGTALK_TOKEN != 'YOUR_DINGTALK_ACCESS_TOKEN' else ''

sys.path.insert(0, os.path.dirname(__file__))


def run_realtime():
    from strategies.realtime_arb_strategy import AShareRealtimeStrategy, RealtimeDataFetcher, StockSelector, MarketAnalyzer
    fetcher = RealtimeDataFetcher()
    selector = StockSelector(fetcher)
    analyzer = MarketAnalyzer(fetcher)
    strategy = AShareRealtimeStrategy(fetcher, selector, analyzer, dingtalk_webhook=DINGTALK_WEBHOOK)
    strategy.run()


def run_longterm():
    from strategies.long_term_strategy import AShareLongTermStrategy
    strategy = AShareLongTermStrategy(dingtalk_webhook=DINGTALK_WEBHOOK)
    strategy.run_continuous()


def run_super():
    from strategies.super_strategy import SuperStrategy
    strategy = SuperStrategy(dingtalk_webhook=DINGTALK_WEBHOOK)
    strategy.initialize()
    strategy.run_continuous()


def run_t0_etf():
    from strategies.t0_etf_strategy import T0ETFStrategy
    strategy = T0ETFStrategy(dingtalk_webhook=DINGTALK_WEBHOOK)
    strategy.initialize()
    strategy.run_continuous()


def run_dashboard():
    import subprocess
    subprocess.run([sys.executable, '-m', 'streamlit', 'run', 'dashboard.py', '--server.port', '8501'])


def main():
    parser = argparse.ArgumentParser(description='A股量化交易系统')
    parser.add_argument('command', choices=['realtime', 'longterm', 'super', 't0', 'dashboard'],
                        help='运行模式: realtime=短线套利, longterm=长线价值, super=超级策略, t0=ETF T+0, dashboard=看板')
    args = parser.parse_args()

    commands = {
        'realtime': run_realtime,
        'longterm': run_longterm,
        'super': run_super,
        't0': run_t0_etf,
        'dashboard': run_dashboard,
    }

    print('=' * 60)
    print(f'📈 A股量化交易系统 - {args.command} 模式')
    print(f'钉钉通知: {"✅ 已配置" if DINGTALK_WEBHOOK else "❌ 未配置(请在.env中设置)"}')
    print('=' * 60)

    commands[args.command]()


if __name__ == '__main__':
    main()
