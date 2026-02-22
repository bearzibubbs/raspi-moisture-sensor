import logging
from typing import Dict, Any, Optional
from pathlib import Path
import httpx
import yaml
from config import AgentConfig


logger = logging.getLogger(__name__)


class ConfigUpdateError(Exception):
    """Raised when config update fails"""
    pass


class ConfigManager:
    def __init__(
        self,
        orchestrator_url: str,
        agent_id: str,
        agent_token: str,
        config_path: Path,
        timeout: int = 30
    ):
        """
        Initialize config manager.

        Args:
            orchestrator_url: Base URL of orchestrator
            agent_id: Unique agent identifier
            agent_token: Permanent agent token for authentication
            config_path: Path to local config file
            timeout: Request timeout in seconds
        """
        self.orchestrator_url = orchestrator_url.rstrip('/')
        self.agent_id = agent_id
        self.agent_token = agent_token
        self.config_path = config_path
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

        # Track config version to detect updates
        self.current_version: Optional[int] = None

    async def pull_config(self) -> Optional[Dict[str, Any]]:
        """
        Pull latest config from orchestrator.

        Returns:
            Config dict if available, None if no update

        Raises:
            ConfigUpdateError: If pull operation fails
        """
        if not self.agent_token:
            raise ConfigUpdateError("Agent token required to pull config")

        url = f"{self.orchestrator_url}/agents/{self.agent_id}/config"
        headers = {"Authorization": f"Bearer {self.agent_token}"}

        try:
            logger.debug(f"Pulling config for agent {self.agent_id}")
            response = await self.client.get(url, headers=headers)

            if response.status_code == 200:
                config_data = response.json()
                logger.debug(f"Received config version {config_data.get('version')}")
                return config_data
            elif response.status_code == 304:
                # No modification - config hasn't changed
                logger.debug("Config up to date (304 Not Modified)")
                return None
            else:
                error_msg = f"Config pull failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise ConfigUpdateError(error_msg)

        except httpx.HTTPError as e:
            error_msg = f"Network error during config pull: {e}"
            logger.warning(error_msg)
            raise ConfigUpdateError(error_msg)

    async def check_for_updates(self) -> bool:
        """
        Check if config has been updated on orchestrator.

        Returns:
            True if update available (or first pull with valid config), False otherwise

        Raises:
            ConfigUpdateError: If check operation fails
        """
        config_data = await self.pull_config()

        if config_data is None:
            return False

        new_version = config_data.get('version')
        config_content = config_data.get('config')

        # First check: apply orchestrator config so local file matches (if we have valid content)
        if self.current_version is None:
            if config_content:
                logger.info("First config pull: applying orchestrator config")
                return True
            # No config on orchestrator yet - just set baseline so we don't treat future v1 as "update"
            self.current_version = new_version or 0
            return False

        if new_version and new_version > self.current_version:
            logger.info(f"Config update available: v{self.current_version} -> v{new_version}")
            return True

        return False

    async def apply_config_update(self) -> Optional[Dict[str, Any]]:
        """
        Pull config from orchestrator and apply to local file.

        Returns:
            The new config dict if config was updated, None if no update available

        Raises:
            ConfigUpdateError: If update operation fails
        """
        config_data = await self.pull_config()

        if config_data is None:
            logger.debug("No config update available")
            return None

        new_version = config_data.get('version')
        config_content = config_data.get('config')

        if not config_content:
            logger.debug("Orchestrator has no config content yet, skipping apply")
            return None

        # Validate config before applying
        try:
            # Test that new config is valid
            AgentConfig(**config_content)
        except Exception as e:
            error_msg = f"Invalid config from orchestrator: {e}"
            logger.error(error_msg)
            raise ConfigUpdateError(error_msg)

        # Backup current config
        backup_path = self.config_path.with_suffix('.yaml.backup')
        if self.config_path.exists():
            logger.info(f"Backing up current config to {backup_path}")
            backup_path.write_text(self.config_path.read_text())

        # Write new config
        try:
            logger.info(f"Applying config version {new_version}")
            with open(self.config_path, 'w') as f:
                yaml.dump(config_content, f, default_flow_style=False)

            self.current_version = new_version
            logger.info(f"Config updated successfully to version {new_version}")
            return config_content

        except Exception as e:
            error_msg = f"Failed to write config file: {e}"
            logger.error(error_msg)

            # Restore backup if write failed
            if backup_path.exists():
                logger.info("Restoring config from backup")
                self.config_path.write_text(backup_path.read_text())

            raise ConfigUpdateError(error_msg)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
