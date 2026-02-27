# Crypto Analyzer Bot - AI Agent Guide

## Project Overview

这是一个 Discord 加密货币行情分析机器人，能够从 Binance 获取合约市场数据，计算技术指标，并使用 AI (Kimi/Moonshot) 生成专业的交易分析和建议。

**主要功能:**
- `/analyze <交易对> <周期>` - AI 综合分析并给出交易建议
- `/indicators <交易对> <周期>` - 查看技术指标数据
- `/price <交易对>` - 查看当前价格和 24h 统计
- `/help` - 查看帮助信息

## Technology Stack

**核心框架:**
- Python 3.8+
- discord.py >= 2.0.0 (Discord Bot 框架)
- python-binance >= 1.0.0 (Binance API 客户端)

**数据处理:**
- pandas >= 1.3.0 (数据分析)
- ta >= 0.10.0 (技术指标计算)
- openai >= 1.0.0 (Moonshot API 兼容层)

**配置管理:**
- python-dotenv >= 1.0.0 (环境变量加载)

**可选依赖:**
- aiohttp-socks (代理支持，如需通过代理访问 Discord)

## Project Structure

```
crypto-analyzer-bot/
├── main.py                 # 程序入口，Discord Bot 初始化和启动
├── config.py               # 配置管理，环境变量加载
├── requirements.txt        # Python 依赖列表
├── .env                    # 环境变量 (敏感信息，不提交到 Git)
├── .env.example            # 环境变量示例模板
├── handlers/               # Discord 命令处理器
│   ├── __init__.py
│   └── commands.py         # 所有斜杠命令的实现
├── services/               # 业务服务层
│   ├── __init__.py
│   ├── binance.py          # Binance 数据获取服务
│   ├── indicators.py       # 技术指标计算服务
│   └── ai_analyzer.py      # Kimi AI 分析服务
└── .github/
    └── copilot-instructions.md  # GitHub Copilot 辅助编码指南
```

## Architecture & Data Flow

### 核心流程

```
Discord 命令 → handlers/commands.py → services/binance.py (获取数据)
                                      ↓
                              services/indicators.py (计算指标)
                                      ↓
                              services/ai_analyzer.py (AI 分析)
                                      ↓
                              Discord 消息回复
```

### 服务层说明

1. **BinanceService** (`services/binance.py`)
   - 使用 `python-binance` 客户端连接 Binance API
   - 获取合约 K 线数据和 24h 行情统计
   - 支持代理配置
   - 返回 pandas DataFrame 格式数据

2. **IndicatorService** (`services/indicators.py`)
   - 使用 `ta` 库计算技术指标
   - 支持指标: MA, EMA, MACD, RSI, Bollinger Bands, ATR
   - 提供指标格式化输出功能

3. **AIAnalyzer** (`services/ai_analyzer.py`)
   - 使用 OpenAI SDK 调用 Moonshot API
   - 构建结构化 Prompt 进行专业交易分析
   - 返回中文分析报告

### 服务实例化模式

服务实例在 `handlers/commands.py` 模块级别**只实例化一次**，所有命令处理器共享这些实例:

```python
binance_service = BinanceService()
indicator_service = IndicatorService()
ai_analyzer = AIAnalyzer()
```

**重要**: 不要在命令处理器中创建新的服务实例。

## Configuration

### 环境变量

所有配置通过 `.env` 文件管理，由 `config.py` 加载:

