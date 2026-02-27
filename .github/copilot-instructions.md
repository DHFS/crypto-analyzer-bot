# AI Coding Agent Instructions - Crypto Analyzer Bot

## Project Overview
A Discord bot that analyzes cryptocurrency prices and technical indicators from Binance, using AI (Moonshot/Kimi) to generate trading recommendations.

## Architecture & Data Flow

### Core Pipeline
1. **Discord Command** → handler in `handlers/commands.py` 
2. **Data Fetching** → `BinanceService` (futures market data)
3. **Analysis** → `IndicatorService` (technical indicators) + `AIAnalyzer` (AI synthesis)
4. **Output** → Discord message (chunked for >2000 char limit)

### Services
- **BinanceService** (`services/binance.py`): Fetches K-line candles and ticker data using `python-binance` client
- **IndicatorService** (`services/indicators.py`): Calculates MA, EMA, MACD, RSI, Bollinger Bands, ATR using `ta` library
- **AIAnalyzer** (`services/ai_analyzer.py`): Calls Moonshot API with structured JSON prompt to generate analysis

### Service Instantiation Pattern
Services are instantiated **once at module level** in `handlers/commands.py`:
```python
binance_service = BinanceService()
indicator_service = IndicatorService()
ai_analyzer = AIAnalyzer()
```
Reuse these instances in all command handlers—do NOT create new instances.

## Key Conventions & Patterns

### Configuration & Secrets
- All config stored in `config.py` as `Config` class attributes
- Loaded from `.env` via `python-dotenv`
- Proxy support: Set in config, applied to both Binance client and Discord bot
- Valid timeframes hardcoded: `VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]`

### Discord Interactions
- Use **slash commands** (`@tree.command`) not message-based
- Always call `interaction.response.defer(thinking=True)` for long operations (>3s)
- Use `interaction.followup.send()` after defer
- Error messages end with emoji context: `❌ error`, `✅ success`, `🚀 status`
- Long responses (>2000 chars): chunk and use `interaction.channel.send()` for additional chunks

### Data Processing
- **Binance data**: Returns K-lines as pandas DataFrame with columns: `timestamp, open, high, low, close, volume`
- **Indicators**: Return dict with structure `{"ma": {"ma5": ..., "ma10": ...}, "macd": {...}, ...}`
- **Symbol format**: Normalize with `.upper()` and `.replace("/", "")` → `ETHUSDT`
- **Timestamp handling**: Binance returns milliseconds; pandas `to_datetime(..., unit="ms")`

### AI Analysis
- Prompt template in `ai_analyzer.py` uses `{symbol}`, `{timeframe}` placeholders
- Indicators serialized to JSON using `json.dumps(..., ensure_ascii=False, default=str)`
- Always include both `current_price` (from indicators) and ticker 24h stats in prompt
- Response wrapped with header: `🤖 Kimi 分析报告\n{'━' * 20}\n\n{result}`

### Error Handling
- All service calls wrapped in **try-except**, catch broad `Exception`
- User-friendly error messages: `"❌ 错误: {str(e)}"`
- Binance errors: `BinanceAPIException` with `.message` attribute
- API errors from AI service: caught and prefixed with context

## Common Tasks

### Adding New Command
1. Add `@tree.command` decorator with proper `@app_commands.describe()` for each param
2. Validate inputs (e.g., `if timeframe not in config.VALID_TIMEFRAMES`)
3. Use `defer(thinking=True)` if fetching data
4. Call service instances (don't instantiate new ones)
5. Handle errors and chunk responses >2000 chars

### Adding New Indicator
1. Calculate in `IndicatorService.calculate_all()` using `ta` library
2. Extract last value with `self._safe_last()` helper
3. Add to return dict with proper nesting (e.g., `"ma": {...}`)
4. Update `format_summary()` to display the new indicator

### Supporting New Exchange/AI Model
- **Exchange**: Extend `BinanceService` or create new `ExchangeService` following same interface
- **AI Model**: Extend `AIAnalyzer` class or update config `VALID_MODELS`; update prompt template accordingly

## Development Workflow
- **Running locally**: `pip install -r requirements.txt` → set `.env` → `python main.py`
- **Debugging**: Check logs (formatted as `%(asctime)s %(levelname)s %(message)s`)
- **Proxy testing**: Set `HTTP_PROXY` in `.env` to test with proxy

## Code Style Notes
- Comments in **Chinese** throughout codebase
- Type hints minimal (duck typing)—follow existing patterns
- Async/await required for Discord interactions and API calls
- No response body validation; assume API returns expected structure
