#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【超级策略】A股超短线 - AI驱动版
核心目标：胜率 > 80%，持续自我进化
集成：Alpha101因子 + LightGBM + 深度学习
"""

import os
import sys
import time
import json
import random
import threading
import requests
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from collections import defaultdict, deque

ETF_T0_AVAILABLE = False
try:
    sys.path.insert(0, '.')
    from etf_t0_predictor import ETFT0Predictor
    ETF_T0_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ ETF T+0预测模块未加载: {e}")

# AI模型库
try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    print("⚠️ LightGBM未安装，使用简化模型")

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ sklearn未安装，使用简化模型")

# ==========================================
# 策略参数配置
# ==========================================
PARAMS = {
    'lookback_days': 250,           # 历史数据回溯天数（1年）
    'update_interval': 30,          # 更新间隔（秒）
    'stop_loss': 0.02,              # 止损2%
    'take_profit': 0.03,           # 止盈3%
    'max_position': 0.15,          # 单品种最大仓位15%
    'total_position': 0.85,        # 总仓位上限85%
    'min_volume_ratio': 0.8,       # 最小量比
    'entry_threshold': 0.75,       # 买入阈值
    'exit_threshold': 0.25,        # 卖出阈值
    'max_drawdown': 0.08,          # 最大回撤8%
    'learning_rate': 0.15,         # 学习率
    'gamma': 0.9,                 # Q-Learning折扣因子
    'strategy_version': 'v7.0-comprehensive-eval'
}

MODEL_FILE = './super_model.json'

# ==========================================
# 数据获取模块
# ==========================================
class SuperDataFetcher:
    def __init__(self):
        pass

    def get_realtime_data(self, code):
        """获取实时行情（腾讯接口）"""
        try:
            url = f"http://qt.gtimg.cn/q={code}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                text = response.text.strip()
                if 'v_pv_none_match' in text or not text:
                    return None

                parts = text.split('~')
                if len(parts) > 40:
                    name = parts[1]
                    price = float(parts[3]) if parts[3] else 0
                    open_p = float(parts[5]) if parts[5] else 0
                    high = float(parts[33]) if parts[33] else 0
                    low = float(parts[34]) if parts[34] else 0
                    volume = float(parts[6]) if parts[6] else 0
                    change_pct = float(parts[32]) if parts[32] else 0
                    
                    # 获取昨日收盘价
                    prev_close = float(parts[4]) if parts[4] else 0
                    
                    # 涨停价计算（A股涨停10%，ST股5%，科创板/创业板20%）
                    if prev_close > 0:
                        if code.startswith('sh688') or code.startswith('sz300'):
                            limit_up = prev_close * 1.20  # 科创板/创业板20%
                        elif 'ST' in name or 'st' in name:
                            limit_up = prev_close * 1.05  # ST股5%
                        else:
                            limit_up = prev_close * 1.10  # 普通股10%
                    else:
                        limit_up = price * 1.10
                    
                    # 判断是否涨停（价格接近涨停价，涨幅接近涨停幅度）
                    is_limit_up = False
                    if prev_close > 0 and price > 0:
                        limit_pct = (price - prev_close) / prev_close
                        is_limit_up = limit_pct >= 0.095  # 涨幅超过9.5%视为涨停
                    
                    # 获取买卖盘口数据
                    bid1_price = float(parts[9]) if len(parts) > 9 and parts[9] else price
                    bid1_volume = float(parts[10]) if len(parts) > 10 and parts[10] else 0
                    ask1_price = float(parts[19]) if len(parts) > 19 and parts[19] else price
                    ask1_volume = float(parts[20]) if len(parts) > 20 and parts[20] else 0
                    
                    # 计算封单量（涨停时买一量，跌停时卖一量）
                    limit_up_volume = bid1_volume if is_limit_up else 0

                    if price > 0:
                        return {
                            'code': code,
                            'name': name,
                            'price': price,
                            'open': open_p,
                            'high': high,
                            'low': low,
                            'volume': volume,
                            'change_pct': change_pct,
                            'prev_close': prev_close,
                            'limit_up': limit_up,
                            'is_limit_up': is_limit_up,
                            'limit_up_volume': limit_up_volume,
                            'bid1_price': bid1_price,
                            'bid1_volume': bid1_volume,
                            'ask1_price': ask1_price,
                            'ask1_volume': ask1_volume
                        }
        except Exception as e:
            pass
        return None

    def get_batch_realtime(self, codes):
        """批量获取实时数据"""
        result = {}
        for code in codes:
            data = self.get_realtime_data(code)
            if data:
                result[code] = data
            time.sleep(0.03)
        return result

    def get_historical_data(self, code, days=250):
        """获取历史数据（多数据源备用）"""
        # 方法1: 新浪财经API
        try:
            market = 'sh' if code.startswith('sh') else 'sz'
            stock_code = code[2:]
            url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
            params = {
                'symbol': f'{market}{stock_code}',
                'scale': '240',
                'ma': 'no',
                'datalen': str(days)
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                import json
                try:
                    data = json.loads(response.text)
                    if isinstance(data, list) and len(data) > 0:
                        result = []
                        for item in data[-days:]:
                            result.append({
                                'date': item.get('day', ''),
                                'open': float(item.get('open', 0)),
                                'close': float(item.get('close', 0)),
                                'high': float(item.get('high', 0)),
                                'low': float(item.get('low', 0)),
                                'volume': float(item.get('volume', 0)),
                                'turnover': 0
                            })
                        if result:
                            return result
                except:
                    pass
        except Exception as e:
            pass

        # 方法2: 腾讯API
        try:
            market = 1 if code.startswith('sh') else 0
            stock_code = code[2:]
            url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            params = {
                '_var': f'kline_day_{code}',
                'param': f'{market}{stock_code},day,,,{days},',
                'r': str(int(time.time() * 1000))
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                text = response.text
                if 'kline_day' in text:
                    import re
                    data_str = re.search(r'kline_day_\w+="(.*?)"', text)
                    if data_str:
                        lines = data_str.group(1).split(';')
                        result = []
                        for line in lines[-days:]:
                            parts = line.split(',')
                            if len(parts) >= 6:
                                result.append({
                                    'date': parts[0],
                                    'open': float(parts[1]) if parts[1] else 0,
                                    'close': float(parts[2]) if parts[2] else 0,
                                    'high': float(parts[3]) if parts[3] else 0,
                                    'low': float(parts[4]) if parts[4] else 0,
                                    'volume': float(parts[5]) if parts[5] else 0,
                                    'turnover': 0
                                })
                        if result:
                            return result
        except Exception as e:
            pass

        # 方法3: 东方财富API
        for retry in range(3):
            try:
                secid = f"1.{code[2:]}" if code.startswith('sh') else f"0.{code[2:]}"
                url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
                params = {
                    'secid': secid,
                    'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
                    'fields1': 'f1,f2,f3,f4,f5,f6',
                    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                    'klt': '101',
                    'fqt': '1',
                    'beg': (datetime.now() - timedelta(days=days+30)).strftime('%Y%m%d'),
                    'end': datetime.now().strftime('%Y%m%d'),
                    'rtntype': '6'
                }
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'http://quote.eastmoney.com/'
                }
                response = requests.get(url, params=params, headers=headers, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    if data and 'data' in data and data['data'] and 'klines' in data['data']:
                        klines = data['data']['klines']
                        result = []
                        for kline in klines[-days:]:
                            parts = kline.split(',')
                            if len(parts) > 10:
                                result.append({
                                    'date': parts[0],
                                    'open': float(parts[1]),
                                    'close': float(parts[2]),
                                    'high': float(parts[3]),
                                    'low': float(parts[4]),
                                    'volume': float(parts[5]) if parts[5] else 0,
                                    'turnover': float(parts[10]) if len(parts) > 10 and parts[10] else 0
                                })
                        if result:
                            return result
            except Exception as e:
                if retry < 2:
                    time.sleep(1)
                    continue
        
        print(f"⚠️ 获取{code}历史数据失败")
        return []

# ==========================================
# 热点板块识别模块 - 学习陈小群风格
# ==========================================
class HotSectorAnalyzer:
    """热点板块识别器 - 只做龙头，不干杂毛 - 一切来自实盘"""
    
    def __init__(self, fetcher):
        self.fetcher = fetcher
    
    def get_realtime_ranking(self, top_n=50):
        """从实盘获取涨幅榜"""
        try:
            # 东方财富涨幅榜API
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1,
                'pz': top_n,
                'po': 1,
                'np': 1,
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
                'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13'
            }
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data and 'data' in data and 'diff' in data['data']:
                    stocks = []
                    for item in data['data']['diff']:
                        code = item.get('f12', '')
                        name = item.get('f14', '')
                        change_pct = item.get('f3', 0) / 100  # 涨幅
                        volume = item.get('f5', 0)  # 成交量
                        amount = item.get('f6', 0)  # 成交额
                        
                        # 转换代码格式
                        if code.startswith('6'):
                            full_code = f'sh{code}'
                        else:
                            full_code = f'sz{code}'
                        
                        stocks.append({
                            'code': full_code,
                            'name': name,
                            'change_pct': change_pct,
                            'volume': volume,
                            'amount': amount
                        })
                    
                    return stocks
        except Exception as e:
            print(f"获取涨幅榜失败: {e}")
        
        return []
    
    def identify_hot_sectors_from_realtime(self, ranking_stocks):
        """从实盘涨幅榜识别热点板块"""
        # 根据涨幅榜股票的共性识别热点
        # 这里简化处理：将涨幅>5%的股票作为热点股票池
        hot_stocks = [s for s in ranking_stocks if s['change_pct'] > 0.05]
        
        if not hot_stocks:
            return []
        
        # 按涨幅排序
        hot_stocks.sort(key=lambda x: x['change_pct'], reverse=True)
        
        return hot_stocks[:10]  # 返回前10只热点股票
    
    def find_sector_leader_from_realtime(self, ranking_stocks):
        """从实盘涨幅榜找出龙头股"""
        if not ranking_stocks:
            return None
        
        # 涨幅榜第一只股票就是龙头
        leader = ranking_stocks[0]
        
        # 获取实时数据
        realtime_data = self.fetcher.get_realtime_data(leader['code'])
        
        if realtime_data:
            return {
                'code': leader['code'],
                'name': leader['name'],
                'change_pct': leader['change_pct'],
                'score': leader['change_pct'] * 10,  # 评分基于涨幅
                'data': realtime_data
            }
        
        return None

# ==========================================
# 市场情绪分析模块
# ==========================================
class SuperSentimentAnalyzer:
    def __init__(self, fetcher):
        self.fetcher = fetcher

    def get_market_sentiment(self):
        """获取市场情绪"""
        try:
            url = "http://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000300"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                lines = response.text.strip().split(';')
                changes = []
                volumes = []
                for line in lines:
                    parts = line.split('~')
                    if len(parts) > 32 and parts[32]:
                        changes.append(float(parts[32]))
                    if len(parts) > 6 and parts[6]:
                        volumes.append(float(parts[6]))

                if changes:
                    avg_change = np.mean(changes)
                    vol_ratio = np.mean(volumes[-3:]) / np.mean(volumes[:-3]) if len(volumes) > 6 else 1

                    sentiment = 0.5
                    if avg_change > 2.0:
                        sentiment = 1.0
                    elif avg_change > 1.0:
                        sentiment = 0.85
                    elif avg_change > 0.5:
                        sentiment = 0.7
                    elif avg_change > 0:
                        sentiment = 0.55
                    elif avg_change > -0.5:
                        sentiment = 0.4
                    elif avg_change > -1.0:
                        sentiment = 0.25
                    else:
                        sentiment = 0.1

                    if vol_ratio > 1.5:
                        sentiment = min(1.0, sentiment + 0.15)
                    elif vol_ratio < 0.7:
                        sentiment = max(0.0, sentiment - 0.15)

                    return sentiment
        except:
            pass
        return 0.5

    def get_sector_sentiment(self):
        """获取板块情绪（简化版）"""
        return 0.5

# ==========================================
# 超级因子系统 - 40+因子
# ==========================================
class SuperFactorEngine:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.historical_data = {}
        self.pattern_database = {}

    def load_data(self, code):
        """加载历史数据"""
        if code not in self.historical_data:
            self.historical_data[code] = self.fetcher.get_historical_data(code, PARAMS['lookback_days'])
        return self.historical_data[code]

    def calculate_all_factors(self, code, realtime_data=None):
        """计算所有因子"""
        hist = self.load_data(code)
        if len(hist) < 60:
            return None

        factors = {}
        current = realtime_data['price'] if realtime_data else hist[-1]['close']
        closes = [h['close'] for h in hist]
        volumes = [h['volume'] for h in hist]
        highs = [h['high'] for h in hist]
        lows = [h['low'] for h in hist]
        opens = [h['open'] for h in hist]

        # ========== 技术指标因子 (10个) ==========
        factors.update(self._technical_indicators(closes, current, highs, lows, volumes, opens))

        # ========== 量价关系因子 (8个) ==========
        factors.update(self._volume_price_analysis(closes, volumes, highs, lows, realtime_data))

        # ========== 动量与趋势因子 (6个) ==========
        factors.update(self._momentum_trend(closes, current))

        # ========== 反转与均值回归因子 (5个) ==========
        factors.update(self._reversion_mean(closes, current, highs, lows))

        # ========== 波动率因子 (4个) ==========
        factors.update(self._volatility_analysis(closes, current))

        # ========== 形态识别因子 (4个) ==========
        factors.update(self._pattern_recognition(closes, current, highs, lows))

        # ========== 市场微观结构因子 (3个) ==========
        factors.update(self._market_microstructure(closes, current, volumes, realtime_data))

        # ========== Alpha101顶级因子 (10个) ==========
        factors.update(self._alpha101_factors(closes, volumes, highs, lows, opens, current))

        return factors

    def _technical_indicators(self, closes, current, highs, lows, volumes, opens):
        factors = {}

        # MA均线系统
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        ma60 = np.mean(closes[-60:])

        ma_score = 0
        if current > ma5 > ma10 > ma20 > ma60:
            ma_score = 1.0
        elif current > ma5 > ma10 > ma20:
            ma_score = 0.9
        elif current > ma5 > ma10:
            ma_score = 0.75
        elif current > ma5:
            ma_score = 0.6
        elif ma5 > ma10 > ma20:
            ma_score = 0.5
        elif current < ma5 and ma5 < ma10:
            ma_score = 0.2
        factors['ma_system'] = ma_score

        # MACD
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        diff = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
        dea = self._ema(diff, 9)
        macd = [(d - de) * 2 for d, de in zip(diff, dea)]
        if len(macd) >= 5:
            if macd[-1] > 0 and macd[-1] > macd[-2] > macd[-3]:
                factors['macd'] = 1.0
            elif macd[-1] > 0 and macd[-1] > macd[-2]:
                factors['macd'] = 0.8
            elif macd[-1] > 0:
                factors['macd'] = 0.6
            elif macd[-1] < 0 and macd[-1] < macd[-2]:
                factors['macd'] = 0.1
            else:
                factors['macd'] = 0.4
        else:
            factors['macd'] = 0.5

        # RSI
        rsi = self._rsi(closes, 14)
        rsi_6 = self._rsi(closes, 6)
        if 40 < rsi < 60:
            factors['rsi'] = 0.6
        elif 20 < rsi < 40 and rsi > rsi_6:
            factors['rsi'] = 0.9
        elif rsi < 20:
            factors['rsi'] = 1.0
        elif 60 < rsi < 80 and rsi < rsi_6:
            factors['rsi'] = 0.3
        elif rsi > 80:
            factors['rsi'] = 0.0
        else:
            factors['rsi'] = 0.5

        # KDJ
        k, d, j = self._kdj(closes, highs, lows)
        if len(k) > 3:
            if k[-1] < 20 and d[-1] < 20 and k[-1] > d[-1] and k[-2] <= d[-2]:
                factors['kdj'] = 1.0
            elif k[-1] < 30 and k[-1] > d[-1]:
                factors['kdj'] = 0.8
            elif k[-1] > 80 and d[-1] > 80:
                factors['kdj'] = 0.0
            elif k[-1] > 70 and k[-1] < d[-1]:
                factors['kdj'] = 0.2
            else:
                factors['kdj'] = 0.5
        else:
            factors['kdj'] = 0.5

        # 布林带
        bb_upper, bb_mid, bb_lower = self._bollinger_bands(closes, 20)
        bb_width = (bb_upper - bb_lower) / bb_mid
        if current < bb_lower:
            factors['bollinger'] = 1.0
        elif current > bb_upper:
            factors['bollinger'] = 0.0
        elif bb_width < 0.03:
            factors['bollinger'] = 0.7
        else:
            factors['bollinger'] = 0.5 + (bb_mid - current) / (bb_upper - bb_lower) * 0.5

        # 威廉指标
        wr = self._williams_r(closes, highs, lows, 14)
        if wr > -20:
            factors['williams_r'] = 0.0
        elif wr > -50:
            factors['williams_r'] = 0.3
        elif wr > -80:
            factors['williams_r'] = 0.7
        else:
            factors['williams_r'] = 1.0

        # CCI
        cci = self._cci(closes, highs, lows, 20)
        if cci > 100:
            factors['cci'] = 0.1
        elif cci > 0:
            factors['cci'] = 0.6
        elif cci > -100:
            factors['cci'] = 0.7
        else:
            factors['cci'] = 1.0

        # DMI
        pdi, mdi, adx = self._dmi(closes, highs, lows, 14)
        if pdi > mdi and adx > 25:
            factors['dmi'] = 1.0
        elif pdi > mdi:
            factors['dmi'] = 0.7
        elif mdi > pdi and adx > 25:
            factors['dmi'] = 0.1
        else:
            factors['dmi'] = 0.5

        # OBV
        obv = self._obv(closes, volumes)
        obv_ma = np.mean(obv[-10:])
        if obv[-1] > obv_ma * 1.05:
            factors['obv'] = 1.0
        elif obv[-1] > obv_ma:
            factors['obv'] = 0.7
        elif obv[-1] < obv_ma * 0.95:
            factors['obv'] = 0.2
        else:
            factors['obv'] = 0.5

        # 成交量MA
        vol_ma5 = np.mean(volumes[-5:])
        vol_ma20 = np.mean(volumes[-20:])
        if vol_ma5 > vol_ma20 * 1.3:
            factors['vol_ma'] = 1.0
        elif vol_ma5 > vol_ma20:
            factors['vol_ma'] = 0.7
        elif vol_ma5 < vol_ma20 * 0.7:
            factors['vol_ma'] = 0.3
        else:
            factors['vol_ma'] = 0.5

        return factors

    def _volume_price_analysis(self, closes, volumes, highs, lows, realtime_data):
        factors = {}

        avg_vol_5 = np.mean(volumes[-5:])
        avg_vol_10 = np.mean(volumes[-10:])
        avg_vol_20 = np.mean(volumes[-20:])
        current_vol = realtime_data['volume'] if realtime_data else volumes[-1]

        # 量比
        vol_ratio_5 = current_vol / avg_vol_5 if avg_vol_5 > 0 else 0
        vol_ratio_20 = current_vol / avg_vol_20 if avg_vol_20 > 0 else 0
        factors['vol_ratio_5'] = self._normalize(vol_ratio_5, 0, 4)
        factors['vol_ratio_20'] = self._normalize(vol_ratio_20, 0, 4)

        # 量价配合度
        if len(closes) > 5:
            price_trend = np.corrcoef(range(5), closes[-5:])[0, 1]
            vol_trend = np.corrcoef(range(5), volumes[-5:])[0, 1]
            if price_trend > 0.5 and vol_trend > 0.5:
                factors['price_volume_match'] = 1.0
            elif price_trend > 0 and vol_trend > 0:
                factors['price_volume_match'] = 0.7
            elif price_trend < 0 and vol_trend > 0:
                factors['price_volume_match'] = 0.3
            else:
                factors['price_volume_match'] = 0.5
        else:
            factors['price_volume_match'] = 0.5

        # 放量上涨
        if len(closes) > 2:
            price_up = closes[-1] > closes[-2]
            vol_up = volumes[-1] > avg_vol_20 * 1.2
            if price_up and vol_up:
                factors['heavy_volume_rise'] = 1.0
            elif price_up:
                factors['heavy_volume_rise'] = 0.6
            elif vol_up:
                factors['heavy_volume_rise'] = 0.4
            else:
                factors['heavy_volume_rise'] = 0.3
        else:
            factors['heavy_volume_rise'] = 0.5

        # 缩量调整
        if len(closes) > 5:
            recent_max = max(closes[-10:])
            is_adjusting = closes[-1] < recent_max * 0.97
            vol_shrinking = volumes[-1] < avg_vol_20 * 0.8
            if is_adjusting and vol_shrinking:
                factors['shrinkage_adjust'] = 1.0
            elif is_adjusting:
                factors['shrinkage_adjust'] = 0.6
            else:
                factors['shrinkage_adjust'] = 0.5
        else:
            factors['shrinkage_adjust'] = 0.5

        # 量价背离
        if len(closes) > 10:
            price_high = closes[-1] > closes[-5]
            vol_low = volumes[-1] < volumes[-5] * 0.8
            if price_high and vol_low:
                factors['volume_price_divergence'] = 0.2
            elif not price_high and not vol_low:
                factors['volume_price_divergence'] = 0.8
            else:
                factors['volume_price_divergence'] = 0.5
        else:
            factors['volume_price_divergence'] = 0.5

        # 振幅
        if len(closes) > 10:
            recent_amp = np.mean([h - l for h, l in zip(highs[-10:], lows[-10:])]) / np.mean(closes[-10:])
            factors['amplitude'] = self._normalize(1.0 - recent_amp * 10, 0, 1)
        else:
            factors['amplitude'] = 0.5

        # 涨跌停判断
        if realtime_data:
            change_pct = realtime_data['change_pct']
            if change_pct >= 9.5:
                factors['limit_status'] = 0.0
            elif change_pct >= 7:
                factors['limit_status'] = 0.3
            elif change_pct <= -9.5:
                factors['limit_status'] = 0.0
            elif change_pct <= -7:
                factors['limit_status'] = 0.7
            else:
                factors['limit_status'] = 0.5
        else:
            factors['limit_status'] = 0.5

        return factors

    def _momentum_trend(self, closes, current):
        factors = {}

        # 短期动量
        mom_1 = (current - closes[-2]) / closes[-2] if len(closes) > 2 else 0
        mom_3 = (current - closes[-4]) / closes[-4] if len(closes) > 4 else 0
        mom_5 = (current - closes[-6]) / closes[-6] if len(closes) > 6 else 0
        mom_10 = (current - closes[-11]) / closes[-11] if len(closes) > 11 else 0

        factors['momentum_1'] = self._normalize(mom_1, -0.05, 0.05)
        factors['momentum_3'] = self._normalize(mom_3, -0.08, 0.08)
        factors['momentum_5'] = self._normalize(mom_5, -0.1, 0.1)
        factors['momentum_10'] = self._normalize(mom_10, -0.15, 0.15)

        # 趋势强度
        if len(closes) > 20:
            x = np.arange(20)
            y = closes[-20:]
            slope, _ = np.polyfit(x, y, 1)
            trend_strength = slope / np.mean(y) * 20
            if trend_strength > 0.05:
                factors['trend_strength'] = 1.0
            elif trend_strength > 0.02:
                factors['trend_strength'] = 0.8
            elif trend_strength > 0:
                factors['trend_strength'] = 0.6
            elif trend_strength > -0.02:
                factors['trend_strength'] = 0.4
            else:
                factors['trend_strength'] = 0.2
        else:
            factors['trend_strength'] = 0.5

        return factors

    def _reversion_mean(self, closes, current, highs, lows):
        factors = {}

        # 超买超卖
        if len(closes) > 20:
            min_20 = min(closes[-20:])
            max_20 = max(closes[-20:])
            if max_20 != min_20:
                position = (current - min_20) / (max_20 - min_20)
                factors['overbought_oversold'] = 1.0 - position
            else:
                factors['overbought_oversold'] = 0.5
        else:
            factors['overbought_oversold'] = 0.5

        # 回归均值距离
        ma20 = np.mean(closes[-20:])
        distance = (current - ma20) / ma20
        if distance < -0.03:
            factors['mean_distance'] = 1.0
        elif distance < -0.01:
            factors['mean_distance'] = 0.8
        elif distance < 0.01:
            factors['mean_distance'] = 0.6
        elif distance < 0.03:
            factors['mean_distance'] = 0.4
        else:
            factors['mean_distance'] = 0.2

        # 高低点位置
        if len(closes) > 10:
            low_10 = min(lows[-10:])
            high_10 = max(highs[-10:])
            if current < low_10 * 1.02:
                factors['low_high_position'] = 1.0
            elif current < low_10 * 1.05:
                factors['low_high_position'] = 0.8
            elif current > high_10 * 0.98:
                factors['low_high_position'] = 0.2
            elif current > high_10 * 0.95:
                factors['low_high_position'] = 0.3
            else:
                factors['low_high_position'] = 0.5
        else:
            factors['low_high_position'] = 0.5

        # 跳空缺口
        if len(closes) > 3:
            gap_up = lows[-1] > highs[-2] * 1.01
            gap_down = highs[-1] < lows[-2] * 0.99
            if gap_up:
                factors['gap'] = 0.3
            elif gap_down:
                factors['gap'] = 0.8
            else:
                factors['gap'] = 0.5
        else:
            factors['gap'] = 0.5

        return factors

    def _volatility_analysis(self, closes, current):
        factors = {}

        if len(closes) > 30:
            returns = np.diff(np.log(closes[-30:]))
            volatility = np.std(returns)
            factors['volatility'] = self._normalize(1.0 - volatility * 10, 0, 1)

            # 波动率变化
            vol_10 = np.std(np.diff(np.log(closes[-10:])))
            vol_20 = np.std(np.diff(np.log(closes[-20:-10])))
            vol_change = (vol_10 - vol_20) / vol_20 if vol_20 > 0 else 0
            if vol_change < -0.2:
                factors['volatility_change'] = 0.8
            elif vol_change < 0:
                factors['volatility_change'] = 0.6
            elif vol_change < 0.2:
                factors['volatility_change'] = 0.5
            else:
                factors['volatility_change'] = 0.3
        else:
            factors['volatility'] = 0.5
            factors['volatility_change'] = 0.5

        # 夏普比率（简化）
        if len(closes) > 20:
            returns_20 = np.diff(closes[-21:]) / closes[-21:-1]
            sharpe = np.mean(returns_20) / np.std(returns_20) if np.std(returns_20) > 0 else 0
            factors['sharpe_simple'] = self._normalize(sharpe, -0.5, 0.5)
        else:
            factors['sharpe_simple'] = 0.5

        return factors

    def _pattern_recognition(self, closes, current, highs, lows):
        factors = {}

        # 底部形态
        if len(closes) > 20:
            recent_min = min(closes[-15:])
            if current > recent_min * 1.05:
                factors['bottom_pattern'] = 1.0
            elif current > recent_min * 1.03:
                factors['bottom_pattern'] = 0.8
            elif current > recent_min * 1.01:
                factors['bottom_pattern'] = 0.6
            else:
                factors['bottom_pattern'] = 0.5
        else:
            factors['bottom_pattern'] = 0.5

        # 上涨趋势确认
        if len(closes) > 15:
            if closes[-1] > closes[-5] > closes[-10] > closes[-15]:
                factors['uptrend_confirmed'] = 1.0
            elif closes[-1] > closes[-5] > closes[-10]:
                factors['uptrend_confirmed'] = 0.8
            elif closes[-1] > closes[-5]:
                factors['uptrend_confirmed'] = 0.6
            else:
                factors['uptrend_confirmed'] = 0.4
        else:
            factors['uptrend_confirmed'] = 0.5

        # W底形态
        if len(closes) > 30:
            mid = len(closes) // 2
            low1 = min(closes[:mid])
            low2 = min(closes[mid:])
            if abs(low1 - low2) / low1 < 0.03 and current > max(low1, low2) * 1.03:
                factors['w_bottom'] = 1.0
            else:
                factors['w_bottom'] = 0.5
        else:
            factors['w_bottom'] = 0.5

        # 突破形态
        if len(closes) > 20:
            resistance = max(highs[-20:-5])
            if current > resistance * 1.01:
                factors['breakout'] = 1.0
            elif current > resistance * 0.99:
                factors['breakout'] = 0.7
            else:
                factors['breakout'] = 0.5
        else:
            factors['breakout'] = 0.5

        return factors

    def _market_microstructure(self, closes, current, volumes, realtime_data):
        factors = {}

        # 开盘位置
        if realtime_data:
            open_p = realtime_data['open']
            if open_p != 0:
                open_position = (current - open_p) / open_p
                if open_position > 0.02:
                    factors['open_position'] = 0.8
                elif open_position > 0:
                    factors['open_position'] = 0.6
                elif open_position > -0.02:
                    factors['open_position'] = 0.5
                else:
                    factors['open_position'] = 0.4
            else:
                factors['open_position'] = 0.5
        else:
            factors['open_position'] = 0.5

        # 日内振幅
        if realtime_data:
            high = realtime_data['high']
            low = realtime_data['low']
            if high != low:
                intraday_amp = (high - low) / low
                position = (current - low) / (high - low)
                if intraday_amp < 0.02 and position > 0.5:
                    factors['intraday'] = 0.7
                elif position < 0.3:
                    factors['intraday'] = 0.8
                elif position > 0.7:
                    factors['intraday'] = 0.3
                else:
                    factors['intraday'] = 0.5
            else:
                factors['intraday'] = 0.5
        else:
            factors['intraday'] = 0.5

        # 成交量分布
        if len(volumes) > 10:
            recent_vol_trend = np.mean(volumes[-3:]) / np.mean(volumes[-10:-3]) if np.mean(volumes[-10:-3]) > 0 else 1
            if recent_vol_trend > 1.5:
                factors['volume_acceleration'] = 1.0
            elif recent_vol_trend > 1.2:
                factors['volume_acceleration'] = 0.8
            elif recent_vol_trend < 0.8:
                factors['volume_acceleration'] = 0.3
            else:
                factors['volume_acceleration'] = 0.5
        else:
            factors['volume_acceleration'] = 0.5

        return factors

    def _alpha101_factors(self, closes, volumes, highs, lows, opens, current):
        """Alpha101顶级因子 - WorldQuant经典因子"""
        factors = {}
        
        try:
            # ========== Alpha#1: 趋势强度因子 ==========
            # 捕捉趋势强度，当收益率为负时使用波动率，否则使用收盘价
            if len(closes) >= 21:
                returns = np.diff(closes[-20:]) / np.array(closes[-20:-1])
                if len(returns) >= 5:
                    power_values = []
                    for i in range(-5, 0):
                        if returns[i] < 0:
                            std_20 = np.std(returns)
                            power_values.append(std_20 ** 2)
                        else:
                            power_values.append(abs(closes[i]))
                    
                    if power_values:
                        max_idx = power_values.index(max(power_values))
                        factors['alpha001_trend'] = (max_idx + 1) / len(power_values)
                    else:
                        factors['alpha001_trend'] = 0.5
                else:
                    factors['alpha001_trend'] = 0.5
            else:
                factors['alpha001_trend'] = 0.5
            
            # ========== Alpha#2: 量价背离因子 ==========
            # 开盘价与成交量的相关性，负相关表示量价背离
            if len(opens) >= 10 and len(volumes) >= 10:
                opens_10 = opens[-10:]
                volumes_10 = volumes[-10:]
                
                # 计算相关系数
                mean_open = np.mean(opens_10)
                mean_vol = np.mean(volumes_10)
                
                numerator = sum((o - mean_open) * (v - mean_vol) for o, v in zip(opens_10, volumes_10))
                denominator = np.sqrt(sum((o - mean_open) ** 2 for o in opens_10)) * np.sqrt(sum((v - mean_vol) ** 2 for v in volumes_10))
                
                if denominator > 0:
                    correlation = numerator / denominator
                    # 负相关表示量价背离，是买入信号
                    factors['alpha002_volume_price'] = 1 - (correlation + 1) / 2  # 归一化到0-1
                else:
                    factors['alpha002_volume_price'] = 0.5
            else:
                factors['alpha002_volume_price'] = 0.5
            
            # ========== Alpha#3: 动量因子 ==========
            # 过去5天的价格变化排名
            if len(closes) >= 6:
                delta_5 = closes[-1] - closes[-6]
                # 计算过去20天的delta排名
                if len(closes) >= 25:
                    deltas = [closes[i] - closes[i-5] for i in range(-20, 0)]
                    sorted_deltas = sorted(deltas)
                    rank = sorted_deltas.index(delta_5) if delta_5 in sorted_deltas else len(sorted_deltas) // 2
                    factors['alpha003_momentum'] = rank / len(sorted_deltas)
                else:
                    factors['alpha003_momentum'] = 0.5 if delta_5 > 0 else 0.3
            else:
                factors['alpha003_momentum'] = 0.5
            
            # ========== Alpha#4: 反转因子 ==========
            # 收盘价与开盘价的排名差异
            if len(closes) >= 2 and len(opens) >= 2:
                close_rank = 1 if closes[-1] > closes[-2] else 0
                open_rank = 1 if opens[-1] > opens[-2] else 0
                # 反转信号
                factors['alpha004_reversal'] = 1 - abs(close_rank - open_rank)
            else:
                factors['alpha004_reversal'] = 0.5
            
            # ========== Alpha#5: 波动率因子 ==========
            # 过去10天的波动率排名
            if len(closes) >= 20:
                std_10 = np.std(closes[-10:])
                std_20_list = [np.std(closes[i-10:i]) for i in range(-10, 0)]
                if std_20_list:
                    sorted_std = sorted(std_20_list)
                    rank = sorted_std.index(std_10) if std_10 in sorted_std else len(sorted_std) // 2
                    # 低波动率更好
                    factors['alpha005_volatility'] = 1 - rank / len(sorted_std)
                else:
                    factors['alpha005_volatility'] = 0.5
            else:
                factors['alpha005_volatility'] = 0.5
            
            # ========== Alpha#6: 成交量加权价格因子 ==========
            # VWAP与收盘价的差异
            if len(closes) >= 10 and len(volumes) >= 10:
                vwap = sum(c * v for c, v in zip(closes[-10:], volumes[-10:])) / sum(volumes[-10:])
                price_diff = (current - vwap) / vwap if vwap > 0 else 0
                # 价格高于VWAP是强势
                if price_diff > 0.02:
                    factors['alpha006_vwap'] = 0.9
                elif price_diff > 0:
                    factors['alpha006_vwap'] = 0.7
                elif price_diff > -0.02:
                    factors['alpha006_vwap'] = 0.5
                else:
                    factors['alpha006_vwap'] = 0.3
            else:
                factors['alpha006_vwap'] = 0.5
            
            # ========== Alpha#7: 高低点因子 ==========
            # 最高价与最低价的排名
            if len(highs) >= 10 and len(lows) >= 10:
                high_rank = 1 if highs[-1] == max(highs[-10:]) else 0.5
                low_rank = 1 if lows[-1] == min(lows[-10:]) else 0.5
                # 创新高不创新低是强势
                factors['alpha007_high_low'] = high_rank * (1 - low_rank) + 0.5
            else:
                factors['alpha007_high_low'] = 0.5
            
            # ========== Alpha#8: 收益率序列因子 ==========
            # 过去5天收益率的相关性
            if len(closes) >= 10:
                returns_5 = [closes[i] - closes[i-1] for i in range(-5, 0)]
                returns_5_prev = [closes[i] - closes[i-1] for i in range(-10, -5)]
                
                if len(returns_5) >= 5 and len(returns_5_prev) >= 5:
                    mean_r1 = np.mean(returns_5)
                    mean_r2 = np.mean(returns_5_prev)
                    
                    numerator = sum((r1 - mean_r1) * (r2 - mean_r2) for r1, r2 in zip(returns_5, returns_5_prev))
                    denominator = np.sqrt(sum((r - mean_r1) ** 2 for r in returns_5)) * np.sqrt(sum((r - mean_r2) ** 2 for r in returns_5_prev))
                    
                    if denominator > 0:
                        correlation = numerator / denominator
                        # 正相关表示趋势延续
                        factors['alpha008_returns_corr'] = (correlation + 1) / 2
                    else:
                        factors['alpha008_returns_corr'] = 0.5
                else:
                    factors['alpha008_returns_corr'] = 0.5
            else:
                factors['alpha008_returns_corr'] = 0.5
            
            # ========== Alpha#9: 价格位置因子 ==========
            # 当前价格在过去20天的位置
            if len(closes) >= 20:
                min_close = min(closes[-20:])
                max_close = max(closes[-20:])
                if max_close > min_close:
                    position = (current - min_close) / (max_close - min_close)
                    factors['alpha009_price_position'] = position
                else:
                    factors['alpha009_price_position'] = 0.5
            else:
                factors['alpha009_price_position'] = 0.5
            
            # ========== Alpha#10: 成交量趋势因子 ==========
            # 成交量的移动平均趋势
            if len(volumes) >= 20:
                ma_vol_5 = np.mean(volumes[-5:])
                ma_vol_20 = np.mean(volumes[-20:])
                if ma_vol_20 > 0:
                    vol_ratio = ma_vol_5 / ma_vol_20
                    # 放量是强势
                    if vol_ratio > 2.0:
                        factors['alpha010_volume_trend'] = 0.9
                    elif vol_ratio > 1.5:
                        factors['alpha010_volume_trend'] = 0.8
                    elif vol_ratio > 1.0:
                        factors['alpha010_volume_trend'] = 0.6
                    else:
                        factors['alpha010_volume_trend'] = 0.4
                else:
                    factors['alpha010_volume_trend'] = 0.5
            else:
                factors['alpha010_volume_trend'] = 0.5
            
        except Exception as e:
            # 如果计算出错，返回默认值
            for i in range(1, 11):
                factors[f'alpha{i:03d}_default'] = 0.5
        
        return factors

    # 技术指标计算函数
    def _ema(self, data, period):
        alpha = 2 / (period + 1)
        ema = [data[0]]
        for i in range(1, len(data)):
            ema.append(alpha * data[i] + (1 - alpha) * ema[-1])
        return ema

    def _rsi(self, closes, period=14):
        if len(closes) < period + 1:
            return 50
        gains = []
        losses = []
        for i in range(1, period + 1):
            change = closes[-i] - closes[-i - 1]
            if change > 0:
                gains.append(change)
            else:
                losses.append(-change)
        avg_gain = np.mean(gains) if gains else 0
        avg_loss = np.mean(losses) if losses else 0
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _kdj(self, closes, highs, lows, n=9, m1=3, m2=3):
        if len(closes) < n:
            return [50], [50], [50]
        k_list = []
        d_list = []
        j_list = []
        for i in range(n - 1, len(closes)):
            high_n = max(highs[i - n + 1:i + 1])
            low_n = min(lows[i - n + 1:i + 1])
            if high_n == low_n:
                rsv = 50
            else:
                rsv = (closes[i] - low_n) / (high_n - low_n) * 100
            if len(k_list) == 0:
                k = 50
                d = 50
            else:
                k = k_list[-1] * (m1 - 1) / m1 + rsv / m1
                d = d_list[-1] * (m2 - 1) / m2 + k / m2
            j = 3 * k - 2 * d
            k_list.append(k)
            d_list.append(d)
            j_list.append(j)
        return k_list, d_list, j_list

    def _bollinger_bands(self, closes, period=20, num_std=2):
        if len(closes) < period:
            return closes[-1] * 1.02, closes[-1], closes[-1] * 0.98
        sma = np.mean(closes[-period:])
        std = np.std(closes[-period:])
        upper = sma + num_std * std
        lower = sma - num_std * std
        return upper, sma, lower

    def _williams_r(self, closes, highs, lows, period=14):
        if len(closes) < period:
            return -50
        high_n = max(highs[-period:])
        low_n = min(lows[-period:])
        if high_n == low_n:
            return -50
        return (high_n - closes[-1]) / (high_n - low_n) * -100

    def _cci(self, closes, highs, lows, period=20):
        if len(closes) < period:
            return 0
        tp = [(h + l + c) / 3 for h, l, c in zip(highs[-period:], lows[-period:], closes[-period:])]
        tp_ma = np.mean(tp)
        md = np.mean([abs(t - tp_ma) for t in tp])
        if md == 0:
            return 0
        return (tp[-1] - tp_ma) / (0.015 * md)

    def _dmi(self, closes, highs, lows, period=14):
        if len(closes) < period + 1:
            return 25, 25, 25
        plus_dm = []
        minus_dm = []
        tr = []
        for i in range(-period, 0):
            up = highs[i] - highs[i - 1]
            down = lows[i - 1] - lows[i]
            if up > down and up > 0:
                plus_dm.append(up)
            else:
                plus_dm.append(0)
            if down > up and down > 0:
                minus_dm.append(down)
            else:
                minus_dm.append(0)
            tr_val = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            tr.append(tr_val)
        atr = np.mean(tr)
        pdi = np.mean(plus_dm) / atr * 100 if atr > 0 else 25
        mdi = np.mean(minus_dm) / atr * 100 if atr > 0 else 25
        dx = abs(pdi - mdi) / (pdi + mdi) * 100 if (pdi + mdi) > 0 else 25
        return pdi, mdi, dx

    def _obv(self, closes, volumes):
        obv = [0]
        for i in range(1, len(closes)):
            if closes[i] > closes[i - 1]:
                obv.append(obv[-1] + volumes[i])
            elif closes[i] < closes[i - 1]:
                obv.append(obv[-1] - volumes[i])
            else:
                obv.append(obv[-1])
        return obv

    def _normalize(self, value, min_val, max_val):
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))

# ==========================================
# Q-Learning强化学习模块
# ==========================================
class QLearningAgent:
    def __init__(self, num_states=10, num_actions=3):
        self.q_table = defaultdict(lambda: np.zeros(num_actions))
        self.num_states = num_states
        self.num_actions = num_actions
        self.learning_rate = PARAMS['learning_rate']
        self.gamma = PARAMS['gamma']
        self.epsilon = 0.1
        self.state_history = deque(maxlen=1000)
        self.action_history = deque(maxlen=1000)
        self.reward_history = deque(maxlen=1000)

    def _discretize_state(self, factors):
        """将因子离散化为状态"""
        state_values = []
        for key in sorted(factors.keys()):
            val = factors[key]
            state_values.append(int(val * (self.num_states - 1)))
        return tuple(state_values[-10:])

    def select_action(self, factors):
        """选择动作"""
        state = self._discretize_state(factors)
        if random.random() < self.epsilon:
            return random.randint(0, self.num_actions - 1)
        return np.argmax(self.q_table[state])

    def update(self, factors, action, reward, next_factors):
        """更新Q表"""
        state = self._discretize_state(factors)
        next_state = self._discretize_state(next_factors) if next_factors else state

        old_q = self.q_table[state][action]
        max_next_q = np.max(self.q_table[next_state])
        new_q = old_q + self.learning_rate * (reward + self.gamma * max_next_q - old_q)
        self.q_table[state][action] = new_q

        self.state_history.append(state)
        self.action_history.append(action)
        self.reward_history.append(reward)

        if len(self.reward_history) % 100 == 0:
            self.epsilon = max(0.01, self.epsilon * 0.99)

    def get_action_score(self, factors, action):
        """获取动作分数"""
        state = self._discretize_state(factors)
        q_values = self.q_table[state]
        max_q = np.max(q_values)
        min_q = np.min(q_values)
        if max_q == min_q:
            return 0.5
        return (q_values[action] - min_q) / (max_q - min_q)

    def save_model(self, filepath):
        """保存模型"""
        try:
            model_data = {
                'q_table': {str(k): list(v) for k, v in self.q_table.items()},
                'epsilon': self.epsilon,
                'learning_rate': self.learning_rate,
                'gamma': self.gamma,
                'save_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(model_data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def load_model(self, filepath):
        """加载模型"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'q_table' in data:
                        self.q_table = defaultdict(lambda: np.zeros(self.num_actions))
                        for k, v in data['q_table'].items():
                            self.q_table[tuple(eval(k))] = np.array(v)
                    if 'epsilon' in data:
                        self.epsilon = data['epsilon']
                print(f"✅ Q-Learning模型已加载")
        except:
            pass

