"""
数据存储模块

提供本地数据存储能力，支持：
1. 短期缓存 - 减少对外部API的调用频率（价格、持仓等）
2. 长期存储 - 为预测模型提供历史数据（价格、宏观指标等）

存储策略：
- 短期缓存：内存/快速查询，有过期时间
- 长期数据：持久化存储，无过期限制，支持大量数据
"""

import json
import os
import sqlite3
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from enum import Enum
import pandas as pd
from loguru import logger

logger.add("./logs/data_store.log", encoding="utf-8", rotation="10 MB")


class StorageType(Enum):
    """存储类型"""
    CACHE = "cache"      # 短期缓存
    HISTORY = "history"  # 长期历史数据


@dataclass
class CacheConfig:
    """缓存配置（短期数据）"""
    price_ttl: int = 300           # 价格数据默认缓存5分钟
    holdings_ttl: int = 86400      # 持仓数据默认缓存1天
    fund_info_ttl: int = 3600      # 基金信息默认缓存1小时
    macro_ttl: int = 3600          # 宏观数据默认缓存1小时


@dataclass
class HistoryConfig:
    """历史数据配置（长期数据）"""
    min_history_years: int = 5     # 最小历史年限
    max_history_years: int = 20    # 最大历史年限
    update_interval_days: int = 1  # 数据更新间隔


