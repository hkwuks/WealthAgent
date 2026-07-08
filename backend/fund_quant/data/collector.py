"""FundQuant 数据采集器 - AkShare/东方财富接口封装"""

import asyncio
import time
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict
from loguru import logger

from ..core.errors import DataCollectionError
from ..core.models import NavPoint, FundHolding, HoldingItem, FundMeta
from ..core.config import fund_quant_settings


class FundDataCollector:
    """基金数据采集器"""

    def __init__(self):
        self._session = None
        self._rate_limit = fund_quant_settings.COLLECTION_RATE_LIMIT
        self._last_request_time = 0.0

    async def _rate_limit_wait(self):
        """速率限制"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)
        self._last_request_time = time.time()

    # ── 历史净值采集 ──

    async def fetch_nav_history(self, fund_code: str,
                                 start_date: Optional[str] = None,
                                 end_date: Optional[str] = None) -> List[NavPoint]:
        """采集基金历史净值"""
        await self._rate_limit_wait()
        try:
            import akshare as ak
            fund_etf_hist = ak.fund_etf_hist_em(
                symbol=fund_code,
                start_date=start_date or "20000101",
                end_date=end_date or date.today().strftime("%Y%m%d"),
                adjust="",
            )
            points = []
            for _, row in fund_etf_hist.iterrows():
                try:
                    d = row["净值日期"] if "净值日期" in fund_etf_hist.columns else row["日期"]
                    if isinstance(d, str):
                        d = datetime.strptime(d, "%Y-%m-%d").date()
                    nav_date = d
                except (ValueError, KeyError):
                    continue
                points.append(NavPoint(
                    fund_code=fund_code,
                    date=nav_date,
                    nav=float(row.get("单位净值", 0)),
                    adjusted_nav=float(row.get("累计净值", 0)) if "累计净值" in row else None,
                    source="eastmoney",
                ))
            return points
        except ImportError:
            raise DataCollectionError("akshare not installed", fund_code)
        except Exception as e:
            raise DataCollectionError(str(e), fund_code)

    async def fetch_valuation_history(self, fund_code: str,
                                       start_date: Optional[str] = None,
                                       end_date: Optional[str] = None) -> List[dict]:
        """采集估值历史数据"""
        await self._rate_limit_wait()
        try:
            import akshare as ak
            df = ak.fund_etf_hist_em(
                symbol=fund_code,
                start_date=start_date or "20000101",
                end_date=end_date or date.today().strftime("%Y%m%d"),
                adjust="qfq",
            )
            results = []
            for _, row in df.iterrows():
                try:
                    d = row.get("净值日期") or row.get("日期", "")
                    if isinstance(d, str):
                        d = datetime.strptime(d, "%Y-%m-%d").date()
                except (ValueError, KeyError):
                    continue
                results.append({
                    "fund_code": fund_code,
                    "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "estimated_nav": float(row.get("估算值", 0)) if "估算值" in row else None,
                    "actual_nav": float(row.get("单位净值", 0)),
                    "deviation_pct": float(row.get("偏差", 0)) if "偏差" in row else None,
                })
            return results
        except ImportError:
            raise DataCollectionError("akshare not installed", fund_code)
        except Exception as e:
            raise DataCollectionError(str(e), fund_code)

    # ── 持仓数据采集 ──

    async def fetch_holdings(self, fund_code: str) -> List[FundHolding]:
        """采集基金持仓数据"""
        await self._rate_limit_wait()
        try:
            import akshare as ak
            df = ak.fund_portfolio_hold_em(symbol=fund_code, date="")
            if df is None or df.empty:
                return []

            results = []
            for period_str in df["报告期"].unique() if "报告期" in df.columns else []:
                period_df = df[df["报告期"] == period_str]
                try:
                    report_period = datetime.strptime(period_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                items = []
                for _, row in period_df.iterrows():
                    items.append(HoldingItem(
                        asset_code=str(row.get("股票代码", "")),
                        asset_name=str(row.get("股票名称", "")),
                        weight=float(row.get("占净值比例", 0)) / 100.0,
                        market_value=float(row.get("持仓市值", 0)) if "持仓市值" in row else None,
                    ))

                # 披露日期：报告期后约20天
                publish_date = report_period + timedelta(days=20)
                results.append(FundHolding(
                    fund_code=fund_code,
                    report_period=report_period,
                    publish_date=publish_date,
                    holdings=items,
                ))
            return results
        except ImportError:
            raise DataCollectionError("akshare not installed", fund_code)
        except Exception as e:
            raise DataCollectionError(str(e), fund_code)

    # ── 基金元数据采集 ──

    async def fetch_fund_meta(self, fund_code: str) -> Optional[FundMeta]:
        """采集基金元数据"""
        await self._rate_limit_wait()
        try:
            import akshare as ak
            info = ak.fund_info_em(symbol=fund_code)
            if info is None or info.empty:
                return None

            meta = FundMeta(fund_code=fund_code)
            info_dict = info.set_index("item")["value"].to_dict() if "item" in info.columns else {}

            meta.fund_name = info_dict.get("基金简称", "")
            meta.fund_type = self._classify_fund_type(info_dict.get("基金类型", ""))

            fee_str = info_dict.get("管理费率", "0")
            try:
                meta.management_fee = float(fee_str.replace("%", "")) / 100.0 if "%" in fee_str else float(fee_str)
            except ValueError:
                pass

            fee_str = info_dict.get("托管费率", "0")
            try:
                meta.custody_fee = float(fee_str.replace("%", "")) / 100.0 if "%" in fee_str else float(fee_str)
            except ValueError:
                pass

            meta.established_date = None
            estab_str = info_dict.get("成立日期", "")
            if estab_str:
                try:
                    meta.established_date = datetime.strptime(estab_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

            return meta
        except ImportError:
            raise DataCollectionError("akshare not installed", fund_code)
        except Exception as e:
            raise DataCollectionError(str(e), fund_code)

    @staticmethod
    def _classify_fund_type(raw_type: str) -> str:
        """将原始基金类型映射为标准类型"""
        mapping = {
            "股票": "stock",
            "混合": "hybrid",
            "债券": "bond",
            "货币": "money",
            "指数": "index",
            "ETF": "etf",
            "联接": "etf_link",
            "QDII": "qdii",
            "FOF": "fof",
        }
        for key, value in mapping.items():
            if key in raw_type:
                return value
        return "hybrid"

    # ── 汇率数据采集 ──

    async def fetch_fx_rates(self) -> Dict[str, float]:
        """采集主要汇率数据"""
        await self._rate_limit_wait()
        try:
            import akshare as ak
            df = ak.currency_boc_sina(symbol="美元人民币")
            rates = {"USD/CNY": float(df["买入价"].iloc[0]) if not df.empty else 7.0}
            return rates
        except Exception:
            logger.warning("汇率数据获取失败，返回默认值")
            return {"USD/CNY": 7.0}

    # ── 国债收益率采集 ──

    async def fetch_yield_10y(self) -> Optional[float]:
        """采集10年期国债收益率"""
        await self._rate_limit_wait()
        try:
            import akshare as ak
            df = ak.bond_china_yield(start_date="20200101")
            if df is not None and not df.empty and "10年" in df.columns:
                return float(df["10年"].iloc[-1]) / 100.0
            return None
        except Exception:
            logger.warning("国债收益率获取失败")
            return None


# 全局单例
fund_data_collector = FundDataCollector()
