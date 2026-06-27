"""
CTP 客户端 — 封装 CTP 行情/交易 API，桥接到 asyncio

线程模型:
  CTP API → 原生线程 → call_soon_threadsafe → asyncio → 系统队列
"""
import asyncio
import json
import os
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from loguru import logger

from backend.gold.core.models import GoldTickData, SignalDirection, OrderStatus
from backend.gold.trading.connectors.ctp_config import CtpConfig

import ctp

# ── 交易方向/开平映射（CTP → 系统） ────────────────────────────

_THOST_OPT_LONG = "0"      # THOST_FTDC_OPT_Long
_THOST_OPT_SHORT = "1"     # THOST_FTDC_OPT_Short
_THOST_F_OPEN = "0"        # THOST_FTDC_F_Open
_THOST_F_CLOSE = "1"       # THOST_FTDC_F_Close
_THOST_F_CLOSETODAY = "2"  # THOST_FTDC_F_CloseToday

# 订单状态映射
_ORDER_STATUS_MAP = {
    "0": "all_traded",     # 全部成交
    "1": "part_traded",    # 部分成交
    "2": "not_traded",     # 未成交
    "3": "canceled",       # 已撤销
    "4": "part_canceled",  # 部分撤销
    "5": "unknown",        # 未知
    "a": "not_traded",     # 未成交
    "b": "trading",        # 正在申报
}


class CtpMdSpi(ctp.CThostFtdcMdSpi):
    """行情回调处理 — 在 CTP 原生线程上被调用"""

    def __init__(self, client: "CtpClient"):
        super().__init__()
        self._client = client

    def OnFrontConnected(self):
        logger.info("[CTP Md] 行情前置连接成功")
        self._client._md_connected = True
        self._client._notify({"type": "md_connected", "ok": True})
        self._login_md()

    def OnFrontDisconnected(self, nReason):
        logger.warning(f"[CTP Md] 行情前置断开 reason={nReason}")
        self._client._md_connected = False
        self._client._notify({"type": "md_connected", "ok": False})

    def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
        if pRspInfo.ErrorID == 0:
            trading_day = pRspUserLogin.CZCETime  # 实际取 TradingDay
            logger.info(f"[CTP Md] 行情登录成功")
            self._client._md_logged_in = True
            self._client._subscribe_symbols()
        else:
            logger.error(f"[CTP Md] 行情登录失败: {pRspInfo.ErrorID} {pRspInfo.ErrorMsg}")

    def OnRtnDepthMarketData(self, pData: ctp.CThostFtdcDepthMarketDataField):
        """行情 Tick 回调"""
        tick = GoldTickData(
            symbol=pData.InstrumentID,
            exchange="SHFE",
            datetime=datetime.now(),
            last_price=pData.LastPrice if pData.LastPrice < 1e8 else 0,
            last_volume=pData.Volume,
            open_interest=pData.OpenInterest,
        )
        self._client._on_tick(tick)

    def _login_md(self):
        field = ctp.CThostFtdcReqUserLoginField()
        field.BrokerID = self._client._cfg.broker_id
        field.UserID = self._client._cfg.user_id
        field.Password = self._client._cfg.password
        self._client._md_api.ReqUserLogin(field, 1)


