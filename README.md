# 🤖 Crypto Analyzer Bot

基于 Discord 的加密货币 AI 量化分析机器人，支持多模型竞技场 (Model Arena) 回测、智能风控与实时预警。

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Discord](https://img.shields.io/badge/Discord-Bot-5865F2.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ 核心特性

### 📊 多维度市场分析
- **多时间周期共振分析** - 小周期入场、中周期交易、大周期趋势
- **资金面数据监控** - 资金费率、未平仓量 (OI)、多空比
- **宏观情绪指标** - 恐慌贪婪指数、市场新闻情绪

### 🤖 Model Arena (多模型竞技场)
- **支持多 AI 模型** - Kimi 2.5、Gemini Pro、GPT-4、Claude 3
- **交易建议追踪** - 自动记录每笔 AI 建议的开平仓点位
- **绩效回测统计** - 胜率、盈亏比、累计收益、资金曲线
- **模型横向对比** - 哪家 AI 预测最准？数据说话！

### 🛡️ 智能风控系统
- **ATR 动态止损** - 基于真实波幅的自适应止损计算
- **爆仓价推算** - 精确计算各杠杆倍数下的爆仓价格
- **仓位规模建议** - 根据风险承受度计算最优仓位
- **GO/NO-GO 决策** - 严格的风控决策流程

### 🔔 实时预警监控
- **技术指标预警** - RSI 超买/超卖、MACD 金叉/死叉
- **价格突破预警** - 自定义价格阈值监控
- **自动定期检查** - 每 5 分钟扫描市场条件

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/DHFS/crypto-analyzer-bot.git
cd crypto-analyzer-bot
```

### 2. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入以下必需配置
```

**必需配置项：**

| 变量名 | 说明 | 获取方式 |
|--------|------|----------|
| `DISCORD_BOT_TOKEN` | Discord Bot Token | [Discord Developer Portal](https://discord.com/developers/applications) |
| `BINANCE_API_KEY` | Binance API Key | [Binance API 管理](https://www.binance.com/cn/my/settings/api-management) |
| `BINANCE_API_SECRET` | Binance API Secret | 同上 |
| `MOONSHOT_API_KEY` | Kimi AI API Key | [Moonshot 开放平台](https://platform.moonshot.cn/) |

**可选配置项：**

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DEFAULT_AI_MODEL` | 默认 AI 模型 | `kimi` |
| `HTTP_PROXY` | 代理地址 (如需要) | 无 |
| `OPENAI_API_KEY` | OpenAI API Key (备用) | 无 |
| `GOOGLE_API_KEY` | Google API Key (Gemini) | 无 |

### 4. 启动 Bot

```bash
python main.py
```

成功启动后会输出：
- `✅ 数据库已初始化`
- `✅ 斜杠命令已同步`
- `🚀 Bot 已登录: {Bot名称}`
- 邀请链接

## 📚 命令列表

### 市场分析命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/analyze` | `<symbol> <timeframe> [model]` | AI 综合分析（支持模型切换） |
| `/indicators` | `<symbol> <timeframe>` | 技术指标与多周期共振分析 |
| `/funding` | `<symbol>` | 合约资金面数据 (OI/资金费率/多空比) |
| `/sentiment` | - | 市场情绪 (恐慌贪婪指数) |
| `/price` | `<symbol>` | 当前价格与 24h 统计 |

### Model Arena 命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/history` | `[symbol] [limit]` | 交易历史记录（带模型标识） |
| `/dashboard` | `[symbol] [days]` | 模型绩效面板与资金曲线 |

### 预警命令

| 命令 | 参数 | 说明 |
|------|------|------|
| `/alert_add` | `<symbol> <condition> [threshold]` | 添加预警 |
| `/alert_list` | - | 查看我的预警 |
| `/alert_remove` | `<alert_id>` | 删除指定预警 |
| `/alert_clear` | - | 清空所有预警 |

## 💡 使用示例

### AI 分析并记录到回测系统

```bash
# 使用默认模型 (Kimi) 分析 ETH
/analyze ETHUSDT 1h

# 使用 Gemini 分析并计入其战绩
/analyze ETHUSDT 1h model:gemini

# 使用 GPT-4 分析
/analyze BTCUSDT 4h model:gpt
```

### 查看回测数据

```bash
# 查看 ETH 最近 10 笔交易记录
/history ETHUSDT 10

# 查看全局绩效面板
/dashboard

# 查看 BTC 近 7 天战绩
/dashboard BTCUSDT days:7
```

### 设置预警

```bash
# RSI 超卖预警
/alert_add ETHUSDT rsi_oversold

# 价格突破 70,000 预警
/alert_add BTCUSDT price_above 70000

# MACD 金叉预警
/alert_add ETHUSDT macd_golden
```

## 🏗️ 项目架构

```
crypto-analyzer-bot/
├── main.py                     # 程序入口
├── config.py                   # 配置管理
├── requirements.txt            # 依赖列表
├── .env                        # 环境变量 (不提交到 Git)
├── handlers/                   # Discord 命令处理器
│   ├── __init__.py
│   └── commands.py             # 所有斜杠命令实现
├── services/                   # 业务服务层
│   ├── __init__.py
│   ├── binance.py              # Binance 数据获取
│   ├── indicators.py           # 技术指标计算
│   ├── ai_analyzer.py          # AI 分析服务
│   ├── risk_math.py            # 风控计算服务 (NEW)
│   ├── database.py             # SQLite 交易日志 (NEW)
│   ├── tracker.py              # 订单追踪结算器 (NEW)
│   ├── alert.py                # 预警服务
│   └── macro.py                # 宏观数据服务
└── data/                       # 数据目录 (自动生成)
    └── trades.db               # SQLite 数据库
```

### 数据流架构

```
Discord 命令 → handlers/commands.py
                    ↓
            services/binance.py (获取市场数据)
                    ↓
            services/indicators.py (计算技术指标)
                    ↓
            services/risk_math.py (风控计算)
                    ↓
            services/ai_analyzer.py (AI 分析)
                    ↓
            ┌─────────────────┴─────────────────┐
            ↓                                   ↓
    返回文本给用户                    交易建议存入 database
            ↓                                   ↓
    /history 查询                    tracker.py 自动结算
            ↓                                   ↓
    /dashboard 统计                  更新盈亏数据
```

## 📊 Model Arena (模型竞技场)

### 核心概念

Model Arena 是一个轻量级的虚拟盘回测系统，用于横向对比不同 AI 模型的交易建议质量。

**工作流程：**
1. 用户使用 `/analyze` 命令获取 AI 交易建议
2. 系统强制 AI 输出结构化 JSON (方向、进场价、止损、止盈)
3. 如果 AI 判断为 `GO` (建议进场)，自动记录到数据库
4. 后台 Tracker 每 5 分钟检查未结算订单
5. 当价格触及 TP/SL 时自动结算，计算实际盈亏
6. `/dashboard` 展示各模型的胜率、盈亏比、累计收益

### 数据结构

```json
{
  "id": 1,
  "symbol": "ETHUSDT",
  "direction": "LONG",
  "entry_price": 3100.50,
  "tp_price": 3200.00,
  "sl_price": 3050.00,
  "leverage": 5,
  "ai_model": "kimi-2.5",
  "status": "CLOSED_TP",
  "pnl_percentage": 16.05,
  "close_reason": "TP"
}
```

### Dashboard 指标

| 指标 | 说明 |
|------|------|
| **胜率** | 止盈订单数 / 总结算订单数 |
| **累计盈亏** | 所有订单盈亏百分比之和 (已乘杠杆) |
| **平均盈亏** | 平均每笔订单的盈亏 |
| **资金曲线** | 累计盈亏随时间变化的可视化图表 |

## 🛡️ 风控计算说明

### ATR 止损计算

```python
# 基于 14 周期 ATR 的止损计算
atr = AverageTrueRange(high, low, close, window=14)
stop_price = current_price - (atr * 2.0)  # LONG 方向
```

### 爆仓价计算

```python
# 逐仓模式爆仓价公式
liquidation_price = entry_price * (1 - 1/leverage + maintenance_margin)
```

### 盈亏计算公式

```
盈亏百分比 = (平仓价 - 开仓价) / 开仓价 × 杠杆倍数 × 100%

例如：
- 方向：LONG
- 开仓价：3000
- 平仓价：3200
- 杠杆：5x

盈亏 = (3200 - 3000) / 3000 × 5 × 100% = +33.33%
```

## 🔧 配置说明

### 支持的 AI 模型

| 模型 | 标识 | 说明 |
|------|------|------|
| Kimi 2.5 | `kimi` | Moonshot 中文大模型 (默认) |
| Gemini Pro | `gemini` | Google 多模态模型 |
| GPT-4 | `gpt` | OpenAI 最强模型 |
| Claude 3 | `claude` | Anthropic 安全模型 |

### 支持的时间周期

`1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`

### 预警条件类型

| 条件 | 说明 |
|------|------|
| `rsi_oversold` | RSI < 30 (超卖) |
| `rsi_overbought` | RSI > 70 (超买) |
| `macd_golden` | MACD 金叉 |
| `macd_dead` | MACD 死叉 |
| `bb_upper` | 触及布林带上轨 |
| `bb_lower` | 触及布林带下轨 |
| `price_above` | 价格突破指定阈值 |
| `price_below` | 价格跌破指定阈值 |

## 📝 开发指南

### 代码规范

- **注释使用中文**，代码使用英文命名
- 类名：PascalCase (如 `BinanceService`)
- 函数/方法：snake_case (如 `get_klines`)
- 常量：UPPER_SNAKE_CASE

### 添加新 AI 模型支持

1. 在 `config.py` 的 `VALID_MODELS` 中添加新模型
2. 在 `ai_analyzer.py` 的 `get_model_name()` 中添加模型映射
3. 在 `commands.py` 的 `MODEL_CHOICES` 中添加选择项

### 数据库迁移

数据库支持自动升级。如需手动修改表结构：

```bash
# 进入 data 目录
sqlite3 data/trades.db

# 查看表结构
.schema trade_logs

# 手动添加字段 (示例)
ALTER TABLE trade_logs ADD COLUMN new_field TEXT;
```

## 🚨 故障排除

### Bot 无法启动

- 检查 `.env` 中的 `DISCORD_BOT_TOKEN` 是否正确
- 检查 Python 版本是否 >= 3.8
- 检查依赖是否完整安装：`pip install -r requirements.txt`

### AI 分析失败

- 检查 API Key 是否有效且余额充足
- 检查网络连接 (如需代理请配置 `HTTP_PROXY`)
- 查看日志中的详细错误信息

### 回测数据不更新

- 检查 tracker 是否正常运行：`/dashboard` 查看是否有"进行中"订单
- 检查数据库文件权限：`data/trades.db` 是否可读写
- 查看控制台日志是否有结算记录

### 命令不显示

- 确保 Bot 已被邀请至服务器且具有 `applications.commands` 权限
- 检查 `setup_hook()` 是否正常执行
- 尝试重新同步命令：`await tree.sync()`

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [discord.py](https://github.com/Rapptz/discord.py) - Discord Bot 框架
- [python-binance](https://github.com/sammchardy/python-binance) - Binance API 客户端
- [Moonshot AI](https://www.moonshot.cn/) - Kimi 大模型
- [ta-lib](https://github.com/TA-Lib/ta-lib-python) - 技术指标库

---

**⚠️ 风险提示：**
本 Bot 仅供学习和研究使用，不构成任何投资建议。加密货币交易风险极高，请务必谨慎决策，切勿投入超过承受能力的资金。AI 分析结果仅供参考，不保证盈利。
