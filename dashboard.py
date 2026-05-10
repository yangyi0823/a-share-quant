# 尝试导入easytrader，如果失败则设置为None
try:
    import easytrader
except ImportError:
    easytrader = None

import streamlit as st
import backtrader as bt
import talib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
import os
import time
import warnings
import pickle
from cryptography.fernet import Fernet
import tempfile
import traceback
import json
import uuid

# ======================== Mac系统专属配置 ========================
DATA_PATH = os.path.expanduser("./quant_data/local_stock_data.csv")
CACHE_FILE = os.path.expanduser("~/Library/Application Support/QuantTrader/account_cache.pkl")
KEY_FILE = os.path.expanduser("~/Library/Application Support/QuantTrader/encryption_key.key")
# 策略文件存储目录
STRATEGY_DIR = os.path.expanduser("./strategies")
MAX_BACKTEST_DATA = 5000

# 初始化目录
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
os.makedirs(STRATEGY_DIR, exist_ok=True)  # 创建策略存储目录
# 新增：确保数据目录存在
os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

# ======================== 加密密钥管理 ========================
def get_encryption_key():
    """本地文件存储密钥，兼容所有Mac系统"""
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "rb") as f:
                key = f.read()
            return Fernet(key)
        except Exception as e:
            st.warning(f"读取密钥失败，生成新密钥：{str(e)}")
    
    # 生成并保存新密钥（仅当前用户可读写）
    key = Fernet.generate_key()
    try:
        with open(KEY_FILE, "wb") as f:
            os.chmod(KEY_FILE, 0o600)
            f.write(key)
    except:
        pass  # 即使保存失败也不影响使用，仅本次有效
    
    return Fernet(key)

fernet = get_encryption_key()

# ======================== 账号缓存管理 ========================
def save_account_cache(broker_type, username, trade_mode):
    """新增：保存账号缓存时记录交易模式"""
    try:
        cache_data = {
            "broker_type": broker_type,
            "username": username,
            "trade_mode": trade_mode,  # 新增：记录模拟/实际模式
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        encrypted_data = fernet.encrypt(pickle.dumps(cache_data))
        with open(CACHE_FILE, "wb") as f:
            f.write(encrypted_data)
    except Exception as e:
        st.warning(f"保存账号缓存失败：{str(e)}")

def load_account_cache():
    """加载账号缓存，容错处理（新增交易模式）"""
    try:
        if not os.path.exists(CACHE_FILE):
            return {"broker_type": "", "username": "", "trade_mode": "模拟交易"}
        
        with open(CACHE_FILE, "rb") as f:
            encrypted_data = f.read()
        cache_data = pickle.loads(fernet.decrypt(encrypted_data))
        # 兼容旧缓存（无trade_mode字段）
        if "trade_mode" not in cache_data:
            cache_data["trade_mode"] = "模拟交易"
        return cache_data
    except:
        # 缓存损坏时删除并返回空
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        return {"broker_type": "", "username": "", "trade_mode": "模拟交易"}

# ======================== 策略文件管理 ========================
def save_strategy_to_file(strategy_code, strategy_name):
    """
    将生成的策略保存到本地文件
    :param strategy_code: 策略代码
    :param strategy_name: 策略名称
    :return: 策略文件路径
    """
    # 生成唯一ID（避免重名）
    strategy_id = str(uuid.uuid4())[:8]
    # 清理文件名非法字符
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', strategy_name)
    # 构建文件名：时间_名称_ID.py
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}_{strategy_id}.py"
    filepath = os.path.join(STRATEGY_DIR, filename)
    
    # 保存策略元数据（名称、ID、创建时间）
    metadata = {
        "id": strategy_id,
        "name": strategy_name,
        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filename": filename
    }
    metadata_file = filepath.replace(".py", "_meta.json")
    
    try:
        # 保存策略代码
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(strategy_code)
        # 保存元数据
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        st.success(f"✅ 策略已保存：{safe_name}（ID：{strategy_id}）")
        st.info(f"📁 文件路径：{filepath}")
        return filepath
    except Exception as e:
        st.error(f"❌ 保存策略失败：{str(e)}")
        return None

