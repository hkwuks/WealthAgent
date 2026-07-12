"""FundQuant SQLite 存储层"""

import json
import sqlite3
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from contextlib import contextmanager
from ..core.config import fund_quant_settings
from ..core.models import NavPoint, FundHolding, FundMeta, BacktestResult, FundSignal
from ..core.errors import StorageError


def _get_db_path() -> str:
    return fund_quant_settings.FUND_QUANT_DB_PATH


def _ensure_db():
    """确保数据库文件和目录存在"""
    path = Path(_get_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    """获取数据库连接（上下文管理器）"""
    _ensure_db()
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """初始化数据库表"""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS nav_history (
            fund_code TEXT NOT NULL,
            date TEXT NOT NULL,
            nav REAL,
            adjusted_nav REAL,
            source TEXT DEFAULT 'eastmoney',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (fund_code, date)
        );

        CREATE TABLE IF NOT EXISTS holdings_history (
            fund_code TEXT NOT NULL,
            report_period TEXT NOT NULL,
            publish_date TEXT NOT NULL,
            holdings_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (fund_code, report_period)
        );

        CREATE TABLE IF NOT EXISTS fund_metadata (
            fund_code TEXT PRIMARY KEY,
            fund_name TEXT,
            fund_type TEXT,
            management_fee REAL,
            custody_fee REAL,
            subscription_fee_tiers_json TEXT,
            scale REAL,
            rating INTEGER,
            tracking_index TEXT,
            established_date TEXT,
            is_listed INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fund_type_defaults (
            fund_type TEXT PRIMARY KEY,
            mgmt_fee_default REAL,
            custody_fee_default REAL,
            sub_fee_default REAL
        );

        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            fund_code TEXT NOT NULL,
            fund_name TEXT,
            signal_type TEXT,
            direction TEXT,
            confidence REAL,
            reason TEXT,
            strategy_name TEXT,
            suggested_amount REAL,
            risk_check_passed INTEGER DEFAULT 1,
            risk_warnings_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS backtest_results (
            backtest_id TEXT PRIMARY KEY,
            strategy_name TEXT,
            fund_codes TEXT,
            start_date TEXT,
            end_date TEXT,
            config_json TEXT,
            result_json TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS collection_status (
            fund_code TEXT NOT NULL,
            data_type TEXT NOT NULL,
            last_collected_date TEXT,
            status TEXT DEFAULT 'pending',
            error_msg TEXT,
            next_retry TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (fund_code, data_type)
        );

        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            total_value REAL,
            cash REAL,
            positions_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_nav_fund_date ON nav_history(fund_code, date);
        CREATE INDEX IF NOT EXISTS idx_signals_fund ON signals(fund_code);
        CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
        CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_results(strategy_name);
        """)


# ═══════════════════════════════════════════
# NAV 操作
# ═══════════════════════════════════════════

def save_nav_points(points: List[NavPoint]):
    """批量保存净值数据（UPSERT）"""
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO nav_history (fund_code, date, nav, adjusted_nav, source)
               VALUES (?, ?, ?, ?, ?)""",
            [(p.fund_code, p.date.isoformat(), p.nav, p.adjusted_nav, p.source) for p in points],
        )


def get_nav_history(fund_code: str, start_date: Optional[str] = None,
                    end_date: Optional[str] = None, limit: Optional[int] = None) -> List[dict]:
    """获取基金净值历史"""
    with get_conn() as conn:
        query = "SELECT * FROM nav_history WHERE fund_code = ?"
        params: List[Any] = [fund_code]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date ASC"
        if limit:
            query += f" LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_latest_nav(fund_code: str) -> Optional[dict]:
    """获取最新净值"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM nav_history WHERE fund_code = ? ORDER BY date DESC LIMIT 1",
            (fund_code,),
        ).fetchone()
        return dict(row) if row else None


# ═══════════════════════════════════════════
# 持仓操作
# ═══════════════════════════════════════════

def save_holdings(holdings: List[FundHolding]):
    """批量保存持仓数据"""
    with get_conn() as conn:
        for h in holdings:
            conn.execute(
                """INSERT OR REPLACE INTO holdings_history (fund_code, report_period, publish_date, holdings_json)
                   VALUES (?, ?, ?, ?)""",
                (h.fund_code, h.report_period.isoformat(), h.publish_date.isoformat(),
                 json.dumps([h2.model_dump() for h2 in h.holdings], default=str)),
            )


def get_holdings(fund_code: str, report_period: Optional[str] = None,
                 as_of_date: Optional[str] = None) -> List[dict]:
    """获取持仓数据

    Args:
        fund_code: 基金代码
        report_period: 指定报告期
        as_of_date: 前视偏差防护 — 只返回 publish_date <= as_of_date 的持仓
    """
    with get_conn() as conn:
        if report_period:
            query = "SELECT * FROM holdings_history WHERE fund_code = ? AND report_period = ?"
            params: List[Any] = [fund_code, report_period]
        else:
            query = "SELECT * FROM holdings_history WHERE fund_code = ?"
            params = [fund_code]

        if as_of_date:
            query += " AND publish_date <= ?"
            params.append(as_of_date)

        query += " ORDER BY report_period DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════
# 基金元数据操作
# ═══════════════════════════════════════════

def upsert_fund_meta(meta: FundMeta):
    """插入或更新基金元数据"""
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO fund_metadata
               (fund_code, fund_name, fund_type, management_fee, custody_fee,
                subscription_fee_tiers_json, scale, rating, tracking_index,
                established_date, is_listed, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (meta.fund_code, meta.fund_name, meta.fund_type,
             meta.management_fee, meta.custody_fee,
             meta.subscription_fee_tiers, meta.scale, meta.rating,
             meta.tracking_index,
             meta.established_date.isoformat() if meta.established_date else None,
             int(meta.is_listed)),
        )


def get_fund_meta(fund_code: str) -> Optional[dict]:
    """获取基金元数据"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM fund_metadata WHERE fund_code = ?", (fund_code,)
        ).fetchone()
        return dict(row) if row else None


def get_all_fund_codes() -> List[str]:
    """获取所有已记录的基金代码"""
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT fund_code FROM nav_history ORDER BY fund_code").fetchall()
        return [r["fund_code"] for r in rows]


# ═══════════════════════════════════════════
# 信号操作
# ═══════════════════════════════════════════

def save_signal(signal: FundSignal):
    """保存信号"""
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO signals
               (signal_id, fund_code, fund_name, signal_type, direction,
                confidence, reason, strategy_name, suggested_amount,
                risk_check_passed, risk_warnings_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal.signal_id, signal.fund_code, signal.fund_name,
             signal.signal_type.value, signal.direction.value,
             signal.confidence, signal.reason, signal.strategy_name,
             signal.suggested_amount, int(signal.risk_check_passed),
             json.dumps(signal.risk_warnings)),
        )


