#!/usr/bin/env python3
"""
Pi Agent - Moisture Sensor Data Collector

Main entry point for the Pi agent service. Coordinates sensor reading,
data storage, synchronization, and configuration management.
"""

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path
import uvicorn
from config import AgentConfig
from storage import StorageManager
from registration import RegistrationClient
from sync import SyncClient
from config_manager import ConfigManager
from scheduler import AgentScheduler
from api import app, init_api


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/pi-agent/agent.log')
    ]
)
logger = logging.getLogger(__name__)


class PiAgent:
    def __init__(self, config_path: Path):
        """Initialize Pi Agent"""
        self.config_path = config_path
        self.config: AgentConfig = None
        self.storage: StorageManager = None
        self.registration_client: RegistrationClient = None
        self.sync_client: SyncClient = None
        self.config_manager: ConfigManager = None
        self.scheduler: AgentScheduler = None
        self.adc = None
        self.start_time = time.time()
        self.running = False

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self.running = False

    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Pi Agent")

        # Load configuration
        logger.info(f"Loading configuration from {self.config_path}")
        self.config = AgentConfig.from_yaml(self.config_path)
        logger.info(f"Agent ID: {self.config.agent.id}")

        # Initialize storage
        logger.info("Initializing storage")
        self.storage = StorageManager(self.config.storage.database_path)
        self.storage.initialize()

        # Check if agent is already registered
        agent_token = self.storage.get_metadata('agent_token')

        if not agent_token and not self.config.agent.bootstrap_token:
            raise RuntimeError(
                "Agent not registered and no bootstrap token configured. "
                "Set BOOTSTRAP_TOKEN environment variable."
            )

        # Initialize registration client
        self.registration_client = RegistrationClient(
            orchestrator_url=self.config.agent.orchestrator_url,
            agent_id=self.config.agent.id,
            bootstrap_token=self.config.agent.bootstrap_token,
            agent_token=agent_token
        )

        # Register if needed
        if not agent_token:
            logger.info("Agent not registered, registering with orchestrator")
            await self._register()
            agent_token = self.storage.get_metadata('agent_token')
        else:
            logger.info("Agent already registered")
            self.registration_client.agent_token = agent_token

        # Initialize sync client
        self.sync_client = SyncClient(
            orchestrator_url=self.config.agent.orchestrator_url,
            agent_id=self.config.agent.id,
            agent_token=agent_token,
            storage=self.storage
        )

        # Initialize config manager
        self.config_manager = ConfigManager(
            orchestrator_url=self.config.agent.orchestrator_url,
            agent_id=self.config.agent.id,
            agent_token=agent_token,
            config_path=self.config_path
        )

        # Initialize ADC (Grove HAT)
        logger.info("Initializing ADC")
        try:
            from grove.adc import ADC
            self.adc = ADC()
        except ImportError:
            logger.warning("grove.py not available, running in simulation mode")
            # Mock ADC for testing without hardware
            self.adc = MockADC()

        # Initialize API
        init_api(self.config, self.storage, self.start_time)

        # Initialize scheduler
        logger.info("Initializing scheduler")
        self.scheduler = AgentScheduler(
            config=self.config,
            storage=self.storage,
            sync_client=self.sync_client,
            config_manager=self.config_manager,
            adc=self.adc
        )

        logger.info("Agent initialization complete")

    async def _register(self):
        """Register agent with orchestrator"""
        import socket

        hostname = socket.gethostname()
        hardware = "Raspberry Pi Zero 2 W"  # Could detect this dynamically

        try:
            result = await self.registration_client.register(hostname, hardware)

            # Store agent token
            agent_token = result.get('agent_token')
            if not agent_token:
                raise RuntimeError("Registration succeeded but no agent_token received")

            self.storage.set_metadata('agent_token', agent_token)
            self.registration_client.agent_token = agent_token

            logger.info("Agent registration successful")

        except Exception as e:
            logger.error(f"Agent registration failed: {e}")
            raise

    async def run(self):
        """Run the agent"""
        try:
            await self.initialize()

            self.running = True

            # Start scheduler
            self.scheduler.start()

            # Send initial heartbeat
            try:
                await self.registration_client.heartbeat()
                logger.info("Initial heartbeat sent")
            except Exception as e:
                logger.warning(f"Initial heartbeat failed: {e}")

            # Start API server in background
            if self.config.local_api.enabled:
                api_server = asyncio.create_task(self._run_api_server())

            logger.info("Agent is running")

            # Main loop - keep alive and send periodic heartbeats
            while self.running:
                await asyncio.sleep(60)

                # Send heartbeat every minute
                try:
                    await self.registration_client.heartbeat()
                    logger.debug("Heartbeat sent")
                except Exception as e:
                    logger.warning(f"Heartbeat failed: {e}")

        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            raise

        finally:
            await self.shutdown()

    async def _run_api_server(self):
        """Run FastAPI server"""
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self.config.local_api.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def shutdown(self):
        """Shutdown agent gracefully"""
        logger.info("Shutting down agent")

        # Stop scheduler
        if self.scheduler:
            self.scheduler.shutdown()

        # Close HTTP clients
        if self.registration_client:
            await self.registration_client.close()

        if self.sync_client:
            await self.sync_client.close()

        if self.config_manager:
            await self.config_manager.close()

        # Close storage
        if self.storage:
            self.storage.close()

        logger.info("Agent shutdown complete")


class MockADC:
    """Mock ADC for testing without hardware"""
    def read(self, channel):
        """Return simulated ADC value"""
        import random
        # Simulate capacitive sensor values (300-800 range)
        return random.randint(400, 700)


async def main():
    """Main entry point"""
    # Default config path
    config_path = Path("/opt/pi-agent/config.yaml")

    # Allow override via command line
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    # Create and run agent
    agent = PiAgent(config_path)

    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
