"""Intempus API client."""

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger(__name__)


class IntempusClient:
    """Client for interacting with Intempus API."""

    def __init__(self):
        self.base_url = settings.INTEMPUS_API_BASE_URL
        self.api_key = settings.INTEMPUS_API_KEY
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": self.api_key},
            timeout=30.0,
        )
        self.case_endpoint = "/web/v1/case/"

    async def get_cases(
        self, logical_timestamp: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Retrieve a list of projects from Intempus with pagination support.

        Fetches all pages of cases using cursor-based pagination. The endpoint
        returns cases in pages with limit of INTEMPUS_PAGINATION_LIMIT cases per page.

        Args:
            logical_timestamp (int): Optional filter. If provided, returns only projects
                with logical_timestamp greater than this value (uses logical_timestamp__gt).

        Returns:
            tuple[list[dict[str, Any]], int]: Tuple of
                (list of all case data, max committed logical_timestamp from header).
        """
        all_cases = []
        max_logical_timestamp = 0

        # Build initial URL
        params = {
            "pagination_type": "cursor",
            "limit": settings.INTEMPUS_PAGINATION_LIMIT,
        }
        if logical_timestamp is not None:
            params["logical_timestamp__gt"] = logical_timestamp

        next_url = self.case_endpoint
        has_more_pages = True

        while has_more_pages:
            if "?" in next_url:
                # Subsequent page
                response = await self.client.get(next_url)
            else:
                # First page
                response = await self.client.get(next_url, params=params)

            response.raise_for_status()
            data = response.json()

            # Extract cases from objects array
            page_cases = data.get("objects", [])
            all_cases.extend(page_cases)

            # Update max logical_timestamp from header
            page_max_timestamp = int(response.headers.get("Logical-Timestamp", "0"))
            max_logical_timestamp = max(max_logical_timestamp, page_max_timestamp)

            # Check for next page
            meta = data.get("meta", {})
            next_url = meta.get("next")
            has_more_pages = next_url is not None
            logger.debug(f"Fetching next page: {next_url}")

        logger.info(f"Fetched {len(all_cases)} cases across all pages")
        return all_cases, max_logical_timestamp

    async def get_case(self, case_id: int) -> dict[str, Any]:
        """Retrieve a single project by ID from Intempus.

        Args:
            case_id (int): The case ID.

        Returns:
            dict[str, Any]: Case data.
        """
        response = await self.client.get(f"{self.case_endpoint}{case_id}/")
        response.raise_for_status()
        return response.json()

    async def create_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new case in Intempus.

        Args:
            case_data: Case data including optional creation_id.

        Returns:
            dict[str, Any]: Created case data.
        """
        response = await self.client.post(self.case_endpoint, json=case_data)
        response.raise_for_status()
        return response.json()

    async def update_case(self, case_id: int, case_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing case in Intempus.

        Args:
            case_id (int): The case ID.
            case_data (dict[str, Any]): Case data to update.

        Returns:
            dict[str, Any]: Updated case data (note: may not include updated logical_timestamp).
        """
        response = await self.client.put(f"{self.case_endpoint}{case_id}/", json=case_data)
        response.raise_for_status()
        return response.json()

    async def delete_case(self, case_id: int) -> None:
        """Delete a project from Intempus.

        Args:
            case_id (int): The case ID.
        """
        response = await self.client.delete(f"{self.case_endpoint}{case_id}/")
        response.raise_for_status()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
