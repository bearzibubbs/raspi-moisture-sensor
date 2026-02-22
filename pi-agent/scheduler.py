import logging
import asyncio
from typing import List, Optional, Callable, Awaitable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from collector import SensorCollector
from storage import StorageManager, Reading
from sync import SyncClient
from config_manager import ConfigManager
from config import AgentConfig


logger = logging.getLogger(__name__)


class AgentScheduler:
    def __init__(
        self,
        config: AgentConfig,
        storage: StorageManager,
        sync_client: SyncClient,
        config_manager: ConfigManager,
        adc,
        on_config_applied: Optional[Callable[[dict], Awaitable[None]]] = None
    ):
        """
        Initialize agent scheduler.

        Args:
            config: Agent configuration
            storage: StorageManager instance
            sync_client: SyncClient for uploading readings
            config_manager: ConfigManager for config updates
            adc: ADC instance from grove.py
            on_config_applied: Optional async callback(new_config_dict) when config is applied
        """
        self.config = config
        self.storage = storage
        self.sync_client = sync_client
        self.config_manager = config_manager
        self.adc = adc
        self.on_config_applied = on_config_applied

        # Create sensor collectors
        self.collectors: List[SensorCollector] = []
        for sensor_config in config.sensors:
            collector = SensorCollector(adc, sensor_config)
            self.collectors.append(collector)

        # Initialize scheduler
        self.scheduler = AsyncIOScheduler()
        self._setup_jobs()

    def _setup_jobs(self):
        """Set up scheduled jobs"""
        # Read sensors every 1 minute
        self.scheduler.add_job(
            self._read_all_sensors,
            trigger=IntervalTrigger(seconds=60),
            id='read_sensors',
            name='Read all sensors',
            replace_existing=True
        )

        # Sync readings based on config interval
        self.scheduler.add_job(
            self._sync_readings,
            trigger=IntervalTrigger(seconds=self.config.agent.sync_interval_seconds),
            id='sync_readings',
            name='Sync readings to orchestrator',
            replace_existing=True
        )

        # Pull config updates based on config interval
        self.scheduler.add_job(
            self._check_config_updates,
            trigger=IntervalTrigger(seconds=self.config.agent.config_pull_interval_seconds),
            id='check_config',
            name='Check for config updates',
            replace_existing=True
        )

        # Cleanup old synced readings daily
        self.scheduler.add_job(
            self._cleanup_old_readings,
            trigger=IntervalTrigger(hours=24),
            id='cleanup_readings',
            name='Cleanup old synced readings',
            replace_existing=True
        )

        logger.info("Scheduled jobs configured:")
        logger.info(f"  - Read sensors: every 60 seconds")
        logger.info(f"  - Sync readings: every {self.config.agent.sync_interval_seconds} seconds")
        logger.info(f"  - Check config: every {self.config.agent.config_pull_interval_seconds} seconds")
        logger.info(f"  - Cleanup readings: every 24 hours")

    async def _read_all_sensors(self):
        """Read all configured sensors and store readings"""
        logger.debug("Reading all sensors")

        for collector in self.collectors:
            try:
                reading = collector.read()

                if reading:
                    # Store reading
                    reading_id = self.storage.store_reading(reading)
                    logger.debug(
                        f"Sensor {reading.sensor_channel} ({reading.sensor_name}): "
                        f"{reading.moisture_percent:.1f}% (raw: {reading.raw_value})"
                    )
                else:
                    logger.warning(
                        f"Sensor {collector.config.channel} "
                        f"({collector.config.labels.sensor_name}) failed to read"
                    )

            except Exception as e:
                logger.error(
                    f"Error reading sensor {collector.config.channel}: {e}",
                    exc_info=True
                )

    async def _sync_readings(self):
        """Sync unsynced readings to orchestrator"""
        try:
            logger.debug("Syncing readings to orchestrator")
            result = await self.sync_client.sync_readings(batch_size=100)

            if result['synced_count'] > 0:
                logger.info(
                    f"Synced {result['synced_count']} readings, "
                    f"{result['total_pending']} remaining"
                )

        except Exception as e:
            logger.warning(f"Sync failed: {e}")

    async def _check_config_updates(self):
        """Check for and apply config updates from orchestrator"""
        try:
            logger.debug("Checking for config updates")
            has_update = await self.config_manager.check_for_updates()

            if has_update:
                logger.info("Config update available, applying...")
                new_config_dict = await self.config_manager.apply_config_update()

                if new_config_dict is not None:
                    if self.on_config_applied:
                        await self.on_config_applied(new_config_dict)
                    else:
                        logger.warning(
                            "Config file updated. Restart agent to use new config."
                        )

        except Exception as e:
            logger.warning(f"Config update check failed: {e}")

    def set_config(self, config: AgentConfig):
        """Update in-memory config and rebuild sensor collectors (e.g. after config pull)."""
        self.config = config
        self.collectors = [
            SensorCollector(self.adc, sensor_config)
            for sensor_config in config.sensors
        ]
        logger.info(f"Reloaded config: {len(config.sensors)} sensor(s)")

    async def _cleanup_old_readings(self):
        """Cleanup old synced readings from storage"""
        try:
            logger.debug("Cleaning up old synced readings")
            days = self.config.storage.cleanup_synced_older_than_days
            deleted = self.storage.cleanup_old_synced(days=days)

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old readings (older than {days} days)")

                # Run VACUUM to reclaim space
                self.storage.vacuum()
                logger.info("Database vacuumed")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}", exc_info=True)

    def start(self):
        """Start the scheduler"""
        logger.info("Starting scheduler")
        self.scheduler.start()

    def shutdown(self):
        """Shutdown the scheduler gracefully"""
        logger.info("Shutting down scheduler")
        self.scheduler.shutdown(wait=True)
