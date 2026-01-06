"""Synchronization service for bidirectional sync between Intempus and System B."""

from httpx import HTTPStatusError
from sqlmodel import Session, select

from app.core.db import engine
from app.core.logging import get_logger
from app.models.case import CaseCreate, CaseUpdate
from app.models.sync import SyncCaseIntempus, SyncCaseSystemB, SyncMetadata
from app.services.intempus_client import IntempusClient
from app.services.system_b_client import SystemBClient


logger = get_logger(__name__)


class SyncService:
    """Service for synchronizing cases between Intempus (System A) and System B.

    These sync scenarios exists:
    1. Initialization sync (full fetch)
    2. Case exists in Intempus but missing in System B
    3. Case exists in System B but missing in Intempus
    4. Case updated in Intempus but not in System B
    5. Case updated in System B but not in Intempus
    6. Case updated in both systems (Intempus takes precedence)
    7. Case deleted in Intempus
    8. Case deleted in System B
    """

    def __init__(self):
        self.intempus_client = IntempusClient()
        self.system_b_client = SystemBClient()

    async def sync(self, is_full_sync: bool = False, is_initialization: bool = False) -> None:
        """Perform bidirectional synchronization.

        Fetches from both systems simultaneously, then processes all sync scenarios.

        Args:
            is_full_sync: If True, performs full sync (no logical_timestamp filter).
                If False, performs incremental sync.
            is_initialization: If True, performs initialization sync (full fetch).
                If False, performs incremental sync.
        """
        with Session(engine) as session:
            # Get sync metadata
            intempus_cases, intempus_max_timestamp, system_b_cases, system_b_max_timestamp = (
                await self._fetch_cases(session, is_full_sync)
            )

            # Check if this is initialization (no cases in sync tables)
            if is_initialization:
                logger.info("Initialization sync - storing all cases in sync tables")
                await self._initialize_sync_tables(session, intempus_cases, system_b_cases)
            else:
                # Process all sync scenarios
                await self._process_sync_scenarios(
                    session, intempus_cases, system_b_cases, is_full_sync
                )

            # Update sync metadata
            sync_metadata = session.get(SyncMetadata, 1)
            sync_metadata.last_intempus_logical_timestamp = intempus_max_timestamp
            sync_metadata.last_system_b_logical_timestamp = system_b_max_timestamp
            session.add(sync_metadata)
            session.commit()

            logger.info("Sync completed successfully")

    async def _fetch_cases(
        self, session: Session, is_full_sync: bool = False
    ) -> tuple[list[dict], int, list[dict], int]:
        """Fetch cases from both systems simultaneously.

        Args:
            session (Session): SQLModel session
            is_full_sync (bool, optional): If True, performs full sync (no logical_timestamp filter).
                If False, performs incremental sync.

        Returns:
            tuple[list[dict], int, list[dict], int]: Tuple containing:
                - list of Intempus cases
                - maximum logical timestamp from Intempus
                - list of System B cases
                - maximum logical timestamp from System B
        """
        sync_metadata = session.get(SyncMetadata, 1)
        if not sync_metadata:
            sync_metadata = SyncMetadata(id=1)
            session.add(sync_metadata)
            session.commit()
            session.refresh(sync_metadata)

        # Determine logical_timestamp filters
        intempus_timestamp = None if is_full_sync else sync_metadata.last_intempus_logical_timestamp
        system_b_timestamp = None if is_full_sync else sync_metadata.last_system_b_logical_timestamp

        # Fetch from both systems simultaneously
        logger.info("Fetching cases from both systems simultaneously...")
        intempus_task = self.intempus_client.get_cases(intempus_timestamp)
        system_b_task = self.system_b_client.get_cases(system_b_timestamp)

        intempus_cases, intempus_max_timestamp = await intempus_task
        system_b_cases, system_b_max_timestamp = await system_b_task

        logger.info(
            f"Fetched {len(intempus_cases)} cases from Intempus, "
            f"{len(system_b_cases)} cases from System B"
        )

        return intempus_cases, intempus_max_timestamp, system_b_cases, system_b_max_timestamp

    async def _initialize_sync_tables(
        self,
        session: Session,
        intempus_cases: list[dict],
        system_b_cases: list[dict],
    ) -> None:
        """Initialize sync tables with cases from both systems (Scenario 1)."""

        # Get all sync table records
        all_intempus_sync = session.exec(select(SyncCaseIntempus)).all()
        all_system_b_sync = session.exec(select(SyncCaseSystemB)).all()

        # Create lookup maps for sync tables
        intempus_sync_map = {(s.customer_id, s.number): s for s in all_intempus_sync}
        system_b_sync_map = {(s.customer_id, s.number): s for s in all_system_b_sync}

        # Store Intempus cases
        for case in intempus_cases:
            if (case.get("customer_id"), case.get("number")) not in intempus_sync_map:
                sync_case = SyncCaseIntempus(
                    case_id=case.get("id"),
                    customer_id=case.get("customer_id"),
                    number=case.get("number"),
                    logical_timestamp=case.get("logical_timestamp"),
                )
                session.add(sync_case)

        # Store System B cases
        for case in system_b_cases:
            if (case.get("customer_id"), case.get("number")) not in system_b_sync_map:
                sync_case = SyncCaseSystemB(
                    case_id=case.get("id"),
                    customer_id=case.get("customer_id"),
                    number=case.get("number"),
                    logical_timestamp=case.get("logical_timestamp"),
                )
                session.add(sync_case)

        session.commit()

        # Cross-check and create missing cases
        await self._create_missing_cases(session, intempus_cases, system_b_cases)

    async def _create_missing_cases(
        self,
        session: Session,
        intempus_cases: list[dict],
        system_b_cases: list[dict],
    ) -> None:
        """Create cases that exist in one system but not the other."""
        # Create lookup maps by (customer_id, number)
        intempus_map = {(c.get("customer_id"), c.get("number")): c for c in intempus_cases}
        system_b_map = {(c.get("customer_id"), c.get("number")): c for c in system_b_cases}

        # Cases in Intempus but not in System B
        for key, intempus_case in intempus_map.items():
            if key not in system_b_map:
                await self._propagate_creation_to_system_b(session, intempus_case)

        # Cases in System B but not in Intempus
        for key, system_b_case in system_b_map.items():
            if key not in intempus_map:
                await self._propagate_creation_to_intempus(session, system_b_case)

    async def _process_sync_scenarios(
        self,
        session: Session,
        intempus_cases: list[dict],
        system_b_cases: list[dict],
        is_full_sync: bool,
    ) -> None:
        """Process all sync scenarios (2-8)."""
        # Create lookup maps
        intempus_map = {(c.get("customer_id"), c.get("number")): c for c in intempus_cases}
        system_b_map = {(c.get("customer_id"), c.get("number")): c for c in system_b_cases}

        # Get all sync table records
        all_intempus_sync = session.exec(select(SyncCaseIntempus)).all()
        all_system_b_sync = session.exec(select(SyncCaseSystemB)).all()

        # Create lookup maps for sync tables
        intempus_sync_map = {(s.customer_id, s.number): s for s in all_intempus_sync}
        system_b_sync_map = {(s.customer_id, s.number): s for s in all_system_b_sync}

        # Process each case from Intempus
        for key, intempus_case in intempus_map.items():
            intempus_sync = intempus_sync_map.get(key)
            system_b_sync = system_b_sync_map.get(key)
            system_b_case = system_b_map.get(key)

            if not intempus_sync:
                # Case created in Intempus
                if not system_b_sync:
                    # Case created in Intempus but not in System B
                    # Propagate creation to System B
                    await self._propagate_creation_to_system_b(session, intempus_case)
                else:
                    # Case Created in Intempus and it already exists in System B
                    # Not clear what to do here, so store the logical_timestamp
                    await self._store_sync_case_intempus(
                        session,
                        intempus_case.get("id"),
                        intempus_case.get("customer_id"),
                        intempus_case.get("number"),
                        intempus_case.get("logical_timestamp"),
                    )
            elif intempus_case.get("logical_timestamp") > intempus_sync.logical_timestamp:
                # Case is updated in Intempus
                if not system_b_sync:
                    # Case is updated in Intempus, but it is not tracked for System B
                    # Propagate update to System B
                    await self._propagate_update_to_system_b(session, intempus_case, system_b_case)
                else:
                    # Case is updated in Intempus and it is tracked for System B
                    if not system_b_case:
                        # Case is updated in Intempus and it is not updated in System B
                        # Propagate update to System B
                        system_b_case = {
                            "id": system_b_sync.case_id,
                            "customer_id": system_b_sync.customer_id,
                            "number": system_b_sync.number,
                            "logical_timestamp": system_b_sync.logical_timestamp,
                        }
                        await self._propagate_update_to_system_b(
                            session, intempus_case, system_b_case
                        )
                    else:
                        # Case is updated in Intempus and it could be updated in System B.
                        if system_b_case.get("logical_timestamp") > system_b_sync.logical_timestamp:
                            # Case is updated in both Intempus and System B. Merge conflict
                            # Propagate update to System B
                            await self._propagate_update_to_system_b(
                                session, intempus_case, system_b_case
                            )
                        else:
                            # Case is updated in Intempus and it is not updated in System B
                            # Propagate update to System B
                            await self._propagate_update_to_system_b(
                                session, intempus_case, system_b_case
                            )

        # Process each case from System B (for cases not in Intempus)
        for key, system_b_case in system_b_map.items():
            system_b_sync = system_b_sync_map.get(key)
            intempus_sync = intempus_sync_map.get(key)
            intempus_case = intempus_map.get(key)

            if not system_b_sync:
                # Case created in System B
                if not intempus_sync:
                    # Case created in System B, and not tracked for Intempus
                    if not intempus_case:
                        # Case created in System B, and doesn't exists in Intempus
                        # Propagate creation to Intempus
                        await self._propagate_creation_to_intempus(session, system_b_case)
                    else:
                        # Case created in both System B, and Intempus. Merge conflict
                        # Propagate update to System B
                        await self._propagate_update_to_system_b(
                            session, intempus_case, system_b_case
                        )
                else:
                    # Case Created in System B and it is tracked for Intempus
                    if not intempus_case:
                        # Case created in System B, and it is not updated in Intempus
                        # Not clear what to do here
                        # Not clear what to do here, so store the logical_timestamp
                        await self._store_sync_case_system_b(
                            session,
                            system_b_case.get("id"),
                            system_b_case.get("customer_id"),
                            system_b_case.get("number"),
                            system_b_case.get("logical_timestamp"),
                        )
                    else:
                        # Case created in System B, and it is updated in Intempus. Merge conflict
                        # Propagate update to System B
                        await self._propagate_update_to_system_b(
                            session, intempus_case, system_b_case
                        )
            elif system_b_case.get("logical_timestamp") > system_b_sync.logical_timestamp:
                # Case is updated in System B
                if not intempus_sync:
                    # Case is updated in System B, but it is not tracked for Intempus
                    if not intempus_case:
                        # Case updated in System B, and doesn't exists in Intempus
                        # Propagate creation to Intempus
                        await self._propagate_creation_to_intempus(session, system_b_case)
                    else:
                        # Case updated in System B, and created in Intempus. Merge conflict
                        # Propagate update to System B
                        await self._propagate_update_to_system_b(
                            session, intempus_case, system_b_case
                        )
                else:
                    # Case is updated in System B and it is tracked for Intempus
                    if not intempus_case:
                        # Case updated in System B, and is not updated in Intempus
                        # Propagate update to Intempus
                        intempus_case = {
                            "id": intempus_sync.case_id,
                            "customer_id": intempus_sync.customer_id,
                            "number": intempus_sync.number,
                            "logical_timestamp": intempus_sync.logical_timestamp,
                        }
                        await self._propagate_update_to_intempus(
                            session, system_b_case, intempus_case
                        )
                    else:
                        if intempus_case.get("logical_timestamp") > intempus_sync.logical_timestamp:
                            # Case updated in both System B and Intempus. Merge conflict
                            # Propagate update to System B
                            await self._propagate_update_to_system_b(
                                session, intempus_case, system_b_case
                            )
                        else:
                            # Case updated in System B, and is not updated in Intempus
                            # Propagate update to Intempus
                            await self._propagate_update_to_intempus(
                                session, system_b_case, intempus_case
                            )

        # Handle deletions (full sync only)
        if is_full_sync:
            await self._process_deletions(
                session, intempus_cases, system_b_cases, all_intempus_sync, all_system_b_sync
            )

    async def _propagate_creation_to_intempus(self, session: Session, system_b_case: dict) -> None:
        """Propagate creation to Intempus."""
        customer_id = system_b_case.get("customer_id")
        number = system_b_case.get("number")

        try:
            case_data = CaseCreate.model_validate(system_b_case).model_dump()

            if not case_data.get("creation_id"):
                case_data["creation_id"] = f"system_b_{system_b_case.get('id')}"

            created_case = await self.intempus_client.create_case(case_data)
            # Returned logical_timestamp is not reliable from the Create Case endpoint
            created_case = await self.intempus_client.get_case(created_case.get("id"))
            new_logical_timestamp = created_case.get("logical_timestamp")

            # Store in SyncCaseIntempus
            sync_case = SyncCaseIntempus(
                case_id=created_case.get("id"),
                customer_id=customer_id,
                number=number,
                logical_timestamp=new_logical_timestamp,
            )
            session.add(sync_case)
            session.commit()

            logger.debug(f"Created case in Intempus: customer_id={customer_id}, number={number}")
        except Exception as e:
            logger.error(f"Error creating case in Intempus: {e}", exc_info=True)
            session.rollback()

    async def _propagate_creation_to_system_b(self, session: Session, intempus_case: dict) -> None:
        """Propagate creation to System B."""
        customer_id = intempus_case.get("customer_id")
        number = intempus_case.get("number")

        try:
            case_data = CaseCreate.model_validate(intempus_case).model_dump()

            if not case_data.get("creation_id"):
                case_data["creation_id"] = f"intempus_{intempus_case.get('id')}"

            created_case = await self.system_b_client.create_case(case_data)
            new_logical_timestamp = created_case.get("logical_timestamp")

            # Store in SyncCaseSystemB
            sync_case = SyncCaseSystemB(
                case_id=created_case.get("id"),
                customer_id=customer_id,
                number=number,
                logical_timestamp=new_logical_timestamp,
            )
            session.add(sync_case)
            session.commit()

            logger.debug(f"Created case in System B: customer_id={customer_id}, number={number}")
        except Exception as e:
            logger.error(f"Error creating case in System B: {e}", exc_info=True)
            session.rollback()

    async def _propagate_update_to_intempus(
        self, session: Session, system_b_case: dict, intempus_case: dict
    ) -> None:
        """Propagate update to Intempus."""
        case_id = intempus_case.get("id")
        customer_id = intempus_case.get("customer_id")
        number = intempus_case.get("number")
        current_logical_timestamp = intempus_case.get("logical_timestamp")

        try:
            case_data = CaseUpdate.model_validate(system_b_case).model_dump()

            intempus_case_before = await self.intempus_client.get_case(case_id)
            intempus_logical_timestamp = intempus_case_before.get("logical_timestamp")

            if intempus_logical_timestamp != current_logical_timestamp:
                logger.debug(
                    f"Aborting update - Intempus has been updated: "
                    f"customer_id={customer_id}, number={number}, "
                    f"expected={current_logical_timestamp}, got={intempus_logical_timestamp}"
                )
                return

            updated_case = await self.intempus_client.update_case(case_id, case_data)

            # Returned logical_timestamp is not reliable from the Update Case endpoint
            updated_case = await self.intempus_client.get_case(case_id)
            new_logical_timestamp = updated_case.get("logical_timestamp")
            await self._store_sync_case_intempus(
                session, case_id, customer_id, number, new_logical_timestamp
            )
            await self._store_sync_case_system_b(
                session,
                system_b_case.get("id"),
                system_b_case.get("customer_id"),
                system_b_case.get("number"),
                system_b_case.get("logical_timestamp"),
            )

            logger.debug(f"Updated case in Intempus: customer_id={customer_id}, number={number}")
        except Exception as e:
            logger.error(f"Error updating case in Intempus: {e}", exc_info=True)
            session.rollback()

    async def _propagate_update_to_system_b(
        self, session: Session, intempus_case: dict, system_b_case: dict
    ) -> None:
        """Propagate update to System B."""
        case_id = system_b_case.get("id")
        customer_id = system_b_case.get("customer_id")
        number = system_b_case.get("number")
        current_logical_timestamp = system_b_case.get("logical_timestamp")

        try:
            case_data = CaseUpdate.model_validate(intempus_case).model_dump()

            updated_case = await self.system_b_client.update_case(
                case_id, case_data, if_match=current_logical_timestamp
            )
            new_logical_timestamp = updated_case.get("logical_timestamp")
            await self._store_sync_case_system_b(
                session, case_id, customer_id, number, new_logical_timestamp
            )
            await self._store_sync_case_intempus(
                session,
                intempus_case.get("id"),
                intempus_case.get("customer_id"),
                intempus_case.get("number"),
                intempus_case.get("logical_timestamp"),
            )

            logger.debug(f"Updated case in System B: customer_id={customer_id}, number={number}")
        except HTTPStatusError as e:
            if e.response.status_code == 412:
                logger.warning(
                    f"Precondition failed updating case in System B: "
                    f"customer_id={customer_id}, number={number}"
                )
            else:
                logger.error(f"Error updating case in System B: {e}", exc_info=True)
            session.rollback()
        except Exception as e:
            logger.error(f"Error updating case in System B: {e}", exc_info=True)
            session.rollback()

    async def _store_sync_case_intempus(
        self, session: Session, case_id: int, customer_id: str, number: str, logical_timestamp: int
    ) -> None:
        """Store a sync case for Intempus in the database."""

        sync_case = session.exec(
            select(SyncCaseIntempus).where(
                SyncCaseIntempus.case_id == case_id,
            )
        ).first()

        if sync_case:
            sync_case.logical_timestamp = logical_timestamp
            session.add(sync_case)
        else:
            sync_case = SyncCaseIntempus(
                case_id=case_id,
                customer_id=customer_id,
                number=number,
                logical_timestamp=logical_timestamp,
            )
            session.add(sync_case)

        session.commit()

        logger.debug(
            f"Stored sync case for Intempus: case_id={case_id}, customer_id={customer_id}, number={number}, logical_timestamp={logical_timestamp}"
        )

    async def _store_sync_case_system_b(
        self, session: Session, case_id: int, customer_id: str, number: str, logical_timestamp: int
    ) -> None:
        """Store a sync case for Intempus in the database."""

        sync_case = session.exec(
            select(SyncCaseSystemB).where(
                SyncCaseSystemB.case_id == case_id,
            )
        ).first()

        if sync_case:
            sync_case.logical_timestamp = logical_timestamp
            session.add(sync_case)
        else:
            sync_case = SyncCaseSystemB(
                case_id=case_id,
                customer_id=customer_id,
                number=number,
                logical_timestamp=logical_timestamp,
            )
            session.add(sync_case)

        session.commit()

        logger.debug(
            f"Stored sync case for System B: case_id={case_id}, customer_id={customer_id}, number={number}, logical_timestamp={logical_timestamp}"
        )

    async def _process_deletions(
        self,
        session: Session,
        intempus_cases: list[dict],
        system_b_cases: list[dict],
        all_intempus_sync: list[SyncCaseIntempus],
        all_system_b_sync: list[SyncCaseSystemB],
    ) -> None:
        """Process deletions (scenarios 7, 8)."""
        intempus_case_ids = {c.get("id") for c in intempus_cases}
        system_b_case_ids = {c.get("id") for c in system_b_cases}

        # Scenario 7: Case deleted in Intempus but not in System B
        for intempus_sync in all_intempus_sync:
            if intempus_sync.case_id not in intempus_case_ids:
                # Find corresponding System B case
                system_b_sync = session.exec(
                    select(SyncCaseSystemB).where(
                        SyncCaseSystemB.customer_id == intempus_sync.customer_id,
                        SyncCaseSystemB.number == intempus_sync.number,
                    )
                ).first()

                if system_b_sync and system_b_sync.case_id in system_b_case_ids:
                    await self._delete_case_in_system_b(session, system_b_sync.case_id)
                    session.delete(system_b_sync)
                    session.delete(intempus_sync)

        # Scenario 8: Case deleted in System B but not in Intempus
        for system_b_sync in all_system_b_sync:
            if system_b_sync.case_id not in system_b_case_ids:
                # Find corresponding Intempus case
                intempus_sync = session.exec(
                    select(SyncCaseIntempus).where(
                        SyncCaseIntempus.customer_id == system_b_sync.customer_id,
                        SyncCaseIntempus.number == system_b_sync.number,
                    )
                ).first()

                if intempus_sync and intempus_sync.case_id in intempus_case_ids:
                    await self._delete_case_in_intempus(session, intempus_sync.case_id)
                    session.delete(intempus_sync)
                    session.delete(system_b_sync)

        session.commit()

    async def _delete_case_in_system_b(self, session: Session, case_id: int) -> None:
        """Delete a case in System B (scenario 7)."""
        try:
            await self.system_b_client.delete_case(case_id)
            logger.debug(f"Deleted case in System B: case_id={case_id}")
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    f"Case not found in System B (may already be deleted): case_id={case_id}"
                )
            else:
                logger.error(f"Error deleting case in System B: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error deleting case in System B: {e}", exc_info=True)

    async def _delete_case_in_intempus(self, session: Session, case_id: int) -> None:
        """Delete a case in Intempus (scenario 8)."""
        try:
            await self.intempus_client.delete_case(case_id)
            logger.debug(f"Deleted case in Intempus: case_id={case_id}")
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    f"Case not found in Intempus (may already be deleted): case_id={case_id}"
                )
            else:
                logger.error(f"Error deleting case in Intempus: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error deleting case in Intempus: {e}", exc_info=True)

    async def close(self):
        """Close the API clients."""
        await self.intempus_client.close()
        await self.system_b_client.close()
