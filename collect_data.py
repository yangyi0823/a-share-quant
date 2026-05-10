#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收集真实历史数据 - 3-5年
使用baostock获取多年数据
"""
import sys
import importlib.util
from datetime import datetime, timedelta
import numpy as np
import pickle

try:
    import baostock as bs
    BAOSTOCK_AVAILABLE = True
except ImportError:
    BAOSTOCK_AVAILABLE = False
    print("baostock未安装")

spec = importlib.util.spec_from_file_location('super_strategy', '20260429_super_strategy.py')
module = importlib.util.module_from_spec(spec)
sys.modules['super_strategy'] = module
spec.loader.exec_module(module)


def get_long_term_data(stock_code, years=3):
    """获取多年真实历史数据"""
    if not BAOSTOCK_AVAILABLE:
        return None

    try:
        lg = bs.login()
        if lg.error_code != '0':
            return None

        if stock_code.startswith('sh'):
            bs_code = f"sh.{stock_code[2:]}"
        elif stock_code.startswith('sz'):
            bs_code = f"sz.{stock_code[2:]}"
        else:
            bs_code = stock_code

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years)

        rs = bs.query_history_k_data_plus(
            bs_code,
            'date,open,high,low,close,volume,amount',
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            frequency='d',
            adjustflag='2'
        )

        data_list = []
        while rs.error_code == '0' and rs.next():
            row = rs.get_row_data()
            if row[1] and row[5]:
                data_list.append({
                    'date': row[0],
                    'open': float(row[1]),
                    'high': float(row[2]),
                    'low': float(row[3]),
                    'close': float(row[4]),
                    'volume': float(row[5]),
                    'amount': float(row[6]) if row[6] else 0
                })

        bs.logout()
        return data_list

    except Exception as e:
        print(f"  获取{stock_code}数据失败: {e}")
        try:
            bs.logout()
        except:
            pass
        return None


def main():
    print("=" * 80)
    print("收集真实历史数据（3年）")
    print("=" * 80)

    stock_pool = [
        'sh600000', 'sh600036', 'sh600519', 'sh600028', 'sh600030',
        'sh601318', 'sh601398', 'sh601857', 'sh601288', 'sh600031',
        'sz000001', 'sz000002', 'sz000858', 'sz002415', 'sz002594',
        'sz300750', 'sz300760', 'sz300015', 'sz002475', 'sz000333'
    ]

    all_data = {}
    real_count = 0

    print("获取历史数据（3年）...")
    for i, code in enumerate(stock_pool):
        print(f"  [{i+1}/{len(stock_pool)}] {code}...", end=" ", flush=True)
        data = get_long_term_data(code, years=3)
        if data and len(data) >= 500:
            all_data[code] = data
            real_count += 1
            print(f"✅ {len(data)}条")
        else:
            print(f"⚠️ 数据不足({len(data) if data else 0}条)")

    print(f"\n成功获取{real_count}只股票的3年真实数据")

    # 保存数据
    data_file = './historical_data_3y.pkl'
    with open(data_file, 'wb') as f:
        pickle.dump(all_data, f)
    print(f"数据已保存到: {data_file}")

    # 统计
    total_days = 0
    for code, data in all_data.items():
        total_days = max(total_days, len(data))

    print(f"\n数据统计:")
    print(f"  - 股票数量: {len(all_data)}")
    print(f"  - 最大天数: {total_days}")
    print(f"  - 日期范围: {all_data[stock_pool[0]][0]['date']} ~ {all_data[stock_pool[0]][-1]['date']}")

    return all_data


if __name__ == '__main__':
    all_data = main()
