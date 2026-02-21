import logging
from typing import Dict, Any, Optional
import httpx


logger = logging.getLogger(__name__)


class RegistrationError(Exception):
    """Raised when agent registration fails"""
    pass


class RegistrationClient:
    def __init__(
        self,
        orchestrator_url: str,
        agent_id: str,
        bootstrap_token: Optional[str] = None,
        agent_token: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize registration client.

        Args:
            orchestrator_url: Base URL of orchestrator
            agent_id: Unique agent identifier
            bootstrap_token: Bootstrap token for initial registration
            agent_token: Permanent agent token (if already registered)
            timeout: Request timeout in seconds
        """
        self.orchestrator_url = orchestrator_url.rstrip('/')
        self.agent_id = agent_id
        self.bootstrap_token = bootstrap_token
        self.agent_token = agent_token
        self.timeout = timeout

        self.client = httpx.AsyncClient(timeout=timeout)

    async def register(self, hostname: str, hardware: str) -> Dict[str, Any]:
        """
        Register agent with orchestrator using bootstrap token.

        Returns:
            Registration response with agent_token and config

        Raises:
            RegistrationError: If registration fails
        """
        if not self.bootstrap_token:
            raise RegistrationError("Bootstrap token required for registration")

        url = f"{self.orchestrator_url}/agents/register"
        headers = {"Authorization": f"Bearer {self.bootstrap_token}"}
        payload = {
            "agent_id": self.agent_id,
            "hostname": hostname,
            "hardware": hardware
        }

        try:
            logger.info(f"Registering agent {self.agent_id} with orchestrator")
            response = await self.client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                logger.info("Agent registration successful")
                return data
            else:
                error_msg = f"Registration failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise RegistrationError(error_msg)

        except httpx.HTTPError as e:
            error_msg = f"Network error during registration: {e}"
            logger.error(error_msg)
            raise RegistrationError(error_msg)

    async def heartbeat(self) -> Dict[str, Any]:
        """
        Send heartbeat to orchestrator.

        Returns:
            Heartbeat response

        Raises:
            RegistrationError: If heartbeat fails
        """
        if not self.agent_token:
            raise RegistrationError("Agent token required for heartbeat")

        url = f"{self.orchestrator_url}/agents/{self.agent_id}/heartbeat"
        headers = {"Authorization": f"Bearer {self.agent_token}"}

        try:
            response = await self.client.post(url, headers=headers, json={})

            if response.status_code == 200:
                return response.json()
            else:
                error_msg = f"Heartbeat failed with status {response.status_code}"
                logger.warning(error_msg)
                raise RegistrationError(error_msg)

        except httpx.HTTPError as e:
            logger.warning(f"Heartbeat network error: {e}")
            raise RegistrationError(str(e))

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
