"""模拟组合跟踪"""

from datetime import datetime, date
from typing import Optional, Dict, List
from ..core.models import Portfolio


class PortfolioTracker:
    """模拟组合跟踪器"""

    def __init__(self, initial_capital: float = 100000.0):
        self._portfolio = Portfolio(total_value=initial_capital, cash=initial_capital)
        self._history: List[dict] = []
        self._initial_capital = initial_capital

    def update(self, fund_code: str, shares: float, nav: float):
        """更新持仓"""
        self._portfolio.nav_values[fund_code] = nav
        current_value = sum(
            self._portfolio.nav_values.get(code, 0) * shares
            for code, shares in self._portfolio.positions.items()
        ) + self._portfolio.cash
        self._portfolio.total_value = current_value

    def buy(self, fund_code: str, amount: float, nav: float):
        """买入操作"""
        if amount > self._portfolio.cash:
            amount = self._portfolio.cash
        shares = amount / nav if nav > 0 else 0
        self._portfolio.positions[fund_code] = self._portfolio.positions.get(fund_code, 0) + shares
        self._portfolio.cash -= amount
        self._portfolio.nav_values[fund_code] = nav
        self._portfolio.total_value = sum(
            self._portfolio.nav_values.get(c, 0) * s
            for c, s in self._portfolio.positions.items()
        ) + self._portfolio.cash
        self._snapshot(f"买入 {fund_code} 金额 {amount:.2f}")

    def sell(self, fund_code: str, pct: float, nav: float):
        """卖出操作"""
        shares = self._portfolio.positions.get(fund_code, 0)
        sell_shares = shares * pct
        amount = sell_shares * nav
        self._portfolio.positions[fund_code] = shares - sell_shares
        self._portfolio.cash += amount
        self._portfolio.nav_values[fund_code] = nav
        self._portfolio.total_value = sum(
            self._portfolio.nav_values.get(c, 0) * s
            for c, s in self._portfolio.positions.items()
        ) + self._portfolio.cash
        self._snapshot(f"卖出 {fund_code} 比例 {pct:.1%}")

    def _snapshot(self, action: str = ""):
        self._history.append({
            "timestamp": datetime.now().isoformat(),
            "total_value": self._portfolio.total_value,
            "cash": self._portfolio.cash,
            "positions": dict(self._portfolio.positions),
            "action": action,
        })

    def get_status(self) -> dict:
        """获取当前组合状态"""
        return {
            "initial_capital": self._initial_capital,
            "total_value": self._portfolio.total_value,
            "cash": self._portfolio.cash,
            "return_pct": ((self._portfolio.total_value - self._initial_capital) / self._initial_capital * 100) if self._initial_capital > 0 else 0,
            "position_count": len(self._portfolio.positions),
            "positions": {
                code: {
                    "shares": shares,
                    "nav": self._portfolio.nav_values.get(code, 0),
                    "value": shares * self._portfolio.nav_values.get(code, 0),
                }
                for code, shares in self._portfolio.positions.items()
            },
            "history_count": len(self._history),
        }


portfolio_tracker = PortfolioTracker()
