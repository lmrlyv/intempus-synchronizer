from sqlmodel import SQLModel, Field
from datetime import datetime


class CaseBase(SQLModel):
    """Base model for Case resource, equivalent to the Case resource in Intempus API.

    Contains all fields that can be updated through the Intempus API "Update Case" endpoint.
    """

    responsible: str | None = None
    co_responsible: str | None = None
    case_state: str | None = None
    customer: str | None = None
    case_group: str | None = None
    customer_country: str | None = None
    customer_city: str | None = None
    customer_street_address: str | None = None
    customer_zip_code: str | None = None
    customer_latitude: int | None = None
    customer_longitude: int | None = None
    customer_name: str | None = None
    department: str | None = None
    department_name: str | None = None
    department_id: str | None = None
    responsible_name: str | None = None
    co_responsible_name: str | None = None
    case_state_name: str | None = None
    customer_id: str | None = None
    responsible_id: str | None = None
    co_responsible_id: str | None = None
    case_state_id: str | None = None
    creation_date: datetime | None = None
    parent: str | None = None
    parent_name: str | None = None
    root_parent: str | None = None
    priority: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    number: str | None = None
    name: str | None = None
    street_address: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str | None = None
    latitude: int | None = None
    longitude: int | None = None
    remarks_required: bool | None = None
    file_upload_required: bool | None = None
    active: bool | None = None
    notes: str | None = None
    hour_budget: int | None = None
    permit_new_workreports: bool | None = None
    all_employees_may_add_work_reports: bool | None = None
    all_worktypes_may_used_in_work_reports: bool | None = None
    geofence: bool | None = None
    creation_id: str | None = None


class Case(CaseBase, table=True):
    """Database model for Case resource.

    Additional Fields:
    - id: Primary key for the case
    - logical_timestamp: Local implementation for change tracking and synchronization

    The logical_timestamp is used to track changes and enable incremental synchronization
    with Intempus. It is automatically incremented whenever a case is created or updated.
    """

    id: int = Field(default=None, primary_key=True)
    logical_timestamp: int = Field(default=0, index=True)


class CaseCreate(CaseBase):
    """Schema for creating a new Case resource.

    The creation_id field is required to prevent duplicate case creation.
    All other fields from CaseBase are optional.
    """

    creation_id: str


class CaseUpdate(CaseBase):
    """Schema for updating an existing Case resource."""

    pass


class CasePublic(CaseBase):
    """Public API response schema for Case resource.

    The logical_timestamp is included in responses to enable clients to track
    changes and implement conditional updates.
    """

    id: int
    logical_timestamp: int
