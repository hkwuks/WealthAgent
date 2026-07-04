"""
CTP 连接配置 — 支持 SimNow 和 openctp TTS 双环境

主力合约自动发现:
  ctp_symbols 为空时自动按当前日期生成后续季度合约，
  客户端通过持仓量识别主力合约。
"""
from datetime import datetime
from backend.gold.core.config import gold_settings


# 各环境特性标识
_ENV_INFO = {
    "simnow": {
        "name": "SimNow",
        "broker_id": "9999",
        "app_id": "simnow_client_test",
        "auth_code": "0000000000000000",
        "needs_auth": True,
    },
    "openctp": {
        "name": "openctp TTS",
        "broker_id": "9999",
        "app_id": "",
        "auth_code": "",
        "needs_auth": False,
    },
}


def _generate_au_contracts(count: int = 6) -> list[str]:
    """
    按当前日期自动生成 AU 季度合约代码
    """
    now = datetime.now()
    year = now.year
    month = now.month

    quarter_months = [2, 4, 6, 8, 10, 12]
    start_idx = 0
    for i, m in enumerate(quarter_months):
        if month >= m:
            start_idx = i

    contracts = []
    y = year
    idx = start_idx
    for _ in range(count):
        if idx >= len(quarter_months):
            idx = 0
            y += 1
        if quarter_months[idx] <= month and y == year:
            idx += 1
            continue
        # CTP 合约代码大写
        ym = f"AU{y % 100:02d}{quarter_months[idx]:02d}"
        contracts.append(ym)
        idx += 1

    return contracts if contracts else [f"AU{year % 100:02d}{quarter_months[-1]:02d}"]


class CtpConfig:
    """CTP 连接参数 — 根据 trading_mode 自动选择对应环境"""

    def __init__(self, mode: str = None):
        s = gold_settings
        self.mode = (mode or s.trading_mode or "simnow").lower()

        # 基础参数（所有环境通用）
        self.enabled: bool = s.ctp_enabled
        self.symbols: list[str] = self._parse_symbols(s.ctp_symbols)

        # 按模式读取对应环境的配置
        if self.mode == "simnow":
            self.user_id: str = s.simnow_user_id
            self.password: str = s.simnow_password
            self.md_address: str = s.simnow_md_address
            self.td_address: str = s.simnow_td_address
        elif self.mode == "openctp":
            self.user_id: str = s.openctp_user_id
            self.password: str = s.openctp_password
            self.md_address: str = s.openctp_md_address
            self.td_address: str = s.openctp_td_address
        else:
            self.user_id = self.password = ""
            self.md_address = self.td_address = ""

        # 环境认证参数（来自 _ENV_INFO）
        env = _ENV_INFO.get(self.mode, _ENV_INFO["simnow"])
        self.broker_id: str = env["broker_id"]
        self.app_id: str = env["app_id"]
        self.auth_code: str = env["auth_code"]
        self.needs_auth: bool = env["needs_auth"]

    def _parse_symbols(self, raw: str) -> list[str]:
        if raw and raw.strip():
            return [x.strip() for x in raw.split(",") if x.strip()]
        return _generate_au_contracts(6)

    def is_valid(self) -> tuple[bool, str]:
        """检查配置是否可连接"""
        if not self.enabled:
            return False, "模拟交易未启用 (GOLD_CTP_ENABLED=false)"
        if not self.user_id:
            return False, f"{self.mode} 用户名未配置"
        if not self.password:
            return False, f"{self.mode} 密码未配置"
        if not self.md_address:
            return False, "行情地址未配置"
        if not self.td_address:
            return False, "交易地址未配置"
        if not self.symbols:
            return False, "订阅合约未配置"
        return True, "ok"

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "broker_id": self.broker_id,
            "user_id": self.user_id[:3] + "***" if self.user_id else "",
            "symbols": self.symbols,
            "md_address": self.md_address,
            "td_address": self.td_address,
        }

    @staticmethod
    def available_modes() -> list[dict]:
        """返回所有可用环境的描述"""
        return [
            {
                "id": "simnow",
                "name": "SimNow",
                "description": "上期技术官方仿真平台，需注册账号，7×24环境",
            },
            {
                "id": "openctp",
                "name": "openctp TTS",
                "description": "CTP开放平台仿真环境，扫码即用，无需认证，7×24稳定",
            },
        ]
