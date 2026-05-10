#!/usr/bin/env python3
import requests
import numpy as np
import time
import threading
import json
from datetime import datetime, time as dt_time
from collections import deque
import os

class ETFT0Predictor:
    def __init__(self, etf_codes=None, update_interval=5):
        self.etf_codes = etf_codes or ['sh510300', 'sh510500', 'sz159919', 'sz159915']
        self.update_interval = update_interval
        self.price_history = {code: deque(maxlen=500) for code in self.etf_codes}
        self.tick_history = {code: deque(maxlen=1000) for code in self.etf_codes}
        self.last_prices = {code: None for code in self.etf_codes}
        self.lock = threading.Lock()

        self.timeframes = {
            '5s':  {'window': 5,  'name': '5秒'},
            '10s': {'window': 10, 'name': '10秒'},
            '30s': {'window': 30, 'name': '30秒'},
            '1min': {'window': 60, 'name': '1分钟'},
            '5min': {'window': 300, 'name': '5分钟'}
        }

        self.prediction_stats = {tf: {'correct': 0, 'total': 0, 'profit': 0, 'right_dir': 0, 'wrong_dir': 0} for tf in self.timeframes}
        self.accuracy_history = {tf: deque(maxlen=100) for tf in self.timeframes}
        self.current_predictions = {code: {} for code in self.etf_codes}
        self.pending_predictions = []

        self.model_weights = {tf: 1.0 for tf in self.timeframes}
        self.best_timeframe = '1min'

        self.pending_predictions = deque(maxlen=100)
        self.evolving = True
        self.min_samples_for_evolution = 20

        self.history_file = './etf_t0_stats.json'
        self.load_stats()

    def load_stats(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    if 'prediction_stats' in data:
                        self.prediction_stats = data['prediction_stats']
                    if 'model_weights' in data:
                        self.model_weights = data['model_weights']
                    if 'best_timeframe' in data:
                        self.best_timeframe = data['best_timeframe']
                    print(f"Loaded stats from {self.history_file}")
            except Exception as e:
                print(f"Failed to load stats: {e}")

    def save_stats(self):
        try:
            data = {
                'prediction_stats': self.prediction_stats,
                'model_weights': self.model_weights,
                'best_timeframe': self.best_timeframe
            }
            with open(self.history_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Failed to save stats: {e}")

    def get_realtime_price(self, code):
        try:
            url = f'http://qt.gtimg.cn/q={code}'
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.text.strip().split('~')
                if len(data) > 10:
                    return {
                        'code': code,
                        'name': data[1],
                        'price': float(data[3]),
                        'change': float(data[31]) if data[31] else 0,
                        'change_pct': float(data[32]) if data[32] else 0,
                        'volume': float(data[36]) if data[36] else 0,
                        'amount': float(data[37]) if data[37] else 0,
                        'bid1': float(data[9]) if data[9] else 0,
                        'ask1': float(data[19]) if data[19] else 0,
                        'bid_vol1': float(data[10]) if data[10] else 0,
                        'ask_vol1': float(data[20]) if data[20] else 0,
                        'timestamp': datetime.now()
                    }
        except Exception as e:
            pass
        return None

    def update_price(self, code):
        data = self.get_realtime_price(code)
        if data:
            with self.lock:
                self.last_prices[code] = data['price']
                self.price_history[code].append(data)
                self.tick_history[code].append(data)

    def calculate_momentum(self, code, window):
        with self.lock:
            history = list(self.price_history[code])
        if len(history) < window:
            return 0
        prices = [h['price'] for h in history[-window:]]
        if len(prices) < 2:
            return 0
        return (prices[-1] - prices[0]) / prices[0]

    def calculate_volatility(self, code, window):
        with self.lock:
            history = list(self.price_history[code])
        if len(history) < window:
            return 0
        prices = [h['price'] for h in history[-window:]]
        if len(prices) < 2:
            return 0
        returns = np.diff(prices) / prices[:-1]
        return np.std(returns) if len(returns) > 0 else 0

    def calculate_volume_ratio(self, code):
        with self.lock:
            history = list(self.price_history[code])
        if len(history) < 20:
            return 1.0
        recent_vol = sum(h.get('volume', 0) for h in history[-5:])
        avg_vol = sum(h.get('volume', 0) for h in history[-20:]) / 20
        return recent_vol / (avg_vol + 1e-10)

    def calculate_order_imbalance(self, code):
        with self.lock:
            history = list(self.tick_history[code])
        if len(history) < 2:
            return 0
        recent = history[-1]
        bid_vol = recent.get('bid_vol1', 0)
        ask_vol = recent.get('ask_vol1', 0)
        if bid_vol + ask_vol == 0:
            return 0
        return (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-10)

    def calculate_micro_trend(self, code):
        with self.lock:
            history = list(self.price_history[code])
        if len(history) < 10:
            return 0.5
        prices = [h['price'] for h in history[-10:]]
        changes = np.diff(prices)
        if len(changes) == 0:
            return 0.5
        up_count = sum(1 for c in changes if c > 0)
        down_count = sum(1 for c in changes if c < 0)
        if up_count + down_count == 0:
            return 0.5
        return up_count / (up_count + down_count)

    def calculate_mean_reversion(self, code, window=20):
        with self.lock:
            history = list(self.price_history[code])
        if len(history) < window:
            return 0.5
        prices = [h['price'] for h in history[-window:]]
        current = prices[-1]
        mean_price = np.mean(prices)
        std_price = np.std(prices)
        if std_price == 0:
            return 0.5
        z_score = (current - mean_price) / std_price
        if z_score > 1:
            return 0.3
        elif z_score < -1:
            return 0.7
        return 0.5

    def calculate_support_resistance(self, code):
        with self.lock:
            history = list(self.price_history[code])
        if len(history) < 30:
            return 0.5, 0.5
        prices = [h['price'] for h in history[-30:]]
        current = prices[-1]
        recent_high = max(prices[-10:])
        recent_low = min(prices[-10:])
        if recent_high == recent_low:
            return 0.5, 0.5
        resistance_strength = (recent_high - current) / (recent_high - recent_low + 1e-10)
        support_strength = (current - recent_low) / (recent_high - recent_low + 1e-10)
        return support_strength, resistance_strength

    def predict(self, code, tick_idx=None):
        features = {}
        for tf_name, tf_info in self.timeframes.items():
            window = tf_info['window']
            momentum = self.calculate_momentum(code, min(window, len(self.price_history[code])))
            volatility = self.calculate_volatility(code, min(window, len(self.price_history[code])))
            features[tf_name] = {
                'momentum': momentum,
                'volatility': volatility,
                'volume_ratio': self.calculate_volume_ratio(code),
                'order_imbalance': self.calculate_order_imbalance(code),
                'micro_trend': self.calculate_micro_trend(code),
                'mean_reversion': self.calculate_mean_reversion(code),
            }

        support, resistance = self.calculate_support_resistance(code)
        for tf_name in features:
            features[tf_name]['support'] = support
            features[tf_name]['resistance'] = resistance

        predictions = {}
        for tf_name, feat in features.items():
            score = self._calculate_prediction_score(feat)
            predictions[tf_name] = {
                'score': score,
                'direction': 'long' if score > 0.52 else ('short' if score < 0.48 else 'neutral'),
                'confidence': abs(score - 0.5) * 2,
                'features': feat
            }

        weighted_score = 0
        total_weight = sum(self.model_weights.values())
        for tf_name, pred in predictions.items():
            weighted_score += pred['score'] * (self.model_weights[tf_name] / total_weight)

        final_direction = 'long' if weighted_score > 0.52 else ('short' if weighted_score < 0.48 else 'neutral')
        final_confidence = abs(weighted_score - 0.5) * 2

        entry_tick_idx = tick_idx
        if tick_idx is not None and final_direction != 'neutral' and final_confidence > 0.3:
            self.pending_predictions.append({
                'code': code,
                'timeframe': self.best_timeframe,
                'direction': final_direction,
                'entry_price': self.last_prices.get(code),
                'entry_time': datetime.now(),
                'entry_tick_idx': tick_idx
            })

        self.current_predictions[code] = {
            'predictions': predictions,
            'weighted_score': weighted_score,
            'direction': final_direction,
            'confidence': final_confidence,
            'timestamp': datetime.now()
        }

        return self.current_predictions[code]

    def _calculate_prediction_score(self, features):
        momentum = features['momentum']
        volatility = features['volatility']
        volume_ratio = features['volume_ratio']
        order_imbalance = features['order_imbalance']
        micro_trend = features['micro_trend']
        mean_reversion = features['mean_reversion']
        support = features['support']
        resistance = features['resistance']

        score = 0.5

        if abs(momentum) > 0.0001:
            score += momentum * 0.3

        if abs(volatility) > 0.00001:
            score += volatility * 0.1

        if abs(volume_ratio - 1) > 0.05:
            score += (volume_ratio - 1) * 0.1

        score += order_imbalance * 0.15

        score += (micro_trend - 0.5) * 0.2

        score += (mean_reversion - 0.5) * 0.1

        score += (support - resistance) * 0.05

        score = max(0.1, min(0.9, score))
        return score

    def verify_predictions(self, current_tick_idx=None):
        """验证待定的预测 - 支持基于tick的验证"""
        now = datetime.now()
        verified = []

        for pred in list(self.pending_predictions):
            code = pred['code']
            tf_name = pred['timeframe']
            predicted_direction = pred['direction']
            entry_price = pred['entry_price']
            entry_time = pred['entry_time']

            window_seconds = self.timeframes[tf_name]['window']

            if current_tick_idx is not None:
                if 'entry_tick_idx' not in pred or pred['entry_tick_idx'] is None:
                    continue
                elapsed_ticks = current_tick_idx - pred['entry_tick_idx']
                window_ticks = window_seconds
                if elapsed_ticks >= window_ticks:
                    current_price = self.last_prices.get(code)
                    if current_price and entry_price > 0:
                        actual_change = (current_price - entry_price) / entry_price
                        actual_direction = 'long' if actual_change > 0.0001 else ('short' if actual_change < -0.0001 else 'neutral')
                        correct = predicted_direction == actual_direction
                        if abs(actual_change) > 0.0001:
                            self.prediction_stats[tf_name]['total'] += 1
                            if correct:
                                self.prediction_stats[tf_name]['correct'] += 1
                                self.prediction_stats[tf_name]['right_dir'] += 1
                            else:
                                self.prediction_stats[tf_name]['wrong_dir'] += 1
                            self.prediction_stats[tf_name]['profit'] += actual_change * 100 if predicted_direction == 'long' else -actual_change * 100
                            self.accuracy_history[tf_name].append(1 if correct else 0)
                    verified.append(pred)
            else:
                elapsed = (now - entry_time).total_seconds()
                if elapsed >= window_seconds:
                    current_price = self.last_prices.get(code)
                    if current_price and entry_price > 0:
                        actual_change = (current_price - entry_price) / entry_price
                        actual_direction = 'long' if actual_change > 0.0001 else ('short' if actual_change < -0.0001 else 'neutral')
                        correct = predicted_direction == actual_direction
                        if abs(actual_change) > 0.0001:
                            self.prediction_stats[tf_name]['total'] += 1
                            if correct:
                                self.prediction_stats[tf_name]['correct'] += 1
                                self.prediction_stats[tf_name]['right_dir'] += 1
                            else:
                                self.prediction_stats[tf_name]['wrong_dir'] += 1
                            self.prediction_stats[tf_name]['profit'] += actual_change * 100 if predicted_direction == 'long' else -actual_change * 100
                            self.accuracy_history[tf_name].append(1 if correct else 0)
                    verified.append(pred)

        for pred in verified:
            if pred in self.pending_predictions:
                self.pending_predictions.remove(pred)

        if verified:
            self.evolve_weights()

    def record_prediction(self, code, direction, entry_price):
        """记录预测以便后续验证"""
        for tf_name in self.timeframes:
            self.pending_predictions.append({
                'code': code,
                'timeframe': tf_name,
                'direction': direction,
                'entry_price': entry_price,
                'entry_time': datetime.now()
            })

    def evolve_weights(self):
        """根据预测准确率进化模型权重"""
        total_accuracy = {}
        for tf_name, stats in self.prediction_stats.items():
            if stats['total'] >= self.min_samples_for_evolution:
                accuracy = stats['correct'] / stats['total']
                recent_list = list(self.accuracy_history[tf_name])
                recent_accuracy = sum(recent_list) / max(1, len(recent_list))
                profit_factor = 1.0 + (stats['profit'] / max(1, abs(stats['total'])) / 100)
                combined_score = accuracy * 0.4 + recent_accuracy * 0.4 + profit_factor * 0.2
                total_accuracy[tf_name] = combined_score

        if not total_accuracy:
            return

        max_score = max(total_accuracy.values())
        min_score = min(total_accuracy.values())

        if max_score > min_score and max_score > 0:
            for tf_name in self.timeframes:
                if tf_name in total_accuracy:
                    normalized = (total_accuracy[tf_name] - min_score) / (max_score - min_score + 1e-10)
                    self.model_weights[tf_name] = 0.3 + normalized * 1.7
                else:
                    self.model_weights[tf_name] *= 0.95
        else:
            for tf_name in self.timeframes:
                self.model_weights[tf_name] = 1.0

        best_tf = max(total_accuracy, key=total_accuracy.get) if total_accuracy else '1min'
        if best_tf != self.best_timeframe:
            self.best_timeframe = best_tf
            print(f"\n🎯 模型进化！最佳时间框架已更新为: {best_tf}")

        self.save_stats()
        self.print_stats()

    def print_stats(self):
        print(f"\n{'='*65}")
        print(f"📊 ETF T+0 预测准确率统计")
        print(f"{'='*65}")
        print(f"{'周期':<8} {'准确率':>8} {'样本':>6} {'正确':>6} {'错误':>6} {'盈亏':>8} {'权重':>6}")
        print(f"{'-'*65}")
        for tf_name in self.timeframes:
            stats = self.prediction_stats[tf_name]
            if stats['total'] > 0:
                acc = stats['correct'] / stats['total'] * 100
                print(f"{tf_name:<8} {acc:>7.1f}% {stats['total']:>6} {stats['right_dir']:>6} {stats['wrong_dir']:>6} {stats['profit']:>7.2f}% {self.model_weights[tf_name]:>6.2f}")
            else:
                print(f"{tf_name:<8} {'N/A':>8} {0:>6} {0:>6} {0:>6} {0:>7.2f}% {self.model_weights[tf_name]:>6.2f}")
        print(f"{'='*65}")
        print(f"🏆 当前最佳时间框架: {self.best_timeframe} (权重: {self.model_weights.get(self.best_timeframe, 1.0):.2f})")
        print(f"{'='*65}\n")

    def get_trade_signal(self, code):
        """获取交易信号"""
        pred = self.current_predictions.get(code)
        if not pred:
            return None

        weighted_score = pred['weighted_score']
        direction = pred['direction']
        confidence = pred['confidence']

        tf_accuracy = {}
        for tf_name in self.timeframes:
            stats = self.prediction_stats[tf_name]
            if stats['total'] >= 10:
                tf_accuracy[tf_name] = stats['correct'] / stats['total']
            else:
                tf_accuracy[tf_name] = 0.5

        best_tf = max(tf_accuracy, key=tf_accuracy.get)
        best_accuracy = tf_accuracy[best_tf]

        min_accuracy_threshold = 0.50
        if best_accuracy < min_accuracy_threshold:
            return None

        if direction == 'neutral':
            return None

        entry_price = self.last_prices.get(code)
        if not entry_price:
            return None

        self.record_prediction(code, direction, entry_price)

        position_size = int(min(confidence * 1000, 10000))

        return {
            'code': code,
            'direction': direction,
            'confidence': confidence,
            'score': weighted_score,
            'position_size': position_size,
            'best_timeframe': best_tf,
            'best_accuracy': best_accuracy,
            'entry_price': entry_price,
            'all_predictions': pred['predictions'],
            'timestamp': pred['timestamp']
        }

    def is_trading_time(self):
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()
        if weekday >= 5:
            return False
        return (dt_time(9, 25) <= current_time <= dt_time(11, 35) or
                dt_time(13, 0) <= current_time <= dt_time(15, 5))

    def run(self):
        print("\n" + "=" * 70)
        print("🚀 ETF T+0 超短线预测系统启动")
        print("=" * 70)
        print(f"📈 监控ETF: {', '.join(self.etf_codes)}")
        print(f"⏱️ 更新间隔: {self.update_interval}秒")
        print(f"📊 预测周期: {', '.join(self.timeframes.keys())}")
        print(f"📋 验证待定预测: {len(self.pending_predictions)}个")
        print("=" * 70)
        self.print_stats()

        running = True
        last_update = {code: 0 for code in self.etf_codes}

        while running:
            try:
                now = datetime.now()

                if not self.is_trading_time():
                    if int(now.timestamp()) % 300 == 0:
                        print(f"[{now.strftime('%H:%M:%S')}] 非交易时间，等待中...")
                    time.sleep(60)
                    continue

                for code in self.etf_codes:
                    if now.timestamp() - last_update.get(code, 0) >= self.update_interval:
                        self.update_price(code)
                        last_update[code] = now.timestamp()

                self.verify_predictions()

                for code in self.etf_codes:
                    if self.last_prices.get(code) and len(self.price_history.get(code, [])) > 10:
                        pred = self.predict(code)
                        signal = self.get_trade_signal(code)

                        if signal and signal['direction'] != 'neutral':
                            print(f"\n{'='*65}")
                            print(f"📊 {signal['code']} 预测信号 [{now.strftime('%H:%M:%S')}]")
                            print(f"{'='*65}")
                            print(f"  方向: {'🔼 做多' if signal['direction'] == 'long' else '🔽 做空'}")
                            print(f"  评分: {signal['score']:.3f} | 置信度: {signal['confidence']:.2f}")
                            print(f"  最佳周期: {signal['best_timeframe']} (准确率: {signal['best_accuracy']:.1%})")
                            print(f"  入场价: {signal['entry_price']:.3f}")
                            print(f"  建议仓位: {signal['position_size']}份")
                            print(f"  各周期预测:")
                            for tf_name, p in signal['all_predictions'].items():
                                stats = self.prediction_stats[tf_name]
                                acc = stats['correct'] / max(1, stats['total']) if stats['total'] > 0 else 0
                                weight = self.model_weights[tf_name]
                                match = "✓" if p['direction'] == signal['direction'] else " "
                                print(f"    {match} {tf_name}: {p['direction']:6s} (准确{acc:.1%} 权重{weight:.2f})")
                            print(f"{'='*65}")

                time.sleep(self.update_interval)

            except KeyboardInterrupt:
                print("\n正在停止ETF T+0预测系统...")
                running = False
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(5)

        self.save_stats()
        self.print_stats()

if __name__ == '__main__':
    predictor = ETFT0Predictor(
        etf_codes=['sh510300', 'sh510500', 'sz159919', 'sz159915'],
        update_interval=3
    )
    predictor.run()
