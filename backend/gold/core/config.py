from pydantic_settings import BaseSettings


class GoldSettings(BaseSettings):
    """黄金量化系统配置"""

    # 数据目录
    gold_data_dir: str = "data/gold"
    gold_db_path: str = "data/gold/gold.db"

    # SHFE AU合约参数
    au_multiplier: int = 1000       # 合约乘数：1000克/手
    au_margin_rate: float = 0.08    # 保证金率：8%
    au_price_tick: float = 0.02     # 最小变动价位：0.02元/克
    au_limit_pct: float = 0.05      # 涨跌停板：±5%

    # 回测默认参数（统一为元/手）
    backtest_capital: float = 1_000_000
    backtest_commission_per_lot: float = 10.0        # 开仓手续费：10元/手
    backtest_close_commission_per_lot: float = 0.0   # 平今手续费：0元/手（SHFE AU平今免费）
    backtest_slippage_per_lot: float = 20.0          # 滑点：1跳=0.02元/克×1000=20元/手
    risk_free_rate: float = 0.025

    # 风控参数
    max_drawdown_pct: float = 0.10
    max_daily_loss_pct: float = 0.03
    max_daily_signals: int = 20

    # AkShare数据
    akshare_symbol: str = "AU0"

    class Config:
        env_prefix = "GOLD_"


gold_settings = GoldSettings()