class DataStore:
    """
    数据存储类

    双存储策略：
    1. 短期缓存(cache) - 快速查询，有过期时间
    2. 长期历史(history) - 持久化存储，用于模型训练

    使用SQLite存储结构化数据
    """

    def __init__(self, data_dir: str = None):
        # 默认使用 backend/data 目录
        if data_dir is None:
            # 获取当前文件所在目录 (backend/)，然后使用其下的 data
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(backend_dir, "data")

        self.data_dir = data_dir
        self.cache_dir = os.path.join(data_dir, "cache")
        self.history_dir = os.path.join(data_dir, "history")

        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.history_dir, exist_ok=True)

        # 短期缓存数据库
        self.cache_db_path = os.path.join(self.cache_dir, "market_cache.db")
        # 长期历史数据库
        self.history_db_path = os.path.join(self.history_dir, "market_history.db")

        self.cache_config = CacheConfig()
        self.history_config = HistoryConfig()

        self._init_cache_db()
        self._init_history_db()

        logger.info(f"DataStore initialized: cache={self.cache_db_path}, history={self.history_db_path}")

    @contextmanager
    def _get_conn(self, storage_type: StorageType = StorageType.CACHE):
        """获取数据库连接"""
        db_path = self.cache_db_path if storage_type == StorageType.CACHE else self.history_db_path
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_cache_db(self):
        """初始化缓存数据库（短期数据）"""
        with self._get_conn(StorageType.CACHE) as conn:
            cursor = conn.cursor()

            # 实时价格缓存表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_code TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    market_type TEXT,
                    price REAL,
                    change_percent REAL,
                    volume REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    source TEXT,
                    raw_data BLOB,
                    UNIQUE(asset_code, asset_type)
                )
            """)

            # 基金持仓缓存表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS holdings_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fund_code TEXT NOT NULL,
                    report_date TEXT,
                    holdings BLOB,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(fund_code)
                )
            """)

            # 基金信息缓存表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fund_info_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fund_code TEXT NOT NULL,
                    fund_name TEXT,
                    fund_type TEXT,
                    tracking_index TEXT,
                    nav REAL,
                    nav_date TEXT,
                    raw_data BLOB,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(fund_code)
                )
            """)

            # 宏观数据缓存表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS macro_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicator_code TEXT NOT NULL,
                    indicator_name TEXT,
                    value REAL,
                    change_percent REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    raw_data BLOB,
                    UNIQUE(indicator_code)
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_price ON price_cache(asset_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_holdings ON holdings_cache(fund_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_fund ON fund_info_cache(fund_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_macro ON macro_cache(indicator_code)")

            conn.commit()

    def _init_history_db(self):
        """初始化历史数据库（长期数据）"""
        with self._get_conn(StorageType.HISTORY) as conn:
            cursor = conn.cursor()

            # 日频价格历史数据表（股票、基金、指数、黄金等）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_code TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    amount REAL,
                    change REAL,
                    change_percent REAL,
                    source TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(asset_code, asset_type, date)
                )
            """)

            # 宏观指标历史数据表（美元指数、利率、VIX等）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS macro_history_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicator_code TEXT NOT NULL,
                    indicator_name TEXT,
                    date TEXT NOT NULL,
                    value REAL,
                    change_percent REAL,
                    source TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(indicator_code, date)
                )
            """)

            # 多因子数据表（用于机器学习模型）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS factor_data_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_code TEXT NOT NULL,
                    date TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    factor_value REAL,
                    factor_category TEXT,  -- technical, macro, sentiment, etc.
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(asset_code, date, factor_name)
                )
            """)

            # 数据更新记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_update_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_type TEXT NOT NULL,  -- price, macro, factor
                    asset_code TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    record_count INTEGER,
                    source TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_hist_price
                ON price_history_daily(asset_code, asset_type, date)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_hist_macro
                ON macro_history_daily(indicator_code, date)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_hist_factor
                ON factor_data_daily(asset_code, date, factor_name)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_update_log
                ON data_update_log(data_type, asset_code, updated_at)
            """)

            conn.commit()

    # ==================== 长期历史数据存储 ====================

    def save_price_history(self, asset_code: str, asset_type: str,
                          data: List[Dict[str, Any]], source: str = None) -> Tuple[bool, int]:
        """
        保存长期价格历史数据

        Args:
            asset_code: 资产代码
            asset_type: 资产类型 (stock, fund, etf, index, gold, crypto)
            data: 历史数据列表，每项包含 date, open, high, low, close, volume, amount, change, change_percent
            source: 数据来源

        Returns:
            (是否成功, 保存记录数)
        """
        if not data:
            return False, 0

        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                cursor = conn.cursor()
                inserted = 0

                for item in data:
                    cursor.execute("""
                        INSERT OR REPLACE INTO price_history_daily
                        (asset_code, asset_type, date, open, high, low, close,
                         volume, amount, change, change_percent, source, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        asset_code, asset_type,
                        item.get('date'),
                        item.get('open'), item.get('high'), item.get('low'), item.get('close'),
                        item.get('volume'), item.get('amount'),
                        item.get('change'), item.get('change_percent'),
                        source
                    ))
                    inserted += cursor.rowcount

                conn.commit()

                # 记录更新日志
                dates = [d['date'] for d in data if 'date' in d]
                if dates:
                    self._log_update('price', asset_code, min(dates), max(dates), inserted, source)

                logger.info(f"Saved {inserted} price history records for {asset_code}")
                return True, inserted

        except Exception as e:
            logger.error(f"Failed to save price history for {asset_code}: {e}")
            return False, 0

    def get_price_history(self, asset_code: str, asset_type: str = None,
                         start_date: str = None, end_date: str = None,
                         as_dataframe: bool = False) -> Union[List[Dict], pd.DataFrame]:
        """
        获取长期价格历史数据

        Args:
            asset_code: 资产代码
            asset_type: 资产类型（可选）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            as_dataframe: 是否返回DataFrame格式

        Returns:
            历史数据列表或DataFrame
        """
        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                query = """
                    SELECT asset_code, asset_type, date, open, high, low, close,
                           volume, amount, change, change_percent, source
                    FROM price_history_daily
                    WHERE asset_code = ?
                """
                params = [asset_code]

                if asset_type:
                    query += " AND asset_type = ?"
                    params.append(asset_type)
                if start_date:
                    query += " AND date >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND date <= ?"
                    params.append(end_date)

                query += " ORDER BY date ASC"

                df = pd.read_sql_query(query, conn, params=params)

                if as_dataframe:
                    return df
                return df.to_dict('records')

        except Exception as e:
            logger.error(f"Failed to get price history for {asset_code}: {e}")
            return pd.DataFrame() if as_dataframe else []

    def save_macro_history(self, indicator_code: str, data: List[Dict[str, Any]],
                          source: str = None) -> Tuple[bool, int]:
        """
        保存宏观指标历史数据

        Args:
            indicator_code: 指标代码，如 DXY, GOLD, VIX, US10Y
            data: 历史数据列表，每项包含 date, value, change_percent
            source: 数据来源

        Returns:
            (是否成功, 保存记录数)
        """
        if not data:
            return False, 0

        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                cursor = conn.cursor()
                inserted = 0

                for item in data:
                    cursor.execute("""
                        INSERT OR REPLACE INTO macro_history_daily
                        (indicator_code, indicator_name, date, value, change_percent, source, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        indicator_code,
                        item.get('indicator_name'),
                        item.get('date'),
                        item.get('value'),
                        item.get('change_percent'),
                        source
                    ))
                    inserted += cursor.rowcount

                conn.commit()

                dates = [d['date'] for d in data if 'date' in d]
                if dates:
                    self._log_update('macro', indicator_code, min(dates), max(dates), inserted, source)

                logger.info(f"Saved {inserted} macro history records for {indicator_code}")
                return True, inserted

        except Exception as e:
            logger.error(f"Failed to save macro history for {indicator_code}: {e}")
            return False, 0

    def get_macro_history(self, indicator_code: str,
                         start_date: str = None, end_date: str = None,
                         as_dataframe: bool = False) -> Union[List[Dict], pd.DataFrame]:
        """
        获取宏观指标历史数据

        Args:
            indicator_code: 指标代码
            start_date: 开始日期
            end_date: 结束日期
            as_dataframe: 是否返回DataFrame格式

        Returns:
            历史数据列表或DataFrame
        """
        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                query = """
                    SELECT indicator_code, indicator_name, date, value, change_percent, source
                    FROM macro_history_daily
                    WHERE indicator_code = ?
                """
                params = [indicator_code]

                if start_date:
                    query += " AND date >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND date <= ?"
                    params.append(end_date)

                query += " ORDER BY date ASC"

                df = pd.read_sql_query(query, conn, params=params)

                if as_dataframe:
                    return df
                return df.to_dict('records')

        except Exception as e:
            logger.error(f"Failed to get macro history for {indicator_code}: {e}")
            return pd.DataFrame() if as_dataframe else []

    def save_factors(self, asset_code: str, date: str,
                    factors: Dict[str, float], factor_category: str = None) -> bool:
        """
        保存因子数据（用于机器学习模型）

        Args:
            asset_code: 资产代码
            date: 日期
            factors: 因子名称和值的字典
            factor_category: 因子类别 (technical, macro, sentiment, etc.)

        Returns:
            bool: 是否成功
        """
        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                cursor = conn.cursor()

                for factor_name, factor_value in factors.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO factor_data_daily
                        (asset_code, date, factor_name, factor_value, factor_category)
                        VALUES (?, ?, ?, ?, ?)
                    """, (asset_code, date, factor_name, factor_value, factor_category))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to save factors for {asset_code}: {e}")
            return False

    def get_factors(self, asset_code: str, factor_names: List[str] = None,
                   start_date: str = None, end_date: str = None,
                   as_dataframe: bool = False) -> Union[List[Dict], pd.DataFrame]:
        """
        获取因子数据

        Args:
            asset_code: 资产代码
            factor_names: 因子名称列表（None表示获取所有）
            start_date: 开始日期
            end_date: 结束日期
            as_dataframe: 是否返回DataFrame格式

        Returns:
            因子数据列表或DataFrame
        """
        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                query = """
                    SELECT asset_code, date, factor_name, factor_value, factor_category
                    FROM factor_data_daily
                    WHERE asset_code = ?
                """
                params = [asset_code]

                if factor_names:
                    placeholders = ','.join(['?' for _ in factor_names])
                    query += f" AND factor_name IN ({placeholders})"
                    params.extend(factor_names)
                if start_date:
                    query += " AND date >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND date <= ?"
                    params.append(end_date)

                query += " ORDER BY date ASC"

                df = pd.read_sql_query(query, conn, params=params)

                if as_dataframe:
                    # 将长格式转换为宽格式
                    if not df.empty:
                        df = df.pivot_table(
                            index=['asset_code', 'date'],
                            columns='factor_name',
                            values='factor_value'
                        ).reset_index()
                    return df
                return df.to_dict('records')

        except Exception as e:
            logger.error(f"Failed to get factors for {asset_code}: {e}")
            return pd.DataFrame() if as_dataframe else []

    def _log_update(self, data_type: str, asset_code: str,
                   start_date: str, end_date: str, record_count: int, source: str):
        """记录数据更新日志"""
        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO data_update_log
                    (data_type, asset_code, start_date, end_date, record_count, source)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (data_type, asset_code, start_date, end_date, record_count, source))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log update: {e}")

    def get_data_coverage(self, asset_code: str = None) -> Dict[str, Any]:
        """
        获取数据覆盖情况

        Returns:
            数据覆盖统计信息
        """
        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                cursor = conn.cursor()

                # 价格数据覆盖
                cursor.execute("""
                    SELECT asset_code, asset_type,
                           MIN(date) as start_date, MAX(date) as end_date,
                           COUNT(*) as record_count
                    FROM price_history_daily
                    GROUP BY asset_code, asset_type
                """)
                price_coverage = [dict(row) for row in cursor.fetchall()]

                # 宏观数据覆盖
                cursor.execute("""
                    SELECT indicator_code,
                           MIN(date) as start_date, MAX(date) as end_date,
                           COUNT(*) as record_count
                    FROM macro_history_daily
                    GROUP BY indicator_code
                """)
                macro_coverage = [dict(row) for row in cursor.fetchall()]

                # 最近更新记录
                cursor.execute("""
                    SELECT data_type, asset_code, start_date, end_date,
                           record_count, source, updated_at
                    FROM data_update_log
                    ORDER BY updated_at DESC
                    LIMIT 20
                """)
                recent_updates = [dict(row) for row in cursor.fetchall()]

                return {
                    'price_coverage': price_coverage,
                    'macro_coverage': macro_coverage,
                    'recent_updates': recent_updates
                }

        except Exception as e:
            logger.error(f"Failed to get data coverage: {e}")
            return {}

    def check_data_gaps(self, asset_code: str, asset_type: str,
                       expected_start: str, expected_end: str) -> List[Dict[str, str]]:
        """
        检查数据缺口

        Args:
            asset_code: 资产代码
            asset_type: 资产类型
            expected_start: 期望开始日期
            expected_end: 期望结束日期

        Returns:
            数据缺口列表
        """
        try:
            with self._get_conn(StorageType.HISTORY) as conn:
                cursor = conn.cursor()

                # 获取已有数据的日期范围
                cursor.execute("""
                    SELECT date FROM price_history_daily
                    WHERE asset_code = ? AND asset_type = ?
                    AND date BETWEEN ? AND ?
                    ORDER BY date
                """, (asset_code, asset_type, expected_start, expected_end))

                existing_dates = {row[0] for row in cursor.fetchall()}

                # 生成期望的所有交易日（简化版，实际应考虑真实交易日历）
                from pandas.tseries.offsets import BDay
                date_range = pd.date_range(expected_start, expected_end, freq=BDay())
                expected_dates = {d.strftime('%Y-%m-%d') for d in date_range}

                # 找出缺失的日期
                missing_dates = sorted(expected_dates - existing_dates)

                # 合并连续的缺失日期为区间
                gaps = []
                if missing_dates:
                    gap_start = missing_dates[0]
                    gap_end = missing_dates[0]

                    for i in range(1, len(missing_dates)):
                        current = datetime.strptime(missing_dates[i], '%Y-%m-%d')
                        prev = datetime.strptime(missing_dates[i-1], '%Y-%m-%d')

                        if (current - prev).days > 3:  # 超过3天认为是新的缺口
                            gaps.append({'start': gap_start, 'end': gap_end})
                            gap_start = missing_dates[i]
                        gap_end = missing_dates[i]

                    gaps.append({'start': gap_start, 'end': gap_end})

                return gaps

        except Exception as e:
            logger.error(f"Failed to check data gaps for {asset_code}: {e}")
            return []

    # ==================== 短期缓存方法 ====================

    def cache_price_history(self, asset_code: str, asset_type: str,
                           history_data: List[Dict[str, Any]]) -> bool:
        """
        缓存历史价格数据

        Args:
            asset_code: 资产代码
            asset_type: 资产类型
            history_data: 历史数据列表，每项包含 date, open, high, low, close, volume

        Returns:
            bool: 是否成功
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()

                for item in history_data:
                    cursor.execute("""
                        INSERT OR REPLACE INTO price_history
                        (asset_code, asset_type, date, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        asset_code,
                        asset_type,
                        item.get('date'),
                        item.get('open'),
                        item.get('high'),
                        item.get('low'),
                        item.get('close'),
                        item.get('volume')
                    ))

                conn.commit()
                logger.info(f"Cached {len(history_data)} history records for {asset_code}")
                return True
        except Exception as e:
            logger.error(f"Failed to cache price history for {asset_code}: {e}")
            return False

    def cache_holdings(self, fund_code: str, holdings: List[Dict[str, Any]],
                       report_date: str = None) -> bool:
        """缓存基金持仓"""
        try:
            with self._get_conn(StorageType.CACHE) as conn:
                cursor = conn.cursor()
                holdings_blob = pickle.dumps(holdings)

                cursor.execute("""
                    INSERT OR REPLACE INTO holdings_cache
                    (fund_code, report_date, holdings, timestamp)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (fund_code, report_date, holdings_blob))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to cache holdings for {fund_code}: {e}")
            return False

    def get_cached_holdings(self, fund_code: str,
                            max_age_seconds: int = None) -> Optional[Dict[str, Any]]:
        """获取缓存的持仓"""
        if max_age_seconds is None:
            max_age_seconds = self.cache_config.holdings_ttl

        try:
            with self._get_conn(StorageType.CACHE) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT holdings, report_date, timestamp FROM holdings_cache
                    WHERE fund_code = ?
                """, (fund_code,))

                result = cursor.fetchone()
                if not result:
                    return None

                holdings_blob, report_date, timestamp_str = result
                timestamp = datetime.fromisoformat(timestamp_str)

                if datetime.now() - timestamp > timedelta(seconds=max_age_seconds):
                    return None

                return {
                    'fund_code': fund_code,
                    'report_date': report_date,
                    'holdings': pickle.loads(holdings_blob),
                    'cached_at': timestamp_str
                }
        except Exception as e:
            logger.error(f"Failed to get cached holdings for {fund_code}: {e}")
            return None

    def cache_fund_info(self, fund_code: str, fund_info: Dict[str, Any]) -> bool:
        """缓存基金信息"""
        try:
            with self._get_conn(StorageType.CACHE) as conn:
                cursor = conn.cursor()
                raw_data = pickle.dumps(fund_info)

                cursor.execute("""
                    INSERT OR REPLACE INTO fund_info_cache
                    (fund_code, fund_name, fund_type, tracking_index, nav, nav_date, raw_data, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    fund_code, fund_info.get('fund_name'), fund_info.get('fund_type'),
                    fund_info.get('tracking_index'), fund_info.get('nav'),
                    fund_info.get('nav_date'), raw_data
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to cache fund info for {fund_code}: {e}")
            return False

    def get_cached_fund_info(self, fund_code: str,
                             max_age_seconds: int = None) -> Optional[Dict[str, Any]]:
        """获取缓存的基金信息"""
        if max_age_seconds is None:
            max_age_seconds = self.cache_config.fund_info_ttl

        try:
            with self._get_conn(StorageType.CACHE) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT raw_data, timestamp FROM fund_info_cache
                    WHERE fund_code = ?
                """, (fund_code,))

                result = cursor.fetchone()
                if not result:
                    return None

                raw_data, timestamp_str = result
                timestamp = datetime.fromisoformat(timestamp_str)

                if datetime.now() - timestamp > timedelta(seconds=max_age_seconds):
                    return None

                return pickle.loads(raw_data)
        except Exception as e:
            logger.error(f"Failed to get cached fund info for {fund_code}: {e}")
            return None

    def cache_macro_indicator(self, indicator_code: str, value: float,
                              indicator_name: str = None,
                              change_percent: float = None,
                              extra_data: Dict[str, Any] = None) -> bool:
        """缓存宏观指标"""
        try:
            with self._get_conn(StorageType.CACHE) as conn:
                cursor = conn.cursor()
                raw_data = pickle.dumps(extra_data) if extra_data else None

                cursor.execute("""
                    INSERT OR REPLACE INTO macro_cache
                    (indicator_code, indicator_name, value, change_percent, raw_data, timestamp)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (indicator_code, indicator_name, value, change_percent, raw_data))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to cache macro indicator {indicator_code}: {e}")
            return False

    def get_cached_macro(self, indicator_code: str,
                         max_age_seconds: int = None) -> Optional[Dict[str, Any]]:
        """获取缓存的宏观指标"""
        if max_age_seconds is None:
            max_age_seconds = self.cache_config.macro_ttl

        try:
            with self._get_conn(StorageType.CACHE) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT indicator_name, value, change_percent, raw_data, timestamp
                    FROM macro_cache
                    WHERE indicator_code = ?
                """, (indicator_code,))

                result = cursor.fetchone()
                if not result:
                    return None

                name, value, change, raw_data, timestamp_str = result
                timestamp = datetime.fromisoformat(timestamp_str)

                if datetime.now() - timestamp > timedelta(seconds=max_age_seconds):
                    return None

                data = {
                    'indicator_code': indicator_code,
                    'indicator_name': name,
                    'value': value,
                    'change_percent': change,
                    'cached_at': timestamp_str
                }
                if raw_data:
                    data.update(pickle.loads(raw_data))
                return data
        except Exception as e:
            logger.error(f"Failed to get cached macro {indicator_code}: {e}")
            return None

    # ==================== 维护操作 ====================

    def clear_expired_cache(self, max_age_days: int = 7):
        """清理过期缓存数据"""
        try:
            with self._get_conn(StorageType.CACHE) as conn:
                cursor = conn.cursor()
                cutoff = datetime.now() - timedelta(days=max_age_days)

                tables = ['price_cache', 'holdings_cache', 'fund_info_cache', 'macro_cache']
                total = 0
                for table in tables:
                    cursor.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff.isoformat(),))
                    total += cursor.rowcount

                conn.commit()
                logger.info(f"Cleared {total} expired cache entries")
                return total
        except Exception as e:
            logger.error(f"Failed to clear expired cache: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        try:
            stats = {'cache': {}, 'history': {}}

            with self._get_conn(StorageType.CACHE) as conn:
                cursor = conn.cursor()
                for table in ['price_cache', 'holdings_cache', 'fund_info_cache', 'macro_cache']:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    stats['cache'][table] = cursor.fetchone()[0]

            with self._get_conn(StorageType.HISTORY) as conn:
                cursor = conn.cursor()
                for table in ['price_history_daily', 'macro_history_daily', 'factor_data_daily']:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    stats['history'][table] = cursor.fetchone()[0]

            return stats
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}


# 全局数据存储实例
data_store = DataStore()