class CtpTraderSpi(ctp.CThostFtdcTraderSpi):
    """交易回调处理"""

    def __init__(self, client: "CtpClient"):
        super().__init__()
        self._client = client
        self._authenticated = False

    def OnFrontConnected(self):
        logger.info("[CTP Trader] 交易前置连接成功")
        self._client._td_connected = True
        self._client._notify({"type": "td_connected", "ok": True})
        self._authenticate()

    def OnFrontDisconnected(self, nReason):
        logger.warning(f"[CTP Trader] 交易前置断开 reason={nReason}")
        self._client._td_connected = False
        self._client._notify({"type": "td_connected", "ok": False})

    def OnRspAuthenticate(self, pRspAuthenticate, pRspInfo, nRequestID, bIsLast):
        if pRspInfo.ErrorID == 0:
            logger.info("[CTP Trader] 认证成功")
            self._authenticated = True
            self._login()
        else:
            # 如果认证失败（旧版CTP不需要认证），直接尝试登录
            logger.warning(f"[CTP Trader] 认证失败 ({pRspInfo.ErrorID}), 直接登录")
            self._login()

    def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
        if pRspInfo.ErrorID == 0:
            logger.info(f"[CTP Trader] 交易登录成功 front_id={pRspUserLogin.FrontID} session_id={pRspUserLogin.SessionID}")
            self._client._td_logged_in = True
            self._client._front_id = pRspUserLogin.FrontID
            self._client._session_id = pRspUserLogin.SessionID
        else:
            logger.error(f"[CTP Trader] 交易登录失败: {pRspInfo.ErrorID} {pRspInfo.ErrorMsg}")

    def OnRspOrderInsert(self, pInputOrder, pRspInfo, nRequestID, bIsLast):
        """下单回报"""
        ref = pInputOrder.RequestID
        if pRspInfo.ErrorID != 0:
            logger.warning(f"[CTP] 下单失败 ref={ref}: {pRspInfo.ErrorMsg}")
            self._client._notify({"type": "order_rejected", "ref": ref, "error": pRspInfo.ErrorMsg})
        else:
            logger.info(f"[CTP] 下单成功 ref={ref}")

    def OnRtnOrder(self, pOrder: ctp.CThostFtdcOrderField):
        """订单状态推送"""
        ref = pOrder.OrderRef
        status = _ORDER_STATUS_MAP.get(pOrder.OrderStatus, "unknown")
        logger.info(f"[CTP] 订单状态 ref={ref} status={status} traded={pOrder.VolumeTraded}")
        self._client._notify({
            "type": "order_status",
            "ref": ref,
            "status": status,
            "traded_volume": pOrder.VolumeTraded,
            "price": pOrder.LimitPrice,
        })

    def OnRtnTrade(self, pTrade: ctp.CThostFtdcTradeField):
        """成交回报"""
        ref = pTrade.OrderRef
        logger.info(f"[CTP] 成交 ref={ref} {pTrade.InstrumentID} {pTrade.Direction} {pTrade.Volume}手 @{pTrade.Price}")
        self._client._notify({
            "type": "trade",
            "ref": ref,
            "symbol": pTrade.InstrumentID,
            "direction": "long" if pTrade.Direction == _THOST_OPT_LONG else "short",
            "volume": pTrade.Volume,
            "price": pTrade.Price,
            "trade_id": pTrade.TradeID,
        })

    def OnRspQryInvestorPosition(self, pPosition, pRspInfo, nRequestID, bIsLast):
        """持仓查询回报"""
        if pPosition:
            self._client._position_result.append({
                "symbol": pPosition.InstrumentID,
                "direction": "long" if pPosition.PosiDirection == _THOST_OPT_LONG else "short",
                "volume": pPosition.Position,
                "avg_price": pPosition.OpenCost / pPosition.Position if pPosition.Position > 0 else 0,
                "pnl": pPosition.PositionProfit,
                "margin": pPosition.UseMargin,
                "yd_volume": pPosition.YdPosition,  # 昨仓
            })
        if bIsLast:
            self._client._position_done.set()

    def OnRspQryTradingAccount(self, pAccount, pRspInfo, nRequestID, bIsLast):
        """资金查询回报"""
        if pAccount:
            self._client._account_result = {
                "balance": pAccount.Balance,
                "available": pAccount.Available,
                "margin": pAccount.CurrMargin,
                "pnl": pAccount.PositionProfit,
                "close_pnl": pAccount.CloseProfit,
                "frozen_margin": pAccount.FrozenMargin,
                "frozen_commission": pAccount.FrozenCommission,
            }
        if bIsLast:
            self._client._account_done.set()

    def OnRspQryOrder(self, pOrder, pRspInfo, nRequestID, bIsLast):
        """委托查询回报"""
        if pOrder:
            self._client._order_result.append({
                "ref": pOrder.OrderRef,
                "symbol": pOrder.InstrumentID,
                "direction": "buy" if pOrder.CombOffsetFlag[0] == _THOST_F_OPEN and pOrder.Direction == _THOST_OPT_LONG else "sell",
                "price": pOrder.LimitPrice,
                "volume": pOrder.VolumeTotalOriginal,
                "traded": pOrder.VolumeTraded,
                "status": _ORDER_STATUS_MAP.get(pOrder.OrderStatus, "unknown"),
                "insert_time": f"{pOrder.InsertDate} {pOrder.InsertTime}",
            })
        if bIsLast:
            self._client._order_done.set()

    def _authenticate(self):
        try:
            field = ctp.CThostFtdcReqAuthenticateField()
            field.BrokerID = self._client._cfg.broker_id
            field.UserID = self._client._cfg.user_id
            # UserProductInfo 在 CTP API 中为 char[11]，超过会抛 TypeError
            field.UserProductInfo = self._client._cfg.app_id[:11]
            field.AuthCode = self._client._cfg.auth_code
            self._client._td_api.ReqAuthenticate(field, 1)
        except Exception as e:
            logger.warning(f"[CTP Trader] 认证字段设置失败 ({e}), 直接登录")
            self._login()

    def _login(self):
        field = ctp.CThostFtdcReqUserLoginField()
        field.BrokerID = self._client._cfg.broker_id
        field.UserID = self._client._cfg.user_id
        field.Password = self._client._cfg.password
        self._client._td_api.ReqUserLogin(field, 2)


