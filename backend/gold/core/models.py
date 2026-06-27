from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class RiskLevel(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    REJECT = "reject"


# ===== 行情数据 =====

class GoldBarData(BaseModel):
    """K线数据"""
    symbol: str
    exchange: str = "SHFE"
    period: str = "1m"
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    turnover: float = 0
    open_interest: float = 0


class GoldTickData(BaseModel):
    """Tick数据 — V2用，V1预留"""
    symbol: str
    exchange: str = "SHFE"
    datetime: datetime
    last_price: float
    last_volume: float = 0
    open_interest: float = 0


# ===== 交易信号 =====

class GoldSignal(BaseModel):
    """交易信号/建议"""
    signal_id: str
    strategy_id: str
    strategy_name: str
    symbol: str
    direction: SignalDirection
    price: float
    volume: int = 1
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 0.0
    reason: Optional[str] = None
    created_at: Optional[datetime] = None


class OrderStatus(str, Enum):
    PENDING = "pending"          # 待风控
    ACCEPTED = "accepted"        # 风控通过，待成交
    REJECTED = "rejected"        # 风控拒绝
    PARTIAL = "partial"          # 部分成交
    FILLED = "filled"            # 全部成交
    CANCELLED = "cancelled"      # 已撤销


class GoldOrder(BaseModel):
    """订单 — 风控→路由→成交 链路中间态"""
    order_id: str
    signal_id: str
    strategy_id: str
    strategy_name: str
    symbol: str
    direction: SignalDirection
    price: float
    volume: int
    filled_volume: int = 0
    status: OrderStatus = OrderStatus.PENDING
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: Optional[str] = None
    risk_check: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class GoldTrade(BaseModel):
    """成交记录"""
    trade_id: str
    order_id: str
    symbol: str
    direction: SignalDirection
    price: float
    volume: int
    commission: float = 0
    slippage: float = 0
    trade_time: datetime


# ===== 风控 =====

class RiskCheckResult(BaseModel):
    """风控检查结果"""
    passed: bool
    risk_level: RiskLevel = RiskLevel.PASS
    check_name: str = ""
    reason: str = ""
    details: dict = {}


# ===== API 响应模型 =====

class MarketDataResponse(BaseModel):
    """市场数据仪表盘响应"""
    symbol: str = "AU0"
    price: float
    change: float = 0
    change_pct: float = 0
    open: float = 0
    high: float = 0
    low: float = 0
    volume: float = 0
    high_20: float = 0
    low_20: float = 0
    rsi_14: Optional[float] = None
    atr_14: Optional[float] = None
    vol_ratio: float = 1.0
    dxy: Optional[float] = None
    vix: Optional[float] = None
    us10y: Optional[float] = None
    tips: Optional[float] = None
    breakeven: Optional[float] = None
    date: str = ""
    timestamp: str = ""


class BacktestResponse(BaseModel):
    """回测结果响应"""
    strategy: str
    signal_count: int = 0
    trade_count: int = 0
    report: dict = {}
    signals: list = []
    trades: list = []


class SignalResponse(BaseModel):
    """交易信号响应"""
    signal_id: str
    order_id: str = ""
    order_status: str = ""
    strategy: str
    symbol: str
    direction: str
    price: float
    volume: int = 1
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 0.0
    reason: Optional[str] = None
    risk_check: dict = {}
    timestamp: Optional[str] = None


# ===== 持仓（回测用） =====

class GoldPosition(BaseModel):
    """持仓 — 回测虚拟持仓"""
    symbol: str
    direction: str
    volume: int = 0
    avg_price: float = 0
    unrealized_pnl: float = 0
    margin: float = 0


# ===== 回测请求 =====

class BacktestRequest(BaseModel):
    """回测请求"""
    strategy_name: str
    symbol: str = "AU0"
    period: str = "d"
    start_date: str = "2020-01-01"
    end_date: str = "2025-12-31"
    capital: float = 1_000_000
    params: Optional[dict] = None


class StrategyComparisonRequest(BaseModel):
    """多策略对比请求"""
    strategy_names: list[str]
    symbol: str = "AU0"
    period: str = "d"
    start_date: str = "2020-01-01"
    end_date: str = "2025-12-31"
    capital: float = 1_000_000


# ===== 策略信息 =====

class StrategyInfo(BaseModel):
    """策略描述"""
    strategy_id: str
    strategy_name: str
    strategy_type: str
    description: str
    default_params: dict
    param_ranges: dict
