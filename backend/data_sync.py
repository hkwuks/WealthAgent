"""
数据同步模块

从外部数据源获取历史数据并存储到本地数据库
支持：
1. 黄金价格历史数据
2. 美元指数、利率等宏观指标
3. 股票、基金、指数历史数据
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import yfinance as yf
import akshare as ak
import pandas as pd
from loguru import logger

from backend.data_store import data_store, StorageType
from backend.config import settings

logger.add("./logs/data_sync.log", encoding="utf-8", rotation="10 MB")


class DataSyncManager:
    """数据同步管理器"""

    # 黄金相关代码映射
    GOLD_SYMBOLS = {
        'GC': {'yf': 'GC=F', 'name': 'COMEX黄金', 'source': 'yfinance'},
        'XAU': {'yf': 'XAUUSD=X', 'name': '现货黄金', 'source': 'yfinance'},
        'SH_GOLD': {'ak': 'AU0', 'name': '上海黄金', 'source': 'akshare'},
    }

    # 宏观指标代码映射
    MACRO_SYMBOLS = {
        'DXY': {'yf': 'DX-Y.NYB', 'name': '美元指数', 'source': 'yfinance'},
        'VIX': {'yf': '^VIX', 'name': '恐慌指数', 'source': 'yfinance'},
        'US10Y': {'yf': '^TNX', 'name': '美国10年期国债', 'source': 'yfinance'},
        'US2Y': {'yf': '^IRX', 'name': '美国2年期国债', 'source': 'yfinance'},
        'SP500': {'yf': '^GSPC', 'name': '标普500', 'source': 'yfinance'},
        'NASDAQ': {'yf': '^IXIC', 'name': '纳斯达克', 'source': 'yfinance'},
    }

    # FRED数据系列
    FRED_SERIES = {
        'TIPS': {'series_id': 'DFII10', 'name': '10Y TIPS实际利率', 'source': 'fred'},
        'BREAKEVEN': {'series_id': 'T10YIE', 'name': '10Y通胀预期', 'source': 'fred'},
    }

    def __init__(self):
        self.data_store = data_store

    # ==================== 黄金数据同步 ====================

    def sync_gold_history(self, symbol: str = 'GC', period: str = "5y") -> Tuple[bool, int]:
        """
        同步黄金历史数据

        Args:
            symbol: 黄金代码，GC=COMEX黄金, XAU=现货黄金
            period: 时间周期，1y, 5y, 10y, max

        Returns:
            (是否成功, 记录数)
        """
        try:
            config = self.GOLD_SYMBOLS.get(symbol, self.GOLD_SYMBOLS['GC'])

            if config['source'] == 'yfinance':
                df = self._fetch_yfinance_history(config['yf'], period)
            else:
                df = self._fetch_akshare_gold(period)

            if df.empty:
                logger.warning(f"No data fetched for {symbol}")
                return False, 0

            # 转换为存储格式
            records = self._convert_price_records(df, symbol, 'gold')

            # 保存到长期存储
            success, count = self.data_store.save_price_history(
                asset_code=symbol,
                asset_type='gold',
                data=records,
                source=config['source']
            )

            logger.info(f"Synced {count} gold records for {symbol}")
            return success, count

        except Exception as e:
            logger.error(f"Failed to sync gold history for {symbol}: {e}")
            return False, 0

    def sync_all_gold_data(self, years: int = 5) -> Dict[str, Tuple[bool, int]]:
        """同步所有黄金数据源"""
        results = {}
        period = f"{years}y"

        for symbol in self.GOLD_SYMBOLS.keys():
            results[symbol] = self.sync_gold_history(symbol, period)

        return results

    # ==================== 宏观指标同步 ====================

    def sync_macro_history(self, indicator: str, period: str = "5y") -> Tuple[bool, int]:
        """
        同步宏观指标历史数据

        Args:
            indicator: 指标代码，如 DXY, VIX, US10Y
            period: 时间周期

        Returns:
            (是否成功, 记录数)
        """
        try:
            config = self.MACRO_SYMBOLS.get(indicator)
            if not config:
                logger.error(f"Unknown macro indicator: {indicator}")
                return False, 0

            if config['source'] == 'yfinance':
                df = self._fetch_yfinance_history(config['yf'], period)
            else:
                return False, 0

            if df.empty:
                logger.warning(f"No data fetched for {indicator}")
                return False, 0

            # 转换为宏观指标存储格式
            records = []
            for _, row in df.iterrows():
                records.append({
                    'date': row['date'],
                    'indicator_name': config['name'],
                    'value': row['close'],
                    'change_percent': row.get('change_percent')
                })

            success, count = self.data_store.save_macro_history(
                indicator_code=indicator,
                data=records,
                source=config['source']
            )

            logger.info(f"Synced {count} macro records for {indicator}")
            return success, count

        except Exception as e:
            logger.error(f"Failed to sync macro history for {indicator}: {e}")
            return False, 0

    def sync_all_macro_data(self, years: int = 5) -> Dict[str, Tuple[bool, int]]:
        """同步所有宏观指标"""
        results = {}
        period = f"{years}y"

        for indicator in self.MACRO_SYMBOLS.keys():
            results[indicator] = self.sync_macro_history(indicator, period)

        # 同步FRED数据
        for indicator in self.FRED_SERIES.keys():
            results[indicator] = self.sync_fred_history(indicator, years)

        return results

    # ==================== 股票/指数数据同步 ====================

    def sync_stock_history(self, symbol: str, market: str = 'us',
                          period: str = "5y") -> Tuple[bool, int]:
        """
        同步股票/指数历史数据

        Args:
            symbol: 股票代码
            market: 市场类型 us, cn, hk
            period: 时间周期

        Returns:
            (是否成功, 记录数)
        """
        try:
            if market == 'us':
                df = self._fetch_yfinance_history(symbol, period)
                source = 'yfinance'
            elif market == 'cn':
                df = self._fetch_akshare_stock(symbol, period)
                source = 'akshare'
            else:
                return False, 0

            if df.empty:
                return False, 0

            records = self._convert_price_records(df, symbol, 'stock')

            success, count = self.data_store.save_price_history(
                asset_code=symbol,
                asset_type='stock',
                data=records,
                source=source
            )

            return success, count

        except Exception as e:
            logger.error(f"Failed to sync stock history for {symbol}: {e}")
            return False, 0

    # ==================== 数据获取方法 ====================

    def _fetch_yfinance_history(self, symbol: str, period: str = "5y") -> pd.DataFrame:
        """从yfinance获取历史数据"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)

            if df.empty:
                return pd.DataFrame()

            df = df.reset_index()
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]

            # 统一列名
            if 'datetime' in df.columns:
                df['date'] = df['datetime'].dt.strftime('%Y-%m-%d')
            elif 'date' in df.columns:
                if hasattr(df['date'], 'dt'):
                    df['date'] = df['date'].dt.strftime('%Y-%m-%d')

            # 计算涨跌幅
            df['change'] = df['close'].diff()
            df['change_percent'] = df['close'].pct_change() * 100

            return df

        except Exception as e:
            logger.error(f"yfinance fetch failed for {symbol}: {e}")
            return pd.DataFrame()

    def _fetch_akshare_gold(self, period: str = "5y") -> pd.DataFrame:
        """从akshare获取黄金数据"""
        try:
            # 上海黄金交易所数据
            df = ak.spot_hist_sge(symbol="Au99.99")

            if df.empty:
                return pd.DataFrame()

            # 计算涨跌幅
            df['change'] = df['close'].diff()
            df['change_percent'] = df['close'].pct_change() * 100

            return df

        except Exception as e:
            logger.error(f"akshare gold fetch failed: {e}")
            return pd.DataFrame()

    def _fetch_akshare_stock(self, symbol: str, period: str = "5y") -> pd.DataFrame:
        """从akshare获取A股数据"""
        try:
            # 计算开始日期
            years = int(period.replace('y', ''))
            start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y%m%d')
            end_date = datetime.now().strftime('%Y%m%d')

            df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date, end_date=end_date)
            return df

        except Exception as e:
            logger.error(f"akshare stock fetch failed for {symbol}: {e}")
            return pd.DataFrame()

    def _convert_price_records(self, df: pd.DataFrame, asset_code: str,
                               asset_type: str) -> List[Dict[str, Any]]:
        """将DataFrame转换为存储记录格式"""
        records = []

        for _, row in df.iterrows():
            record = {
                'date': row.get('date'),
                'open': float(row['open']) if pd.notna(row.get('open')) else None,
                'high': float(row['high']) if pd.notna(row.get('high')) else None,
                'low': float(row['low']) if pd.notna(row.get('low')) else None,
                'close': float(row['close']) if pd.notna(row.get('close')) else None,
                'volume': float(row['volume']) if pd.notna(row.get('volume')) else None,
                'amount': float(row.get('amount')) if pd.notna(row.get('amount')) else None,
                'change': float(row.get('change')) if pd.notna(row.get('change')) else None,
                'change_percent': float(row.get('change_percent')) if pd.notna(row.get('change_percent')) else None,
            }
            records.append(record)

        return records

    # ==================== FRED数据同步 ====================

    def sync_fred_history(self, indicator: str, years: int = 5) -> Tuple[bool, int]:
        """
        同步FRED宏观指标（TIPS、Breakeven）

        Args:
            indicator: 指标代码，如 TIPS, BREAKEVEN
            years: 历史年限

        Returns:
            (是否成功, 记录数)
        """
        config = self.FRED_SERIES.get(indicator)
        if not config:
            logger.error(f"Unknown FRED indicator: {indicator}")
            return False, 0

        try:
            df = self._fetch_fred_series(config['series_id'], years)

            if df.empty:
                logger.warning(f"No FRED data fetched for {indicator}")
                return False, 0

            records = []
            for _, row in df.iterrows():
                records.append({
                    'date': row['date'],
                    'indicator_name': config['name'],
                    'value': row['value'],
                    'change_percent': row.get('change_percent')
                })

            success, count = self.data_store.save_macro_history(
                indicator_code=indicator,
                data=records,
                source='fred'
            )

            logger.info(f"Synced {count} FRED records for {indicator}")
            return success, count

        except Exception as e:
            logger.error(f"Failed to sync FRED data for {indicator}: {e}")
            return False, 0

    def _fetch_fred_series(self, series_id: str, years: int = 5) -> pd.DataFrame:
        """从FRED API获取数据系列"""
        api_key = settings.FRED_API_KEY

        # 优先使用fredapi
        if api_key:
            try:
                from fredapi import Fred
                fred = Fred(api_key=api_key)
                end_date = datetime.now()
                start_date = end_date - timedelta(days=years * 365)

                series = fred.get_series(series_id, start_date, end_date)

                if series.empty:
                    return pd.DataFrame()

                df = pd.DataFrame({
                    'date': series.index.strftime('%Y-%m-%d'),
                    'value': series.values
                })
                df['change_percent'] = pd.to_numeric(df['value'], errors='coerce').pct_change() * 100

                return df

            except ImportError:
                logger.warning("fredapi not installed, trying HTTP API fallback")
            except Exception as e:
                logger.warning(f"fredapi failed for {series_id}: {e}, trying HTTP fallback")

        # HTTP API fallback
        try:
            import httpx
            base_url = "https://api.stlouisfed.org/fred/series/observations"
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=years * 365)).strftime('%Y-%m-%d')

            params = {
                'series_id': series_id,
                'observation_start': start_date,
                'observation_end': end_date,
                'file_type': 'json',
            }
            if api_key:
                params['api_key'] = api_key
            else:
                # FRED allows limited access without key
                logger.warning("No FRED API key configured, data may be limited")
                return pd.DataFrame()

            resp = httpx.get(base_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            observations = data.get('observations', [])
            if not observations:
                return pd.DataFrame()

            df = pd.DataFrame(observations)
            df = df[df['value'] != '.']  # FRED用'.'表示缺失
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            df['value'] = pd.to_numeric(df['value'], errors='coerce')
            df['change_percent'] = df['value'].pct_change() * 100

            return df[['date', 'value', 'change_percent']]

        except Exception as e:
            logger.error(f"FRED HTTP API failed for {series_id}: {e}")
            return pd.DataFrame()

    # ==================== 增量更新 ====================

    def incremental_update(self, asset_code: str, asset_type: str) -> Tuple[bool, int]:
        """
        增量更新数据

        Args:
            asset_code: 资产代码
            asset_type: 资产类型

        Returns:
            (是否成功, 新增记录数)
        """
        try:
            # 获取本地最新日期
            df = self.data_store.get_price_history(
                asset_code=asset_code,
                asset_type=asset_type,
                limit=1,
                as_dataframe=True
            )

            if df.empty:
                # 没有历史数据，进行全量同步
                if asset_type == 'gold':
                    return self.sync_gold_history(asset_code)
                return False, 0

            last_date = pd.to_datetime(df['date'].iloc[0])
            today = datetime.now()

            if (today - last_date).days <= 1:
                logger.info(f"{asset_code} is up to date")
                return True, 0

            # 获取增量数据
            period = f"{(today - last_date).days}d"

            if asset_type == 'gold':
                config = self.GOLD_SYMBOLS.get(asset_code, self.GOLD_SYMBOLS['GC'])
                if config['source'] == 'yfinance':
                    df_new = self._fetch_yfinance_history(config['yf'], period)
                else:
                    df_new = self._fetch_akshare_gold(period)
            else:
                return False, 0

            if df_new.empty:
                return False, 0

            # 过滤已存在的日期
            df_new['date'] = pd.to_datetime(df_new['date'])
            df_new = df_new[df_new['date'] > last_date]

            if df_new.empty:
                return True, 0

            records = self._convert_price_records(df_new, asset_code, asset_type)

            success, count = self.data_store.save_price_history(
                asset_code=asset_code,
                asset_type=asset_type,
                data=records,
                source='incremental'
            )

            logger.info(f"Incremental update for {asset_code}: {count} new records")
            return success, count

        except Exception as e:
            logger.error(f"Incremental update failed for {asset_code}: {e}")
            return False, 0

    # ==================== 数据完整性检查 ====================

    def check_data_completeness(self, asset_code: str, asset_type: str,
                                expected_years: int = 5) -> Dict[str, Any]:
        """
        检查数据完整性

        Args:
            asset_code: 资产代码
            asset_type: 资产类型
            expected_years: 期望的数据年限

        Returns:
            完整性检查结果
        """
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=expected_years*365)).strftime('%Y-%m-%d')

            # 获取数据覆盖情况
            df = self.data_store.get_price_history(
                asset_code=asset_code,
                asset_type=asset_type,
                start_date=start_date,
                end_date=end_date,
                as_dataframe=True
            )

            if df.empty:
                return {
                    'asset_code': asset_code,
                    'status': 'missing',
                    'record_count': 0,
                    'coverage_percent': 0,
                    'gaps': [{'start': start_date, 'end': end_date}]
                }

            # 计算数据缺口
            gaps = self.data_store.check_data_gaps(
                asset_code=asset_code,
                asset_type=asset_type,
                expected_start=start_date,
                expected_end=end_date
            )

            # 计算覆盖率
            expected_days = expected_years * 252  # 约252个交易日/年
            actual_days = len(df)
            coverage = min(100, actual_days / expected_days * 100)

            return {
                'asset_code': asset_code,
                'status': 'complete' if not gaps else 'partial',
                'record_count': actual_days,
                'date_range': {
                    'start': df['date'].min(),
                    'end': df['date'].max()
                },
                'coverage_percent': round(coverage, 2),
                'gaps': gaps
            }

        except Exception as e:
            logger.error(f"Data completeness check failed for {asset_code}: {e}")
            return {'asset_code': asset_code, 'status': 'error', 'error': str(e)}


