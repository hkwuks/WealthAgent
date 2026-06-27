from typing import Optional
from pydantic_settings import BaseSettings


class GoldSettings(BaseSettings):
    """黄金量化系统配置"""

    # 数据目录
    gold_data_dir: str = "data/backend/gold"
    gold_db_path: str = "data/backend/gold/gold.db"

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
    max_position_lots: int = 10        # 单品种最大持仓手数
    max_margin_ratio: float = 0.30     # 保证金占比上限
    max_consecutive_losses: int = 3    # 连续亏损熔断次数

    # AkShare数据
    akshare_symbol: str = "AU0"

    # CTP/SimNow 连接配置
    ctp_enabled: bool = False
    ctp_broker_id: str = "9999"
    ctp_user_id: str = ""
    ctp_password: str = ""
    ctp_md_address: str = "tcp://182.254.243.31:40011"   # 7×24 行情前置
    ctp_td_address: str = "tcp://182.254.243.31:40001"   # 7×24 交易前置
    ctp_app_id: str = "simnow_client_test"
    ctp_auth_code: str = "0000000000000000"
    ctp_symbols: str = ""                                 # 订阅合约列表（逗号分隔），留空自动按季度生成后续合约
    ctp_main_symbol: str = "AU0"                          # 前端显示用的主连代码（仅展示）

    class Config:
        env_prefix = "GOLD_"


gold_settings = GoldSettings()
