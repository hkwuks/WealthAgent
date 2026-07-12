"""FundQuant APScheduler 配置与生命周期管理"""

import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
from loguru import logger

from ..core.config import fund_quant_settings
from ..core.errors import DataCollectionError


class FundQuantScheduler:
    """基金量化定时任务调度器"""

    def __init__(self):
        self._scheduler = None

    def init_scheduler(self):
        """初始化 APScheduler"""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

            jobstores = {
                "default": SQLAlchemyJobStore(url=fund_quant_settings.SCHEDULER_JOBSTORE_URL)
            }
            job_defaults = {
                "max_instances": fund_quant_settings.SCHEDULER_MAX_INSTANCES,
                "misfire_grace_time": fund_quant_settings.SCHEDULER_MISFIRE_GRACE,
                "coalesce": fund_quant_settings.SCHEDULER_COALESCE,
            }
            self._scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                job_defaults=job_defaults,
            )
            logger.info("FundQuant 调度器初始化完成")
        except ImportError:
            logger.warning("APScheduler 未安装，调度器功能不可用")
            self._scheduler = None

    def start(self):
        """启动调度器"""
        if self._scheduler:
            self._scheduler.start()
            logger.info("FundQuant 调度器已启动")

    def shutdown(self, wait: bool = True):
        """关闭调度器"""
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=wait)
                logger.info("FundQuant 调度器已关闭")
            except Exception as e:
                logger.warning(f"FundQuant 调度器关闭异常: {e}")

    def add_daily_job(self, func, job_id: str, hour: int = 15, minute: int = 30,
                      args: Optional[list] = None, kwargs: Optional[dict] = None):
        """添加每日定时任务"""
        if not self._scheduler:
            logger.warning(f"调度器未初始化，跳过任务注册: {job_id}")
            return
        self._scheduler.add_job(
            func,
            trigger="cron",
            hour=hour,
            minute=minute,
            id=job_id,
            replace_existing=True,
            args=args or [],
            kwargs=kwargs or {},
        )
        logger.info(f"定时任务 [{job_id}] 已注册: 每日 {hour}:{minute}")

    def add_backtest_job(self, func, backtest_id: str, args: Optional[list] = None):
        """添加回测任务（立即执行一次）"""
        if not self._scheduler:
            logger.warning(f"调度器未初始化，跳过回测任务: {backtest_id}")
            return
        self._scheduler.add_job(
            func,
            trigger="date",
            run_date=datetime.now(),
            id=backtest_id,
            replace_existing=False,
            args=args or [],
            max_instances=1,
        )

    @property
    def is_running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running


# 全局单例
fund_quant_scheduler = FundQuantScheduler()


async def daily_collection_job():
    """每日数据采集任务"""
    from ..data.collector import fund_data_collector
    from ..data.storage import save_nav_points, get_all_fund_codes
    logger.info("开始每日数据采集...")

    fund_codes = get_all_fund_codes()
    if not fund_codes:
        logger.info("无基金需要采集")
        return

    success_count = 0
    for fund_code in fund_codes:
        try:
            points = await fund_data_collector.fetch_nav_history(fund_code)
            if points:
                save_nav_points(points)
                success_count += 1
            await asyncio.sleep(0.1)  # 速率限制
        except DataCollectionError as e:
            logger.warning(f"采集失败 [{fund_code}]: {e}")
        except Exception as e:
            logger.error(f"采集异常 [{fund_code}]: {e}")

    logger.info(f"每日数据采集完成: {success_count}/{len(fund_codes)} 成功")