# 全局数据同步管理器实例
data_sync = DataSyncManager()


# 便捷函数
def sync_gold_for_prediction(years: int = 5) -> Dict[str, Any]:
    """
    同步黄金价格预测所需的全部数据

    Args:
        years: 历史数据年限

    Returns:
        同步结果
    """
    results = {
        'gold_data': data_sync.sync_all_gold_data(years),
        'macro_data': data_sync.sync_all_macro_data(years),
        'completeness_checks': {}
    }

    # 检查数据完整性
    for symbol in data_sync.GOLD_SYMBOLS.keys():
        results['completeness_checks'][symbol] = data_sync.check_data_completeness(
            symbol, 'gold', years
        )

    return results


def get_gold_training_data(symbol: str = 'GC', lookback_days: int = 2520) -> pd.DataFrame:
    """
    获取黄金训练数据

    Args:
        symbol: 黄金代码
        lookback_days: 回溯天数（默认10年）

    Returns:
        训练数据DataFrame
    """
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

    # 获取黄金价格
    gold_records = data_store.get_price_history(
        asset_code=symbol,
        asset_type='gold',
        start_date=start_date,
        end_date=end_date
    )

    if not gold_records:
        # 尝试同步数据
        data_sync.sync_gold_history(symbol, period=f"{lookback_days//252}y")
        gold_records = data_store.get_price_history(
            asset_code=symbol,
            asset_type='gold',
            start_date=start_date,
            end_date=end_date
        )

    if not gold_records:
        return pd.DataFrame()

    # 转换为DataFrame
    gold_df = pd.DataFrame(gold_records)

    # 获取相关宏观指标（含TIPS和Breakeven）
    for indicator in ['DXY', 'VIX', 'US10Y', 'TIPS', 'BREAKEVEN']:
        macro_records = data_store.get_macro_history(
            indicator_code=indicator,
            start_date=start_date,
            end_date=end_date
        )

        if macro_records:
            macro_df = pd.DataFrame(macro_records)
            macro_df = macro_df.rename(columns={'value': f'{indicator}_value'})
            gold_df = gold_df.merge(
                macro_df[['date', f'{indicator}_value']],
                on='date',
                how='left'
            )

    return gold_df