def load_strategy_from_file(filepath):
    """
    从本地文件加载策略代码
    :param filepath: 策略文件路径
    :return: 策略代码
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        st.error(f"❌ 加载策略失败：{str(e)}")
        return None

def list_saved_strategies():
    strategies = []
    try:
        # 直接扫描所有 .py 策略文件，不管有没有 meta，都能显示
        for file in os.listdir(STRATEGY_DIR):
            if file.endswith(".py") and not file.endswith("_meta.json"):
                # 自动构造 meta
                meta = {
                    "id": file[-12:-3],
                    "name": file[:-15],
                    "create_time": "2026-01-01 00:00:00",
                    "filename": file,
                    "filepath": os.path.join(STRATEGY_DIR, file)
                }
                strategies.append(meta)

        strategies.sort(key=lambda x: x["create_time"], reverse=True)
    except Exception as e:
        st.warning(f"📋 读取策略列表失败：{str(e)}")
    return strategies

def delete_strategy_file(strategy_meta):
    """
    删除指定策略的文件（代码+元数据）
    :param strategy_meta: 策略元数据
    """
    try:
        # 删除代码文件
        if os.path.exists(strategy_meta["filepath"]):
            os.remove(strategy_meta["filepath"])
        # 删除元数据文件
        meta_file = strategy_meta["filepath"].replace(".py", "_meta.json")
        if os.path.exists(meta_file):
            os.remove(meta_file)
        
        st.success(f"✅ 已删除策略：{strategy_meta['name']}（ID：{strategy_meta['id']}）")
    except Exception as e:
        st.error(f"❌ 删除策略失败：{str(e)}")
        return False
    return True

# ======================== 数据加载 ========================
def load_sample_data(stock_code="600519"):
    """
    不依赖akshare，直接使用模拟数据（避免模块缺失错误）
    :param stock_code: 6位股票代码（如600519、000001）
    :return: 适配Backtrader的DataFrame数据
    """
    # 1. 定义本地缓存文件路径（按股票代码命名）
    cache_file = os.path.join(os.path.dirname(DATA_PATH), f"{stock_code}.csv")
    st.info(f"🔍 检查{stock_code}本地缓存：{cache_file}")
    
    # 2. 本地有缓存 → 直接加载
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(
                cache_file,
                index_col=0,
                parse_dates=True
            )
            # 校验数据格式
            required_cols = ["open", "high", "low", "close", "volume"]
            if all(col in df.columns for col in required_cols):
                df = df[required_cols].tail(MAX_BACKTEST_DATA)
                st.success(f"✅ 加载{stock_code}本地缓存数据成功（共{len(df)}条）")
                return df
            else:
                st.warning(f"⚠️ 本地缓存格式错误，重新生成模拟数据")
                os.remove(cache_file)
        except Exception as e:
            st.warning(f"⚠️ 读取本地缓存失败：{str(e)}，重新生成模拟数据")
            os.remove(cache_file) if os.path.exists(cache_file) else None
    
    # 3. 直接生成模拟数据（不依赖akshare）
    st.info(f"📊 生成{stock_code}模拟股票数据（无需akshare）...")
    
    # 计算时间范围（近2年）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    
    # 基于股票代码生成不同的模拟数据（避免所有股票数据都一样）
    np.random.seed(int(stock_code[-3:]) if len(stock_code)>=3 else 42)
    base_price = np.random.randint(10, 200)  # 随机基础股价
    price = base_price + np.cumsum(np.random.randn(len(dates)) * 2)
    
    df = pd.DataFrame({
        'open': price + np.random.randn(len(dates)) * 0.5,
        'high': price + np.random.randn(len(dates)) * 0.5 + 3,
        'low': price + np.random.randn(len(dates)) * 0.5 - 3,
        'close': price,
        'volume': np.random.randint(100000, 1000000, len(dates))
    }, index=dates)
    
    # 保存到本地缓存（下次直接用）
    df.to_csv(cache_file, encoding="utf-8")
    st.success(f"✅ {stock_code}模拟数据生成成功（共{len(df)}条）")
    return df

# ======================== 策略回测 ========================
def backtest_strategy(strategy_code, data_df):
    """执行策略回测，返回回测结果"""
    try:
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(100000.0)  # 初始资金10万
        cerebro.broker.setcommission(commission=0.001)  # 佣金千分之一
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        
        # 加载数据
        data_feed = bt.feeds.PandasData(dataname=data_df)
        cerebro.adddata(data_feed)
        
        # 动态加载生成的策略
        locals_dict = {}
        exec(strategy_code, globals(), locals_dict)
        if 'GeneratedStrategy' not in locals_dict:
            st.error("策略代码必须包含GeneratedStrategy类")
            return {'success': False, 'error': '缺少策略类'}
        
        GeneratedStrategy = locals_dict['GeneratedStrategy']
        cerebro.addstrategy(GeneratedStrategy)
        
        # 执行回测
        init_cash = cerebro.broker.getvalue()
        st.write(f"📊 初始资金：{init_cash:.2f} 元")
        
        results = cerebro.run()
        final_cash = cerebro.broker.getvalue()
        total_return = (final_cash - init_cash) / init_cash * 100
        
        # 提取回测指标
        sharpe = results[0].analyzers.sharpe.get_analysis().get('sharperatio', 0)
        drawdown = results[0].analyzers.drawdown.get_analysis()['max']['drawdown']
        
        # 展示结果
        st.write(f"💰 最终资金：{final_cash:.2f} 元")
        st.write(f"📈 总收益率：{total_return:.2f}%")
        st.write(f"📊 夏普比率：{sharpe:.2f}")
        st.write(f"📉 最大回撤：{drawdown:.2f}%")
        
        # 绘制图表
        fig = cerebro.plot(style='candlestick', iplot=False, volume=False)[0][0]
        st.pyplot(fig, use_container_width=True)
        
        return {
            'success': True,
            'init_cash': init_cash,
            'final_cash': final_cash,
            'total_return': total_return,
            'sharpe': sharpe,
            'drawdown': drawdown
        }
    except Exception as e:
        st.error(f"回测执行失败：{str(e)}")
        st.code(traceback.format_exc())  # 显示详细错误堆栈
        return {'success': False, 'error': str(e)}

# ======================== 券商客户端适配 ========================
class MockBrokerClient:
    def __init__(self, broker_type, username):
        self.broker_type = broker_type
        self.username = username
        self.balance = {
            "可用资金": 1000000.00,
            "总资产": 1000000.00,
            "持仓市值": 0.00
        }
        self.position = []
        self.trade_records = []  # 保存交易记录
    
    def buy(self, stock_code, price, amount):
        # 计算交易金额
        total_amount = price * amount
        
        # 检查资金是否足够
        if total_amount > self.balance["可用资金"]:
            return {
                "success": False,
                "msg": f"资金不足：可用资金 {self.balance['可用资金']:.2f} 元，需要 {total_amount:.2f} 元",
                "order_id": ""
            }
        
        # 扣减资金
        self.balance["可用资金"] -= total_amount
        
        # 检查是否已有该股票持仓
        existing_position = None
        for pos in self.position:
            if pos["证券代码"] == stock_code:
                existing_position = pos
                break
        
        if existing_position:
            # 更新现有持仓
            existing_position["持仓数量"] += amount
            existing_position["可用股份"] += amount
            existing_position["市值"] = existing_position["持仓数量"] * price
        else:
            # 添加新持仓
            new_position = {
                "证券代码": stock_code,
                "证券名称": f"股票{stock_code}",
                "持仓数量": amount,
                "可用股份": amount,
                "市值": amount * price,
                "盈亏比例": 0.0
            }
            self.position.append(new_position)
        
        # 更新总资产和持仓市值
        self._update_balance()
        
        # 保存交易记录
        trade_record = {
            "交易时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "证券代码": stock_code,
            "证券名称": f"股票{stock_code}",
            "买卖方向": "买入",
            "成交价格": price,
            "成交数量": amount,
            "成交金额": total_amount,
            "交易类型": "手动交易"
        }
        self.trade_records.append(trade_record)
        
        return {
            "success": True,
            "msg": f"模拟买入{stock_code} {amount}股，价格{price}元（无真实交易）",
            "order_id": "mock_" + str(int(price * amount))
        }
    
    def sell(self, stock_code, price, amount):
        # 检查是否有该股票持仓
        existing_position = None
        for pos in self.position:
            if pos["证券代码"] == stock_code:
                existing_position = pos
                break
        
        if not existing_position:
            return {
                "success": False,
                "msg": f"没有{stock_code}的持仓",
                "order_id": ""
            }
        
        # 检查可用数量是否足够
        if amount > existing_position["可用股份"]:
            return {
                "success": False,
                "msg": f"可用数量不足：可用 {existing_position['可用股份']} 股，卖出 {amount} 股",
                "order_id": ""
            }
        
        # 计算交易金额
        total_amount = price * amount
        
        # 增加资金
        self.balance["可用资金"] += total_amount
        
        # 更新持仓
        existing_position["持仓数量"] -= amount
        existing_position["可用股份"] -= amount
        existing_position["市值"] = existing_position["持仓数量"] * price
        
        # 如果持仓数量为0，移除该持仓
        if existing_position["持仓数量"] == 0:
            self.position.remove(existing_position)
        
        # 更新总资产和持仓市值
        self._update_balance()
        
        # 保存交易记录
        trade_record = {
            "交易时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "证券代码": stock_code,
            "证券名称": f"股票{stock_code}",
            "买卖方向": "卖出",
            "成交价格": price,
            "成交数量": amount,
            "成交金额": total_amount,
            "交易类型": "手动交易"
        }
        self.trade_records.append(trade_record)
        
        return {
            "success": True,
            "msg": f"模拟卖出{stock_code} {amount}股，价格{price}元（无真实交易）",
            "order_id": "mock_" + str(int(price * amount))
        }
    
    def _update_balance(self):
        """更新账户余额信息"""
        # 计算总持仓市值
        total_market_value = sum(pos["市值"] for pos in self.position)
        self.balance["持仓市值"] = total_market_value
        
        # 计算总资产
        self.balance["总资产"] = self.balance["可用资金"] + total_market_value

# 新增：实际交易客户端基础类（预留扩展接口）
class RealBrokerClient:
    """实际交易客户端基类（需对接具体券商API）"""
    def __init__(self, broker_type, username, password):
        self.broker_type = broker_type
        self.username = username
        self.is_connected = False
        # 实际交易需实现以下方法
        self.connect(password)
    
    def connect(self, password):
        """连接实际券商（需根据具体券商API实现）"""
        raise NotImplementedError(f"请实现{self.broker_type}的实际交易连接逻辑")
    
    def get_security_info(self, stock_code):
        """获取真实股票信息"""
        raise NotImplementedError("请实现真实股票信息查询逻辑")
    
    def buy(self, stock_code, price, amount):
        """真实买入"""
        raise NotImplementedError("请实现真实买入逻辑")
    
    def sell(self, stock_code, price, amount):
        """真实卖出"""
        raise NotImplementedError("请实现真实卖出逻辑")
    
    def get_trade_records(self):
        """获取真实交易记录"""
        raise NotImplementedError("请实现真实交易记录查询逻辑")
    
    def get_positions(self):
        """获取真实持仓"""
        raise NotImplementedError("请实现真实持仓查询逻辑")

def init_broker_client(broker_type, username, password, trade_mode):
    """
    初始化券商客户端（支持华泰证券实盘/模拟交易）
    :param broker_type: 券商类型（华泰证券/其他）
    :param username: 账号
    :param password: 密码
    :param trade_mode: 交易模式：模拟交易/实际交易
    :return: 客户端实例
    """
    try:
        if trade_mode == "模拟交易":
            # 模拟交易模式（保留原有逻辑）
            st.info("ℹ️ 注意：当前使用模拟交易客户端，不会产生真实交易")
            client = MockBrokerClient(broker_type, username)
            st.success(f"✅ {broker_type}模拟客户端初始化成功！")
            st.success(f"📱 登录账号：{username}")
            st.info(f"💵 初始模拟资金：{client.balance['可用资金']:.2f} 元")
            return client
        
        # 实际交易模式（重点实现华泰证券）
        else:
            st.warning("⚠️ 注意：当前将连接实际交易客户端，会产生真实交易，请注意风险！")
            
            # 检查easytrader是否安装
            if easytrader is None:
                st.error("❌ 初始化华泰客户端失败：未安装easytrader库")
                st.info("💡 提示：请使用 pip install easytrader 安装easytrader库")
                return None
            
            # 华泰证券实际交易对接（基于easytrader）
            if broker_type == "华泰证券":
                # 1. 初始化华泰客户端
                try:
                    client = easytrader.use('htzq_client')
                except ImportError as init_error:
                    if 'win32clipboard' in str(init_error):
                        st.error("❌ 初始化华泰客户端失败：Mac系统不支持win32clipboard")
                        st.info("💡 提示：华泰证券客户端仅支持Windows系统，Mac系统暂无法使用实际交易功能")
                    else:
                        st.error(f"❌ 初始化华泰客户端失败：{str(init_error)}")
                        st.info("💡 提示：请确保已安装easytrader库并更新到最新版本")
                    return None
                except Exception as init_error:
                    st.error(f"❌ 初始化华泰客户端失败：{str(init_error)}")
                    st.info("💡 提示：请确保已安装easytrader库并更新到最新版本")
                    return None
                
                # 2. 尝试多种登录方式
                login_success = False
                
                # 方式1：标准登录（账号密码）
                try:
                    st.info("🔐 尝试标准登录方式...")
                    client.prepare(
                        user=username,        # 华泰账号
                        password=password,    # 交易密码
                        comm_password="",     # 通讯密码（若无则留空）
                        exe_path="/Applications/华泰证券.app"  # Mac版华泰客户端路径
                    )
                    login_success = True
                except Exception as login_error:
                    st.warning(f"标准登录失败：{str(login_error)}")
                    
                    # 方式2：尝试不同的客户端路径
                    try:
                        st.info("🔐 尝试备选客户端路径...")
                        # 常见的华泰客户端路径
                        alternative_paths = [
                            "/Applications/华泰证券.app",
                            "/Applications/涨乐财富通.app",
                            "/Users/{}/Applications/华泰证券.app".format(os.getenv('USER', '')),
                            "/Users/{}/Applications/涨乐财富通.app".format(os.getenv('USER', ''))
                        ]
                        
                        for path in alternative_paths:
                            if os.path.exists(path):
                                st.info(f"尝试路径：{path}")
                                client.prepare(
                                    user=username,
                                    password=password,
                                    comm_password="",
                                    exe_path=path
                                )
                                login_success = True
                                break
                    except Exception as alt_login_error:
                        st.warning(f"备选路径登录失败：{str(alt_login_error)}")
                
                # 3. 验证登录并获取账户信息
                if login_success:
                    try:
                        balance = client.balance
                        if balance:
                            st.success(f"✅ 华泰证券实际客户端登录成功！")
                            st.success(f"📱 账号：{username}")
                            st.info(f"💵 可用资金：{balance['可用资金']:.2f} 元")
                            st.info(f"💰 总资产：{balance['总资产']:.2f} 元")
                            return client
                        else:
                            st.error("❌ 登录成功但未获取到账户信息，请检查客户端配置")
                            return None
                    except Exception as balance_error:
                        st.error(f"❌ 获取账户信息失败：{str(balance_error)}")
                        st.info("💡 提示：请检查网络连接和客户端状态")
                        return None
                else:
                    st.error("❌ 所有登录方式均失败，请检查以下事项：")
                    st.info("1. 华泰证券客户端已安装并正常运行")
                    st.info("2. 已开启客户端的「外接访问」权限")
                    st.info("3. 账号密码正确")
                    st.info("4. 网络连接正常")
                    return None
            
            # 其他券商暂未实现（可后续扩展）
            else:
                st.error(f"❌ {broker_type}实际交易客户端暂未实现，仅支持华泰证券")
                return None
    
    # 异常处理（覆盖所有可能的错误）
    except FileNotFoundError:
        st.error("❌ 未找到华泰证券客户端，请先安装并确保路径正确：/Applications/华泰证券.app")
        st.info("💡 提示：需先在华泰证券客户端中开启「外接访问」权限")
        return None
    except PermissionError:
        st.error("❌ 华泰证券客户端外接访问权限未开启，请按以下步骤操作：")
        st.info("1. 打开华泰证券Mac客户端")
        st.info("2. 进入「设置」→「外接访问」")
        st.info("3. 开启外接访问权限并设置允许的IP")
        return None
    except Exception as e:
        st.error(f"❌ 客户端初始化失败：{str(e)}")
        with st.expander("查看详细错误信息"):
            st.code(traceback.format_exc())
        return None

# ======================== 交易执行 ========================
def execute_trade(client, stock_code, trade_type, amount, trade_mode):
    """
    执行交易（兼容模拟/实际客户端）
    """
    try:
        # 1. 交易前检查
        if trade_mode == "实际交易":
            # 风险提示
            st.warning("⚠️ 实际交易风险提示：您正在执行真实交易，资金可能会有盈亏，请确认操作！")
            
            # 检查账号连接状态
            if not hasattr(client, 'balance'):
                st.error("❌ 客户端未正确连接，请重新连接券商")
                return
            
            # 获取账户信息
            try:
                balance = client.balance
                if not balance:
                    st.error("❌ 无法获取账户信息，请重新连接")
                    return
                available_cash = balance.get('可用资金', 0)
            except Exception as balance_error:
                st.error(f"❌ 获取账户信息失败：{str(balance_error)}")
                return
        
        # 2. 获取当前股价
        if trade_mode == "实际交易":
            # 华泰证券实际交易：获取实时股票价格
            try:
                # 尝试使用easytrader的get_security_info方法
                if hasattr(client, 'get_security_info'):
                    stock_info = client.get_security_info(stock_code)
                    price = stock_info['最新价']
                # 或者尝试使用其他方法获取股票信息
                elif hasattr(client, 'get_market_data'):
                    market_data = client.get_market_data([stock_code])
                    price = market_data[0]['price']
                else:
                    # 如果无法获取实时价格，使用模拟价格
                    st.warning("无法获取实时股票价格，使用模拟价格")
                    price = round(10 + (ord(stock_code[-1]) % 50), 2)
            except Exception as price_error:
                st.warning(f"获取股票价格失败：{str(price_error)}，使用模拟价格")
                price = round(10 + (ord(stock_code[-1]) % 50), 2)
        else:
            price = round(10 + (ord(stock_code[-1]) % 50), 2)  # 模拟价格
        
        # 3. 交易金额计算和检查
        total_amount = price * amount
        
        if trade_mode == "实际交易":
            # 检查资金是否足够（买入时）
            if trade_type == "buy" and total_amount > available_cash:
                st.error(f"❌ 资金不足：可用资金 {available_cash:.2f} 元，需要 {total_amount:.2f} 元")
                return
            
            # 检查持仓是否足够（卖出时）
            if trade_type == "sell":
                try:
                    positions = client.position
                    stock_position = None
                    for pos in positions:
                        if pos.get('证券代码') == stock_code or pos.get('股票代码') == stock_code:
                            stock_position = pos
                            break
                    if not stock_position:
                        st.error(f"❌ 没有{stock_code}的持仓")
                        return
                    available_shares = stock_position.get('可用股份', 0) or stock_position.get('可用数量', 0)
                    if amount > available_shares:
                        st.error(f"❌ 持仓不足：可用数量 {available_shares} 股，卖出 {amount} 股")
                        return
                except Exception as position_error:
                    st.warning(f"获取持仓信息失败：{str(position_error)}")
        # 4. 执行买入/卖出
        if trade_type == "buy":
            if trade_mode == "实际交易":
                # 华泰实际买入（按实际盘口价格）
                result = client.buy(
                    stock_code,
                    price=price,
                    amount=amount
                )
            else:
                # 模拟买入
                result = client.buy(stock_code, price, amount)
        
        elif trade_type == "sell":
            if trade_mode == "实际交易":
                # 华泰实际卖出
                result = client.sell(
                    stock_code,
                    price=price,
                    amount=amount
                )
            else:
                # 模拟卖出
                result = client.sell(stock_code, price, amount)
        
        # 5. 显示交易结果
        if isinstance(result, dict) and result.get("success", True):
            st.success(f"✅ 交易成功！")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("股票", stock_code)
            with col2:
                st.metric("类型", "买入" if trade_type == "buy" else "卖出")
            with col3:
                st.metric("数量", f"{amount}股")
            col4, col5, col6 = st.columns(3)
            with col4:
                st.metric("价格", f"{price}元")
            with col5:
                st.metric("金额", f"{total_amount:.2f}元")
            with col6:
                if "order_id" in result:
                    st.metric("委托号", result['order_id'])
                else:
                    st.metric("委托号", "-")
        elif isinstance(result, dict):
            st.error(f"❌ 交易失败：{result.get('msg', '未知错误')}")
        else:
            # 华泰证券返回的可能是订单号而不是字典
            st.success(f"✅ 交易成功！")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("股票", stock_code)
            with col2:
                st.metric("类型", "买入" if trade_type == "buy" else "卖出")
            with col3:
                st.metric("数量", f"{amount}股")
            col4, col5, col6 = st.columns(3)
            with col4:
                st.metric("价格", f"{price}元")
            with col5:
                st.metric("金额", f"{total_amount:.2f}元")
            with col6:
                st.metric("委托号", result)
        
        # 6. 交易后更新账户信息
        try:
            if trade_mode == "实际交易":
                new_balance = client.balance
                if new_balance:
                    st.info(f"💰 交易后可用资金：{new_balance.get('可用资金', 0):.2f} 元")
                    st.info(f"🏦 交易后总资产：{new_balance.get('总资产', 0):.2f} 元")
            else:
                # 模拟交易：显示交易后账户信息
                st.info(f"💰 交易后可用资金：{client.balance['可用资金']:.2f} 元")
                st.info(f"🏦 交易后总资产：{client.balance['总资产']:.2f} 元")
                st.info(f"📈 交易后持仓市值：{client.balance['持仓市值']:.2f} 元")
        except Exception as update_error:
            pass
    
    except Exception as e:
        st.error(f"❌ 执行交易失败：{str(e)}")
        with st.expander("查看详细错误"):
            st.code(traceback.format_exc())

# ======================== Web界面 ========================
# ======================== Web界面 ========================
# ======================== Web界面 ========================
# ======================== Web界面 ========================
def main():
    st.set_page_config(
        page_title="Mac量化交易系统", 
        layout="wide", 
        initial_sidebar_state="expanded"
    )
    # 强制触发渲染，防止空白
    st.empty()
    
    # 初始化会话状态
    if 'client' not in st.session_state:
        st.session_state.client = None
    if 'strategy_code' not in st.session_state:
        st.session_state.strategy_code = ""
    if 'backtest_result' not in st.session_state:
        st.session_state.backtest_result = None
    if 'mode' not in st.session_state:
        st.session_state.mode = "回测模式"  # 默认回测模式
    if 'selected_strategy' not in st.session_state:
        st.session_state.selected_strategy = None  # 选中的策略
    if 'trade_mode' not in st.session_state:  # 新增：记录交易模式
        st.session_state.trade_mode = "模拟交易"
    
    # 顶部系统标题（美观、专业、大气）
    st.markdown("""
    <div style='background: linear-gradient(135deg, #1a237e 0%, #283593 100%); padding: 40px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 30px;'>
        <h1 style='color: white; text-align: center; font-size: 36px; font-weight: bold; margin: 0;'>
            🍎 量化交易系统
        </h1>
        <p style='color: #e3f2fd; text-align: center; font-size: 18px; margin-top: 10px;'>
            智能算法 · 精准交易 · 稳健收益
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # 加载账号缓存
    cache_data = load_account_cache()
    
    # ======================== 页面布局配置 ========================
    # 美化页面和侧边栏，移除顶部空白
    st.markdown("""
    <style>
        /* 移除页面顶部空白 */
        .main > div {
            padding-top: 0rem !important;
        }
        
        /* 美化侧边栏背景颜色，使用专业的深色主题 */
        [data-testid="stSidebar"] {
            background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
        }
        [data-testid="stSidebar"] .stHeader {
            color: white;
        }
        [data-testid="stSidebar"] .stRadio > div {
            color: white;
        }
        [data-testid="stSidebar"] .stSelectbox > label {
            color: white;
        }
        [data-testid="stSidebar"] .stTextInput > label {
            color: white;
        }
        [data-testid="stSidebar"] .stCheckbox > label {
            color: white;
        }
        [data-testid="stSidebar"] .stButton > button {
            background-color: #3949ab;
            color: white;
        }
        [data-testid="stSidebar"] .stInfo {
            background-color: rgba(255, 255, 255, 0.1);
            color: white;
        }
        [data-testid="stSidebar"] .stWarning {
            background-color: rgba(255, 235, 59, 0.2);
            color: white;
        }
        [data-testid="stSidebar"] .stDivider {
            background-color: rgba(255, 255, 255, 0.2);
        }
    </style>
    """, unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("⚙️ 系统配置")
        
        # 模式切换
        st.session_state.mode = st.radio(
            "运行模式",
            ["回测模式", "模拟实盘模式"],
            index=0 if st.session_state.mode == "回测模式" else 1,
            key="mode_radio"  # 唯一key
        )
        
        st.divider()
        
        # 券商配置（仅模拟实盘模式显示）
        if st.session_state.mode == "模拟实盘模式":
            st.header("📱 券商配置")
            
            # 交易模式选择（模拟/实际）
            st.session_state.trade_mode = st.radio(
                "交易模式",
                ["模拟交易", "实际交易"],
                index=0 if cache_data["trade_mode"] == "模拟交易" else 1,
                help="⚠️ 模拟交易：无真实资金风险；实际交易：对接真实券商，会产生真实交易风险！",
                key="trade_mode_radio"  # 唯一key
            )
            
            # 实际交易仅显示风险提示文字，移除勾选框
            if st.session_state.trade_mode == "实际交易":
                st.warning("⚠️ 重要提醒：实际交易模式会对接真实券商账户，产生真实的资金盈亏，请谨慎操作！")
            
            broker_type = st.selectbox(
                "选择券商",
                ["华泰证券", "国信证券", "同花顺", "东方财富", "中信证券"],
                index=["华泰证券", "国信证券", "同花顺", "东方财富", "中信证券"].index(cache_data["broker_type"]) 
                if cache_data["broker_type"] in ["华泰证券", "国信证券", "同花顺", "东方财富", "中信证券"] else 0,
                key="broker_select"  # 唯一key
            )
            username = st.text_input("账号", value=cache_data["username"], placeholder="输入账号（模拟可填任意）", key="username_input")
            password = st.text_input("密码", type="password", placeholder="输入密码（模拟可填任意）", key="password_input")
            remember_account = st.checkbox(
                "记住账号和交易模式（密码不保存）", 
                value=True,
                key="remember_account_checkbox"  # 唯一key
            )
            
            # 连接券商按钮（模拟和实际交易都显示，模拟交易自动点击）
            if st.button("🔗 连接券商", type="primary", key="connect_broker_btn"):
                if not username or not password:
                    st.warning("请输入账号和密码！")
                else:
                    with st.spinner(f"正在连接{broker_type}（{st.session_state.trade_mode}）..."):
                        if remember_account:
                            save_account_cache(broker_type, username, st.session_state.trade_mode)
                        # 直接初始化客户端
                        st.session_state.client = init_broker_client(
                            broker_type, 
                            username, 
                            password, 
                            st.session_state.trade_mode
                        )
            
            # 模拟交易自动连接（如果已输入账号密码但未连接）
            if st.session_state.trade_mode == "模拟交易" and username and password and not st.session_state.client:
                with st.spinner(f"正在连接{broker_type}（{st.session_state.trade_mode}）..."):
                    if remember_account:
                        save_account_cache(broker_type, username, st.session_state.trade_mode)
                    # 直接初始化客户端
                    st.session_state.client = init_broker_client(
                        broker_type, 
                        username, 
                        password, 
                        st.session_state.trade_mode
                    )
        
        st.divider()
        
        # 策略管理（仅回测模式显示）
        if st.session_state.mode == "回测模式":
            st.header("📁 策略管理")
            # 加载本地策略列表
            saved_strategies = list_saved_strategies()
            
            if saved_strategies:
                # 构建策略选择列表：显示名称+ID+时间
                strategy_options = [
                    f"{s['name']} (ID:{s['id']}) - {s['create_time']}" 
                    for s in saved_strategies
                ]
                # 策略选择下拉框
                selected_option = st.selectbox(
                    "选择已保存的策略",
                    ["请选择策略..."] + strategy_options,
                    index=0,
                    key="strategy_select"  # 唯一key
                )
                
                # 处理策略选择
                if selected_option != "请选择策略...":
                    # 找到对应的策略元数据
                    selected_idx = strategy_options.index(selected_option)
                    selected_strategy = saved_strategies[selected_idx]
                    st.session_state.selected_strategy = selected_strategy
                    
                    # 加载策略代码（仅在用户点击时）
                    if st.button("📝 加载选中策略", key="load_strategy_btn"):
                        strategy_code = load_strategy_from_file(selected_strategy["filepath"])
                        if strategy_code:
                            st.session_state.strategy_code = strategy_code
                            st.success(f"✅ 已加载策略：{selected_strategy['name']}")
                
                # 删除策略按钮（修复st.rerun()兼容性）
                if st.session_state.selected_strategy and st.button("🗑️ 删除选中策略", type="secondary", key="delete_strategy_btn"):
                    if delete_strategy_file(st.session_state.selected_strategy):
                        # 兼容刷新（替代st.rerun()，避免空白）
                        if hasattr(st, 'experimental_rerun'):
                            st.experimental_rerun()
                        else:
                            st.rerun()
            else:
                st.info("📋 暂无已保存的策略")
        
        st.divider()
        st.info("💡 回测模式：纯本地回测，无需登录")
        st.info("💡 模拟实盘模式：可选择模拟/实际交易，模拟无资金风险")
        st.info("🔒 所有输入的账号密码仅本地使用，不会上传")
    
    # ======================== 主内容区 ========================
    with st.container():
        # ======================== 策略代码预览 ========================
        if st.session_state.strategy_code:
            st.header("📝 策略代码")
            st.code(st.session_state.strategy_code, language="python", line_numbers=True)
        
        # ======================== 回测模式 ========================
        if st.session_state.mode == "回测模式":
            st.header("📊 策略回测")
            # 回测股票代码输入
            stock_code = st.text_input(
                "回测股票代码", 
                value="600519", 
                placeholder="输入6位A股代码，如600519（茅台）、000001（平安银行）",
                key="backtest_stock_code"  # 唯一key
            )
            if st.button("▶️ 运行回测", key="run_backtest_btn"):
                if not st.session_state.strategy_code:
                    st.warning("请先加载策略代码！")
                else:
                    with st.spinner("正在执行回测..."):
                        data_df = load_sample_data(stock_code)
                        st.session_state.backtest_result = backtest_strategy(
                            st.session_state.strategy_code, 
                            data_df
                        )
        
        # ======================== 模拟实盘模式 ========================
        else:
            pass  # 移除实盘交易标题
            
            # 账户信息查询
            if st.session_state.client:
                st.divider()
                st.subheader("💰 账户信息")
                
                # 显示账户余额（实时展示，无需点击刷新）
                try:
                    if st.session_state.trade_mode == "实际交易":
                        # 实际交易：获取真实账户信息
                        balance = st.session_state.client.balance
                        if balance:
                            # 美化账户信息展示
                            st.markdown("""<div style='background-color: #f0f8ff; padding: 20px; border-radius: 10px;'>""", unsafe_allow_html=True)
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("可用资金", f"{balance.get('可用资金', 0):.2f} 元", delta_color="normal")
                            with col2:
                                st.metric("总资产", f"{balance.get('总资产', 0):.2f} 元", delta_color="normal")
                            with col3:
                                st.metric("持仓市值", f"{balance.get('持仓市值', 0):.2f} 元", delta_color="normal")
                            st.markdown("""</div>""", unsafe_allow_html=True)
                        else:
                            st.error("❌ 无法获取账户信息")
                    else:
                        # 模拟交易：显示模拟账户信息
                        st.markdown("""<div style='background-color: #f0f8ff; padding: 20px; border-radius: 10px;'>""", unsafe_allow_html=True)
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("可用资金", f"{st.session_state.client.balance['可用资金']:.2f} 元", delta_color="normal")
                        with col2:
                            st.metric("总资产", f"{st.session_state.client.balance['总资产']:.2f} 元", delta_color="normal")
                        with col3:
                            st.metric("持仓市值", f"{st.session_state.client.balance['持仓市值']:.2f} 元", delta_color="normal")
                        st.markdown("""</div>""", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"❌ 获取账户信息失败：{str(e)}")
                
                # 显示持仓信息（实时展示）
                st.subheader("📋 持仓信息")
                try:
                    if st.session_state.trade_mode == "实际交易":
                        # 实际交易：获取真实持仓
                        positions = st.session_state.client.position
                        if positions:
                            # 转换为DataFrame显示
                            pos_df = pd.DataFrame(positions)
                            # 显示关键列
                            if not pos_df.empty:
                                st.dataframe(pos_df[['证券代码', '证券名称', '持仓数量', '可用股份', '市值', '盈亏比例']], 
                                            use_container_width=True, 
                                            hide_index=True)
                            else:
                                st.info("📭 暂无持仓")
                        else:
                            st.info("📭 暂无持仓")
                    else:
                        # 模拟交易：显示模拟持仓
                        if st.session_state.client.position:
                            pos_df = pd.DataFrame(st.session_state.client.position)
                            # 确保列名一致
                            pos_df = pos_df[['证券代码', '证券名称', '持仓数量', '可用股份', '市值', '盈亏比例']]
                            st.dataframe(pos_df, use_container_width=True, hide_index=True)
                        else:
                            st.info("📭 暂无持仓")
                except Exception as e:
                    st.error(f"❌ 获取持仓信息失败：{str(e)}")
            
            # 交易模式选择
            st.divider()
            trade_mode_option = st.radio(
                "交易模式",
                ["手动交易", "自动量化交易"],
                index=0,
                key="trade_mode_option"
            )
            
            if trade_mode_option == "手动交易":
                # 手动交易
                st.subheader(f"💸 手动执行{st.session_state.trade_mode}")
                col3, col4, col5 = st.columns(3)
                with col3:
                    stock_code = st.text_input("股票代码", placeholder="600000（浦发银行）", key="trade_stock_code")
                with col4:
                    trade_type = st.selectbox("交易类型", ["buy（买入）", "sell（卖出）"], key="trade_type_select")
                with col5:
                    amount = st.number_input("交易数量", min_value=100, step=100, value=100, key="trade_amount_input")
            else:
                # 自动量化交易
                st.subheader(f"🤖 自动量化交易")
                
                # 策略选择
                saved_strategies = list_saved_strategies()
                if saved_strategies:
                    strategy_options = [f"{s['name']} (ID:{s['id']})" for s in saved_strategies]
                    selected_strategy = st.selectbox(
                        "选择交易策略",
                        strategy_options,
                        key="auto_strategy_select"
                    )
                

                
                # 自动选择配置
                market_sector = st.selectbox(
                    "市场板块",
                    ["全部", "沪深300", "创业板", "科创板", "中小板"],
                    key="market_sector_select"
                )
                
                # 运行参数和安全参数（紧凑展示）
                st.subheader("⚙️ 运行与安全参数")
                col_param1, col_param2, col_param3 = st.columns(3)
                with col_param1:
                    max_position_percent = st.slider("单笔最大仓位", 0.1, 1.0, 0.3, 0.1, key="max_position_slider")
                    check_interval = st.number_input("检查间隔（秒）", min_value=1, step=1, value=30, key="check_interval_input")
                with col_param2:
                    max_trade_amount = st.number_input("单笔最大金额（元）", min_value=1000, step=1000, value=10000, key="max_trade_amount_input")
                    max_trades_per_day = st.number_input("每日最大交易次数", min_value=1, step=1, value=10, key="max_trades_per_day_input")
                with col_param3:
                    max_total_position = st.slider("总仓位上限", 0.1, 1.0, 0.8, 0.1, key="max_total_position_slider")
                    st.info(f"自动选择{market_sector}股票")
        
        # 交易确认和执行
        if trade_mode_option == "手动交易":
            if st.session_state.mode == "模拟实盘模式":
                col_execute, col_confirm = st.columns([3, 1])
                with col_execute:
                    if st.button("✅ 执行交易", type="primary", key="execute_trade_btn"):
                        if not st.session_state.client:
                            st.warning("请先在侧边栏成功连接券商客户端！")
                        elif not stock_code:
                            st.warning("请输入股票代码！")
                        else:
                            # 计算交易金额
                            estimated_price = round(10 + (ord(stock_code[-1]) % 50), 2) if st.session_state.trade_mode == "模拟交易" else 0
                            estimated_amount = estimated_price * amount
                            
                            # 显示交易确认对话框
                            with st.expander("📋 交易确认", expanded=True):
                                st.info(f"📈 股票：{stock_code}")
                                st.info(f"🔄 类型：{trade_type}")
                                st.info(f"📊 数量：{amount}股")
                                if st.session_state.trade_mode == "实际交易":
                                    st.info(f"💵 预估金额：{estimated_amount:.2f} 元")
                                else:
                                    st.info(f"💵 交易金额：{estimated_amount:.2f} 元")
                                
                                # 风险提示
                            if st.session_state.trade_mode == "实际交易":
                                st.warning("⚠️ 重要提醒：")
                                st.warning("1. 您正在执行真实交易，资金可能会有盈亏")
                                st.warning("2. 请确认股票代码和交易数量正确")
                                st.warning("3. 交易一旦执行，无法撤销")
                                
                                # 确认按钮（仅实际交易需要）
                                confirm = st.checkbox("我已确认交易信息，愿意承担交易风险", key="trade_confirm_checkbox")
                                
                                if confirm:
                                    with st.spinner("正在发送交易指令..."):
                                        # 转换交易类型
                                        trade_type = trade_type.split("（")[0]
                                        execute_trade(
                                            st.session_state.client, 
                                            stock_code, 
                                            trade_type, 
                                            amount,
                                            st.session_state.trade_mode  # 传入交易模式
                                        )
                                    # 交易完成后自动刷新页面，更新账户信息和持仓
                                    st.experimental_rerun() if hasattr(st, 'experimental_rerun') else st.rerun()
                                else:
                                    st.info("请勾选确认框后再执行交易")
                            else:
                                # 模拟交易：直接执行，无需确认
                                with st.spinner("正在发送交易指令..."):
                                    # 转换交易类型
                                    trade_type = trade_type.split("（")[0]
                                    execute_trade(
                                        st.session_state.client, 
                                        stock_code, 
                                        trade_type, 
                                        amount,
                                        st.session_state.trade_mode  # 传入交易模式
                                    )
                                # 交易完成后自动刷新页面，更新账户信息和持仓
                                # 注意：使用rerun会重新加载页面，但客户端状态已保存在session_state中
                                time.sleep(1)  # 等待1秒确保交易记录已保存
                                st.experimental_rerun() if hasattr(st, 'experimental_rerun') else st.rerun()
        else:
            # 自动量化交易控制
            col_auto1, col_auto2 = st.columns(2)
            with col_auto1:
                if st.button("▶️ 启动自动交易", type="primary", key="start_auto_trade_btn"):
                    if not st.session_state.client:
                        st.warning("请先在侧边栏成功连接券商客户端！")
                    elif not saved_strategies:
                        st.warning("请先保存交易策略！")
                    else:
                        st.success("✅ 自动量化交易已启动！")
                        
                        # 紧凑展示核心参数
                        col_param1, col_param2, col_param3, col_param4 = st.columns(4)
                        with col_param1:
                            st.metric("策略", selected_strategy.split(' (ID:')[0])
                        with col_param2:
                            st.metric("单笔仓位", f"{max_position_percent*100:.0f}%")
                        with col_param3:
                            st.metric("总仓上限", f"{max_total_position*100:.0f}%")
                        with col_param4:
                            st.metric("检查间隔", f"{check_interval}秒")
                        
                        col_param5, col_param6, col_param7, col_param8 = st.columns(4)
                        with col_param5:
                            st.metric("单笔限额", f"{max_trade_amount}元")
                        with col_param6:
                            st.metric("每日最大交易", f"{max_trades_per_day}次")
                        with col_param7:
                            st.metric("交易标的", f"{market_sector}")
                        with col_param8:
                            st.metric("模式", "量化自动")
                        
                        # 自动交易核心逻辑
                        import threading
                        import random
                        
                        # 全局变量控制自动交易状态
                        today_trades = 0
                        
                        def auto_trade_thread():
                            nonlocal today_trades
                            today_date = datetime.now().strftime('%Y-%m-%d')
                            
                            while st.session_state.get('auto_trade_running', True):
                                try:
                                    # 检查是否需要重置每日交易计数
                                    current_date = datetime.now().strftime('%Y-%m-%d')
                                    if current_date != today_date:
                                        today_trades = 0
                                        today_date = current_date
                                    
                                    # 检查每日交易次数限制
                                    if today_trades >= max_trades_per_day:
                                        st.info(f"今日交易次数已达上限（{max_trades_per_day}次）")
                                        time.sleep(check_interval)
                                        continue
                                    
                                    # 获取账户信息
                                    if st.session_state.trade_mode == "实际交易":
                                        balance = st.session_state.client.balance
                                        available_cash = balance.get('可用资金', 0)
                                    else:
                                        available_cash = st.session_state.client.balance['可用资金']
                                    
                                    # 计算总仓位
                                    if st.session_state.trade_mode == "实际交易":
                                        total_asset = balance.get('总资产', 0)
                                    else:
                                        total_asset = st.session_state.client.balance['总资产']
                                    
                                    current_position = (total_asset - available_cash) / total_asset if total_asset > 0 else 0
                                    
                                    # 检查总仓位限制
                                    if current_position >= max_total_position:
                                        st.info(f"总仓位已达上限（{max_total_position*100:.0f}%）")
                                        time.sleep(check_interval)
                                        continue
                                    
                                    # 确定交易标的
                                    sector_stocks = {
                                        "全部": ["600519", "000001", "600000", "000858", "601318", "600036", "601888", "600276", "002594", "300750"],
                                        "沪深300": ["600519", "000001", "600000", "601318", "600036", "601888"],
                                        "创业板": ["300750", "300124", "300413", "300760"],
                                        "科创板": ["688981", "688009", "688256"],
                                        "中小板": ["002594", "002415", "002759"]
                                    }
                                    
                                    stocks = sector_stocks.get(market_sector, sector_stocks["全部"])
                                    selected_stocks = stocks
                                    
                                    # 遍历交易标的
                                    for stock_code in selected_stocks:
                                        if not st.session_state.get('auto_trade_running', True):
                                            break
                                        
                                        # 检查交易次数
                                        if today_trades >= max_trades_per_day:
                                            break
                                        
                                        # 计算单笔交易金额
                                        max_position_amount = available_cash * max_position_percent
                                        trade_amount = min(max_position_amount, max_trade_amount)
                                        
                                        if trade_amount < 1000:
                                            continue
                                        
                                        # 获取股票价格（模拟）
                                        price = round(10 + (ord(stock_code[-1]) % 50), 2)
                                        shares = int(trade_amount // (price * 100)) * 100  # 按100股整数倍
                                        
                                        if shares < 100:
                                            continue
                                        
                                        # 执行买入交易
                                        if st.session_state.trade_mode == "实际交易":
                                            result = st.session_state.client.buy(stock_code, price=price, amount=shares)
                                        else:
                                            result = st.session_state.client.buy(stock_code, price, shares)
                                        
                                        # 记录交易
                                        if isinstance(result, dict) and result.get("success", True):
                                            today_trades += 1
                                            st.info(f"✅ 自动交易：买入 {stock_code} {shares}股，价格{price}元")
                                            
                                            # 模拟交易时添加交易记录
                                            if st.session_state.trade_mode == "模拟交易":
                                                trade_record = {
                                                    "交易时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                    "证券代码": stock_code,
                                                    "证券名称": f"股票{stock_code}",
                                                    "买卖方向": "买入",
                                                    "成交价格": price,
                                                    "成交数量": shares,
                                                    "成交金额": price * shares,
                                                    "交易类型": "量化自动交易"
                                                }
                                                st.session_state.client.trade_records.append(trade_record)
                                        
                                        # 等待一段时间再进行下一笔交易
                                        time.sleep(5)
                                    
                                except Exception as e:
                                    st.error(f"自动交易出错：{str(e)}")
                                
                                # 等待下一次检查
                                time.sleep(check_interval)
                        
                        # 启动自动交易线程
                        auto_thread = threading.Thread(target=auto_trade_thread)
                        auto_thread.daemon = True
                        auto_thread.start()
                        
                        # 保存自动交易状态
                        st.session_state.auto_trade_running = True
                        st.session_state.auto_thread = auto_thread
            with col_auto2:
                if st.button("⏹️ 停止自动交易", type="secondary", key="stop_auto_trade_btn"):
                    # 停止自动交易线程
                    if hasattr(st.session_state, 'auto_trade_running'):
                        st.session_state.auto_trade_running = False
                        # 等待线程结束
                        if hasattr(st.session_state, 'auto_thread'):
                            st.session_state.auto_thread.join(timeout=5)
                    st.success("✅ 自动量化交易已停止！")
        
        # 显示交易记录（放在最下面）
        if st.session_state.client:
            st.divider()
            st.subheader("📝 交易记录")
            try:
                if st.session_state.trade_mode == "实际交易":
                    # 实际交易：获取真实交易记录
                    if hasattr(st.session_state.client, 'get_trade_records'):
                        trades = st.session_state.client.get_trade_records()
                    elif hasattr(st.session_state.client, 'trade'):
                        trades = st.session_state.client.trade
                    else:
                        trades = []
                else:
                    # 模拟交易：获取模拟交易记录
                    trades = st.session_state.client.trade_records
                
                if trades:
                    trade_df = pd.DataFrame(trades)
                    # 显示关键列，包含交易类型
                    if not trade_df.empty:
                        # 确保交易类型列存在
                        if '交易类型' not in trade_df.columns:
                            trade_df['交易类型'] = '手动交易'  # 默认为手动交易
                        st.dataframe(trade_df[['交易时间', '证券代码', '证券名称', '买卖方向', '成交价格', '成交数量', '成交金额', '交易类型']], use_container_width=True)
                    else:
                        st.info("📭 暂无交易记录")
                else:
                    st.info("📭 暂无交易记录")
            except Exception as e:
                st.error(f"❌ 获取交易记录失败：{str(e)}")

if __name__ == "__main__":
    warnings.filterwarnings('ignore')
    os.environ["STREAMLIT_WATCHER_TYPE"] = "poll"
    # 修复临时目录问题
    os.environ["TMPDIR"] = tempfile.gettempdir()
    main()