| 变量名 | 说明 | 是否必需 |
|--------|------|----------|
| `DISCORD_BOT_TOKEN` | Discord Bot Token | 是 |
| `BINANCE_API_KEY` | Binance API Key (只需读取权限) | 是 |
| `BINANCE_API_SECRET` | Binance API Secret | 是 |
| `MOONSHOT_API_KEY` | Moonshot AI API Key | 是 |
| `OPENAI_API_KEY` | OpenAI API Key (备用) | 否 |
| `ANTHROPIC_API_KEY` | Anthropic API Key (备用) | 否 |
| `GOOGLE_API_KEY` | Google API Key (备用) | 否 |
| `DEFAULT_AI_MODEL` | 默认 AI 模型: gpt/claude/gemini/kimi | 否 (默认: kimi) |
| `HTTP_PROXY` | HTTP 代理地址 (如 http://127.0.0.1:4780) | 否 |

### 配置常量

`config.py` 中定义的常量:

- `VALID_TIMEFRAMES`: `["1m", "5m", "15m", "30m", "1h", "4h", "1d"]`
- `VALID_MODELS`: `["gpt", "claude", "gemini", "kimi"]`

## Build and Run Commands

### 环境准备

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. 安装依赖
pip install -r requirements.txt
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入所有必需的 API Keys
```

### 运行

```bash
# 启动 Bot
python main.py
```

成功启动后会输出:
- `✅ 斜杠命令已同步`
- `🚀 Bot 已登录: {Bot名称}`
- 邀请链接

## Code Style Guidelines

### 语言规范
- **所有注释使用中文**
- 代码使用英文命名 (类名、函数名、变量名)
- 字符串输出给用户的内容使用中文

### 命名规范
- 类名: PascalCase (如 `BinanceService`)
- 函数/方法: snake_case (如 `get_klines`)
- 常量: UPPER_SNAKE_CASE (如 `ANALYSIS_PROMPT`)
- 私有方法: 下划线前缀 (如 `_safe_last`)

### 类型提示
- 适度使用类型提示，非强制
- 函数参数和返回值建议标注类型
- 优先使用标准类型 (如 `dict`, `list`) 而非 `typing` 模块

### 异步编程
- Discord 交互必须使用 `async/await`
- API 调用使用异步客户端 (`AsyncOpenAI`)
- 长时间操作需要 `defer(thinking=True)`

## Discord Interaction Patterns

### 斜杠命令定义

```python
@tree.command(name="command_name", description="命令描述")
@app_commands.describe(
    param1="参数1描述",
    param2="参数2描述"
)
async def command_name(interaction: discord.Interaction, param1: str, param2: str):
    # 验证输入
    if invalid:
        await interaction.response.send_message("错误信息", ephemeral=True)
        return
    
    # 长时间操作需要 defer
    await interaction.response.defer(thinking=True)
    
    # 执行操作...
    result = await some_async_operation()
    
    # 回复结果
    await interaction.followup.send(result)
```

### 消息长度处理

Discord 消息限制 2000 字符，超长消息需要分段:

```python
if len(analysis) <= 2000:
    await interaction.followup.send(analysis)
else:
    chunks = [analysis[i:i+1990] for i in range(0, len(analysis), 1990)]
    for i, chunk in enumerate(chunks):
        if i == 0:
            await interaction.followup.send(chunk)
        else:
            await interaction.channel.send(chunk)
```

### 错误处理

统一错误消息格式，使用 emoji 标识:
- `❌` - 错误
- `✅` - 成功
- `🚀` - 状态提示

```python
try:
    result = await operation()
except Exception as e:
    await interaction.followup.send(f"❌ 操作失败: {str(e)}")
```

## Data Processing Conventions

### 交易对格式

- 输入: `ETHUSDT` 或 `ethusdt` 或 `ETH/USDT`
- 内部处理: 统一转换为大写，移除斜杠
- 代码: `symbol = symbol.upper().replace("/", "")`

### 时间周期

支持的时间周期:
- `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`

验证: `if timeframe not in config.VALID_TIMEFRAMES`

### K 线数据格式

Binance 返回的数据转换为 pandas DataFrame，列名:
- `timestamp`: datetime
- `open`: float
- `high`: float
- `low`: float
- `close`: float
- `volume`: float

时间戳转换: `pd.to_datetime(df["timestamp"], unit="ms")`

### 指标数据格式

`IndicatorService.calculate_all()` 返回 dict 结构:

```python
{
    "current_price": float,
    "ma": {"ma5": float, "ma10": float, ...},
    "ema": {"ema7": float, "ema25": float, ...},
    "macd": {"macd": float, "signal": float, "histogram": float},
    "rsi": float,
    "bollinger": {"upper": float, "middle": float, "lower": float},
    "atr": float,
    "volume": {"current": float, "ma5": float, "ma20": float},
    "recent": {"high_20": float, "low_20": float},
}
```

## AI Analysis Prompt

AI 分析使用的 Prompt 模板位于 `services/ai_analyzer.py`，包含:
- 交易对信息
- 当前价格和 24h 统计
- 技术指标 JSON 数据
- 分析要求: 趋势判断、关键价位、开单建议、仓位建议、风险提示

输出格式:
```
🤖 Kimi 分析报告
━━━━━━━━━━━━━━━━━━━━

{AI 分析内容}
```

## Testing Instructions

### 本地测试

1. 确保 `.env` 文件配置正确
2. 运行 `python main.py`
3. 在 Discord 中使用 `/help` 测试基础功能
4. 使用 `/price ETHUSDT` 测试 Binance 连接
5. 使用 `/indicators ETHUSDT 1h` 测试指标计算
6. 使用 `/analyze ETHUSDT 1h` 测试完整流程

### 日志查看

日志格式: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

启动时会输出 Bot 信息和邀请链接。

### 代理测试

如需通过代理访问 Discord 或 Binance:
1. 在 `.env` 中设置 `HTTP_PROXY=http://127.0.0.1:4780`
2. 重启 Bot
3. 检查是否能正常获取数据

## Security Considerations

### API Keys 管理

- **永远不要**将 `.env` 文件提交到 Git
- `.env` 文件应添加到 `.gitignore`
- 定期轮换 API Keys
- 使用最小权限原则 (Binance API 只需读取权限)

### 代理安全

- 代理配置仅用于网络访问
- 敏感数据 (API Keys) 直接发送到官方 API，不经过代理

### 错误信息

- 向用户展示的错误信息不应暴露内部细节
- 日志中可记录详细错误信息用于调试

## Deployment Notes

### 运行环境

- Python 3.8 或更高版本
- 建议 Linux 服务器 (如 Ubuntu)
- 需要稳定的网络连接

### 进程管理

建议使用 `systemd` 或 `supervisor` 管理 Bot 进程，确保崩溃后自动重启。

### 监控

- 监控 Bot 进程状态
- 监控 API 调用错误率
- 设置 Discord 状态检查 (如需要)

## Common Development Tasks

### 添加新命令

1. 在 `handlers/commands.py` 中添加新的 `@tree.command` 装饰器函数
2. 使用 `@app_commands.describe()` 描述参数
3. 验证输入参数
4. 如需长时间操作，使用 `defer(thinking=True)`
5. 调用现有服务实例 (不要创建新实例)
6. 处理错误并格式化输出

### 添加新指标

1. 在 `IndicatorService.calculate_all()` 中使用 `ta` 库计算指标
2. 使用 `_safe_last()` 获取最新值
3. 添加到返回字典中
4. 在 `format_summary()` 中添加格式化显示
5. 更新 `ai_analyzer.py` 中的 Prompt (如需 AI 分析)

### 支持新的 AI 模型

1. 在 `config.py` 的 `VALID_MODELS` 中添加新模型
2. 在 `ai_analyzer.py` 中扩展 `AIAnalyzer` 类
3. 更新配置加载逻辑
4. 测试新模型的 API 响应格式

## Troubleshooting

### Bot 无法启动

- 检查 `DISCORD_BOT_TOKEN` 是否正确
- 检查端口是否被占用
- 检查网络连接

### 无法获取 Binance 数据

- 检查 `BINANCE_API_KEY` 和 `BINANCE_API_SECRET`
- 检查 API Key 是否有读取权限
- 检查网络连接和代理设置

### AI 分析失败

- 检查 `MOONSHOT_API_KEY` 是否正确
- 检查 API 余额是否充足
- 检查网络连接

### 命令不显示

- 检查 Bot 是否正确启动
- 检查 `setup_hook()` 是否被调用
- 检查 Discord 权限设置
