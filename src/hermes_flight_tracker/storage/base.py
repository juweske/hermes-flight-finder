"""Storage interface and errors for persistent flight watches."""

from __future__ import annotations

from typing import Protocol

from hermes_flight_tracker.models import AlertRecord, PriceObservation, Watch


class StorageError(Exception):
    """Local tracker state could not be read or written."""


class StateCorruptError(StorageError):
    """The local state file is not a valid Hermes Flight Tracker document."""


class WatchRepository(Protocol):
    """Persist and retrieve project-owned watch models."""

    def list(self) -> list[Watch]:
        """List watches in stable creation order."""
        ...

    def get(self, watch_id: str) -> Watch | None:
        """Get one watch by id."""
        ...

    def save(self, watch: Watch) -> None:
        """Create or replace a watch."""
        ...

    def delete(self, watch_id: str) -> bool:
        """Delete a watch, returning whether it was present."""
        ...

    def list_observations(self, watch_id: str) -> list[PriceObservation]: ...

    def record_observation(self, observation: PriceObservation) -> None: ...

    def list_alerts(self, watch_id: str) -> list[AlertRecord]: ...

    def record_alert(self, alert: AlertRecord) -> None: ...
