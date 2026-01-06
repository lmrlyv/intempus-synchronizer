from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Path, Query, Response, status
from sqlmodel import Session, select

from app.core.db import SessionDep
from app.core.logging import get_logger
from app.models.case import Case, CaseCreate, CasePublic, CaseUpdate
from app.services.logical_timestamp import LogicalTimestampManager


logger = get_logger(__name__)

router = APIRouter(prefix="/case", tags=["case"])


def add_logical_timestamp_header(response: Response, session: Session):
    """Add Logical-Timestamp header to response."""
    max_timestamp = LogicalTimestampManager.get_max_comitted(session)
    response.headers["Logical-Timestamp"] = str(max_timestamp)


@router.get(
    "/",
    response_model=list[CasePublic],
    summary="Retrieve a list of cases",
    description=(
        "Retrieve a list of cases, optionally filtered by logical_timestamp. This endpoint "
        "returns all cases or cases that have been modified since a given logical timestamp. This "
        "is useful for incremental synchronization to fetch only changed cases.\n\n"
        "**Note:** Fetching only diffs (using logical_timestamp filter) carries a risk "
        "of missing deleted cases. Full sync (without filter) is required periodically "
        "to capture deletions."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Successfully retrieved cases",
            "headers": {
                "Logical-Timestamp": {
                    "description": "The maximum logical timestamp committed across all cases in the system",
                    "schema": {"type": "string"},
                }
            },
        }
    },
    response_description="List of case resources. Empty list if no cases match the filter criteria.",
)
def get_cases(
    logical_timestamp: Annotated[
        int | None,
        Query(
            alias="logical_timestamp",
            description=(
                "Optional query parameter. If provided, returns only cases with "
                "logical_timestamp greater than this value. Used for fetching diffs "
                "of changes since the last fetch."
            ),
        ),
    ] = None,
    session: SessionDep = None,
    response: Response = None,
):
    query = select(Case)

    if logical_timestamp is not None:
        # Filter cases with logical_timestamp greater than the provided value
        query = query.where(Case.logical_timestamp > logical_timestamp)

    cases = session.exec(query).all()
    add_logical_timestamp_header(response, session)
    return cases