# ==========================================
# AI模型模块 - LightGBM & 深度学习
# ==========================================
class AIModelEnsemble:
    """AI模型集成 - LightGBM + 随机森林 + 梯度提升"""
    
    def __init__(self):
        self.models = {}
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self.is_trained = False
        self.feature_names = []
        self.training_data = {'X': [], 'y': []}
        
        # 初始化模型
        if LIGHTGBM_AVAILABLE:
            self.models['lightgbm'] = lgb.LGBMClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
                verbose=-1
            )
        
        if SKLEARN_AVAILABLE:
            self.models['random_forest'] = RandomForestClassifier(
                n_estimators=100,
                max_depth=5,
                random_state=42,
                n_jobs=-1
            )
            
            self.models['gradient_boosting'] = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
    
    def prepare_features(self, factors):
        """准备特征向量"""
        if not factors:
            return None
        
        # 按key排序，确保特征顺序一致
        sorted_keys = sorted(factors.keys())
        if not self.feature_names:
            self.feature_names = sorted_keys
        
        features = []
        for key in self.feature_names:
            if key in factors:
                features.append(factors[key])
            else:
                features.append(0.5)  # 默认值
        
        return np.array(features).reshape(1, -1)
    
    def train(self, X, y):
        """训练模型"""
        if not SKLEARN_AVAILABLE or len(X) < 50:
            return False
        
        try:
            # 标准化
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练所有模型
            for name, model in self.models.items():
                try:
                    model.fit(X_scaled, y)
                    print(f"✅ {name}模型训练完成")
                except Exception as e:
                    print(f"⚠️ {name}模型训练失败: {e}")
            
            self.is_trained = True
            return True
        except Exception as e:
            print(f"⚠️ 模型训练失败: {e}")
            return False
    
    def predict(self, factors):
        """预测 - 返回买入概率"""
        if not self.is_trained or not self.models:
            return 0.5
        
        features = self.prepare_features(factors)
        if features is None:
            return 0.5
        
        try:
            # 标准化
            features_scaled = self.scaler.transform(features)
            
            # 集成预测
            predictions = []
            for name, model in self.models.items():
                try:
                    if hasattr(model, 'predict_proba'):
                        proba = model.predict_proba(features_scaled)[0]
                        # 假设类别1是买入
                        buy_prob = proba[1] if len(proba) > 1 else proba[0]
                        predictions.append(buy_prob)
                except:
                    pass
            
            if predictions:
                return np.mean(predictions)
            return 0.5
        except:
            return 0.5
    
    def add_training_sample(self, factors, label):
        """添加训练样本"""
        features = self.prepare_features(factors)
        if features is not None:
            self.training_data['X'].append(features.flatten())
            self.training_data['y'].append(label)
            
            # 定期训练
            if len(self.training_data['X']) >= 100 and len(self.training_data['X']) % 50 == 0:
                X = np.array(self.training_data['X'])
                y = np.array(self.training_data['y'])
                self.train(X, y)
    
    def save_models(self, filepath):
        """保存模型"""
        try:
            import pickle
            model_data = {
                'models': self.models,
                'scaler': self.scaler,
                'feature_names': self.feature_names,
                'is_trained': self.is_trained,
                'training_data': self.training_data
            }
            with open(filepath, 'wb') as f:
                pickle.dump(model_data, f)
            print(f"✅ AI模型已保存")
        except Exception as e:
            print(f"⚠️ 模型保存失败: {e}")
    
    def load_models(self, filepath):
        """加载模型"""
        try:
            import pickle
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    model_data = pickle.load(f)
                    self.models = model_data.get('models', {})
                    self.scaler = model_data.get('scaler', StandardScaler() if SKLEARN_AVAILABLE else None)
                    self.feature_names = model_data.get('feature_names', [])
                    self.is_trained = model_data.get('is_trained', False)
                    self.training_data = model_data.get('training_data', {'X': [], 'y': []})
                print(f"✅ AI模型已加载")
        except Exception as e:
            print(f"⚠️ 模型加载失败: {e}")

