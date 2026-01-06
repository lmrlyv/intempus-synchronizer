"""System B API client."""

import httpx
from typing import Any
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SystemBClient:
    """Client for interacting with System B API."""

    def __init__(self):
        self.base_url = settings.SYSTEM_B_API_BASE_URL
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
        )
        self.case_endpoint = f"{settings.API_PREFIX}/case/"

    async def get_cases(
        self, logical_timestamp: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Retrieve a list of cases from System B.

        Args:
            logical_timestamp (int): Optional filter. If provided, returns only cases
                with logical_timestamp greater than this value.

        Returns:
            tuple[list[dict[str, Any]], int]: Tuple of
                (list of all case data, max committed logical_timestamp from header).
        """
        params = {}
        if logical_timestamp is not None:
            params["logical_timestamp"] = logical_timestamp

        response = await self.client.get(self.case_endpoint, params=params)
        response.raise_for_status()

        max_logical_timestamp = int(response.headers.get("Logical-Timestamp", "0"))
        cases = response.json()

        return cases, max_logical_timestamp

    async def get_case(self, case_id: int) -> dict[str, Any]:
        """Retrieve a single case by ID from System B.

        Args:
            case_id (int): The case ID.

        Returns:
            dict[str, Any]: Case data.
        """
        response = await self.client.get(f"{self.case_endpoint}{case_id}")
        response.raise_for_status()
        return response.json()

    async def create_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new case in System B.

        Args:
            case_data (dict[str, Any]): Case data including optional creation_id.

        Returns:
            dict[str, Any]: Created case data with id and logical_timestamp.
        """
        response = await self.client.post(self.case_endpoint, json=case_data)
        response.raise_for_status()
        return response.json()

    async def update_case(
        self, case_id: int, case_data: dict[str, Any], if_match: int | None = None
    ) -> dict[str, Any]:
        """Update an existing case in System B.

        Args:
            case_id (int): The case ID.
            case_data (dict[str, Any]): Case data to update.
            if_match (int): Optional logical_timestamp for conditional update.

        Returns:
            dict[str, Any]: Updated case data with newly assigned logical_timestamp.
        """
        headers = {}
        if if_match is not None:
            headers["If-Match"] = str(if_match)

        response = await self.client.put(
            f"{self.case_endpoint}{case_id}", json=case_data, headers=headers
        )
        response.raise_for_status()
        return response.json()

    async def delete_case(self, case_id: int) -> dict[str, Any]:
        """Delete a case from System B.

        Args:
            case_id (int): The case ID.

        Returns:
            dict[str, Any]: Deleted case data.
        """
        response = await self.client.delete(f"{self.case_endpoint}{case_id}")
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
