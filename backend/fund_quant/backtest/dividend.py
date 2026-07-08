"""分红处理（V1简化版）"""

from typing import Optional


class DividendHandler:
    """分红处理器"""

    def process_dividend(self, nav: float, dividend_per_share: float,
                         shares: float, holding_days: int) -> dict:
        """处理分红"""
        tax_rate = 0.0 if holding_days >= 365 else 0.10
        dividend_amount = dividend_per_share * shares
        tax = dividend_amount * tax_rate
        net_dividend = dividend_amount - tax

        return {
            "dividend_per_share": dividend_per_share,
            "shares": shares,
            "gross_amount": dividend_amount,
            "tax": tax,
            "tax_rate": tax_rate,
            "net_amount": net_dividend,
            "reinvested_shares": 0.0,  # V2: 红利再投
        }


dividend_handler = DividendHandler()
