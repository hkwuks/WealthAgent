"""
交易适配器工厂 — 根据 trading_mode 创建对应的适配器

支持模式:
  simnow  - SimNow 官方仿真（CTP API）
  openctp - openctp TTS 仿真（CTP API，地址不同）
"""
from backend.gold.trading.connectors.base import TradingAdapter


_MODE_LABELS = {
    "simnow": "SimNow",
    "openctp": "openctp TTS",
}


def list_modes() -> list[dict]:
    """返回所有可用交易模式"""
    return [
        {"id": k, "name": v, "current": False}
        for k, v in _MODE_LABELS.items()
    ]


def create_adapter(mode: str = None, **kwargs) -> TradingAdapter:
    """
    创建交易适配器

    Args:
        mode: "simnow" / "openctp"
        **kwargs: 传递给具体适配器的参数

    Returns:
        TradingAdapter 实例
    """
    if mode is None:
        from backend.gold.core.config import gold_settings
        mode = (gold_settings.trading_mode or "simnow").lower()

    if mode in ("simnow", "openctp"):
        from backend.gold.trading.connectors.ctp_adapter import CtpAdapter
        from backend.gold.trading.connectors.ctp_config import CtpConfig
        cfg = CtpConfig(mode=mode)
        return CtpAdapter(cfg, name=mode)

    else:
        raise ValueError(f"未知交易模式: {mode}，支持: simnow, openctp")
