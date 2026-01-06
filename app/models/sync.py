from sqlmodel import Field, Index, SQLModel


class SyncMetadata(SQLModel, table=True):
    """Metadata for tracking synchronization state.

    Stores the last Logical-Timestamp value read from Intempus API and System B
    to enable incremental synchronization. Only one record should exist (id=1).
    """

    id: int = Field(default=1, primary_key=True)
    last_intempus_logical_timestamp: int = Field(default=0)
    last_system_b_logical_timestamp: int = Field(default=0)


class SyncCaseIntempus(SQLModel, table=True):
    """Table for storing Intempus cases to be synchronized."""

    __table_args__ = (
        Index("ix_sync_case_intempus_customer_number", "customer_id", "number", unique=True),
    )

    id: int = Field(default=None, primary_key=True)
    case_id: int = Field(default=None, index=True)
    customer_id: str | None = Field(default=None, index=True)
    number: str | None = Field(default=None, index=True)
    logical_timestamp: int = Field(default=0)


class SyncCaseSystemB(SQLModel, table=True):
    """Table for storing System B cases to be synchronized."""

    __table_args__ = (
        Index("ix_sync_case_systemb_customer_number", "customer_id", "number", unique=True),
    )

    id: int = Field(default=None, primary_key=True)
    case_id: int = Field(default=None, index=True)
    customer_id: str | None = Field(default=None, index=True)
    number: str | None = Field(default=None, index=True)
    logical_timestamp: int = Field(default=0)
