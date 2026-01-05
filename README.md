# Intempus Resource Synchronizer

A bidirectional synchronization system that keeps Cases (aka. Projects) in sync between Intempus and so-called "System B". The synchronizer detects changes on either side and propagates updates to maintain data consistency.

> :zap: **Note**: This implementation is intentionally simplified to meet the 3-hour assignment requirement. A production-ready design would require additional considerations (see [Production Considerations](#production-considerations) section).

## Architecture Overview

The solution consists of three main components:

- **System A (Intempus)**: The external system with its own API for managing cases
- **System B (Local System)**: A FastAPI-based local system implementing an Intempus-compatible API with SQLite storage
- **Synchronizer**: Background jobs that monitor and sync changes bidirectionally between the two systems

> **Note**: Ideally, System B and the Synchronizer would be separate components following a distributed architecture. For this assignment, they are implemented together in a single repository for simplicity.

## System A: Intempus API

### Available Endpoints

Intempus API exposes 5 endpoints to interact with cases:

1. **Retrieve a list of projects**
   - Supports filtering on `logical_timestamp`, could be used for fetching diffs of changes since the last fetch
   - :warning: Fetching only diffs carries a risk of missing deleted projects. Full sync is required periodically with lower frequency.

2. **Retrieve a single project by ID**

3. **Create a new project**
   - The `creation_id` value must be provided to avoid duplicate case/project creation

4. **Update an existing project**
   - Does not support conditional updates

5. **Delete an existing project**

### API Limitations

The Intempus API has several limitations that impact the synchronization strategy:

- **No conditional updates**: The Update Case endpoint does not support conditional updates, which means there's no built-in protection against overwriting newer versions. This creates a race condition risk where a case could be updated by a third-party system between "Fetch" and "Update" operations from the sync system.

- **Outdated logical_timestamp in update response**: The response from the "Update Case" endpoint does not include the newly assigned `logical_timestamp` value. To avoid sync loops, the sync system must fetch the same case immediately after updating to read the new `logical_timestamp`. However, this creates another potential race condition window where a third-party system could update the case between our "Update" and subsequent "Fetch", potentially causing data loss.

## System B: Local System

System B is implemented as a FastAPI application providing an Intempus-compatible API for case management.

### API Features

- Intempus-like REST API endpoints for case operations
- `logical_timestamp` field per case for change tracking
- `Logical-Timestamp` response header indicating the maximum logical timestamp committed across all cases
- **Conditional updates**: Unlike System A, System B supports conditional updates to protect against race conditions
- Update responses include the newly assigned `logical_timestamp` value

### Data Storage

SQLite database with two tables:

- **`case`**
  - `logical_timestamp` (local implementation)
  - All fields of the case resource that can be updated through the Intempus API "Update Case" endpoint

- **`case_metadata`**
  - `max_logical_timestamp` - Tracks the maximum logical timestamp across all cases (to avoid performing MAX aggregation on the case table for every fetch request)
    > **Note**: In a production system, an in-memory store like Redis would be more appropriate for this metadata. This method is chosen for simplicity.

## Synchronizer

The synchronizer uses APScheduler to run background jobs that perform bidirectional synchronization.

### Background Jobs

Two types of background jobs handle synchronization:

1. **Incremental Sync Job** (runs frequently)
   - Syncs only diffs by using the last-read header `Logical-Timestamp` value in a filter.
   - Less load on the APIs and faster execution due to smaller data sets

2. **Full Sync Job** (runs less frequently)
   - Performs a complete sync to capture deletions

### Assumptions

The synchronization logic is built on the following assumptions:

- **Cases as atomic units**: All fields in a case object are interdependent, so partial merging of conflicting versions would violate data integrity. Therefore, cases are synchronized as complete atomic units.

- **Intempus as source of truth**: When conflict is detected, Intempus's version takes precedence.

- **Logical-Timestamp-based change detection**: The `logical_timestamp` field is sufficient for detecting changes and determining synchronization order.

- **Eventual consistency**: The aim is to achieve eventual consistency. So, temporary divergence between systems is acceptable during sync intervals.

### Conflict Resolution

When a conflict is detected, Intempus takes precedence as it is assumed to be the source of truth. The synchronizer will overwrite the conflicting case in System B with Intempus's version.

### Race Condition Mitigation

To reduce the risk of race conditions described in [API Limitations](#api-limitations), the synchronizer fetches the case from Intempus immediately before and after issuing the update request to confirm the logical_timestamps. However, due to limitations of the Intempus API, race conditions cannot be completely eliminated.

## Production Considerations

For a production-ready implementation of Synchronizer, the following improvements would be necessary:

- Intempus supports webhook event streaming on cases. Utilizing this would drammatically decrease load on the API.
- Replace APScheduler with a distributed task queue (Celery + RabbitMQ) to enable multiple sync workers running across different machines. This allows the system to scale horizontally based on load and provides fault tolerance.
- Ensure only one worker processes a given case at any time by utilizing locks. This would prevent race conditions in a multi-worker environment while allowing parallel processing of different cases.
- Rather than treating cases as atomic units, track changes at the field level. This will enable smarter merging as non-conflicting fields could be automatically combined, potentially leading to reduced merge conflicts.
- Use of dead letter queues for failed sync operation to enable manual review.
- Use in-memory database such as Redis to cache frequently accessed data like logical_timestamps. It could also be used to lock cases for sync workers.
