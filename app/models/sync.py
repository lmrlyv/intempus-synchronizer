from sqlmodel import SQLModel, Field


class SyncMetadata(SQLModel, table=True):
    """Metadata for tracking synchronization state.

    Stores the last Logical-Timestamp value read from Intempus API and System B
    to enable incremental synchronization. Only one record should exist (id=1).
    """

    id: int = Field(default=1, primary_key=True)
    last_intempus_logical_timestamp: int = Field(default=0)
    last_system_b_logical_timestamp: int = Field(default=0)
