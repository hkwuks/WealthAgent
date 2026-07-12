"""分红处理 — 红利再投 + 现金分红 + 非复权净值路径"""

from typing import Optional


class DividendHandler:
    """分红处理器"""

    def __init__(self, dividend_tax_under_1y: float = 0.10,
                 dividend_tax_over_1y: float = 0.0):
        self.tax_short = dividend_tax_under_1y
        self.tax_long = dividend_tax_over_1y

    def _tax_rate(self, holding_days: int) -> float:
        return self.tax_long if holding_days >= 365 else self.tax_short

    def process_dividend(self, nav: float, dividend_per_share: float,
                         shares: float, holding_days: int) -> dict:
        """处理分红（基础版）"""
        tax_rate = self._tax_rate(holding_days)
        dividend_amount = dividend_per_share * shares
        tax = dividend_amount * tax_rate
        net_dividend = dividend_amount - tax

        # 红利再投: 按除权后净值增持
        ex_dividend_nav = nav - dividend_per_share
        reinvested_shares = 0.0
        if ex_dividend_nav > 0:
            reinvested_shares = net_dividend / ex_dividend_nav

        return {
            "dividend_per_share": dividend_per_share,
            "shares": shares,
            "gross_amount": round(dividend_amount, 4),
            "tax": round(tax, 4),
            "tax_rate": tax_rate,
            "net_amount": round(net_dividend, 4),
            "reinvested_shares": round(reinvested_shares, 4),
            "ex_dividend_nav": round(ex_dividend_nav, 4),
        }

    def reinvest(self, dividend_result: dict,
                 current_shares: float) -> float:
        """红利再投，返回增持后的总份额"""
        return current_shares + dividend_result.get("reinvested_shares", 0.0)

    def cash_dividend(self, dividend_result: dict) -> float:
        """现金分红，返回税后现金金额"""
        return dividend_result.get("net_amount", 0.0)

    def ex_dividend_nav_series(self, nav_series: list,
                                dividend_dates: dict) -> list:
        """将复权净值转为非复权 + 分红再投路径

        Args:
            nav_series: 原始净值序列 [{date, nav}, ...]
            dividend_dates: {date: dividend_per_share}

        Returns:
            含adjusted_nav的[{date, nav, adjusted_nav}, ...]
        """
        result = []
        cumulative_dividend = 0.0
        for point in nav_series:
            d = point["date"]
            nav = point["nav"]
            div = dividend_dates.get(d, 0.0)
            if div > 0:
                cumulative_dividend += div
                ex_nav = nav - div
                result.append({"date": d, "nav": nav,
                               "adjusted_nav": round(ex_nav, 4),
                               "dividend": div,
                               "cumulative_dividend": round(cumulative_dividend, 4)})
            else:
                result.append({"date": d, "nav": nav,
                               "adjusted_nav": nav})
        return result


dividend_handler = DividendHandler()
