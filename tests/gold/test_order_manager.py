"""订单管理器测试"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime
import pytest

from gold.core.models import GoldSignal, SignalDirection, OrderStatus
from gold.risk.order_manager import OrderManager


class TestOrderManager:
    def test_create_order_from_signal(self):
        mgr = OrderManager()
        signal = GoldSignal(
            signal_id="sig1", strategy_id="test", strategy_name="test",
            symbol="AU0", direction=SignalDirection.LONG,
            price=500, volume=2, stop_loss=495, reason="test",
            created_at=datetime.now(),
        )
        order = mgr.create_from_signal(signal)
        assert order.signal_id == "sig1"
        assert order.status == OrderStatus.ACCEPTED
        assert order.volume == 2

    def test_create_order_rejected_by_risk(self):
        mgr = OrderManager()
        signal = GoldSignal(
            signal_id="sig2", strategy_id="test", strategy_name="test",
            symbol="AU0", direction=SignalDirection.SHORT,
            price=500, volume=1, created_at=datetime.now(),
        )
        order = mgr.create_from_signal(signal, risk_reason="回撤超限")
        assert order.status == OrderStatus.REJECTED
        assert order.risk_check == "回撤超限"

    def test_fill_order(self):
        mgr = OrderManager()
        signal = GoldSignal(
            signal_id="sig3", strategy_id="test", strategy_name="test",
            symbol="AU0", direction=SignalDirection.LONG,
            price=500, volume=3, created_at=datetime.now(),
        )
        order = mgr.create_from_signal(signal)
        trade = mgr.fill(order.order_id, fill_price=501, fill_volume=3)
        assert trade is not None
        assert trade.volume == 3
        assert trade.price == 501
        # order should be fully filled
        assert mgr.get_order(order.order_id).status == OrderStatus.FILLED

    def test_partial_fill(self):
        mgr = OrderManager()
        signal = GoldSignal(
            signal_id="sig4", strategy_id="test", strategy_name="test",
            symbol="AU0", direction=SignalDirection.LONG,
            price=500, volume=5, created_at=datetime.now(),
        )
        order = mgr.create_from_signal(signal)

        # First partial fill
        t1 = mgr.fill(order.order_id, fill_price=500, fill_volume=2)
        assert t1 is not None
        assert order.filled_volume == 2
        assert order.status == OrderStatus.PARTIAL

        # Second fill
        t2 = mgr.fill(order.order_id, fill_price=502, fill_volume=3)
        assert t2 is not None
        assert order.filled_volume == 5
        assert order.status == OrderStatus.FILLED

    def test_cancel_order(self):
        mgr = OrderManager()
        signal = GoldSignal(
            signal_id="sig5", strategy_id="test", strategy_name="test",
            symbol="AU0", direction=SignalDirection.LONG,
            price=500, volume=1, created_at=datetime.now(),
        )
        order = mgr.create_from_signal(signal)
        assert mgr.cancel(order.order_id, "手工撤单") is True
        assert mgr.get_order(order.order_id).status == OrderStatus.CANCELLED

    def test_cancel_filled_order_fails(self):
        mgr = OrderManager()
        signal = GoldSignal(
            signal_id="sig6", strategy_id="test", strategy_name="test",
            symbol="AU0", direction=SignalDirection.LONG,
            price=500, volume=1, created_at=datetime.now(),
        )
        order = mgr.create_from_signal(signal)
        mgr.fill(order.order_id, fill_price=500)
        assert mgr.cancel(order.order_id) is False

    def test_fill_nonexistent_order(self):
        mgr = OrderManager()
        assert mgr.fill("no_such_order", 500) is None

    def test_get_open_orders(self):
        mgr = OrderManager()
        s1 = GoldSignal(signal_id="s1", strategy_id="t", strategy_name="t",
                        symbol="AU0", direction=SignalDirection.LONG, price=500, volume=1, created_at=datetime.now())
        s2 = GoldSignal(signal_id="s2", strategy_id="t", strategy_name="t",
                        symbol="AU0", direction=SignalDirection.SHORT, price=500, volume=1, created_at=datetime.now())
        o1 = mgr.create_from_signal(s1)
        mgr.create_from_signal(s2)
        mgr.fill(o1.order_id, 501)
        open_orders = mgr.get_open_orders()
        assert len(open_orders) == 1  # s2 still open, s1 filled

    def test_get_trades(self):
        mgr = OrderManager()
        s = GoldSignal(signal_id="s3", strategy_id="t", strategy_name="t",
                       symbol="AU0", direction=SignalDirection.LONG, price=500, volume=2, created_at=datetime.now())
        o = mgr.create_from_signal(s)
        mgr.fill(o.order_id, 501, 1)
        mgr.fill(o.order_id, 502, 1)
        trades = mgr.get_trades()
        assert len(trades) == 2