def get_signals(fund_code: Optional[str] = None,
                signal_type: Optional[str] = None,
                limit: int = 50, offset: int = 0) -> List[dict]:
    """获取信号历史"""
    with get_conn() as conn:
        query = "SELECT * FROM signals WHERE 1=1"
        params: List[Any] = []
        if fund_code:
            query += " AND fund_code = ?"
            params.append(fund_code)
        if signal_type:
            query += " AND signal_type = ?"
            params.append(signal_type)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════
# 回测结果操作
# ═══════════════════════════════════════════

def save_backtest_result(result: BacktestResult):
    """保存回测结果"""
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO backtest_results
               (backtest_id, strategy_name, fund_codes, start_date, end_date,
                config_json, result_json, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (result.backtest_id, result.config.strategy_name,
             json.dumps(result.config.fund_codes),
             result.config.start_date, result.config.end_date,
             result.config.model_dump_json(),
             result.model_dump_json(), result.status),
        )


def get_backtest_result(backtest_id: str) -> Optional[dict]:
    """获取回测结果"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM backtest_results WHERE backtest_id = ?", (backtest_id,)
        ).fetchone()
        return dict(row) if row else None


def list_backtest_results(strategy_name: Optional[str] = None, limit: int = 20) -> List[dict]:
    """列出回测结果"""
    with get_conn() as conn:
        query = "SELECT backtest_id, strategy_name, fund_codes, start_date, end_date, status, created_at FROM backtest_results"
        params: List[Any] = []
        if strategy_name:
            query += " WHERE strategy_name = ?"
            params.append(strategy_name)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════
# 采集状态操作
# ═══════════════════════════════════════════

def upsert_collection_status(fund_code: str, data_type: str, status: str,
                              last_collected_date: Optional[str] = None,
                              error_msg: Optional[str] = None):
    """更新采集状态"""
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO collection_status
               (fund_code, data_type, last_collected_date, status, error_msg)
               VALUES (?, ?, ?, ?, ?)""",
            (fund_code, data_type, last_collected_date, status, error_msg),
        )


def get_pending_collections() -> List[dict]:
    """获取待采集任务"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM collection_status WHERE status IN ('pending', 'failed') ORDER BY fund_code"
        ).fetchall()
        return [dict(r) for r in rows]
