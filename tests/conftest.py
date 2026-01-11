"""Pytest configuration and fixtures."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models.sync import SyncMetadata
from app.services.intempus_client import IntempusClient
from app.services.sync_service import SyncService
from app.services.system_b_client import SystemBClient


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Create initial SyncMetadata
        sync_metadata = SyncMetadata(id=1)
        session.add(sync_metadata)
        session.commit()
        yield session
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def mock_intempus_client():
    """Create a mock IntempusClient."""
    client = MagicMock(spec=IntempusClient)
    client.get_cases = AsyncMock(return_value=([], 0))
    client.get_case = AsyncMock()
    client.create_case = AsyncMock()
    client.update_case = AsyncMock()
    client.delete_case = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_system_b_client():
    """Create a mock SystemBClient."""
    client = MagicMock(spec=SystemBClient)
    client.get_cases = AsyncMock(return_value=([], 0))
    client.get_case = AsyncMock()
    client.create_case = AsyncMock()
    client.update_case = AsyncMock()
    client.delete_case = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_sync_service(db_session, mock_intempus_client, mock_system_b_client):
    with patch.object(SyncService, "__init__", lambda self: None):
        sync_service = SyncService()
        sync_service.intempus_client = mock_intempus_client
        sync_service.system_b_client = mock_system_b_client

        with patch("app.services.sync_service.Session") as mock_session_class:
            mock_session_class.return_value.__enter__.return_value = db_session
            mock_session_class.return_value.__exit__.return_value = None
            yield sync_service


@pytest.fixture
def sample_case_data():
    """Sample case data for testing."""
    return {
        "id": 1,
        "customer_id": "customer1",
        "number": "1",
        "name": "Test 1",
        "logical_timestamp": 100,
    }