@router.get(
    "/{case_id}",
    response_model=CasePublic,
    summary="Retrieve a single case by ID",
    description="Retrieve a single case resource by its unique identifier.",
    responses={
        status.HTTP_200_OK: {
            "description": "Successfully retrieved the case",
            "headers": {
                "Logical-Timestamp": {
                    "description": "The maximum logical timestamp committed across all cases in the system",
                    "schema": {"type": "string"},
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Case not found",
            "content": {"application/json": {"example": {"detail": "Case not found"}}},
        },
    },
    response_description="The case resource with all its fields including id and logical_timestamp.",
)
def get_case(
    case_id: Annotated[int, Path(description="The unique identifier of the case to retrieve")],
    session: SessionDep = None,
    response: Response = None,
):
    case = session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    add_logical_timestamp_header(response, session)
    return case


@router.post(
    "/",
    response_model=CasePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new case resource",
    description=(
        "Create a new case with the provided data. The creation_id field is required to prevent "
        "duplicate case creation. All other fields are optional.\n\n"
        "**Note:** The creation_id value must be provided to avoid duplicate case creation. "
        "This is equivalent to the Intempus API requirement."
    ),
    responses={
        status.HTTP_201_CREATED: {
            "description": "Case successfully created",
            "content": {
                "application/json": {
                    "description": "The newly created case resource with assigned id and logical_timestamp"
                }
            },
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Bad request - creation_id is required for case creation",
            "content": {
                "application/json": {
                    "example": {"detail": "creation_id is required for case creation"}
                }
            },
        },
        status.HTTP_409_CONFLICT: {
            "description": "Conflict - Case with this creation_id already exists",
            "content": {
                "application/json": {
                    "example": {"detail": "Case with this creation_id already exists"}
                }
            },
        },
    },
    response_description="The newly created case resource with assigned id and logical_timestamp.",
)
def create_case(case: CaseCreate, session: SessionDep = None):
    if not case.creation_id:
        raise HTTPException(status_code=400, detail="creation_id is required for case creation")

    # Check if case with this creation_id already exists
    existing = session.exec(select(Case).where(Case.creation_id == case.creation_id)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Case with this creation_id already exists")

    # Create new case with logical timestamp
    db_case = Case(**case.model_dump())
    db_case.logical_timestamp = LogicalTimestampManager.get_next(session)

    session.add(db_case)
    session.commit()
    session.refresh(db_case)

    return db_case


@router.put(
    "/{case_id}",
    response_model=CasePublic,
    summary="Update an existing case resource",
    description=(
        "Update a case with the provided data. Supports conditional updates via the If-Match "
        "header to prevent race conditions. Only fields provided in the request body will be "
        "updated (partial update)."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Case successfully updated",
            "content": {
                "application/json": {
                    "description": "The updated case resource with the newly assigned logical_timestamp"
                }
            },
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Bad request - If-Match header must be a valid integer",
            "content": {
                "application/json": {
                    "example": {"detail": "If-Match header must be a valid integer"}
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Case not found",
            "content": {"application/json": {"example": {"detail": "Case not found"}}},
        },
        status.HTTP_412_PRECONDITION_FAILED: {
            "description": (
                "Precondition failed - expected logical_timestamp doesn't match "
                "the case's current logical_timestamp"
            ),
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Precondition failed: expected logical_timestamp 5, but case has 6"
                    }
                }
            },
        },
    },
    response_description="The updated case resource with the newly assigned logical_timestamp.",
)
def update_case(
    case_id: Annotated[int, Path(description="The unique identifier of the case to update")],
    case: CaseUpdate,
    if_match: Annotated[
        str | None,
        Header(
            alias="If-Match",
            description=(
                "Optional header parameter. If provided, the update will only proceed if "
                "the case's current logical_timestamp matches this value. This implements "
                "conditional updates to prevent overwriting newer versions. "
                "Must be a valid integer."
            ),
        ),
    ] = None,
    session: SessionDep = None,
):
    db_case = session.get(Case, case_id)
    if not db_case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Conditional update: check if If-Match header matches current logical_timestamp
    if if_match is not None:
        try:
            expected_timestamp = int(if_match)
            if db_case.logical_timestamp != expected_timestamp:
                raise HTTPException(
                    status_code=412,
                    detail=(
                        f"Precondition failed: expected logical_timestamp {expected_timestamp}, "
                        f"but case has {db_case.logical_timestamp}"
                    ),
                )
        except ValueError:
            raise HTTPException(status_code=400, detail="If-Match header must be a valid integer")

    # Update case fields (excluding id and logical_timestamp)
    case_data = case.model_dump(exclude_unset=True)
    db_case.sqlmodel_update(case_data)

    # Increment logical timestamp
    db_case.logical_timestamp = LogicalTimestampManager.get_next(session)

    session.add(db_case)
    session.commit()
    session.refresh(db_case)

    return db_case


@router.delete(
    "/{case_id}",
    response_model=CasePublic,
    summary="Delete an existing case resource",
    description="Permanently delete a case from the system. The deleted case is returned in the response.",
    responses={
        status.HTTP_200_OK: {
            "description": "Case successfully deleted",
            "content": {
                "application/json": {"description": "The deleted case resource (before deletion)"}
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Case not found",
            "content": {"application/json": {"example": {"detail": "Case not found"}}},
        },
    },
    response_description="The deleted case resource (before deletion).",
)
def delete_case(
    case_id: Annotated[int, Path(description="The unique identifier of the case to delete")],
    session: SessionDep = None,
):
    db_case = session.get(Case, case_id)
    if not db_case:
        raise HTTPException(status_code=404, detail="Case not found")

    session.delete(db_case)
    session.commit()

    return db_case