class CtpClient:
    """
    CTP 客户端 — 行情订阅 + 交易下单

    使用方式:
        client = CtpClient(config, loop)
        await client.start()
        # ... 使用 ...
        await client.stop()
    """

    def __init__(self, config: CtpConfig, loop: asyncio.AbstractEventLoop = None):
        self._cfg = config
        self._loop = loop or asyncio.get_event_loop()

        # CTP API 实例
        self._md_api: Optional[ctp.CThostFtdcMdApi] = None
        self._td_api: Optional[ctp.CThostFtdcTraderApi] = None

        # SPI 实例（必须保持引用，防止 GC）
        self._md_spi: Optional[CtpMdSpi] = None
        self._td_spi: Optional[CtpTraderSpi] = None

        # 状态
        self._running = False
        self._md_connected = False
        self._td_connected = False
        self._md_logged_in = False
        self._td_logged_in = False
        self._front_id = 0
        self._session_id = 0
        self._thread: Optional[threading.Thread] = None

        # 异步队列
        self.tick_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.event_callback: Optional[Callable] = None

        # 查询同步（CTP 查询是异步回调，用 Event 同步）
        self._position_result: list = []
        self._position_done: threading.Event = threading.Event()
        self._account_result: dict = {}
        self._account_done: threading.Event = threading.Event()
        self._order_result: list = []
        self._order_done: threading.Event = threading.Event()

        # 行情回调挂钩（给 BarAssembler 用）
        self.on_tick_callback: Optional[Callable] = None

        # 主力合约检测
        self._open_interest_map: dict[str, float] = {}  # symbol → open_interest
        self._main_contract: str = ""

    # ── 主力合约检测 ──────────────────────────────────────────

    def get_main_contract(self) -> str:
        """根据持仓量返回当前主力合约"""
        if not self._main_contract and self._open_interest_map:
            self._main_contract = max(self._open_interest_map, key=self._open_interest_map.get)
        return self._main_contract

    def _update_open_interest(self, symbol: str, oi: float):
        """更新持仓量，触发主力切换"""
        if oi > 0:
            old_main = self._main_contract
            self._open_interest_map[symbol] = max(self._open_interest_map.get(symbol, 0), oi)
            new_main = max(self._open_interest_map, key=self._open_interest_map.get)
            if new_main != old_main and old_main:
                logger.info(f"[CTP] 主力合约切换: {old_main} → {new_main} (OI: {self._open_interest_map})")
            self._main_contract = new_main

    # ── 生命周期 ──────────────────────────────────────────────

    async def start(self):
        """启动 CTP 连接（非阻塞）"""
        if self._running:
            logger.warning("[CTP] 已在运行")
            return

        valid, msg = self._cfg.is_valid()
        if not valid:
            logger.warning(f"[CTP] {msg}")
            return

        self._running = True
        self._position_result = []
        self._account_result = {}
        self._order_result = []

        # CTP 对象创建（Create/Register/Init）是纯内存操作，很快
        # Init() 启动的后台网络连接异步进行
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._init_sync)

        self._start_monitor()
        logger.info("[CTP] 初始化完成（后台线程连接中）")

        self._start_monitor()
        logger.info("[CTP] 初始化完成（后台线程连接中）")

    def _init_sync(self):
        """CTP API 同步初始化（在线程池中运行）"""
        flow_dir = os.path.join("data", "backend", "gold", "ctp_flow")
        os.makedirs(flow_dir, exist_ok=True)

        self._md_api = ctp.CThostFtdcMdApi.CreateFtdcMdApi(
            os.path.join(flow_dir, "md").encode("utf-8").decode("utf-8")
        )
        self._md_spi = CtpMdSpi(self)
        self._md_api.RegisterSpi(self._md_spi)
        self._md_api.RegisterFront(self._cfg.md_address)
        self._md_api.Init()

        self._td_api = ctp.CThostFtdcTraderApi.CreateFtdcTraderApi(
            os.path.join(flow_dir, "td").encode("utf-8").decode("utf-8")
        )
        self._td_spi = CtpTraderSpi(self)
        self._td_api.RegisterSpi(self._td_spi)
        self._td_api.RegisterFront(self._cfg.td_address)
        self._td_api.SubscribePrivateTopic(ctp.THOST_TERT_QUICK)  # type: ignore
        self._td_api.SubscribePublicTopic(ctp.THOST_TERT_QUICK)   # type: ignore
        self._td_api.Init()

    async def stop(self):
        """关闭 CTP 连接"""
        self._running = False
        if self._md_api:
            self._md_api.Release()
            self._md_api = None
        if self._td_api:
            self._td_api.Release()
            self._td_api = None
        self._md_connected = False
        self._td_connected = False
        self._md_logged_in = False
        self._td_logged_in = False
        logger.info("[CTP] 已关闭")

    # ── 下单 ───────────────────────────────────────────────────

    def send_order(self, symbol: str, direction: SignalDirection,
                   price: float, volume: int,
                   order_ref: int = 0) -> int:
        """
        下单

        Args:
            symbol: 合约代码（如 au2608）
            direction: LONG/SHORT/CLOSE_LONG/CLOSE_SHORT
            price: 价格
            volume: 手数
            order_ref: 引用号（0 自动生成）

        Returns:
            order_ref
        """
        if not self._td_logged_in:
            logger.error("[CTP] 未登录，无法下单")
            return -1

        ref = order_ref or int(time.time() * 1000) % 1000000

        field = ctp.CThostFtdcInputOrderField()
        field.BrokerID = self._cfg.broker_id
        field.InvestorID = self._cfg.user_id
        field.InstrumentID = symbol
        field.LimitPrice = price
        field.VolumeTotalOriginal = volume
        field.OrderRef = str(ref)
        field.UserID = self._cfg.user_id

        # 组合开平标志 + 方向
        if direction in (SignalDirection.LONG, SignalDirection.SHORT):
            # 开仓
            field.CombOffsetFlag[0] = _THOST_F_OPEN
        else:
            # 平仓 — SimNow 统一平昨，简化处理
            field.CombOffsetFlag[0] = _THOST_F_CLOSE

        if direction in (SignalDirection.LONG, SignalDirection.CLOSE_SHORT):
            field.Direction = _THOST_OPT_LONG
        else:
            field.Direction = _THOST_OPT_SHORT

        # 限价单
        field.OrderPriceType = "2"  # THOST_FTDC_OPT_LimitPrice
        field.CombHedgeFlag[0] = "1"  # 投机
        field.ContingentCondition = "1"  # 立即
        field.ForceCloseReason[0] = "0"
        field.IsAutoSuspend = 0
        field.TimeCondition = "3"  # 当日有效
        field.VolumeCondition = "1"  # 任意数量
        field.MinVolume = 1

        result = self._td_api.ReqOrderInsert(field, ref)
        if result == 0:
            logger.info(f"[CTP] 下单成功: {symbol} {direction.value} {volume}手 @{price} ref={ref}")
        else:
            logger.error(f"[CTP] 下单失败: result={result}")

        return ref

    def cancel_order(self, symbol: str, order_ref: int, front_id: int = 0,
                     session_id: int = 0) -> int:
        """撤单"""
        field = ctp.CThostFtdcInputOrderActionField()
        field.BrokerID = self._cfg.broker_id
        field.InvestorID = self._cfg.user_id
        field.InstrumentID = symbol
        field.OrderRef = str(order_ref)
        field.FrontID = front_id or self._front_id
        field.SessionID = session_id or self._session_id
        field.ActionFlag = "0"  # 删除
        return self._td_api.ReqOrderAction(field, 1)

    # ── 查询 ───────────────────────────────────────────────────

    async def query_positions(self, symbol: str = "") -> list[dict]:
        """查询持仓（异步等待 CTP 回报）"""
        if not self._td_logged_in:
            return []
        self._position_result = []
        self._position_done.clear()
        field = ctp.CThostFtdcQryInvestorPositionField()
        field.BrokerID = self._cfg.broker_id
        field.InvestorID = self._cfg.user_id
        if symbol:
            field.InstrumentID = symbol
        self._td_api.ReqQryInvestorPosition(field, 1)
        done = await self._loop.run_in_executor(None, lambda: self._position_done.wait(5.0))
        if not done:
            logger.warning("[CTP] 查询持仓超时")
        return self._position_result

    async def query_account(self) -> dict:
        """查询资金账户"""
        if not self._td_logged_in:
            return {}
        self._account_result = {}
        self._account_done.clear()
        field = ctp.CThostFtdcQryTradingAccountField()
        field.BrokerID = self._cfg.broker_id
        field.InvestorID = self._cfg.user_id
        self._td_api.ReqQryTradingAccount(field, 1)
        done = await self._loop.run_in_executor(None, lambda: self._account_done.wait(5.0))
        if not done:
            logger.warning("[CTP] 查询资金超时")
        return self._account_result

    async def query_orders(self, symbol: str = "") -> list[dict]:
        """查询当日委托"""
        if not self._td_logged_in:
            return []
        self._order_result = []
        self._order_done.clear()
        field = ctp.CThostFtdcQryOrderField()
        field.BrokerID = self._cfg.broker_id
        field.InvestorID = self._cfg.user_id
        if symbol:
            field.InstrumentID = symbol
        self._td_api.ReqQryOrder(field, 1)
        done = await self._loop.run_in_executor(None, lambda: self._order_done.wait(5.0))
        if not done:
            logger.warning("[CTP] 查询委托超时")
        return self._order_result

    # ── 状态 ───────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "md_connected": self._md_connected,
            "td_connected": self._td_connected,
            "md_logged_in": self._md_logged_in,
            "td_logged_in": self._td_logged_in,
            "symbols": self._cfg.symbols,
            "main_contract": self.get_main_contract(),
            "open_interest": dict(self._open_interest_map),
        }

    # ── 内部 ───────────────────────────────────────────────────

    def _on_tick(self, tick: GoldTickData):
        """行情 Tick → 主力检测 + 入队列 + 回调"""
        # 主力合约检测
        self._update_open_interest(tick.symbol, tick.open_interest)

        try:
            self.tick_queue.put_nowait(tick)
        except asyncio.QueueFull:
            pass  # 丢弃最旧的，保持最新数据
        if self.on_tick_callback:
            try:
                self.on_tick_callback(tick)
            except Exception as e:
                logger.debug(f"[CTP] tick callback error: {e}")

    def _notify(self, msg: dict):
        """CTP 事件 → 异步通知"""
        if self.event_callback:
            self._loop.call_soon_threadsafe(self.event_callback, msg)
        else:
            logger.debug(f"[CTP] event (no callback): {msg.get('type')}")

    def _subscribe_symbols(self):
        """订阅合约行情"""
        ret = self._md_api.SubscribeMarketData(self._cfg.symbols, len(self._cfg.symbols))
        logger.info(f"[CTP] 订阅行情: {self._cfg.symbols} ret={ret}")

    def _start_monitor(self):
        """后台监控线程 — 检查连接状态，自动重连"""
        def _monitor():
            while self._running:
                time.sleep(30)
                if not self._md_connected and self._running:
                    logger.warning("[CTP] 行情断开，等待自动重连...")
                if not self._td_connected and self._running:
                    logger.warning("[CTP] 交易断开，等待自动重连...")
        t = threading.Thread(target=_monitor, daemon=True, name="ctp-monitor")
        t.start()
