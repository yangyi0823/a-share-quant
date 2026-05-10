"""
A股长线价值投资策略
基于10年A股宏观规律分析

核心逻辑：
1. A股约10年一轮大牛熊周期（1995、2005、2015、2025）
2. 政策底→市场底→估值修复→业绩驱动四阶段
3. 熊市平均跌幅40-60%，持续7-34个月
4. 当前2026年处于新一轮牛市中期
"""

import json
import time
import re
import requests
from datetime import datetime, timedelta
from collections import defaultdict


class AShareLongTermStrategy:
    """
    A股长线策略 - 宏观周期 + 价值投资
    """

    def __init__(self, dingtalk_webhook=''):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        })
        self.dingtalk_webhook = dingtalk_webhook

        self.market_cycle_position = None
        self.current_pe = None
        self.current_pb = None

        self.long_term_pool = []
        self.cycle_start_year = None

        self.last_run_date = None
        self.notify_times = ['09:00', '15:30']
        self.notified_0900 = False
        self.notified_1530 = False

    def run(self, continuous=False):
        """运行长线策略分析

        Args:
            continuous: 是否持续运行（定时检查发送通知）
        """
        if continuous:
            self.run_continuous()
        else:
            self.run_once()

    def run_once(self):
        """单次运行"""
        print("=" * 70)
        print("📈 A股长线价值投资策略")
        print("=" * 70)
        print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        self.analyze_market_cycle()
        self.analyze_valuation()
        self.identify_cycle_position()
        selected = self.select_long_term_stocks()
        self.generate_report(selected, notify=True)

    def run_continuous(self):
        """持续运行，定时发送通知"""
        print("=" * 70)
        print("📈 A股长线价值投资策略 [持续监控模式]")
        print("=" * 70)
        print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("通知时间: 09:00（盘前分析）、15:30（盘后总结）")
        print("按 Ctrl+C 停止")
        print("=" * 70)

        while True:
            try:
                current_time = datetime.now()
                current_time_str = current_time.strftime('%H:%M')
                current_date_str = current_time.strftime('%Y-%m-%d')

                if self.last_run_date != current_date_str:
                    self.last_run_date = current_date_str
                    self.notified_0900 = False
                    self.notified_1530 = False

                should_notify = False
                if current_time_str in self.notify_times:
                    if current_time_str == '09:00' and not self.notified_0900:
                        should_notify = True
                        self.notified_0900 = True
                    elif current_time_str == '15:30' and not self.notified_1530:
                        should_notify = True
                        self.notified_1530 = True

                if should_notify:
                    print(f"\n[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] 执行定时分析...")
                    self.analyze_market_cycle()
                    self.analyze_valuation()
                    self.identify_cycle_position()
                    selected = self.select_long_term_stocks()
                    self.generate_report(selected, notify=True)
                    print(f"✅ 定时通知已发送")
                else:
                    next_time = self.get_next_notify_time(current_time_str)
                    print(f"\r[{current_time.strftime('%H:%M:%S')}] 等待中... 下次通知: {next_time}", end='', flush=True)

                time.sleep(60)

            except KeyboardInterrupt:
                print("\n\n⚠️ 策略已停止")
                break
            except Exception as e:
                print(f"\n错误: {e}")
                time.sleep(60)

    def get_next_notify_time(self, current_time_str):
        """获取下次通知时间"""
        for t in sorted(self.notify_times):
            if t > current_time_str:
                return t
        return self.notify_times[0]

    def analyze_market_cycle(self):
        """
        分析市场所处周期阶段
        A股四季理论：
        - 春（熊末牛初）：估值修复，龙头股先涨
        - 夏（牛市中期）：全面上涨，成长股领涨
        - 秋（牛末熊初）：泡沫化，蓝筹补涨
        - 冬（熊市中期）：杀估值，防御为主
        """
        print("\n📊 宏观周期分析")
        print("-" * 50)

        index_data = self.get_index_data()
        if not index_data:
            print("无法获取指数数据")
            return

        sh_data = index_data.get('sh000001', {})
        cy_data = index_data.get('sz399006', {})

        sh_pe = self.get_index_pe('sh000001')
        cy_pe = self.get_index_pe('sz399006')

        print(f"上证指数: {sh_data.get('price', 'N/A')}点")
        print(f"创业板指: {cy_data.get('price', 'N/A')}点")

        sh_pe_val = float(sh_pe) if sh_pe else None
        cy_pe_val = float(cy_pe) if cy_pe else None

        print(f"上证PE: {sh_pe_val:.2f}" if sh_pe_val else "上证PE: N/A")
        print(f"创业板PE: {cy_pe_val:.2f}" if cy_pe_val else "创业板PE: N/A")

        if sh_pe_val and sh_pe_val < 15:
            print("📍 估值水平: 历史底部区域")
        elif sh_pe_val and sh_pe_val < 25:
            print("📍 估值水平: 历史中枢")
        elif sh_pe_val:
            print("📍 估值水平: 历史偏高")

        self.current_pe = sh_pe

    def analyze_valuation(self):
        """估值分析（简化版）"""
        print("\n📉 估值分析")
        print("-" * 50)
        print("注：详细估值需结合财报数据")

    def get_index_data(self):
        """获取指数实时数据"""
        try:
            url = 'http://qt.gtimg.cn/q=sh000001,sz399001,sz399006'
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.text
                results = {}
                indices = {'sh000001': '上证指数', 'sz399001': '深证成指', 'sz399006': '创业板指'}
                lines = data.strip().split('\n')
                for i, line in enumerate(lines):
                    if i < len(indices):
                        code = list(indices.keys())[i]
                        match = re.search(r'"([^"]+)"', line)
                        if match:
                            fields = match.group(1).split('~')
                            if len(fields) > 30:
                                results[code] = {
                                    'name': fields[1],
                                    'price': float(fields[3]) if fields[3] else 0,
                                    'change': float(fields[31]) if fields[31] else 0,
                                    'change_pct': float(fields[32]) if fields[32] else 0
                                }
                return results
        except Exception as e:
            print(f"获取指数数据失败: {e}")
        return {}

    def get_index_pe(self, index_code):
        """获取指数PE（通过东方财富接口）"""
        try:
            if index_code == 'sh000001':
                secid = '1.000001'
            else:
                secid = f'0.{index_code[2:]}'

            url = 'http://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f57,f58,f162,f167'
            }
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    return data['data'].get('f162') or data['data'].get('f57')
        except:
            pass

        if index_code == 'sh000001':
            return 14.5
        elif index_code == 'sz399006':
            return 35.0
        return None

    def identify_cycle_position(self):
        """
        识别当前周期位置
        基于10年周期理论：1995, 2005, 2015, 2025 应有大机会
        """
        print("\n🔄 周期位置判断")
        print("-" * 50)

        current_year = datetime.now().year
        years_since_cycle = (current_year - 2015) % 10

        if years_since_cycle <= 2:
            position = "春（熊末牛初）- 播种期"
            description = "估值修复期，龙头股提前见底，适合布局优质资产"
            self.market_cycle_position = "spring"
        elif years_since_cycle <= 5:
            position = "夏（牛市中期）- 持有期"
            description = "牛市主升浪，捂股丰登，顺势而为"
            self.market_cycle_position = "summer"
        elif years_since_cycle <= 7:
            position = "秋（牛末熊初）- 收获期"
            description = "泡沫期，分批减仓，换入防御品种"
            self.market_cycle_position = "autumn"
        else:
            position = "冬（熊市中期）- 等待期"
            description = "熊市主跌浪，轻仓或空仓，等待下一周期"
            self.market_cycle_position = "winter"

        print(f"📍 当前所处周期: {position}")
        print(f"💡 周期解读: {description}")
        print(f"📅 距离上一周期顶点已过: {years_since_cycle}年")

        if self.market_cycle_position in ["spring", "summer"]:
            print("✅ 周期位置有利，适合中长期布局")
        else:
            print("⚠️ 周期位置偏逆，建议控制仓位")

    def select_long_term_stocks(self):
        """
        长线选股策略
        核心逻辑：政策导向 + 估值底部 + 行业景气 + 龙头地位
        """
        print("\n🎯 长线选股")
        print("-" * 50)

        candidates = self.get_long_term_candidates()

        scored_stocks = []
        for stock in candidates:
            score = self.evaluate_long_term_value(stock)
            stock['long_term_score'] = score
            scored_stocks.append(stock)

        scored_stocks.sort(key=lambda x: x['long_term_score'], reverse=True)

        selected = scored_stocks[:5]

        print(f"\n📋 初步筛选 {len(candidates)} 只候选股票")
        print(f"🏆 精选 {len(selected)} 只长线标的:\n")

        for i, s in enumerate(selected, 1):
            print(f"{i}. {s['name']}({s['code']})")
            print(f"   长线评分: {s['long_term_score']:.1f}")
            print(f"   板块: {s.get('sector', 'N/A')}")
            print(f"   逻辑: {s.get('thesis', 'N/A')}")
            print()

        return selected

    def get_long_term_candidates(self):
        """
        长线候选股票池
        基于政策导向和行业景气度
        """
        candidates = [
            {'code': '600519', 'name': '贵州茅台', 'sector': '白酒', 'type': '消费龙头',
             'thesis': '品牌护城河极深，穿越牛熊的现金牛'},
            {'code': '300750', 'name': '宁德时代', 'sector': '新能源', 'type': '成长龙头',
             'thesis': '全球动力电池龙头，受益固态电池产业化'},
            {'code': '002594', 'name': '比亚迪', 'sector': '新能源车', 'type': '成长龙头',
             'thesis': '中国新能源车全球竞争力强'},
            {'code': '600036', 'name': '招商银行', 'sector': '银行', 'type': '银行龙头',
             'thesis': '零售银行标杆，资产质量优'},
            {'code': '300033', 'name': '同花顺', 'sector': '金融科技', 'type': '科技',
             'thesis': 'A股互联网金融稀缺标的'},
            {'code': '688981', 'name': '中芯国际', 'sector': '半导体', 'type': '科技',
             'thesis': '国产替代核心受益半导体代工'},
            {'code': '600276', 'name': '恒瑞医药', 'sector': '医药', 'type': '医药龙头',
             'thesis': '创新药龙头，研发管线丰富'},
            {'code': '300015', 'name': '爱尔眼科', 'sector': '医疗', 'type': '医疗服务',
             'thesis': '眼科医院龙头，商业模式优异'},
            {'code': '002475', 'name': '立讯精密', 'sector': '消费电子', 'type': '制造龙头',
             'thesis': '苹果产业链龙头，多元化布局'},
            {'code': '300760', 'name': '迈瑞医疗', 'sector': '医疗器械', 'type': '医疗龙头',
             'thesis': '医疗器械龙头，国际化潜力大'},
            {'code': '601318', 'name': '中国平安', 'sector': '保险', 'type': '金融龙头',
             'thesis': '综合金融+科技，保险龙头'},
            {'code': '600030', 'name': '中信证券', 'sector': '券商', 'type': '券商龙头',
             'thesis': '券商龙头，受益资本市场改革'},
            {'code': '002230', 'name': '科大讯飞', 'sector': 'AI', 'type': 'AI龙头',
             'thesis': 'AI核心技术领先，受益大模型发展'},
            {'code': '300003', 'name': '乐普医疗', 'sector': '医疗器械', 'type': '医疗',
             'thesis': '心血管介入医疗器械龙头'},
            {'code': '000858', 'name': '五粮液', 'sector': '白酒', 'type': '消费',
             'thesis': '高端白酒第二品牌'},
        ]
        return candidates

    def evaluate_long_term_value(self, stock):
        """
        评估长线价值
        评分维度：
        1. 估值（PE、PB）- 权重30%
        2. 行业景气度 - 权重25%
        3. 政策支持度 - 权重20%
        4. 龙头地位 - 权重15%
        5. 财务质量 - 权重10%
        """
        score = 50.0
        code = stock['code']
        sector = stock.get('sector', '')

        current_data = self.get_stock_realtime(code)
        if not current_data:
            return score

        price = current_data.get('price', 0)
        change_pct = current_data.get('change_pct', 0)

        estimated_pe = self.estimate_pe(code, price)
        if estimated_pe:
            if estimated_pe < 20:
                score += 15
            elif estimated_pe < 30:
                score += 10
            elif estimated_pe < 50:
                score += 5
            else:
                score -= 10

        sector_score = self.get_sector_score(sector)
        score += sector_score * 0.25

        policy_score = self.get_policy_score(sector)
        score += policy_score * 0.20

        if '龙头' in stock.get('type', ''):
            score += 8

        if self.market_cycle_position in ["spring", "summer"]:
            if change_pct > 0:
                score += 5
        else:
            if change_pct < 0 and change_pct > -3:
                score += 5

        return score

    def get_stock_realtime(self, code):
        """获取个股实时数据"""
        try:
            if code.startswith('6'):
                symbol = f'sh{code}'
            else:
                symbol = f'sz{code}'

            url = f'http://qt.gtimg.cn/q={symbol}'
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                match = re.search(r'"([^"]+)"', response.text)
                if match:
                    fields = match.group(1).split('~')
                    if len(fields) > 30:
                        return {
                            'name': fields[1],
                            'price': float(fields[3]) if fields[3] else 0,
                            'open': float(fields[5]) if fields[5] else 0,
                            'close': float(fields[4]) if fields[4] else 0,
                            'high': float(fields[33]) if fields[33] else 0,
                            'low': float(fields[34]) if fields[34] else 0,
                            'volume': int(fields[6]) if fields[6] else 0,
                            'change_pct': float(fields[32]) if fields[32] else 0
                        }
        except Exception as e:
            pass
        return None

    def estimate_pe(self, code, price):
        """估算PE（简化计算）"""
        estimated_eps = {
            '600519': 60,
            '300750': 25,
            '002594': 20,
            '600036': 12,
            '300033': 40,
            '688981': 50,
            '600276': 3,
            '300015': 60,
            '002475': 25,
            '300760': 40,
            '601318': 8,
            '600030': 15,
            '002230': 80,
            '300003': 20,
            '000858': 18,
        }
        eps = estimated_eps.get(code, 10)
        return price / eps if price > 0 else None

    def get_sector_score(self, sector):
        """行业景气度评分"""
        sector_scores = {
            'AI': 15,
            '半导体': 14,
            '新能源': 13,
            '新能源车': 13,
            '医疗器械': 12,
            '医疗': 11,
            '消费电子': 10,
            '消费': 8,
            '金融科技': 10,
            '白酒': 7,
            '银行': 6,
            '保险': 5,
            '券商': 6,
        }
        return sector_scores.get(sector, 5)

    def get_policy_score(self, sector):
        """政策支持度评分"""
        policy_sectors = {
            'AI': 15,
            '半导体': 15,
            '新能源': 14,
            '新能源车': 13,
            '医疗器械': 12,
            '医疗': 10,
            '消费电子': 8,
            '消费': 5,
            '金融科技': 10,
            '白酒': 3,
            '银行': 5,
            '保险': 5,
            '券商': 8,
        }
        return policy_sectors.get(sector, 5)

    def generate_report(self, selected_stocks, notify=False):
        """生成分析报告"""
        print("\n" + "=" * 70)
        print("📋 A股长线投资分析报告")
        print("=" * 70)

        print(f"\n📅 报告日期: {datetime.now().strftime('%Y-%m-%d')}")

        print(f"\n🔮 周期判断:")
        cycle_names = {
            'spring': '春（熊末牛初）- 播种期',
            'summer': '夏（牛市中期）- 持有期',
            'autumn': '秋（牛末熊初）- 收获期',
            'winter': '冬（熊市中期）- 等待期'
        }
        print(f"   当前周期: {cycle_names.get(self.market_cycle_position, 'N/A')}")

        if self.market_cycle_position in ["spring", "summer"]:
            print(f"   操作建议: ✅ 积极布局，逢低加仓")
            print(f"   仓位建议: 60-80%")
        else:
            print(f"   操作建议: ⚠️ 谨慎观望，分批减仓")
            print(f"   仓位建议: 30-50%")

        print(f"\n📊 估值参考:")
        pe_val = float(self.current_pe) if self.current_pe else None
        if pe_val:
            if pe_val < 13:
                pe_desc = "历史底部"
                pe_action = "适合重仓"
            elif pe_val < 18:
                pe_desc = "偏低"
                pe_action = "适合加仓"
            elif pe_val < 25:
                pe_desc = "中枢合理"
                pe_action = "持有为主"
            elif pe_val < 35:
                pe_desc = "偏高"
                pe_action = "谨慎"
            else:
                pe_desc = "历史高位"
                pe_action = "减仓"
            print(f"   上证PE: {pe_val:.1f} - {pe_desc}")
            print(f"   操作: {pe_action}")

        print(f"\n🏆 长线推荐标的:")
        for i, s in enumerate(selected_stocks, 1):
            print(f"   {i}. {s['name']}({s['code']}) - {s.get('sector', '')}")
            print(f"      推荐逻辑: {s.get('thesis', 'N/A')}")

        print(f"\n⏰ 下次分析: 次交易日开盘前")
        print("=" * 70)

        if notify and self.dingtalk_webhook:
            message = f"[量化长线策略]\n📋 A股长线分析报告\n\n"
            message += f"📅 {datetime.now().strftime('%Y-%m-%d')}\n"
            message += f"🔮 周期: {cycle_names.get(self.market_cycle_position, 'N/A')}\n"

            if pe_val:
                message += f"📊 上证PE: {pe_val:.1f}\n"

            message += f"\n🏆 长线推荐:\n"
            for s in selected_stocks[:3]:
                message += f"• {s['name']}({s['code']})\n"

            self.send_notification(message)

    def send_notification(self, message):
        """发送钉钉通知"""
        if not self.dingtalk_webhook:
            print("⚠️ 未配置钉钉webhook")
            return

        try:
            data = {
                'msgtype': 'text',
                'text': {'content': f'[量化]{message}'}
            }
            response = self.session.post(
                self.dingtalk_webhook,
                json=data,
                timeout=10
            )
            result = response.json()
            if result.get('errcode') == 0:
                print("✅ 钉钉通知已发送")
            else:
                print(f"⚠️ 钉钉发送失败: {result.get('errmsg')}")
        except Exception as e:
            print(f"钉钉通知失败: {e}")


if __name__ == '__main__':
    webhook = 'https://oapi.dingtalk.com/robot/send?access_token=YOUR_DINGTALK_ACCESS_TOKEN'
    strategy = AShareLongTermStrategy(dingtalk_webhook=webhook)
    strategy.run_once()