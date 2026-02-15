import logging
from typing import List, Dict, Any, Optional
import httpx
from storage import StorageManager


logger = logging.getLogger(__name__)


class SyncError(Exception):
    """Raised when sync operation fails"""
    pass


class SyncClient:
    def __init__(
        self,
        orchestrator_url: str,
        agent_id: str,
        agent_token: str,
        storage: StorageManager,
        timeout: int = 30
    ):
        """
        Initialize sync client.

        Args:
            orchestrator_url: Base URL of orchestrator
            agent_id: Unique agent identifier
            agent_token: Permanent agent token for authentication
            storage: StorageManager instance
            timeout: Request timeout in seconds
        """
        self.orchestrator_url = orchestrator_url.rstrip('/')
        self.agent_id = agent_id
        self.agent_token = agent_token
        self.storage = storage
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def sync_readings(self, batch_size: int = 100) -> Dict[str, Any]:
        """
        Sync unsynced readings to orchestrator in batches.

        Args:
            batch_size: Maximum number of readings to sync per request

        Returns:
            Dict with sync statistics (synced_count, failed_count, etc.)

        Raises:
            SyncError: If sync operation fails
        """
        if not self.agent_token:
            raise SyncError("Agent token required for sync")

        # Get unsynced readings
        unsynced = self.storage.get_unsynced_readings(limit=batch_size)

        if not unsynced:
            logger.debug("No unsynced readings to upload")
            return {
                "synced_count": 0,
                "failed_count": 0,
                "total_pending": 0
            }

        logger.info(f"Syncing {len(unsynced)} readings to orchestrator")

        # Prepare readings for upload (remove internal fields)
        readings_payload = []
        reading_ids = []

        for reading in unsynced:
            reading_ids.append(reading['id'])
            # Remove db-specific fields
            payload = {k: v for k, v in reading.items()
                      if k not in ['id', 'synced', 'created_at']}
            readings_payload.append(payload)

        # Upload to orchestrator
        url = f"{self.orchestrator_url}/agents/{self.agent_id}/readings"
        headers = {"Authorization": f"Bearer {self.agent_token}"}
        payload = {"readings": readings_payload}

        try:
            response = await self.client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                # Mark readings as synced
                self.storage.mark_synced(reading_ids)

                logger.info(f"Successfully synced {len(reading_ids)} readings")

                # Get remaining unsynced count
                remaining = len(self.storage.get_unsynced_readings(limit=1))

                return {
                    "synced_count": len(reading_ids),
                    "failed_count": 0,
                    "total_pending": remaining
                }
            else:
                error_msg = f"Sync failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise SyncError(error_msg)

        except httpx.HTTPError as e:
            error_msg = f"Network error during sync: {e}"
            logger.warning(error_msg)
            raise SyncError(error_msg)

    async def sync_all_readings(self, batch_size: int = 100) -> Dict[str, Any]:
        """
        Sync all unsynced readings, handling multiple batches if needed.

        Args:
            batch_size: Maximum number of readings per batch

        Returns:
            Dict with total sync statistics

        Raises:
            SyncError: If any batch fails
        """
        total_synced = 0
        total_failed = 0

        while True:
            result = await self.sync_readings(batch_size=batch_size)
            total_synced += result['synced_count']
            total_failed += result['failed_count']

            # If no more pending, we're done
            if result['total_pending'] == 0:
                break

            # If nothing was synced this round, avoid infinite loop
            if result['synced_count'] == 0:
                logger.warning("No readings synced in this batch, stopping")
                break

        logger.info(f"Sync complete: {total_synced} synced, {total_failed} failed")

        return {
            "synced_count": total_synced,
            "failed_count": total_failed,
            "total_pending": 0
        }

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
