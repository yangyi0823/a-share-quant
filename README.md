# A股量化交易系统

基于Python的A股智能量化交易系统，集成多策略、AI驱动、钉钉实时通知。

## 策略概览

| 策略 | 文件 | 风格 | 说明 |
|------|------|------|------|
| 短线套利 | `strategies/realtime_arb_strategy.py` | 日内短线 | BGM模型+技术面+情绪面选股，实时盯盘 |
| 长线价值 | `strategies/long_term_strategy.py` | 中长线 | 宏观周期定位+估值分析，盘前盘后通知 |
| 超级策略 | `strategies/super_strategy.py` | 超短线 | 40+因子+Q-Learning强化学习，目标胜率>80% |
| ETF T+0 | `strategies/t0_etf_strategy.py` | 日内T+0 | ETF多时间框架预测，5s/10s/30s/1min/5min |
| 看板 | `dashboard.py` | 可视化 | Streamlit Web界面，回测+实盘监控 |

## 核心特性

- **免费数据源** — 腾讯行情+东方财富，无需付费API
- **钉钉通知** — 买卖信号实时推送到钉钉群
- **AI驱动** — Q-Learning强化学习+LightGBM+Alpha101因子
- **风控系统** — 止损/止盈/最大回撤/仓位控制
- **Web看板** — Streamlit可视化回测和实盘监控
- **自动下单** — 支持easytrader对接券商（可选）

## 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/yangyi0823/a-share-quant.git
cd a-share-quant
pip install -r requirements.txt
```

> **TA-Lib安装提示**: macOS用 `brew install ta-lib` 先装C库，Linux用 `sudo apt install libta-lib-dev`

### 2. 配置通知

```bash
# 复制配置模板
cp .env.example .env

# 编辑.env，填入你的钉钉机器人access_token
# 获取方式: 钉钉群 → 设置 → 智能群助手 → 添加机器人 → 自定义
# DINGTALK_ACCESS_TOKEN=你的token
```

> 不配置钉钉也能运行，信号会打印到控制台

### 3. 运行策略

```bash
# 给脚本加执行权限
chmod +x start.sh stop.sh

# 运行短线套利策略
./start.sh realtime

# 运行长线价值策略
./start.sh longterm

# 运行超级策略(AI驱动)
./start.sh super

# 运行ETF T+0策略
./start.sh t0

# 启动Web看板
./start.sh dashboard

# 后台运行所有策略
./start.sh all

# 停止所有策略
./stop.sh
```

或者用Python直接运行：

```bash
python3 main.py realtime    # 短线套利
python3 main.py longterm    # 长线价值
python3 main.py super       # 超级策略
python3 main.py t0          # ETF T+0
python3 main.py dashboard   # Web看板
```

### 4. 收集历史数据（可选，用于回测）

```bash
python3 collect_data.py
```

## 项目结构

```
a-share-quant/
├── main.py                          # 统一启动入口
├── start.sh                         # 启动脚本
├── stop.sh                          # 停止脚本
├── dashboard.py                     # Streamlit Web看板
├── collect_data.py                  # 历史数据收集
├── requirements.txt                 # Python依赖
├── .env.example                     # 配置模板
├── strategies/
│   ├── realtime_arb_strategy.py     # 短线套利策略
│   ├── long_term_strategy.py        # 长线价值策略
│   ├── super_strategy.py            # 超级策略(AI)
│   ├── t0_etf_strategy.py           # ETF T+0策略
│   └── etf_t0_predictor.py          # ETF T+0预测器
├── data/                            # 数据目录(gitignore)
├── models/                          # 模型文件(gitignore)
├── logs/                            # 日志目录(gitignore)
└── config/                          # 配置目录(gitignore)
```

## 配置说明

所有敏感信息通过 `.env` 文件管理，**绝不硬编码在代码中**。

| 配置项 | 说明 | 获取方式 |
|--------|------|----------|
| `DINGTALK_ACCESS_TOKEN` | 钉钉机器人Token | 钉钉群→设置→智能群助手→添加机器人 |
| `BROKER_TYPE` | 券商类型(可选) | gf/yh/ht/yjb |
| `BROKER_ACCOUNT` | 券商账号(可选) | 你的券商资金账号 |
| `BROKER_PASSWORD` | 券商密码(可选) | 你的交易密码 |

## 风险提示

⚠️ **本项目仅供学习研究，不构成任何投资建议**

- 策略基于历史数据回测，过往表现不代表未来收益
- A股市场受政策影响大，任何模型都可能失效
- 实盘交易请务必做好风控，设置止损
- 建议先用模拟盘验证策略有效性

## License

MIT