# ==========================================
# 风险控制模块
# ==========================================
class SuperRiskManager:
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions = {}
        self.highest_capital = initial_capital
        self.drawdown = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.consecutive_losses = 0
        self.total_profit = 0.0

    def can_trade(self, code, price, market_sentiment=0.5):
        """检查是否可以交易"""
        if self.drawdown >= PARAMS['max_drawdown']:
            return False
        if code in self.positions:
            return False
        if len(self.positions) >= 5:
            return False
        if self.consecutive_losses >= 3 and market_sentiment < 0.5:
            return False
        return True

    def enter_position(self, code, price, composite_score=0.5, market_sentiment=0.5):
        """开仓 - 根据评分和市场情绪动态决定仓位"""
        if not self.can_trade(code, price, market_sentiment):
            return None

        # 动态仓位计算：评分越高，仓位越大
        # 基础仓位 = 总资金 * 最大单品种仓位比例
        base_position = self.capital * PARAMS['max_position']
        
        # 评分调整：评分0.75-1.0，仓位从50%到100%
        score_multiplier = 0.5 + (composite_score - 0.75) * 2 if composite_score >= 0.75 else 0.5
        
        # 情绪调整：市场情绪好，增加仓位
        sentiment_multiplier = 0.7 + market_sentiment * 0.3
        
        # 最终仓位
        final_position = base_position * score_multiplier * sentiment_multiplier
        
        # 计算买入数量（向下取整到100股的整数倍）
        size = int(final_position / price // 100) * 100
        if size <= 0:
            return None

        cost = size * price
        total_position_value = sum(p['size'] * p['entry_price'] for p in self.positions.values())
        if cost + total_position_value > self.capital * PARAMS['total_position']:
            # 如果超过总仓位限制，减少买入数量
            available = self.capital * PARAMS['total_position'] - total_position_value
            size = int(available / price // 100) * 100
            if size <= 0:
                return None
            cost = size * price

        self.capital -= cost
        self.positions[code] = {
            'code': code,
            'entry_price': price,
            'entry_time': datetime.now(),
            'size': size,
            'highest_price': price,
            'trailing_stop': price * 0.98,
            'composite_score': composite_score,
            'market_sentiment': market_sentiment
        }
        self.trade_count += 1

        return {'code': code, 'entry_price': price, 'size': size}

    def exit_position(self, code, exit_price, partial_size=None):
        """平仓 - 支持分批卖出"""
        if code not in self.positions:
            return None

        position = self.positions[code]
        
        # 如果指定了分批卖出数量，只卖部分
        if partial_size and partial_size < position['size']:
            sell_size = partial_size
            profit = (exit_price - position['entry_price']) * sell_size
            profit_pct = (exit_price - position['entry_price']) / position['entry_price']
            
            # 更新持仓
            position['size'] -= sell_size
            self.capital += exit_price * sell_size
            self.total_profit += profit
            
            # 不更新胜率统计，因为还没清仓
            
            return {
                'code': code,
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'size': sell_size,
                'profit': profit,
                'profit_pct': profit_pct,
                'hold_time': (datetime.now() - position['entry_time']).total_seconds(),
                'win': profit > 0,
                'partial': True
            }
        else:
            # 全部卖出
            position = self.positions.pop(code)
            profit = (exit_price - position['entry_price']) * position['size']
            profit_pct = (exit_price - position['entry_price']) / position['entry_price']
            self.capital += exit_price * position['size']
            self.total_profit += profit

            if profit > 0:
                self.win_count += 1
                self.consecutive_losses = 0
            else:
                self.loss_count += 1
                self.consecutive_losses += 1

            if self.capital > self.highest_capital:
                self.highest_capital = self.capital
            self.drawdown = (self.highest_capital - self.capital) / self.highest_capital

            return {
                'code': code,
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'size': position['size'],
                'profit': profit,
                'profit_pct': profit_pct,
                'hold_time': (datetime.now() - position['entry_time']).total_seconds(),
                'win': profit > 0,
                'partial': False
            }

    def check_stop_loss_take_profit(self, realtime_data, hist_data_cache=None):
        """智能动态止盈止损 - 涨停板特殊处理"""
        to_exit = []
        exit_reasons = {}
        
        for code, position in list(self.positions.items()):
            if code not in realtime_data:
                continue
                
            data = realtime_data[code]
            price = data['price']
            profit_pct = (price - position['entry_price']) / position['entry_price']
            hold_time = (datetime.now() - position['entry_time']).total_seconds()
            
            # ========== 涨停板特殊处理 ==========
            is_limit_up = data.get('is_limit_up', False)
            limit_up_volume = data.get('limit_up_volume', 0)
            
            if is_limit_up:
                # 涨停时，不触发止盈，观察封单
                # 初始化封单历史记录
                if 'limit_up_history' not in position:
                    position['limit_up_history'] = []
                
                position['limit_up_history'].append({
                    'time': datetime.now(),
                    'volume': limit_up_volume,
                    'price': price
                })
                
                # 保留最近10次记录
                if len(position['limit_up_history']) > 10:
                    position['limit_up_history'] = position['limit_up_history'][-10:]
                
                # 判断封单强度
                if len(position['limit_up_history']) >= 3:
                    recent_volumes = [h['volume'] for h in position['limit_up_history'][-3:]]
                    avg_volume = sum(recent_volumes) / len(recent_volumes)
                    
                    # 封单衰减判断
                    if limit_up_volume < avg_volume * 0.5:  # 封单减少超过50%
                        to_exit.append(code)
                        exit_reasons[code] = '涨停封单衰减'
                        continue
                    elif limit_up_volume < position['limit_up_history'][-2]['volume'] * 0.7:  # 连续衰减
                        to_exit.append(code)
                        exit_reasons[code] = '涨停封单减弱'
                        continue
                
                # 封单强劲，继续持有
                if limit_up_volume > 100000:  # 封单超过10万手
                    continue  # 不触发任何卖出
            
            # ========== 跌停板处理 ==========
            # 判断是否跌停
            is_limit_down = False
            if 'prev_close' in data and data['prev_close'] > 0:
                limit_down_pct = (price - data['prev_close']) / data['prev_close']
                is_limit_down = limit_down_pct <= -0.095  # 跌幅超过9.5%视为跌停
            
            if is_limit_down:
                # 跌停时，不卖，等开板
                print(f"⚠️ {code} 跌停封死，等待开板...")
                continue
            
            # ========== 分批止盈 ==========
            # 初始化分批卖出记录
            if 'partial_sells' not in position:
                position['partial_sells'] = []
            
            # 盈利3%，卖出30%
            if profit_pct >= 0.03 and len(position['partial_sells']) == 0:
                partial_size = int(position['size'] * 0.3 // 100) * 100
                if partial_size > 0:
                    to_exit.append(code)
                    exit_reasons[code] = '分批止盈(30%)'
                    position['partial_sells'].append({'time': datetime.now(), 'pct': 0.3, 'size': partial_size})
                    continue
            
            # 盈利5%，再卖出50%
            if profit_pct >= 0.05 and len(position['partial_sells']) == 1:
                partial_size = int(position['size'] * 0.5 // 100) * 100
                if partial_size > 0:
                    to_exit.append(code)
                    exit_reasons[code] = '分批止盈(50%)'
                    position['partial_sells'].append({'time': datetime.now(), 'pct': 0.5, 'size': partial_size})
                    continue
            
            # ========== 利润回撤保护 ==========
            if profit_pct > 0.02:  # 已盈利2%
                # 从最高点回撤超过1%，立即卖出
                drawdown_from_high = (position['highest_price'] - price) / position['highest_price']
                if drawdown_from_high > 0.01:
                    to_exit.append(code)
                    exit_reasons[code] = '利润回撤保护'
                    continue
            
            # ========== 正常止盈止损逻辑 ==========
            
            # 更新最高价和追踪止损
            if price > position['highest_price']:
                position['highest_price'] = price
                # 盈利超过1%后启动追踪止损
                if profit_pct > 0.01:
                    trailing_pct = min(0.02, profit_pct * 0.5)  # 追踪止损为盈利的50%，最大2%
                    position['trailing_stop'] = max(position['trailing_stop'], price * (1 - trailing_pct))
            
            # 动态止损计算
            base_stop_loss = PARAMS['stop_loss']  # 基础止损2%
            
            # 1. 波动率调整：高波动放宽止损
            volatility_adj = 0
            if hist_data_cache and code in hist_data_cache:
                hist = hist_data_cache[code]
                if len(hist) > 20:
                    closes = [h['close'] for h in hist[-20:]]
                    returns = np.diff(closes) / closes[:-1]
                    volatility = np.std(returns) * np.sqrt(252)  # 年化波动率
                    # 波动率30%以上，止损放宽到3%
                    if volatility > 0.30:
                        volatility_adj = 0.01
                    # 波动率20%以下，止损收紧到1.5%
                    elif volatility < 0.20:
                        volatility_adj = -0.005
            
            # 2. 持仓时间调整：持仓越久，止损越严格
            time_adj = 0
            if hold_time > 3600:  # 超过1小时
                time_adj = -0.005
            elif hold_time > 7200:  # 超过2小时
                time_adj = -0.01
            
            # 3. 盈利保护：盈利后提高止损线
            profit_protection = 0
            if profit_pct > 0.02:  # 盈利超过2%
                profit_protection = profit_pct - 0.01  # 止损线提高到盈利-1%
            
            # 最终止损线
            dynamic_stop_loss = base_stop_loss + volatility_adj + time_adj
            if profit_protection > 0:
                dynamic_stop_loss = min(dynamic_stop_loss, -profit_protection)
            
            # 动态止盈计算
            base_take_profit = PARAMS['take_profit']  # 基础止盈3%
            
            # 1. 趋势强度调整：趋势强时扩大止盈
            trend_adj = 0
            if 'composite_score' in position:
                score = position['composite_score']
                if score > 0.85:  # 评分很高，扩大止盈到5%
                    trend_adj = 0.02
                elif score > 0.80:  # 评分较高，扩大止盈到4%
                    trend_adj = 0.01
            
            # 2. 盈利加速：盈利加速时扩大止盈
            acceleration_adj = 0
            if profit_pct > 0.02:  # 已盈利2%
                # 检查是否加速上涨
                if price > position['highest_price'] * 0.995:  # 接近或创新高
                    acceleration_adj = 0.01
            
            # 3. 持仓时间调整：持仓越久，止盈越保守
            time_adj_profit = 0
            if hold_time > 3600:  # 超过1小时
                time_adj_profit = -0.005
            elif hold_time > 7200:  # 超过2小时
                time_adj_profit = -0.01
            
            # 最终止盈线
            dynamic_take_profit = base_take_profit + trend_adj + acceleration_adj + time_adj_profit
            
            # 检查是否触发
            if price <= position['trailing_stop']:
                to_exit.append(code)
                exit_reasons[code] = '追踪止损'
            elif profit_pct <= -dynamic_stop_loss:
                to_exit.append(code)
                exit_reasons[code] = f'止损({dynamic_stop_loss*100:.1f}%)'
            elif profit_pct >= dynamic_take_profit:
                to_exit.append(code)
                exit_reasons[code] = f'止盈({dynamic_take_profit*100:.1f}%)'
        
        return to_exit, exit_reasons

    def get_win_rate(self):
        total = self.win_count + self.loss_count
        return self.win_count / total if total > 0 else 0

    def get_position_summary(self):
        total_value = self.capital
        for code, pos in self.positions.items():
            total_value += pos['size'] * pos['entry_price']
        return {
            'capital': self.capital,
            'positions': len(self.positions),
            'drawdown': self.drawdown,
            'total_value': total_value,
            'total_profit': total_value - self.initial_capital,
            'win_rate': self.get_win_rate()
        }

# ==========================================
# 通知模块
# ==========================================
class SuperNotifier:
    def __init__(self, dingtalk_webhook=''):
        self.dingtalk_webhook = dingtalk_webhook

    def send(self, title, content):
        print(f"\n📢 {title}")
        print(content)
        if self.dingtalk_webhook:
            try:
                payload = {
                    'msgtype': 'markdown',
                    'markdown': {
                        'title': title,
                        'text': f"## {title}\n\n{content}\n\n---\n*超级策略 {PARAMS['strategy_version']}*"
                    }
                }
                requests.post(self.dingtalk_webhook, json=payload, timeout=5)
            except:
                pass

# ==========================================
# 策略主类
# ==========================================
class SuperStrategy:
    def __init__(self, dingtalk_webhook=''):
        self.fetcher = SuperDataFetcher()
        self.sentiment_analyzer = SuperSentimentAnalyzer(self.fetcher)
        self.hot_sector_analyzer = HotSectorAnalyzer(self.fetcher)
        self.factor_engine = SuperFactorEngine(self.fetcher)
        self.q_agent = QLearningAgent()
        self.ai_model = AIModelEnsemble()
        self.risk_manager = SuperRiskManager()
        self.notifier = SuperNotifier(dingtalk_webhook)
        self.stock_pool = []
        self.is_running = False
        self.pending_trades = {}
        self.current_hot_sectors = []
        self.last_pool_update = None

        if ETF_T0_AVAILABLE:
            self.etf_predictor = ETFT0Predictor(
                etf_codes=['sh510300', 'sh510500', 'sz159919', 'sz159915'],
                update_interval=5
            )
            self.etf_thread = None
            self.etf_running = False
            print("✅ ETF T+0 超短线预测模块已加载（独立线程）")
        else:
            self.etf_predictor = None
            self.etf_thread = None
            print("⚠️ ETF T+0 超短线预测模块未加载")

    def initialize(self):
        """初始化"""
        print("=" * 70)
        print("🚀 【超级策略】A股超短线 - AI驱动版 启动")
        print("=" * 70)
        print("📊 集成：Alpha101因子 + LightGBM + 随机森林 + 梯度提升")
        print("📊 股票池：实盘涨幅榜动态获取")
        print("=" * 70)
        self.q_agent.load_model(MODEL_FILE)
        self.ai_model.load_models(MODEL_FILE.replace('.json', '_ai.pkl'))
        if self.etf_predictor:
            print("✅ ETF T+0 超短线预测模块已就绪")
        print("✅ 初始化完成，准备交易\n")

    def is_trading_hours(self):
        """检查是否为交易时间"""
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()

        if weekday >= 5:
            return False

        return (
            (dt_time(9, 25) <= current_time <= dt_time(11, 35)) or
            (dt_time(13, 0) <= current_time <= dt_time(15, 5))
        )

    def get_check_interval(self):
        """获取检查间隔 - 根据交易时段动态调整"""
        now = datetime.now()
        current_time = now.time()

        if dt_time(9, 25) <= current_time <= dt_time(9, 35):
            return 5
        elif dt_time(9, 35) <= current_time <= dt_time(9, 50):
            return 8
        elif dt_time(9, 50) <= current_time <= dt_time(10, 20):
            return 15
        elif dt_time(14, 30) <= current_time <= dt_time(15, 0):
            return 10
        else:
            return PARAMS['update_interval']

    def run_once(self):
        """运行一次 - 实盘并行获取，下单前综合评估"""
        if not self.is_trading_hours():
            return
        
        current_time = datetime.now()
        print(f"\n{'=' * 70}")
        print(f"⏰ {current_time.strftime('%H:%M:%S')} 实盘扫描")
        print("=" * 70)

        # 第一步：并行获取所有实盘数据
        print("\n📊 【实盘数据获取】")
        
        # 1. 宏观数据：大盘指数
        index_data = {
            'sh000001': self.fetcher.get_realtime_data('sh000001'),
            'sz399001': self.fetcher.get_realtime_data('sz399001'),
            'sz399006': self.fetcher.get_realtime_data('sz399006')
        }
        market_trend = self._analyze_market_trend(index_data)
        print(f"  📈 大盘: {market_trend['status']} ({market_trend['change']:+.2f}%)")
        
        # 2. 市场情绪
        market_sentiment = self.sentiment_analyzer.get_market_sentiment()
        print(f"  💓 情绪: {market_sentiment:.2f}")
        
        # 3. 板块热点：实盘涨幅榜
        ranking_stocks = self.hot_sector_analyzer.get_realtime_ranking(top_n=50)
        if not ranking_stocks:
            print("  ⚠️ 无法获取涨幅榜，跳过")
            return
        
        hot_sectors = self._identify_hot_sectors(ranking_stocks)
        print(f"  🔥 热点: {', '.join(hot_sectors[:3])}")
        
        # 4. 个股数据：动态股票池
        self.stock_pool = [s['code'] for s in ranking_stocks[:30]]
        realtime_data = {}
        for stock in ranking_stocks[:30]:
            code = stock['code']
            data = self.fetcher.get_realtime_data(code)
            if data:
                realtime_data[code] = data
        print(f"  🎯 股票池: {len(self.stock_pool)}只")
        
        # 5. 龙头股
        leader = self.hot_sector_analyzer.find_sector_leader_from_realtime(ranking_stocks)
        if leader:
            print(f"  👑 龙头: {leader['name']} +{leader['change_pct']:.2f}%")

        # 第二步：风险控制（优先级最高）
        print("\n⚠️ 【风险控制】")
        
        # 大盘暴跌清仓
        if market_trend['status'] == '暴跌':
            print("  🚨 大盘暴跌，清仓！")
            for code in list(self.risk_manager.positions.keys()):
                data = self.fetcher.get_realtime_data(code)
                if data:
                    trade = self.risk_manager.exit_position(code, data['price'])
                    if trade:
                        self._send_exit_notification(trade, market_sentiment, '大盘暴跌清仓')
            return
        
        # 大盘弱势降仓
        if market_trend['status'] in ['弱势', '大跌']:
            market_sentiment *= 0.7
            print(f"  ⚠️ 大盘弱势，情绪降至 {market_sentiment:.2f}")
        
        # 持仓检查
        hist_data_cache = {}
        for code in self.risk_manager.positions.keys():
            if code not in hist_data_cache:
                hist_data_cache[code] = self.fetcher.get_historical_data(code, 30)

        to_exit, exit_reasons = self.risk_manager.check_stop_loss_take_profit(realtime_data, hist_data_cache)
        for code in to_exit:
            reason = exit_reasons.get(code, '未知')
            partial_size = None
            if '分批止盈' in reason:
                position = self.risk_manager.positions.get(code)
                if position and 'partial_sells' in position and position['partial_sells']:
                    partial_size = position['partial_sells'][-1]['size']
            
            trade = self.risk_manager.exit_position(code, realtime_data[code]['price'], partial_size)
            if trade:
                self._send_exit_notification(trade, market_sentiment, reason)

        # 第三步：下单前综合评估
        print("\n🎯 【综合评估】")
        
        # 龙头股优先
        if leader and leader['score'] > 50:
            code = leader['code']
            data = leader['data']
            
            print(f"\n  📊 评估龙头: {leader['name']}")
            
            factors = self.factor_engine.calculate_all_factors(code, data)
            if factors:
                evaluation = self._comprehensive_evaluation(
                    factors=factors,
                    market_trend=market_trend,
                    market_sentiment=market_sentiment,
                    hot_sectors=hot_sectors,
                    is_leader=True,
                    leader_score=leader['score']
                )
                
                print(f"    📈 Alpha101: {evaluation['alpha101_score']:.2f}")
                print(f"    📊 传统因子: {evaluation['traditional_score']:.2f}")
                print(f"    🧠 Q-Learning: {evaluation['q_score']:.2f}")
                print(f"    🤖 AI模型: {evaluation['ai_score']:.2f}")
                print(f"    🎯 综合评分: {evaluation['final_score']:.2f}")
                print(f"    ⚠️ 风险等级: {evaluation['risk_level']}")
                
                if evaluation['final_score'] >= PARAMS['entry_threshold'] and self.risk_manager.can_trade(code, data['price'], market_sentiment):
                    print(f"    ✅ 决策: 买入")
                    self._try_enter_position(code, evaluation['final_score'], evaluation['factor_score'], evaluation['q_score'], data, factors, market_sentiment)
                else:
                    print(f"    ❌ 决策: 不买入（评分不足或风险控制）")
                
                return

        # 非龙头股评估
        signals = []
        for code, data in realtime_data.items():
            factors = self.factor_engine.calculate_all_factors(code, data)
            if factors:
                evaluation = self._comprehensive_evaluation(
                    factors=factors,
                    market_trend=market_trend,
                    market_sentiment=market_sentiment,
                    hot_sectors=hot_sectors,
                    is_leader=False,
                    leader_score=0
                )
                
                if evaluation['final_score'] >= PARAMS['entry_threshold'] and self.risk_manager.can_trade(code, data['price'], market_sentiment):
                    signals.append((code, evaluation, data, factors))

        if signals:
            signals.sort(key=lambda x: x[1]['final_score'], reverse=True)
            for i in range(min(2, len(signals))):
                best_code, best_eval, best_data, best_factors = signals[i]
                self._try_enter_position(best_code, best_eval['final_score'], best_eval['factor_score'], best_eval['q_score'], best_data, best_factors, market_sentiment)

        summary = self.risk_manager.get_position_summary()
        print(f"\n💼 持仓: {summary['positions']} | 资金: {summary['capital']:.0f} | 回撤: {summary['drawdown']:.2%} | 胜率: {summary['win_rate']:.1%}")

    def _comprehensive_evaluation(self, factors, market_trend, market_sentiment, hot_sectors, is_leader, leader_score):
        """综合评估 - 下单前综合所有因素"""
        
        # 1. 因子评估
        alpha101_score = self._calculate_alpha101_score(factors)
        traditional_score = self._calculate_traditional_score(factors)
        factor_score = alpha101_score * 0.7 + traditional_score * 0.3
        
        # 2. AI评估
        q_score = self.q_agent.get_action_score(factors, 0)
        ai_score = self.ai_model.predict(factors)
        
        # 3. 综合评分（因子50% + Q-Learning 20% + AI 30%）
        base_score = factor_score * 0.5 + q_score * 0.2 + ai_score * 0.3
        
        # 4. 市场环境调整
        market_adjustment = 0.7 + market_sentiment * 0.3
        adjusted_score = base_score * market_adjustment
        
        # 5. 龙头股加分
        if is_leader:
            adjusted_score += 0.20
        
        # 6. 热点板块加分
        if hot_sectors and hot_sectors[0] != '综合':
            adjusted_score += 0.05
        
        # 7. 风险等级评估
        risk_level = self._assess_market_risk(market_trend, market_sentiment)
        
        return {
            'alpha101_score': alpha101_score,
            'traditional_score': traditional_score,
            'factor_score': factor_score,
            'q_score': q_score,
            'ai_score': ai_score,
            'base_score': base_score,
            'market_adjustment': market_adjustment,
            'final_score': adjusted_score,
            'risk_level': risk_level
        }

    def _assess_market_risk(self, market_trend, market_sentiment):
        """评估市场风险等级"""
        if market_trend['status'] == '暴跌':
            return '极高风险'
        elif market_trend['status'] == '大跌':
            return '高风险'
        elif market_trend['status'] == '弱势':
            return '中等风险'
        elif market_sentiment < 0.4:
            return '中等风险'
        elif market_sentiment > 0.7:
            return '低风险'
        else:
            return '正常风险'
    
    def _identify_hot_sectors(self, ranking_stocks):
        """识别热点板块"""
        sectors = []
        for stock in ranking_stocks[:20]:
            name = stock.get('name', '')
            # 简单的板块识别（可以根据股票名称判断）
            if '科技' in name or '电子' in name or '芯片' in name:
                if '科技' not in sectors:
                    sectors.append('科技')
            elif '医药' in name or '生物' in name:
                if '医药' not in sectors:
                    sectors.append('医药')
            elif '新能源' in name or '锂电' in name or '光伏' in name:
                if '新能源' not in sectors:
                    sectors.append('新能源')
            elif '白酒' in name or '酒' in name:
                if '白酒' not in sectors:
                    sectors.append('白酒')
            elif '金融' in name or '银行' in name or '证券' in name:
                if '金融' not in sectors:
                    sectors.append('金融')
        
        return sectors if sectors else ['综合']
    
    def _analyze_sector_rotation(self, ranking_stocks):
        """分析板块轮动"""
        if not ranking_stocks:
            return '无数据'
        
        # 统计涨幅榜前10的板块分布
        top_stocks = ranking_stocks[:10]
        avg_change = sum(s['change_pct'] for s in top_stocks) / len(top_stocks)
        
        if avg_change > 5:
            return '强势轮动'
        elif avg_change > 3:
            return '正常轮动'
        elif avg_change > 1:
            return '弱势轮动'
        else:
            return '无轮动'
    
    def _calculate_alpha101_score(self, factors):
        """计算Alpha101因子评分"""
        alpha101_keys = [k for k in factors.keys() if k.startswith('alpha')]
        if not alpha101_keys:
            return 0.5
        
        scores = [factors[k] for k in alpha101_keys]
        return sum(scores) / len(scores)
    
    def _calculate_traditional_score(self, factors):
        """计算传统因子评分"""
        traditional_keys = [k for k in factors.keys() if not k.startswith('alpha')]
        if not traditional_keys:
            return 0.5
        
        scores = [factors[k] for k in traditional_keys]
        return sum(scores) / len(scores)

    def _analyze_market_trend(self, index_data):
        """分析大盘趋势"""
        changes = []
        for code, data in index_data.items():
            if data and 'change_pct' in data:
                changes.append(data['change_pct'])
        
        if not changes:
            return {'status': '未知', 'change': 0}
        
        avg_change = sum(changes) / len(changes)
        
        if avg_change <= -3.0:
            return {'status': '暴跌', 'change': avg_change}
        elif avg_change <= -2.0:
            return {'status': '大跌', 'change': avg_change}
        elif avg_change <= -1.0:
            return {'status': '弱势', 'change': avg_change}
        elif avg_change >= 2.0:
            return {'status': '强势', 'change': avg_change}
        elif avg_change >= 1.0:
            return {'status': '偏强', 'change': avg_change}
        else:
            return {'status': '震荡', 'change': avg_change}

    def _calculate_factor_score(self, factors):
        """计算因子综合分数 - 集成Alpha101顶级因子"""
        weights = {
            # ========== Alpha101顶级因子（权重更高）==========
            'alpha001_trend': 0.08,  # 趋势强度
            'alpha002_volume_price': 0.09,  # 量价背离
            'alpha003_momentum': 0.08,  # 动量
            'alpha004_reversal': 0.07,  # 反转
            'alpha005_volatility': 0.06,  # 波动率
            'alpha006_vwap': 0.08,  # VWAP
            'alpha007_high_low': 0.07,  # 高低点
            'alpha008_returns_corr': 0.06,  # 收益率相关
            'alpha009_price_position': 0.07,  # 价格位置
            'alpha010_volume_trend': 0.08,  # 成交量趋势
            
            # ========== 传统技术指标因子 ==========
            'ma_system': 0.04, 'macd': 0.03, 'rsi': 0.03, 'kdj': 0.02,
            'bollinger': 0.02, 'williams_r': 0.02, 'cci': 0.02, 'dmi': 0.02,
            'obv': 0.03, 'vol_ma': 0.03, 'vol_ratio_5': 0.03, 'vol_ratio_20': 0.02,
            'price_volume_match': 0.03, 'heavy_volume_rise': 0.03, 'shrinkage_adjust': 0.02,
            'trend_strength': 0.03, 'overbought_oversold': 0.02, 'bottom_pattern': 0.02,
            'uptrend_confirmed': 0.02, 'breakout': 0.02, 'market_sentiment': 0.02
        }

        score = 0
        total_weight = 0
        for key, weight in weights.items():
            if key in factors:
                score += factors[key] * weight
                total_weight += weight

        base_score = score / total_weight if total_weight > 0 else 0.5
        
        # ========== AI模型预测 ==========
        ai_score = self.ai_model.predict(factors)
        
        # 最终分数：因子分数70% + AI预测30%
        final_score = base_score * 0.7 + ai_score * 0.3
        
        return final_score

    def _try_enter_position(self, code, composite_score, factor_score, q_score, data, factors, market_sentiment):
        """尝试开仓"""
        if not self.is_trading_hours():
            return

        position = self.risk_manager.enter_position(code, data['price'], composite_score=composite_score, market_sentiment=market_sentiment)
        if position:
            self.pending_trades[code] = {
                'entry_factors': factors,
                'entry_price': data['price'],
                'entry_time': datetime.now()
            }
            
            buy_amount = position['size'] * data['price']
            position_count = len(self.risk_manager.positions)
            
            self.notifier.send(
                "🎯 买入信号",
                f"**{data['name']} ({code})**\n\n"
                f"� 买入价: {data['price']:.2f}元\n"
                f"📦 买入数量: {position['size']}股\n"
                f"� 买入金额: {buy_amount:.0f}元\n\n"
                f"� 当前持仓: {position_count}只股票\n"
                f"🎯 止盈价: {data['price'] * 1.03:.2f}元 (+3%)\n"
                f"🛑 止损价: {data['price'] * 0.98:.2f}元 (-2%)\n\n"
                f"� 评分: {composite_score:.2f} | 情绪: {market_sentiment:.2f}"
            )

    def _send_exit_notification(self, trade, market_sentiment, reason="未知"):
        """发送平仓通知"""
        if not self.is_trading_hours():
            return

        emoji = "✅" if trade['win'] else "❌"
        action = "清仓卖出" if trade['win'] else "止损卖出"

        if trade['code'] in self.pending_trades:
            pending = self.pending_trades.pop(trade['code'])
            next_factors = self.factor_engine.calculate_all_factors(trade['code'])
            reward = trade['profit_pct'] * 100
            self.q_agent.update(pending['entry_factors'], 0, reward, next_factors)
            
            # ========== AI模型训练 ==========
            # 标签：盈利为1，亏损为0
            label = 1 if trade['win'] else 0
            self.ai_model.add_training_sample(pending['entry_factors'], label)

        sell_amount = trade['size'] * trade['exit_price']
        hold_minutes = int(trade['hold_time'] // 60)
        total_profit = self.risk_manager.total_profit
        win_rate = self.risk_manager.get_win_rate() * 100
        
        self.notifier.send(
            f"{emoji} {action}",
            f"**{trade['code']}**\n\n"
            f"� 买入价: {trade['entry_price']:.2f}元\n"
            f"� 卖出价: {trade['exit_price']:.2f}元\n"
            f"� 卖出数量: {trade['size']}股\n"
            f"💵 卖出金额: {sell_amount:.0f}元\n\n"
            f"{'✅ 本次盈利' if trade['win'] else '❌ 本次亏损'}: {trade['profit']:+.0f}元 ({trade['profit_pct']:+.2%})\n"
            f"⏱️ 持仓时间: {hold_minutes}分钟\n\n"
            f"📊 累计盈利: {total_profit:+.0f}元\n"
            f"� 当前胜率: {win_rate:.1f}%\n"
            f"📈 市场情绪: {market_sentiment:.2f}"
        )

        self.q_agent.save_model(MODEL_FILE)
        self.ai_model.save_models(MODEL_FILE.replace('.json', '_ai.pkl'))

    def run_continuous(self):
        """持续运行"""
        self.is_running = True
        self._start_etf_predictor()
        print(f"\n🔄 持续运行模式 | 动态间隔调整")

        try:
            while self.is_running:
                self.run_once()
                interval = self.get_check_interval()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n策略已停止")
        finally:
            self._stop_etf_predictor()
            final_summary = self.risk_manager.get_position_summary()
            print(f"📊 最终: 资金 {final_summary['capital']:.0f} | 总收益 {final_summary['total_profit']:+.0f} | 胜率 {final_summary['win_rate']:.1%}")

    def _start_etf_predictor(self):
        """启动ETF预测独立线程"""
        if self.etf_predictor and not self.etf_running:
            self.etf_running = True
            self.etf_thread = threading.Thread(target=self._etf_predictor_loop, daemon=True)
            self.etf_thread.start()
            print("✅ ETF T+0 预测线程已启动（独立运行）")

    def _stop_etf_predictor(self):
        """停止ETF预测线程"""
        if self.etf_running:
            self.etf_running = False
            if self.etf_thread:
                self.etf_thread.join(timeout=2)
            print("✅ ETF T+0 预测线程已停止")

    def _etf_predictor_loop(self):
        """ETF预测独立循环"""
        while self.etf_running:
            try:
                if self.etf_predictor.is_trading_time():
                    for etf_code in self.etf_predictor.etf_codes:
                        self.etf_predictor.update_price(etf_code)
                    self.etf_predictor.verify_predictions()
                    for etf_code in self.etf_predictor.etf_codes:
                        if self.etf_predictor.last_prices.get(etf_code):
                            self.etf_predictor.predict(etf_code)
                time.sleep(self.etf_predictor.update_interval)
            except Exception as e:
                print(f"ETF预测线程异常: {e}")
                time.sleep(5)


# ==========================================
# 主函数
# ==========================================
if __name__ == '__main__':
    DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=YOUR_DINGTALK_ACCESS_TOKEN'
    strategy = SuperStrategy(dingtalk_webhook=DINGTALK_WEBHOOK)
    strategy.initialize()
    strategy.run_continuous()
