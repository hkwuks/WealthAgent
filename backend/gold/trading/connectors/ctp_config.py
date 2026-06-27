"""
CTP 连接配置 — 从 GoldSettings 读取并校验

主力合约自动发现:
  ctp_symbols 为空时自动按当前日期生成后续季度合约，
  客户端通过持仓量识别主力合约。
"""
from datetime import datetime
from backend.gold.core.config import gold_settings


def _generate_au_contracts(count: int = 6) -> list[str]:
    """
    按当前日期自动生成 AU 季度合约代码

    SHFE 黄金期货交割月: 2,4,6,8,10,12 (偶数月)
    生成从下个季度月开始的 count 个合约。
    """
    now = datetime.now()
    year = now.year
    month = now.month

    # 最近的季度月
    quarter_months = [2, 4, 6, 8, 10, 12]
    start_idx = 0
    for i, m in enumerate(quarter_months):
        if month >= m:
            start_idx = i
    # 从下个季度月开始
    contracts = []
    y = year
    idx = start_idx
    for _ in range(count):
        if idx >= len(quarter_months):
            idx = 0
            y += 1
        # 跳过当月（当月合约即将到期）
        if quarter_months[idx] <= month and y == year:
            idx += 1
            continue
        ym = f"au{y % 100:02d}{quarter_months[idx]:02d}"
        contracts.append(ym)
        idx += 1

    return contracts if contracts else [f"au{year % 100:02d}{quarter_months[-1]:02d}"]


class CtpConfig:
    """CTP 连接参数"""

    def __init__(self):
        s = gold_settings
        self.enabled: bool = s.ctp_enabled
        self.broker_id: str = s.ctp_broker_id
        self.user_id: str = s.ctp_user_id
        self.password: str = s.ctp_password
        self.md_address: str = s.ctp_md_address
        self.td_address: str = s.ctp_td_address
        self.app_id: str = s.ctp_app_id
        self.auth_code: str = s.ctp_auth_code

        raw = s.ctp_symbols.strip()
        if raw:
            self.symbols = [x.strip() for x in raw.split(",") if x.strip()]
        else:
            # 自动生成
            self.symbols = _generate_au_contracts(6)

    def is_valid(self) -> tuple[bool, str]:
        """检查配置是否可连接"""
        if not self.enabled:
            return False, "CTP 未启用 (GOLD_CTP_ENABLED=false)"
        if not self.user_id:
            return False, "CTP 用户名未配置 (GOLD_CTP_USER_ID)"
        if not self.password:
            return False, "CTP 密码未配置 (GOLD_CTP_PASSWORD)"
        if not self.md_address:
            return False, "CTP 行情地址未配置 (GOLD_CTP_MD_ADDRESS)"
        if not self.td_address:
            return False, "CTP 交易地址未配置 (GOLD_CTP_TD_ADDRESS)"
        if not self.symbols:
            return False, "CTP 订阅合约未配置 (GOLD_CTP_SYMBOLS)"
        return True, "ok"

    def to_dict(self) -> dict:
        return {
            "broker_id": self.broker_id,
            "user_id": self.user_id[:3] + "***" if self.user_id else "",
            "symbols": self.symbols,
            "md_address": self.md_address,
            "td_address": self.td_address,
        }
