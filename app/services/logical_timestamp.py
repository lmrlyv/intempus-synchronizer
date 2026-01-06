from sqlmodel import Session, func, select

from app.core.logging import get_logger
from app.models.case import Case


logger = get_logger(__name__)


class LogicalTimestampManager:
    """Manages logical timestamps for change tracking and synchronization.

    This class provides functionality to generate and track logical timestamps
    used for change detection and incremental synchronization between systems.
    Logical timestamps are monotonically increasing integers that represent
    the order of changes to resources.

    Attributes:
        _RESERVED_LT: Class-level metadata storing the reserved logical timestamp.
            This is a temporary in-memory cache of the next available logical
            timestamp. Ideally, this metadata should be stored in persistent
            storage (e.g., database or Redis) to ensure that separate requests
            or application restarts don't produce duplicate logical timestamp
            values. In a production system, this would prevent race conditions
            and ensure uniqueness across distributed instances.

    Note:
        The current implementation uses a class variable for simplicity, but
        this approach has limitations in distributed or multi-process
        environments where the same logical timestamp could be generated
        concurrently by different processes or after application restarts.
    """

    _RESERVED_LT: int | None = None

    @classmethod
    def get_next(cls, session: Session) -> int:
        """Get the next logical timestamp.

        Increments and returns the next available logical timestamp. If the
        reserved timestamp is not initialized, it first fetches the maximum
        committed logical timestamp from the database.

        Args:
            session: SQLModel database session for querying the database.

        Returns:
            int: The next logical timestamp value as an integer.

        Note:
            The reserved timestamp is cached in memory. In a production
            environment with multiple instances or after restarts, this could
            lead to duplicate values. Consider using persistent storage for
            the reserved timestamp metadata.
        """
        if cls._RESERVED_LT is None:
            logger.debug("Reserved Logical Timestamp is None. Fetching max from DB")
            cls._RESERVED_LT = cls.get_max_comitted(session)

        cls._RESERVED_LT += 1

        logger.debug(f"Next reserved Logical Timestamp: {cls._RESERVED_LT}")
        return cls._RESERVED_LT

    @classmethod
    def get_max_comitted(cls, session: Session) -> int:
        """Get the maximum logical timestamp committed in the database.

        Queries the database to find the highest logical_timestamp value
        that has been committed across all Case records.

        Args:
            session: SQLModel database session for querying the database.

        Returns:
            int: The maximum committed logical timestamp value. Returns 0 if no
            cases exist in the database.
        """
        query = select(func.max(Case.logical_timestamp))
        max_committed_lt = session.exec(query).one_or_none() or 0

        return max_committed_lt
