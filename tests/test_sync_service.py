"""Tests for SyncService synchronization scenarios."""

import pytest
from unittest.mock import patch
from sqlmodel import select
from app.services.sync_service import SyncService
from app.models.sync import SyncCaseIntempus, SyncCaseSystemB


class TestInitialSync:
    """Test initial synchronization scenarios."""

    @pytest.mark.asyncio
    async def test_initial_sync_cases_from_intempus_to_system_b(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """Initial sync - cases from Intempus are created in System B."""
        # Setup: Intempus has cases, System B is empty
        intempus_case = sample_case_data.copy()
        intempus_case["logical_timestamp"] = 100

        mock_intempus_client.get_cases.return_value = ([intempus_case], 100)
        mock_system_b_client.get_cases.return_value = ([], 0)

        # Mock System B create_case to return created case
        created_case = intempus_case.copy()
        created_case["id"] = 1  # System B assigns new ID
        created_case["logical_timestamp"] = 1
        mock_system_b_client.create_case.return_value = created_case

        # Create SyncService with mocked clients
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run initial sync
                await sync_service.sync(is_full_sync=True, is_initialization=True)

        # Verify: Case was created in System B
        mock_system_b_client.create_case.assert_called_once()
        call_args = mock_system_b_client.create_case.call_args[0][0]
        assert call_args["customer_id"] == "customer1"
        assert call_args["number"] == "1"

        # Verify: SyncCaseSystemB was created
        sync_case = db_session.exec(
            select(SyncCaseSystemB).where(
                SyncCaseSystemB.customer_id == "customer1",
                SyncCaseSystemB.number == "1",
            )
        ).first()
        assert sync_case is not None
        assert sync_case.case_id == 1
        assert sync_case.logical_timestamp == 1

    @pytest.mark.asyncio
    async def test_initial_sync_cases_from_system_b_to_intempus(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """Initial sync - cases from System B are created in Intempus."""
        # Setup: System B has cases, Intempus is empty
        system_b_case = sample_case_data.copy()
        system_b_case["logical_timestamp"] = 50

        mock_intempus_client.get_cases.return_value = ([], 0)
        mock_system_b_client.get_cases.return_value = ([system_b_case], 50)

        # Mock Intempus create_case to return created case
        created_case = system_b_case.copy()
        created_case["id"] = 1  # Intempus assigns new ID
        created_case["logical_timestamp"] = 200
        mock_intempus_client.create_case.return_value = created_case
        # After create_case, sync_service calls get_case to get reliable logical_timestamp
        mock_intempus_client.get_case.return_value = created_case

        # Create SyncService with mocked clients
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run initial sync
                await sync_service.sync(is_full_sync=True, is_initialization=True)

        # Verify: Case was created in Intempus
        mock_intempus_client.create_case.assert_called_once()
        call_args = mock_intempus_client.create_case.call_args[0][0]
        assert call_args["customer_id"] == "customer1"
        assert call_args["number"] == "1"

        # Verify: SyncCaseIntempus was created
        sync_case = db_session.exec(
            select(SyncCaseIntempus).where(
                SyncCaseIntempus.customer_id == "customer1",
                SyncCaseIntempus.number == "1",
            )
        ).first()
        assert sync_case is not None
        assert sync_case.case_id == 1
        assert sync_case.logical_timestamp == 200


class TestPostInitCreation:
    """Test creation scenarios after initial sync."""

    @pytest.mark.asyncio
    async def test_creation_from_intempus_after_initial_sync(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """New case from Intempus is created in System B after initial sync."""
        # Setup: Existing sync data
        existing_intempus_case = sample_case_data.copy()
        existing_intempus_case["id"] = 1
        existing_intempus_case["logical_timestamp"] = 100

        # Create existing sync record
        sync_intempus = SyncCaseIntempus(
            case_id=1,
            customer_id="customer1",
            number="1",
            logical_timestamp=100,
        )
        db_session.add(sync_intempus)
        db_session.commit()

        # New case from Intempus
        new_intempus_case = {
            "id": 2,
            "customer_id": "customer2",
            "number": "2",
            "name": "New Case",
            "logical_timestamp": 150,
        }

        mock_intempus_client.get_cases.return_value = (
            [existing_intempus_case, new_intempus_case],
            150,
        )
        mock_system_b_client.get_cases.return_value = ([], 0)

        # Mock System B create_case
        created_case = new_intempus_case.copy()
        created_case["id"] = 10  # System B assigns new ID
        created_case["logical_timestamp"] = 5
        mock_system_b_client.create_case.return_value = created_case

        # Create SyncService
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run incremental sync
                await sync_service.sync(is_full_sync=False, is_initialization=False)

        # Verify: New case was created in System B
        create_calls = [call[0][0] for call in mock_system_b_client.create_case.call_args_list]
        assert any(
            case["customer_id"] == "customer2" and case["number"] == "2" for case in create_calls
        )

        # Verify: SyncCaseSystemB was created for new case
        sync_case = db_session.exec(
            select(SyncCaseSystemB).where(
                SyncCaseSystemB.customer_id == "customer2",
                SyncCaseSystemB.number == "2",
            )
        ).first()
        assert sync_case is not None
        assert sync_case.case_id == 10

    @pytest.mark.asyncio
    async def test_creation_from_system_b_after_initial_sync(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """New case from System B is created in Intempus after initial sync."""
        # Setup: Existing sync data
        existing_system_b_case = sample_case_data.copy()
        existing_system_b_case["id"] = 1
        existing_system_b_case["logical_timestamp"] = 50

        # Create existing sync record
        sync_system_b = SyncCaseSystemB(
            case_id=1,
            customer_id="customer1",
            number="1",
            logical_timestamp=50,
        )
        db_session.add(sync_system_b)
        db_session.commit()

        # New case from System B
        new_system_b_case = {
            "id": 2,
            "customer_id": "customer2",
            "number": "2",
            "name": "New Case",
            "logical_timestamp": 60,
        }

        mock_intempus_client.get_cases.return_value = ([], 0)
        mock_system_b_client.get_cases.return_value = (
            [existing_system_b_case, new_system_b_case],
            60,
        )

        # Mock Intempus create_case
        created_case = new_system_b_case.copy()
        created_case["id"] = 20  # Intempus assigns new ID
        created_case["logical_timestamp"] = 250
        mock_intempus_client.create_case.return_value = created_case
        # After create_case, sync_service calls get_case to get reliable logical_timestamp
        mock_intempus_client.get_case.return_value = created_case

        # Create SyncService
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run incremental sync
                await sync_service.sync(is_full_sync=False, is_initialization=False)

        # Verify: New case was created in Intempus
        create_calls = [call[0][0] for call in mock_intempus_client.create_case.call_args_list]
        assert any(
            case["customer_id"] == "customer2" and case["number"] == "2" for case in create_calls
        )

        # Verify: SyncCaseIntempus was created for new case
        sync_case = db_session.exec(
            select(SyncCaseIntempus).where(
                SyncCaseIntempus.customer_id == "customer2",
                SyncCaseIntempus.number == "2",
            )
        ).first()
        assert sync_case is not None
        assert sync_case.case_id == 20


class TestPostInitUpdate:
    """Test update scenarios after initial sync."""

    @pytest.mark.asyncio
    async def test_update_from_intempus_propagated_to_system_b(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """Update from Intempus is propagated to System B."""
        # Setup: Existing sync data
        intempus_case = sample_case_data.copy()
        intempus_case["id"] = 1
        intempus_case["logical_timestamp"] = 150  # Updated from 100

        system_b_case = sample_case_data.copy()
        system_b_case["id"] = 10
        system_b_case["logical_timestamp"] = 5  # Not updated

        # Create sync records
        sync_intempus = SyncCaseIntempus(
            case_id=1,
            customer_id="customer1",
            number="1",
            logical_timestamp=100,  # Old timestamp
        )
        sync_system_b = SyncCaseSystemB(
            case_id=10,
            customer_id="customer1",
            number="1",
            logical_timestamp=5,
        )
        db_session.add(sync_intempus)
        db_session.add(sync_system_b)
        db_session.commit()

        mock_intempus_client.get_cases.return_value = ([intempus_case], 150)
        mock_system_b_client.get_cases.return_value = ([system_b_case], 5)

        # Mock System B update_case
        updated_case = system_b_case.copy()
        updated_case["logical_timestamp"] = 6
        mock_system_b_client.update_case.return_value = updated_case

        # Create SyncService
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run incremental sync
                await sync_service.sync(is_full_sync=False, is_initialization=False)

        # Verify: System B was updated
        mock_system_b_client.update_case.assert_called_once()
        call_args = mock_system_b_client.update_case.call_args
        assert call_args[0][0] == 10  # case_id
        assert call_args[1]["if_match"] == 5  # logical_timestamp as keyword argument

        # Verify: SyncCaseSystemB was updated
        db_session.refresh(sync_system_b)
        assert sync_system_b.logical_timestamp == 6

    @pytest.mark.asyncio
    async def test_update_from_system_b_propagated_to_intempus(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """Update from System B is propagated to Intempus."""
        # Setup: Existing sync data
        intempus_case = sample_case_data.copy()
        intempus_case["id"] = 1
        intempus_case["logical_timestamp"] = 100  # Not updated

        system_b_case = sample_case_data.copy()
        system_b_case["id"] = 10
        system_b_case["logical_timestamp"] = 6  # Updated from 5

        # Create sync records
        sync_intempus = SyncCaseIntempus(
            case_id=1,
            customer_id="customer1",
            number="1",
            logical_timestamp=100,
        )
        sync_system_b = SyncCaseSystemB(
            case_id=10,
            customer_id="customer1",
            number="1",
            logical_timestamp=5,  # Old timestamp
        )
        db_session.add(sync_intempus)
        db_session.add(sync_system_b)
        db_session.commit()

        mock_intempus_client.get_cases.return_value = ([intempus_case], 100)
        mock_system_b_client.get_cases.return_value = ([system_b_case], 6)

        # Mock Intempus get_case and update_case
        mock_intempus_client.get_case.return_value = intempus_case  # Still at 100
        updated_intempus_case = intempus_case.copy()
        updated_intempus_case["logical_timestamp"] = 200
        mock_intempus_client.update_case.return_value = updated_intempus_case
        mock_intempus_client.get_case.side_effect = [
            intempus_case,  # First call to verify timestamp
            updated_intempus_case,  # Second call after update
        ]

        # Create SyncService
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run incremental sync
                await sync_service.sync(is_full_sync=False, is_initialization=False)

        # Verify: Intempus was updated
        assert mock_intempus_client.update_case.called
        call_args = mock_intempus_client.update_case.call_args
        assert call_args[0][0] == 1  # case_id

        # Verify: SyncCaseIntempus was updated
        db_session.refresh(sync_intempus)
        assert sync_intempus.logical_timestamp == 200


class TestPostInitDeletion:
    """Test deletion scenarios after initial sync."""

    @pytest.mark.asyncio
    async def test_deletion_from_intempus_propagated_to_system_b(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """Deletion from Intempus is propagated to System B (full sync only)."""
        # Setup: Existing sync data
        system_b_case = sample_case_data.copy()
        system_b_case["id"] = 10
        system_b_case["logical_timestamp"] = 5

        # Create sync records
        sync_intempus = SyncCaseIntempus(
            case_id=1,
            customer_id="customer1",
            number="1",
            logical_timestamp=100,
        )
        sync_system_b = SyncCaseSystemB(
            case_id=10,
            customer_id="customer1",
            number="1",
            logical_timestamp=5,
        )
        db_session.add(sync_intempus)
        db_session.add(sync_system_b)
        db_session.commit()

        # Intempus doesn't return the case (deleted), System B still has it
        mock_intempus_client.get_cases.return_value = ([], 0)
        mock_system_b_client.get_cases.return_value = ([system_b_case], 5)

        # Mock System B delete_case
        mock_system_b_client.delete_case.return_value = None

        # Create SyncService
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run full sync (deletions only detected in full sync)
                await sync_service.sync(is_full_sync=True, is_initialization=False)

        # Verify: System B case was deleted
        mock_system_b_client.delete_case.assert_called_once_with(10)

        # Verify: SyncCaseSystemB was deleted
        sync_case = db_session.exec(
            select(SyncCaseSystemB).where(SyncCaseSystemB.case_id == 10)
        ).first()
        assert sync_case is None

    @pytest.mark.asyncio
    async def test_deletion_from_system_b_propagated_to_intempus(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """Deletion from System B is propagated to Intempus (full sync only)."""
        # Setup: Existing sync data
        intempus_case = sample_case_data.copy()
        intempus_case["id"] = 1
        intempus_case["logical_timestamp"] = 100

        # Create sync records
        sync_intempus = SyncCaseIntempus(
            case_id=1,
            customer_id="customer1",
            number="1",
            logical_timestamp=100,
        )
        sync_system_b = SyncCaseSystemB(
            case_id=10,
            customer_id="customer1",
            number="1",
            logical_timestamp=5,
        )
        db_session.add(sync_intempus)
        db_session.add(sync_system_b)
        db_session.commit()

        # System B doesn't return the case (deleted), Intempus still has it
        mock_intempus_client.get_cases.return_value = ([intempus_case], 100)
        mock_system_b_client.get_cases.return_value = ([], 0)

        # Mock Intempus delete_case
        mock_intempus_client.delete_case.return_value = None

        # Create SyncService
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run full sync (deletions only detected in full sync)
                await sync_service.sync(is_full_sync=True, is_initialization=False)

        # Verify: Intempus case was deleted
        mock_intempus_client.delete_case.assert_called_once_with(1)

        # Verify: SyncCaseIntempus was deleted
        sync_case = db_session.exec(
            select(SyncCaseIntempus).where(SyncCaseIntempus.case_id == 1)
        ).first()
        assert sync_case is None


class TestCircularUpdatePrevention:
    """Test prevention of circular updates."""

    @pytest.mark.asyncio
    async def test_no_circular_update_intempus_to_system_b(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """No circular update when Intempus updates trigger System B update and vice versa."""
        # Setup: Intempus case updated
        intempus_case = sample_case_data.copy()
        intempus_case["id"] = 1
        intempus_case["logical_timestamp"] = 150  # Updated

        system_b_case = sample_case_data.copy()
        system_b_case["id"] = 10
        system_b_case["logical_timestamp"] = 5  # Not updated

        # Create sync records
        sync_intempus = SyncCaseIntempus(
            case_id=1,
            customer_id="customer1",
            number="1",
            logical_timestamp=100,  # Old timestamp
        )
        sync_system_b = SyncCaseSystemB(
            case_id=10,
            customer_id="customer1",
            number="1",
            logical_timestamp=5,
        )
        db_session.add(sync_intempus)
        db_session.add(sync_system_b)
        db_session.commit()

        mock_intempus_client.get_cases.return_value = ([intempus_case], 150)
        mock_system_b_client.get_cases.return_value = ([system_b_case], 5)

        # Mock System B update_case
        updated_system_b_case = system_b_case.copy()
        updated_system_b_case["logical_timestamp"] = 6
        mock_system_b_client.update_case.return_value = updated_system_b_case

        # Create SyncService
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run first sync
                await sync_service.sync(is_full_sync=False, is_initialization=False)

            # Verify: System B was updated once
            assert mock_system_b_client.update_case.call_count == 1

            updated_system_b_case_2 = updated_system_b_case.copy()
            updated_system_b_case_2["logical_timestamp"] = 6  # Same timestamp
            mock_system_b_client.get_cases.return_value = ([updated_system_b_case_2], 6)
            mock_intempus_client.get_case.return_value = intempus_case

            # Run second sync
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                await sync_service.sync(is_full_sync=False, is_initialization=False)

            # Verify: System B was NOT updated again (no circular update)
            assert not mock_intempus_client.update_case.called

    @pytest.mark.asyncio
    async def test_no_circular_update_system_b_to_intempus(
        self, db_session, mock_intempus_client, mock_system_b_client, sample_case_data
    ):
        """No circular update when System B updates trigger Intempus update and vice versa."""
        # Setup: System B case updated
        intempus_case = sample_case_data.copy()
        intempus_case["id"] = 1
        intempus_case["logical_timestamp"] = 100  # Not updated

        system_b_case = sample_case_data.copy()
        system_b_case["id"] = 10
        system_b_case["logical_timestamp"] = 6  # Updated

        # Create sync records
        sync_intempus = SyncCaseIntempus(
            case_id=1,
            customer_id="customer1",
            number="1",
            logical_timestamp=100,
        )
        sync_system_b = SyncCaseSystemB(
            case_id=10,
            customer_id="customer1",
            number="1",
            logical_timestamp=5,  # Old timestamp
        )
        db_session.add(sync_intempus)
        db_session.add(sync_system_b)
        db_session.commit()

        mock_intempus_client.get_cases.return_value = ([intempus_case], 100)
        mock_system_b_client.get_cases.return_value = ([system_b_case], 6)

        # Mock Intempus get_case and update_case
        mock_intempus_client.get_case.return_value = intempus_case
        updated_intempus_case = intempus_case.copy()
        updated_intempus_case["logical_timestamp"] = 200
        mock_intempus_client.update_case.return_value = updated_intempus_case
        mock_intempus_client.get_case.side_effect = [
            intempus_case,  # First call to verify timestamp
            updated_intempus_case,  # Second call after update
        ]

        # Create SyncService
        with patch.object(SyncService, "__init__", lambda self: None):
            sync_service = SyncService()
            sync_service.intempus_client = mock_intempus_client
            sync_service.system_b_client = mock_system_b_client

            # Mock Session to return our test session
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                # Run first sync
                await sync_service.sync(is_full_sync=False, is_initialization=False)

            # Verify: Intempus was updated once
            assert mock_intempus_client.update_case.call_count == 1

            # Reset mocks and run sync again
            updated_intempus_case_2 = updated_intempus_case.copy()
            updated_intempus_case_2["logical_timestamp"] = 200  # Same timestamp
            mock_intempus_client.get_cases.return_value = ([updated_intempus_case_2], 200)

            # Run second sync
            with patch("app.services.sync_service.Session") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = db_session
                mock_session_class.return_value.__exit__.return_value = None

                await sync_service.sync(is_full_sync=False, is_initialization=False)

        # Verify: Intempus was NOT updated again (no circular update)
        assert not mock_system_b_client.update_case.called
