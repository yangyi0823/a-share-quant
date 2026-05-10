import requests
from datetime import datetime, timedelta, time
import json
import re
import time as time_module

class RealtimeDataFetcher:
    """
    实时数据获取类 - 从腾讯、东方财富等免费接口获取A股数据
    数据源:
    1. 腾讯行情接口 (主): http://qt.gtimg.cn/q=股票代码
    2. 东方财富接口 (备): http://push2.eastmoney.com/api/qt/stock/get
    3. 东方财富板块: http://push2.eastmoney.com/api/qt/clist/get
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def get_realtime_data(self, stock_code):
        """
        获取单个股票实时数据
        """
        try:
            url = f'http://qt.gtimg.cn/q={stock_code}'
            response = self.session.get(url, timeout=5)

            if response.status_code == 200:
                data = response.text
                match = re.search(r'"([^"]+)"', data)
                if match:
                    fields = match.group(1).split('~')
                    if len(fields) > 30:
                        return {
                            'code': stock_code,
                            'name': fields[1],
                            'price': float(fields[3]),
                            'open': float(fields[5]),
                            'close': float(fields[4]),
                            'high': float(fields[33]),
                            'low': float(fields[34]),
                            'volume': int(fields[36]),
                            'bid1': float(fields[9]),
                            'ask1': float(fields[19]),
                            'time': fields[30]
                        }
            return None
        except Exception as e:
            print(f"获取{stock_code}数据失败: {e}")
            return None

    def get_batch_realtime_data(self, stock_codes):
        """
        批量获取股票实时数据
        """
        results = {}
        codes_str = ','.join([f'sh{code}' if code.startswith('6') else f'sz{code}' for code in stock_codes])

        try:
            url = f'http://qt.gtimg.cn/q={codes_str}'
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.text
                lines = data.strip().split('\n')

                for i, line in enumerate(lines):
                    if i < len(stock_codes):
                        match = re.search(r'"([^"]+)"', line)
                        if match and len(stock_codes) > i:
                            fields = match.group(1).split('~')
                            if len(fields) > 30:
                                stock_code = stock_codes[i]
                                results[stock_code] = {
                                    'code': stock_code,
                                    'name': fields[1],
                                    'price': float(fields[3]),
                                    'open': float(fields[5]),
                                    'close': float(fields[4]),
                                    'high': float(fields[33]),
                                    'low': float(fields[34]),
                                    'volume': int(fields[36]),
                                    'change': float(fields[3]) - float(fields[4]),
                                    'change_pct': (float(fields[3]) - float(fields[4])) / float(fields[4]) * 100,
                                    'bid1': float(fields[9]),
                                    'ask1': float(fields[19]),
                                    'time': fields[30]
                                }
            return results
        except Exception as e:
            print(f"腾讯接口获取数据失败: {e}，尝试东方财富接口...")
            return self.get_batch_realtime_data_em(stock_codes)

    def get_index_data(self):
        """
        获取大盘指数数据
        """
        indices = {
            'sh000001': '上证指数',
            'sz399001': '深证成指',
            'sz399006': '创业板指'
        }

        results = {}
        codes_str = ','.join(indices.keys())

        try:
            url = f'http://qt.gtimg.cn/q={codes_str}'
            response = self.session.get(url, timeout=5)

            if response.status_code == 200:
                data = response.text
                lines = data.strip().split('\n')

                for i, (code, name) in enumerate(indices.items()):
                    if i < len(lines):
                        match = re.search(r'"([^"]+)"', lines[i])
                        if match:
                            fields = match.group(1).split('~')
                            if len(fields) > 30:
                                results[code] = {
                                    'code': code,
                                    'name': name,
                                    'price': float(fields[3]),
                                    'close': float(fields[4]),
                                    'high': float(fields[33]),
                                    'low': float(fields[34]),
                                    'volume': int(fields[36]),
                                    'change': float(fields[3]) - float(fields[4]),
                                    'change_pct': (float(fields[3]) - float(fields[4])) / float(fields[4]) * 100,
                                    'time': fields[30]
                                }
            return results
        except Exception as e:
            print(f"获取指数数据失败: {e}")
            return {}

    def get_sector_data(self):
        """
        获取热门板块数据（东方财富接口）
        """
        try:
            url = 'http://push2.eastmoney.com/api/qt/clist/get'
            params = {
                'cb': 'jQuery',
                'pn': 1,
                'pz': 20,
                'po': 1,
                'np': 1,
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:90 t:2 f:!50',
                'fields': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f62,f128,f136,f115,f152'
            }

            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                text = response.text
                json_str = re.search(r'\{.*\}', text, re.DOTALL)
                if json_str:
                    data = json.loads(json_str.group())
                    sectors = []

                    if 'data' in data and 'diff' in data['data']:
                        for item in data['data']['diff'][:10]:
                            sectors.append({
                                'name': item.get('f14', ''),
                                'change_pct': item.get('f3', 0),
                                'volume': item.get('f6', 0),
                                'lead_stock': item.get('f12', ''),
                                'lead_stock_name': item.get('f14', '')
                            })
                    return sectors
            return []
        except Exception as e:
            print(f"获取板块数据失败: {e}")
            return []

    def get_realtime_data_em(self, stock_code):
        """
        获取单个股票实时数据（东方财富接口-备用）
        secid格式: 1.上海股票 0.深圳股票
        """
        try:
            if stock_code.startswith('6'):
                secid = f'1.{stock_code}'
            else:
                secid = f'0.{stock_code}'

            url = 'http://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f43,f44,f45,f46,f47,f48,f49,f50,f57,f58,f60,f170',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }

            response = self.session.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if data.get('rc') == 0 and 'data' in data:
                    d = data['data']
                    return {
                        'code': d.get('f57', stock_code),
                        'name': d.get('f58', ''),
                        'price': float(d.get('f43', 0)) / 100 if d.get('f43') else 0,
                        'open': float(d.get('f46', 0)) / 100 if d.get('f46') else 0,
                        'close': float(d.get('f60', 0)) / 100 if d.get('f60') else 0,
                        'high': float(d.get('f44', 0)) / 100 if d.get('f44') else 0,
                        'low': float(d.get('f45', 0)) / 100 if d.get('f45') else 0,
                        'volume': int(d.get('f47', 0)),
                        'amount': float(d.get('f48', 0)),
                        'change_pct': float(d.get('f170', 0)) / 100 if d.get('f170') else 0,
                    }
            return None
        except Exception as e:
            print(f"东方财富接口获取{stock_code}数据失败: {e}")
            return None

    def get_batch_realtime_data_em(self, stock_codes):
        """
        批量获取股票实时数据（东方财富接口-备用）
        """
        results = {}

        try:
            secids = []
            for code in stock_codes:
                if code.startswith('6'):
                    secids.append(f'1.{code}')
                else:
                    secids.append(f'0.{code}')

            url = 'http://push2.eastmoney.com/api/qt/ulist.np/get'
            params = {
                'secids': ','.join(secids),
                'fields': 'f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }

            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('rc') == 0 and 'data' in data:
                    for item in data['data']:
                        stock_code = item.get('f12', '')
                        if stock_code:
                            results[stock_code] = {
                                'code': stock_code,
                                'name': item.get('f14', ''),
                                'price': item.get('f2', 0),
                                'change_pct': item.get('f3', 0),
                                'open': item.get('f5', 0),
                                'close': item.get('f4', 0),
                                'high': item.get('f15', 0),
                                'low': item.get('f16', 0),
                                'volume': item.get('f6', 0),
                                'amount': item.get('f8', 0),
                            }
            return results
        except Exception as e:
            print(f"东方财富批量获取数据失败: {e}")
            return {}

    def get_index_data_em(self):
        """
        获取大盘指数数据（东方财富接口-备用）
        """
        indices = {
            '1.000001': ('上证指数', 'sh000001'),
            '0.399001': ('深证成指', 'sz399001'),
            '0.399006': ('创业板指', 'sz399006')
        }

        results = {}

        try:
            secids = ','.join(indices.keys())
            url = 'http://push2.eastmoney.com/api/qt/ulist.np/get'
            params = {
                'secids': secids,
                'fields': 'f12,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }

            response = self.session.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if data.get('rc') == 0 and 'data' in data:
                    for item in data['data']:
                        secid = item.get('f12', '')
                        if secid in indices:
                            name, code = indices[secid]
                            change_pct = item.get('f3', 0)
                            price = item.get('f2', 0)
                            results[code] = {
                                'code': code,
                                'name': name,
                                'price': price,
                                'close': price - (change_pct * price / 100) if price and change_pct else price,
                                'high': item.get('f15', 0),
                                'low': item.get('f16', 0),
                                'volume': item.get('f6', 0),
                                'change': change_pct * price / 100 if price and change_pct else 0,
                                'change_pct': change_pct,
                            }
            return results
        except Exception as e:
            print(f"东方财富获取指数数据失败: {e}")
            return {}

    def get_historical_kline(self, stock_code, days=20):
        """
        获取股票历史K线数据（腾讯接口-主源）
        :param stock_code: 股票代码
        :param days: 获取天数
        :return: K线数据列表 [{date, open, close, high, low, volume}, ...]
        """
        try:
            if stock_code.startswith('6'):
                symbol = f'sh{stock_code}'
            else:
                symbol = f'sz{stock_code}'

            url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={symbol},day,,,{days},qfq'

            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                text = response.text
                if '=' in text:
                    text = text.split('=', 1)[1]
                data = json.loads(text)

                if 'data' in data and symbol in data['data']:
                    day_data = data['data'][symbol].get('qfqday') or data['data'][symbol].get('day', [])
                    result = []
                    for item in day_data[-days:]:
                        if len(item) >= 6:
                            result.append({
                                'date': item[0],
                                'open': float(item[1]),
                                'close': float(item[2]),
                                'high': float(item[3]),
                                'low': float(item[4]),
                                'volume': int(float(item[5]))
                            })
                    return result
            return []
        except Exception as e:
            print(f"获取历史K线失败: {e}")
            return []

    def cross_validate_data(self, stock_code, tx_data, em_data):
        """
        交叉验证两个数据源的数据
        返回:(验证通过的数据, 警告信息)
        """
        warnings = []

        if tx_data is None and em_data is None:
            return None, ['两个数据源都获取失败']

        if tx_data is None:
            return em_data, ['腾讯接口失败，使用东方财富数据']

        if em_data is None:
            return tx_data, ['东方财富接口失败，使用腾讯数据']

        price_diff = abs(tx_data.get('price', 0) - em_data.get('price', 0))
        if price_diff > 0.1:
            warning = f"数据不一致警告: 腾讯{tx_data.get('price')} vs 东方财富{em_data.get('price')}"
            warnings.append(warning)
            print(warning)

        if abs(tx_data.get('change_pct', 0) - em_data.get('change_pct', 0)) > 0.5:
            warning = f"涨跌幅不一致: 腾讯{tx_data.get('change_pct')}% vs 东方财富{em_data.get('change_pct')}%"
            warnings.append(warning)
            print(warning)

        return tx_data, warnings

class MarketSentimentAnalyzer:
    """
    大盘情绪分析器
    """

    def __init__(self, data_fetcher):
        self.data_fetcher = data_fetcher

    def analyze_sentiment(self):
        """
        分析大盘情绪
        """
        indices = self.data_fetcher.get_index_data()

        if not indices:
            return {'sentiment': 'unknown', 'score': 0, 'description': '无法获取大盘数据'}

        total_score = 0
        details = []

        for code, data in indices.items():
            change_pct = data['change_pct']

            if change_pct > 2:
                score = 10
                level = '极强'
            elif change_pct > 1:
                score = 8
                level = '强势'
            elif change_pct > 0.5:
                score = 6
                level = '偏强'
            elif change_pct > 0:
                score = 5
                level = '略强'
            elif change_pct > -0.5:
                score = 4
                level = '略弱'
            elif change_pct > -1:
                score = 3
                level = '偏弱'
            elif change_pct > -2:
                score = 1
                level = '弱势'
            else:
                score = 0
                level = '极弱'

            total_score += score
            details.append({
                'name': data['name'],
                'change_pct': change_pct,
                'level': level,
                'score': score
            })

        avg_score = total_score / len(indices)

        if avg_score >= 8:
            sentiment = '极强'
        elif avg_score >= 6:
            sentiment = '强势'
        elif avg_score >= 5:
            sentiment = '中性偏强'
        elif avg_score >= 4:
            sentiment = '中性偏弱'
        elif avg_score >= 2:
            sentiment = '弱势'
        else:
            sentiment = '极弱'

        return {
            'sentiment': sentiment,
            'score': avg_score,
            'details': details,
            'description': f'大盘情绪{sentiment}，综合评分{avg_score:.1f}/10'
        }

class StockSelector:
    """
    智能选股器
    """

    def __init__(self, data_fetcher, market_analyzer):
        self.data_fetcher = data_fetcher
        self.market_analyzer = market_analyzer

        # 股票池
        self.stock_pool = [
            '600519', '000858', '601318', '600036', '000001',
            '002594', '601888', '000333', '600276', '300750',
            '688981', '300760', '002475', '600900', '601012',
        ]

        # T+0品种池（可转债、ETF等）
        self.t0_pool = [
            '113050', '113051', '113052', '113053', '113054',  # 可转债
            '510300', '510500', '159915',  # 沪深300、创业板ETF
            '512000', '512100', '513500',  # 券商、军工、黄金ETF
            '513100', '513030', '513080',  # 纳指、港股、日经ETF
            '124000', '128000', '110000',  # 更多可转债
            '511010', '511020', '511030',  # 国债ETF
            '159788', '159866', '159825',  # 行业ETF
        ]

    def is_t0_product(self, code):
        """
        判断是否为T+0品种
        """
        return code in self.t0_pool

    def select_stocks(self, top_n=2, prefer_t0=False, market_session='normal'):
        """
        智能选股
        :param top_n: 选择的股票数量
        :param prefer_t0: 是否优先选择T+0品种
        :param market_session: 市场时段 ('open_rush': 开盘1-3分钟, 'normal': 其它)
        """
        sectors = self.data_fetcher.get_sector_data()
        sentiment = self.market_analyzer.analyze_sentiment()

        if sentiment['sentiment'] in ['极弱', '弱势'] and sentiment['score'] < 2:
            print('大盘情绪极弱，暂不选股')
            return []

        # 确定扫描范围
        if prefer_t0:
            scan_pool = self.t0_pool + self.stock_pool[:5]
        else:
            scan_pool = self.stock_pool + self.t0_pool

        stocks_data = self.data_fetcher.get_batch_realtime_data(scan_pool)

        if not stocks_data:
            print('无法获取股票数据')
            return []

        stock_scores = []

        for code, data in stocks_data.items():
            score = self._calculate_score(data, sectors, sentiment, market_session)

            stock_scores.append({
                'code': code,
                'name': data['name'],
                'price': data['price'],
                'change_pct': data['change_pct'],
                'score': score,
                'volume': data['volume'],
                'high': data['high'],
                'low': data['low'],
                'open': data['open'],
                'close': data['close'],
                'is_t0': self.is_t0_product(code)
            })

        stock_scores.sort(key=lambda x: x['score'], reverse=True)

        for stock in stock_scores[:10]:
            pattern_score, pattern_desc = self.analyze_pattern(stock['code'], stock['price'])
            stock['pattern_score'] = pattern_score
            stock['pattern_desc'] = pattern_desc
            stock['score'] += pattern_score

        stock_scores.sort(key=lambda x: x['score'], reverse=True)
        selected = stock_scores[:top_n]

        for s in selected:
            s['reason'] = self._get_select_reason(s, sectors)
            if s['pattern_desc'] != '普通形态' and s['pattern_desc'] != '数据不足':
                s['reason'] += f" | {s['pattern_desc']}"

        print(f"大盘情绪: {sentiment['description']}")
        print(f"热门板块: {[s['name'] for s in sectors[:3]]}")
        print(f"选中股票: {[(s['name'], s['score'], 'T+0' if s['is_t0'] else 'T+1') for s in selected]}")

        return selected

    def _calculate_score(self, stock_data, sectors, sentiment, market_session='normal'):
        """
        计算股票评分 - 严格模式，只选高胜率标的
        重点关注：集合竞价、开盘走势、量价配合、板块联动

        :param market_session: 市场时段
            'open_rush': 开盘1-3分钟(9:30-9:33) - 可追高条件
            'normal': 其它时段 - 禁止追高
        """
        score = 50

        change_pct = stock_data['change_pct']
        price = stock_data['price']
        open_price = stock_data['open']
        close_price = stock_data['close']
        high = stock_data['high']
        low = stock_data['low']
        volume = stock_data['volume']
        code = stock_data.get('code', '')

        # 涨跌停判断 - 直接排除
        limit_up_pct = 9.9
        if change_pct >= limit_up_pct:
            return -100
        if change_pct <= -9.9:
            return -100

        # 距离涨停的距离
        distance_to_limit = limit_up_pct - change_pct

        # ========== 竞价时段特殊评分 ==========
        if market_session == 'auction':
            if sentiment['sentiment'] in ['极弱', '弱势']:
                return -40

            sector_good = any(s['change_pct'] > 2 for s in sectors[:3])
            if not sector_good:
                score -= 20

            if change_pct > 6:
                score -= 30
            elif 2 <= change_pct <= 5:
                score += 25
            elif 0 <= change_pct < 2:
                score += 15
            else:
                score -= 20

            if volume > 3000000:
                score += 15
            elif volume > 1000000:
                score += 8

            if distance_to_limit < 2:
                score -= 25

            return score

        # ========== 其它时段禁止追高 ==========
        if market_session != 'open_rush' and change_pct > 7:
            return -60

        # ========== A股特有评分因素 ==========

        # 【因素1】量比（放量程度）
        # 量比 > 2 表示明显放量，可能是主力介入
        if volume > 0 and close_price > 0:
            # 假设日常平均成交量为收盘价 * 1000000 / 均价（约20元）
            avg_volume_estimate = 2000000  # 简化估算
            volume_ratio = volume / avg_volume_estimate
            if volume_ratio > 3:
                score += 20  # 巨量，主力明显介入
            elif volume_ratio > 2:
                score += 15
            elif volume_ratio > 1.5:
                score += 10
            elif volume_ratio < 0.5:
                score -= 15  # 缩量，观望

        # 【因素2】换手率估算
        # 换手率 = 成交量 / 流通股本 * 100%
        # A股正常换手率 1-5%，过高可能主力出货，过低不活跃
        turnover_rate = (volume / 10000000) * 100 if volume > 0 else 0  # 简化估算
        if 2 <= turnover_rate <= 8:
            score += 12  # 健康换手率
        elif turnover_rate > 15:
            score -= 10  # 换手率过高，可能主力对倒

        # 【因素3】振幅（日内波动）
        # 振幅过大不稳定，振幅过小不活跃
        if high > 0 and low > 0 and close_price > 0:
            amplitude = (high - low) / low * 100
            if 2 <= amplitude <= 5:
                score += 10  # 波动适中，最佳
            elif amplitude > 8:
                score -= 8   # 振幅过大，风险高
            elif amplitude < 1:
                score -= 5   # 振幅过小，不活跃

        # 【因素4】价格位置（相对于日内高低点）
        # A股特性：在低位起涨比在高位追安全
        if high > low:
            position_in_range = (price - low) / (high - low) * 100 if high != low else 50
            if position_in_range < 25:
                score += 15  # 回调低位，安全边际高
            elif position_in_range < 40:
                score += 10  # 上涨中继
            elif position_in_range > 85:
                score -= 15  # 接近高点，追高风险
            elif position_in_range > 95:
                score -= 25  # 接近涨停，风险极大

        # 【因素5】开盘方式（A股特有：高开低走陷阱）
        if open_price > 0 and close_price > 0 and price > 0:
            open_change_pct = (open_price - close_price) / close_price * 100
            price_change_from_open = (price - open_price) / open_price * 100

            # 低开高走 = 主力吸筹 or 洗盘结束
            if open_change_pct < -1 and price_change_from_open > 1:
                score += 18  # 低开高走，强势信号
            # 平开高走
            elif abs(open_change_pct) < 0.5 and price_change_from_open > 1:
                score += 15  # 平稳上涨
            # 高开低走 = 主力出货 or 诱多（A股常见陷阱）
            elif open_change_pct > 2 and price_change_from_open < -1:
                score -= 25  # 高开低走，危险信号
            # 竞价涨停后被砸（A股常见）
            elif open_change_pct > 5 and change_pct < open_change_pct - 2:
                score -= 20  # 竞价被砸

        # 【因素6】板块效应（A股羊群效应明显）
        # 跟涨板块比独自上涨更安全
        sector_match = False
        strong_sectors = [s for s in sectors if s['change_pct'] > 2]
        if strong_sectors:
            for strong_sector in strong_sectors:
                sector_name = strong_sector['name']
                # 检查股票是否可能属于这些强势板块（通过股票代码粗略判断）
                if self._is_stock_in_sector(stock_data.get('code', ''), sector_name):
                    sector_match = True
                    score += 18
                    break

        if not sector_match and change_pct > 3:
            score -= 12  # 独自上涨，板块不跟，风险

        # 【因素7】大盘配合度（A股跟大盘相关性高）
        if sentiment['sentiment'] in ['极强', '强势']:
            if change_pct > 0:
                score += 15  # 大盘涨它也涨，顺势
        elif sentiment['sentiment'] in ['弱势', '极弱']:
            if change_pct < 0:
                score += 10  # 大盘跌它也跌，抗跌
            elif change_pct > 2:
                score -= 20  # 大盘差它却涨，逆势风险大
        else:  # 中性
            if change_pct > 0:
                score += 5

        # 【因素8】涨跌停距离（A股涨停板战法）
        if change_pct >= 8:
            score -= 30  # 接近涨停，可能被砸板
        elif change_pct >= 7:
            score -= 20
        elif 4 <= change_pct < 7:
            score += 8  # 涨幅适中，还有空间
        elif 2 <= change_pct < 4:
            score += 15  # 黄金区间
        elif 1 <= change_pct < 2:
            score += 12
        elif 0 <= change_pct < 1:
            score += 5
        else:
            score -= 20  # 下跌不碰

        # 【因素9】T+0品种加分（可日内止损）
        if self.is_t0_product(stock_data.get('code', '')):
            score += 8  # T+0可以日内纠错

        # 【因素10】市值特征（A股大盘股稳定，小盘股弹性大）
        if price > 0:
            # 假设流通股本约为成交量/换手率（简化）
            market_cap_proxy = price * 10000000  # 简化估算
            if price > 100:  # 高价股（通常是龙头）
                score += 5
            elif price < 5:  # 低价股风险大
                score -= 10

        # 【因素11】北向资金代理（通过沪深股通成分股判断）
        # 沪深股通标的更受外资青睐
        if self._is_market_connect_stock(stock_data.get('code', '')):
            score += 5  # 陆股通标的加分

        return score

    def _is_stock_in_sector(self, code, sector_name):
        if not code:
            return False

        sector_stocks = {
            '白酒': ['600519', '000858', '000596', '603589', '000568', '002304'],
            '银行': ['600000', '600036', '601318', '601328', '601398', '601288', '600015', '002142'],
            '医药': ['600276', '000538', '600196', '000623', '002007', '300003', '300015', '688180'],
            '新能源': ['300750', '002594', '601012', '600438', '002459', '603806', '002074'],
            '科技': ['000001', '600570', '300033', '002230', '688981', '300760', '002475'],
            '消费': ['000333', '002024', '600887', '000651', '603259', '300015'],
            '券商': ['600030', '601066', '000776', '600999', '601688', '000166'],
        }

        if sector_name in sector_stocks:
            return code in sector_stocks[sector_name]

        if sector_name == '新能源' and (code.startswith('30') or code.startswith('60')):
            return True

        return False

    def _is_market_connect_stock(self, code):
        if not code:
            return False
        return True

    def _get_select_reason(self, stock_data, sectors):
        """
        获取选股原因
        """
        reasons = []

        if stock_data['change_pct'] > 2:
            reasons.append(f'涨幅{stock_data["change_pct"]:.2f}%，强势上涨')
        elif stock_data['change_pct'] > 0:
            reasons.append(f'涨幅{stock_data["change_pct"]:.2f}%，稳步上涨')

        for sector in sectors[:3]:
            if sector['change_pct'] > 2:
                reasons.append(f'所在板块{sector["name"]}强势')

        return '; '.join(reasons) if reasons else '综合评分较高'

    def analyze_pattern(self, stock_code, current_price):
        """
        形态分析 - 分析股票历史走势形态
        返回: (形态评分, 形态描述)
        """
        try:
            klines = self.data_fetcher.get_historical_kline(stock_code, days=20)
            if len(klines) < 10:
                return 0, '数据不足'

            closes = [k['close'] for k in klines]
            volumes = [k['volume'] for k in klines]

            pattern_score = 0
            pattern_desc = []

            # 计算均线
            ma5 = sum(closes[-5:]) / 5
            ma10 = sum(closes[-10:]) / 10
            ma20 = sum(closes[-20:]) if len(closes) >= 20 else sum(closes) / len(closes)

            # 【形态1】近期有涨停板
            limit_up_days = 0
            for i in range(min(5, len(klines))):
                if i > 0:
                    prev_close = klines[-(i+1)]['close']
                    curr_close = klines[-i]['close']
                    if curr_close >= prev_close * 1.095:  # 涨停
                        limit_up_days += 1
                        if i <= 3:
                            pattern_score += 20  # 近期有涨停加分
                            pattern_desc.append(f'{i}日前涨停')

            # 【形态2】回调不破均线（经典形态）
            current_ma5_diff = (current_price - ma5) / ma5 * 100
            current_ma10_diff = (current_price - ma10) / ma10 * 100

            if limit_up_days > 0:
                # 有涨停历史，当前回调到均线附近
                if abs(current_ma5_diff) < 2:
                    pattern_score += 25
                    pattern_desc.append('回调MA5不破')
                if abs(current_ma10_diff) < 3:
                    pattern_score += 15
                    pattern_desc.append('回调MA10不破')

            # 【形态3】量价配合（上涨时放量，调整时缩量）
            recent_vol_avg = sum(volumes[-5:]) / 5
            earlier_vol_avg = sum(volumes[-10:-5]) / 5 if len(volumes) >= 10 else recent_vol_avg

            if recent_vol_avg > earlier_vol_avg * 1.5:
                pattern_score += 15
                pattern_desc.append('量能放大')

            # 【形态4】均线多头排列
            if ma5 > ma10 > ma20 * 0.98:
                pattern_score += 20
                pattern_desc.append('均线多头')
            elif ma5 > ma10:
                pattern_score += 10
                pattern_desc.append('均线向上')

            # 【形态5】近期走势强劲（累计涨幅）
            if len(closes) >= 5:
                gain_5d = (closes[-1] - closes[-5]) / closes[-5] * 100
                if gain_5d > 10:
                    pattern_score += 15
                    pattern_desc.append('5日涨幅10%+')
                elif gain_5d > 5:
                    pattern_score += 10
                    pattern_desc.append('5日涨幅5%+')

            # 【形态6】今日价格位置（在日内高低点区间）
            if len(klines) > 0:
                today_high = klines[-1]['high']
                today_low = klines[-1]['low']
                if today_high > today_low:
                    price_position = (current_price - today_low) / (today_high - today_low) * 100
                    if price_position < 40:
                        pattern_score += 10
                        pattern_desc.append('价格回调低位')

            desc = ', '.join(pattern_desc) if pattern_desc else '普通形态'
            return pattern_score, desc

        except Exception as e:
            print(f"形态分析失败: {e}")
            return 0, '分析失败'

    def calculate_technical_indicators(self, klines):
        """
        计算技术指标（RSI、MACD等）
        """
        if len(klines) < 20:
            return {}

        closes = [k['close'] for k in klines]

        # RSI计算
        delta = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in delta]
        losses = [-d if d < 0 else 0 for d in delta]

        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14

        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        # MACD（简化计算）
        ema12 = sum(closes[-12:]) / 12
        ema26 = sum(closes[-26:]) / 26
        macd = ema12 - ema26

        return {
            'rsi': rsi,
            'macd': macd,
            'ema12': ema12,
            'ema26': ema26
        }

class TradingStrategy:
    """
    交易策略
    """

    def __init__(self, data_fetcher, stock_selector, market_analyzer, dingtalk_webhook=''):
        self.data_fetcher = data_fetcher
        self.stock_selector = stock_selector
        self.market_analyzer = market_analyzer
        self.dingtalk_webhook = dingtalk_webhook
        self.positions = {}
        self.trade_log = []
        self.max_positions = 2
        self.max_loss_per_trade = 0.03
        self.trade_count = 0

    def send_notification(self, message):
        """
        发送钉钉通知
        """
        if not self.dingtalk_webhook:
            print(message)
            return

        try:
            full_message = f"【量化】{message}"
            payload = {
                "msgtype": "text",
                "text": {
                    "content": full_message
                }
            }
            response = requests.post(self.dingtalk_webhook, json=payload, timeout=10)
            response.raise_for_status()
            print(f"通知发送成功: {message}")
        except Exception as e:
            print(f"通知发送失败: {e}")

    def check_and_trade(self):
        """
        检查市场并交易
        """
        current_time = datetime.now().time()
        current_date = datetime.now().strftime('%Y-%m-%d')

        print(f"\n{'='*60}")
        print(f"时间: {current_date} {current_time.strftime('%H:%M:%S')}")
        print(f"{'='*60}")

        sentiment = self.market_analyzer.analyze_sentiment()
        print(f"大盘情绪: {sentiment['description']}")

        # 判断是否为开盘1-3分钟追高时段
        open_rush = time(9, 30) <= current_time <= time(9, 33)
        morning_session = time(9, 30) <= current_time <= time(10, 20)
        other_session = time(10, 21) <= current_time <= time(14, 55)
        afternoon_session = time(13, 0) <= current_time <= time(14, 55)

        market_session = 'open_rush' if open_rush else 'normal'

        # 集合竞价时段选股（竞价委托）
        auction_session = time(9, 15) <= current_time <= time(9, 25)
        if auction_session and len(self.positions) < self.max_positions:
            self.auction_selection()

        # 早盘选股（主要买点）
        if morning_session and len(self.positions) < self.max_positions:
            self.morning_selection(market_session=market_session)

        # 下午盘T+0日内套利机会
        if afternoon_session:
            self.afternoon_t0_opportunity()

        # 其他时段选股（次要买点）
        if other_session and len(self.positions) < self.max_positions:
            self.other_session_selection()

        # 监控持仓（特别是T+0品种可以更频繁交易）
        self.monitor_positions()

        # 只有在交易日（非周末）且15:00后才发送收盘总结
        if current_time >= time(15, 0) and datetime.now().weekday() < 5:
            self.close_all_positions()

    def auction_selection(self):
        """
        集合竞价时段选股
        如果看到持续买盘增加、量价配合上涨，结合形态、板块、情绪等综合判断，
        可以在竞价阶段（9:25前）挂单买入
        """
        print("\n检查集合竞价标的...")

        selected_stocks = self.stock_selector.select_stocks(
            top_n=self.max_positions - len(self.positions),
            prefer_t0=False,
            market_session='auction'
        )

        if not selected_stocks:
            return

        # 只推送高置信度的标的（评分>85）
        high_confidence = [s for s in selected_stocks if s['score'] >= 85]

        if high_confidence:
            stock_list = '\n'.join([
                f"{s['name']}({s['code']}) 竞价买入 评分:{s['score']:.0f}"
                for s in high_confidence
            ])
            message = f"⚡ 竞价委托信号\n{stock_list}\n时间: {datetime.now().strftime('%H:%M:%S')}\n说明: 集合竞价9:25前有效"
            self.send_notification(message)

            for stock in high_confidence:
                self.buy_stock(stock)

    def morning_selection(self, market_session='normal'):
        """
        早盘选股（主要买点）
        :param market_session: 市场时段 ('open_rush': 开盘1-3分钟, 'normal': 其它)
        """
        print("\n开始早盘选股...")

        selected_stocks = self.stock_selector.select_stocks(
            top_n=self.max_positions - len(self.positions),
            prefer_t0=False,
            market_session=market_session
        )

        if not selected_stocks:
            self.send_notification("📊 早盘选股结果：未找到合适标的，建议观望")
            return

        stock_list = '\n'.join([f"{s['name']}({s['code']}) 涨幅{s['change_pct']:.2f}% {'🔄T+0' if s['is_t0'] else '📅T+1'}" 
                               for s in selected_stocks])
        message = f"📈 早盘选股结果\n股票:\n{stock_list}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self.send_notification(message)

        for stock in selected_stocks:
            self.buy_stock(stock)

    def afternoon_t0_opportunity(self):
        """
        下午盘T+0日内套利机会
        利用T+0品种的特性，在下午进行日内波段操作
        """
        if not self.positions:
            print("\n检查T+0日内套利机会...")
            
            # 寻找便宜的T+0品种进行日内套利
            selected_stocks = self.stock_selector.select_stocks(
                top_n=1,
                prefer_t0=True
            )
            
            if selected_stocks and selected_stocks[0]['score'] >= 70:
                stock = selected_stocks[0]
                
                # 检查是否在低位（适合日内买入）
                if -2 < stock['change_pct'] < 2:
                    print(f"发现T+0日内套利机会: {stock['name']}")
                    self.buy_stock(stock, is_intraday=True)
        else:
            # 持仓中有T+0品种，检查是否可以日内高抛低吸
            for code, position in list(self.positions.items()):
                if self.stock_selector.is_t0_product(code):
                    self.intraday_t0_trade(code, position)

    def intraday_t0_trade(self, code, position):
        """
        T+0日内交易
        """
        codes = [code]
        data = self.data_fetcher.get_batch_realtime_data(codes)
        
        if code not in data:
            return
        
        stock_data = data[code]
        current_price = stock_data['price']
        buy_price = position['buy_price']
        change_pct = stock_data['change_pct']
        
        if current_price <= 0:
            return
        
        # 如果持仓盈利超过2%，考虑先卖出部分锁利
        profit_pct = (current_price - buy_price) / buy_price * 100
        
        if profit_pct > 3 and position.get('intraday_sold', False) == False:
            # 日内卖出，锁定利润
            message = f"🔄 T+0日内锁利\n股票: {position['name']}({code})\n当前价: {current_price:.2f}\n持仓盈利: {profit_pct:.2f}%\n说明: T+0品种日内先卖，尾盘接回"
            self.send_notification(message)
            position['intraday_sold'] = True
            position['intraday_sell_price'] = current_price
        
        # 如果之前卖出，现在价格回落，可以接回
        if position.get('intraday_sold', False) and change_pct < 0:
            sell_price = position.get('intraday_sell_price', buy_price)
            if current_price < sell_price * 0.99:
                message = f"🔄 T+0日内接回\n股票: {position['name']}({code})\n买回价: {current_price:.2f}\n卖出价: {sell_price:.2f}\n节省成本: {(sell_price - current_price) * position['shares']:.2f}元"
                self.send_notification(message)
                position['intraday_sold'] = False

    def other_session_selection(self):
        """
        其他时段选股（次要买点）
        """
        print("\n检查其他时段机会...")

        sentiment = self.market_analyzer.analyze_sentiment()

        if sentiment['sentiment'] not in ['极强', '强势', '中性偏强']:
            print("大盘情绪不够强，不建议追涨")
            return

        selected_stocks = self.stock_selector.select_stocks(
            top_n=self.max_positions - len(self.positions),
            prefer_t0=True
        )

        if not selected_stocks:
            return

        for stock in selected_stocks:
            if stock['score'] >= 80:
                print(f"发现优质标的: {stock['name']}, 评分: {stock['score']}")
                self.buy_stock(stock)

    def buy_stock(self, stock, is_intraday=False):
        """
        买入股票
        """
        code = stock['code']
        name = stock['name']
        price = stock['price']

        if price <= 0:
            print(f"股票价格异常，跳过买入: {name}")
            return

        position_size = 100

        self.positions[code] = {
            'name': name,
            'buy_price': price,
            'buy_time': datetime.now(),
            'shares': position_size,
            'stop_loss': price * (1 - self.max_loss_per_trade),
            'target': price * 1.05,
            'status': 'holding',
            'highest_price': price,
            'is_t0': stock.get('is_t0', False),
            'is_intraday': is_intraday
        }

        self.trade_count += 1

        t0_tag = '🔄T+0' if stock.get('is_t0', False) else '📅T+1'
        intraday_tag = ' (日内套利)' if is_intraday else ''

        message = f"✅ 买入信号{t0_tag}{intraday_tag}\n股票: {name}({code})\n价格: {price:.2f}\n数量: {position_size}股\n买入时间: {datetime.now().strftime('%H:%M:%S')}\n止损价: {price*0.97:.2f}\n目标价: {price*1.05:.2f}\n交易编号: #{self.trade_count}"
        self.send_notification(message)

        self.trade_log.append({
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'action': 'BUY',
            'code': code,
            'name': name,
            'price': price,
            'shares': position_size,
            'is_t0': stock.get('is_t0', False),
            'is_intraday': is_intraday
        })

    def monitor_positions(self):
        """
        监控持仓
        """
        if not self.positions:
            return

        codes = list(self.positions.keys())
        data = self.data_fetcher.get_batch_realtime_data(codes)

        current_time = datetime.now().time()

        for code, position in list(self.positions.items()):
            if code not in data:
                continue

            stock_data = data[code]
            current_price = stock_data['price']
            buy_price = position['buy_price']
            change_pct = stock_data['change_pct']

            if current_price <= 0:
                continue

            profit_pct = (current_price - buy_price) / buy_price * 100

            # 更新最高价
            if current_price > position['highest_price']:
                position['highest_price'] = current_price

            # 止损检查
            if current_price <= position['stop_loss']:
                self.sell_stock(code, '止损', current_price, profit_pct)
                continue

            # 止盈检查
            if profit_pct >= 5:
                self.sell_stock(code, '止盈', current_price, profit_pct)
                continue

            # T+0品种更积极的止损
            if position['is_t0']:
                # 如果下跌超过1.5%且盈利超过2%，考虑先出局
                if change_pct < -1.5 and profit_pct > 2:
                    self.sell_stock(code, 'T+0保护利润', current_price, profit_pct)
                    continue

            # 非T+0品种的持仓时间管理
            hold_hours = 0
            if not position['is_t0']:
                hold_hours = (datetime.now() - position['buy_time']).total_seconds() / 3600
                if hold_hours > 48:
                    self.sell_stock(code, '超时平仓', current_price, profit_pct)
                    continue

            # 尾盘决策
            if time(14, 30) <= current_time <= time(14, 55):
                if profit_pct < -1:
                    self.sell_stock(code, '尾盘止损', current_price, profit_pct)
                elif profit_pct > 0 and hold_hours > 4:
                    trailing_stop = position['highest_price'] * 0.98
                    if current_price <= trailing_stop:
                        self.sell_stock(code, '移动止损', current_price, profit_pct)

    def sell_stock(self, code, reason, current_price, profit_pct):
        """
        卖出股票
        """
        if code not in self.positions:
            return

        position = self.positions[code]
        name = position['name']
        buy_price = position['buy_price']
        shares = position['shares']

        profit = (current_price - buy_price) * shares

        t0_tag = '🔄T+0' if position['is_t0'] else '📅T+1'

        message = f"🔔 卖出信号{t0_tag}\n股票: {name}({code})\n原因: {reason}\n买入价: {buy_price:.2f}\n卖出价: {current_price:.2f}\n收益率: {profit_pct:.2f}%\n收益金额: {profit:.2f}元"
        self.send_notification(message)

        self.trade_log.append({
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'action': 'SELL',
            'code': code,
            'name': name,
            'price': current_price,
            'shares': shares,
            'reason': reason,
            'profit_pct': profit_pct,
            'profit': profit,
            'is_t0': position['is_t0']
        })

        del self.positions[code]

    def close_all_positions(self):
        """
        收盘平仓
        """
        if not self.positions:
            print("无持仓")
            return

        codes = list(self.positions.keys())
        data = self.data_fetcher.get_batch_realtime_data(codes)

        for code in codes:
            if code in data:
                position = self.positions[code]
                current_price = data[code]['price']
                buy_price = position['buy_price']
                profit_pct = (current_price - buy_price) / buy_price * 100

                self.sell_stock(code, '收盘平仓', current_price, profit_pct)

        self.send_daily_summary()

    def send_daily_summary(self):
        """
        发送交易日总结
        """
        if not self.trade_log:
            return

        buys = [t for t in self.trade_log if t['action'] == 'BUY']
        sells = [t for t in self.trade_log if t['action'] == 'SELL']
        
        t0_trades = [t for t in self.trade_log if t.get('is_t0', False)]

        total_profit = sum([t.get('profit', 0) for t in sells])

        summary = f"📊 交易日总结\n日期: {datetime.now().strftime('%Y-%m-%d')}\n"
        summary += f"买入次数: {len(buys)}\n"
        summary += f"卖出次数: {len(sells)}\n"
        summary += f"T+0交易: {len(t0_trades)}次\n"
        summary += f"总收益: {total_profit:.2f}元\n"
        summary += f"剩余持仓: {len(self.positions)}只"

        self.send_notification(summary)

class AShareRealtimeStrategy:
    """
    A股实时套利策略主类
    """

    def __init__(self, dingtalk_webhook=''):
        self.data_fetcher = RealtimeDataFetcher()
        self.market_analyzer = MarketSentimentAnalyzer(self.data_fetcher)
        self.stock_selector = StockSelector(self.data_fetcher, self.market_analyzer)
        self.trading_strategy = TradingStrategy(
            self.data_fetcher,
            self.stock_selector,
            self.market_analyzer,
            dingtalk_webhook
        )

    def run(self, interval_minutes=5):
        """
        运行策略 - 智能调整检查间隔
        不同时段使用不同间隔:
        - 早盘 9:30-10:20: 2分钟（黄金买点）
        - 盘中 10:21-14:30: 5分钟
        - 尾盘 14:30-15:00: 2分钟（移动止损）
        - T+0品种: 额外每3分钟监控
        """
        print("="*60)
        print("A股实时套利策略启动（智能间隔版）")
        print("="*60)

        while True:
            try:
                current_time = datetime.now().time()
                weekday = datetime.now().weekday()

                # 交易时段判断（包含周末判断）
                trading_hours = (
                    weekday < 5 and  # 仅工作日
                    (
                        time(9, 25) <= current_time <= time(11, 35) or
                        time(13, 0) <= current_time <= time(15, 5)
                    )
                )

                if trading_hours:
                    interval = self._get_adaptive_interval(current_time)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 检查市场，间隔{interval}秒...")
                    self.trading_strategy.check_and_trade()
                    time_module.sleep(interval)
                else:
                    time_module.sleep(300)

            except KeyboardInterrupt:
                print("\n策略已停止")
                break
            except Exception as e:
                print(f"策略执行错误: {e}")
                time_module.sleep(60)

    def _get_adaptive_interval(self, current_time):
        """
        根据时段返回合适的检查间隔（秒）
        集合竞价和开盘是关键时段，需要高频扫描
        """
        # 集合竞价早期 9:15-9:20
        call_early = time(9, 15) <= current_time <= time(9, 20)
        # 集合竞价后期 + 开盘 9:20-9:35（黄金时段）
        call_late_open = time(9, 20) <= current_time <= time(9, 35)
        # 开盘延续 9:35-9:50
        open_extend = time(9, 35) <= current_time <= time(9, 50)
        # 早盘主要时段 9:50-10:20
        morning_main = time(9, 50) <= current_time <= time(10, 20)
        # 尾盘关键时段 14:30-15:00
        afternoon_key = time(14, 30) <= current_time <= time(15, 0)

        if call_early:
            return 10  # 10秒
        elif call_late_open:
            return 5   # 5秒 - 黄金时段最高频
        elif open_extend:
            return 10  # 10秒
        elif morning_main:
            return 60  # 1分钟
        elif afternoon_key:
            return 120  # 2分钟
        else:
            return 180  # 3分钟

    def run_once(self):
        """
        运行一次检查
        """
        self.trading_strategy.check_and_trade()

if __name__ == '__main__':
    strategy = AShareRealtimeStrategy()
    strategy.run_once()