"""Stable domain models independent of individual flight providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from re import fullmatch
from uuid import uuid4


class Cabin(StrEnum):
    """Supported cabin classes."""

    ECONOMY = "ECONOMY"
    PREMIUM_ECONOMY = "PREMIUM_ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class MaxStops(StrEnum):
    """Maximum number of stops allowed in a search."""

    ANY = "ANY"
    NON_STOP = "NON_STOP"
    ONE_STOP_OR_FEWER = "ONE_STOP_OR_FEWER"
    TWO_OR_FEWER_STOPS = "TWO_OR_FEWER_STOPS"


def _validate_iata(code: str, field_name: str) -> str:
    normalized = code.upper()
    if not fullmatch(r"[A-Z]{3}", normalized):
        raise ValueError(f"{field_name} must be a three-letter IATA airport code")
    return normalized


@dataclass(frozen=True, slots=True)
class FlightQuery:
    """A request for a specific-date one-way or round-trip search."""

    origin: str
    destination: str
    departure_date: date
    return_date: date | None = None
    cabin: Cabin = Cabin.ECONOMY
    max_stops: MaxStops = MaxStops.ANY
    passengers: int = 1
    currency: str = "EUR"
    airlines: tuple[str, ...] = ()
    departure_window: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin", _validate_iata(self.origin, "origin"))
        object.__setattr__(self, "destination", _validate_iata(self.destination, "destination"))
        if self.origin == self.destination:
            raise ValueError("origin and destination must be different")
        if self.departure_date < date.today():
            raise ValueError("departure date must not be in the past")
        if self.return_date is not None and self.return_date <= self.departure_date:
            raise ValueError("return date must be after departure date")
        if self.passengers < 1:
            raise ValueError("passengers must be at least 1")
        currency = self.currency.upper()
        if not fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be a three-letter ISO 4217 code")
        object.__setattr__(self, "currency", currency)
        normalized_airlines = tuple(airline.upper() for airline in self.airlines)
        if any(not fullmatch(r"[A-Z0-9]{2,3}", airline) for airline in normalized_airlines):
            raise ValueError("airlines must use two- or three-character IATA codes")
        object.__setattr__(self, "airlines", normalized_airlines)
        if self.departure_window is not None:
            start, end = self.departure_window
            if not 0 <= start <= 23 or not 1 <= end <= 24 or start >= end:
                raise ValueError("departure window must be an ascending hour range within 0-24")


@dataclass(frozen=True, slots=True)
class FlexibleSearchQuery:
    """A round-trip date-range request with a range of trip durations."""

    origin: str
    destination: str
    start_date: date
    end_date: date
    min_nights: int
    max_nights: int
    cabin: Cabin = Cabin.ECONOMY
    max_stops: MaxStops = MaxStops.ANY
    passengers: int = 1
    currency: str = "EUR"
    airlines: tuple[str, ...] = ()
    departure_window: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin", _validate_iata(self.origin, "origin"))
        object.__setattr__(self, "destination", _validate_iata(self.destination, "destination"))
        if self.origin == self.destination:
            raise ValueError("origin and destination must be different")
        if self.start_date < date.today():
            raise ValueError("start date must not be in the past")
        if self.end_date < self.start_date:
            raise ValueError("end date must not be before start date")
        if self.min_nights < 1:
            raise ValueError("minimum nights must be at least 1")
        if self.max_nights < self.min_nights:
            raise ValueError("maximum nights must not be less than minimum nights")
        if self.passengers < 1:
            raise ValueError("passengers must be at least 1")
        currency = self.currency.upper()
        if not fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be a three-letter ISO 4217 code")
        object.__setattr__(self, "currency", currency)
        normalized_airlines = tuple(airline.upper() for airline in self.airlines)
        if any(not fullmatch(r"[A-Z0-9]{2,3}", airline) for airline in normalized_airlines):
            raise ValueError("airlines must use two- or three-character IATA codes")
        object.__setattr__(self, "airlines", normalized_airlines)
        if self.departure_window is not None:
            start, end = self.departure_window
            if not 0 <= start <= 23 or not 1 <= end <= 24 or start >= end:
                raise ValueError("departure window must be an ascending hour range within 0-24")


@dataclass(frozen=True, slots=True)
class FlightLeg:
    """One operated flight segment within an itinerary."""

    airline: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_at: datetime
    arrival_at: datetime
    duration_minutes: int


@dataclass(frozen=True, slots=True)
class FlightOffer:
    """A normalized itinerary returned by a provider."""

    price: Decimal | None
    currency: str | None
    duration_minutes: int
    stops: int
    legs: tuple[FlightLeg, ...]
    booking_url: str | None = None

    @property
    def airlines(self) -> tuple[str, ...]:
        """Unique airlines in itinerary order."""
        return tuple(dict.fromkeys(leg.airline for leg in self.legs))


@dataclass(frozen=True, slots=True)
class BookingOption:
    """A current vendor handoff for a selected flight itinerary."""

    vendor_name: str | None
    is_airline_direct: bool
    price: Decimal | None
    currency: str | None
    fare_name: str | None
    booking_url: str | None
    google_click_url: str | None

    @property
    def handoff_url(self) -> str | None:
        """Prefer a direct vendor link, falling back to Google Flights."""
        return self.booking_url or self.google_click_url


@dataclass(frozen=True, slots=True)
class FlexibleDateOffer:
    """A provider-supplied price for a round trip on a pair of dates."""

    departure_date: date
    return_date: date
    price: Decimal
    currency: str | None
    booking_url: str | None = None

    @property
    def nights(self) -> int:
        """Number of nights between departure and return."""
        return (self.return_date - self.departure_date).days


@dataclass(frozen=True, slots=True)
class Watch:
    """A persisted flexible-date query and future deal-alert preferences."""

    id: str
    origin: str
    destination: str
    start_date: date
    end_date: date
    min_nights: int
    max_nights: int
    cabin: Cabin = Cabin.ECONOMY
    max_stops: MaxStops = MaxStops.ANY
    passengers: int = 1
    currency: str = "EUR"
    airlines: tuple[str, ...] = ()
    departure_window: tuple[int, int] | None = None
    target_price: Decimal | None = None
    drop_percent: Decimal | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", self.id):
            raise ValueError("watch id must contain lowercase letters, numbers, and hyphens")
        query = FlexibleSearchQuery(
            origin=self.origin,
            destination=self.destination,
            start_date=self.start_date,
            end_date=self.end_date,
            min_nights=self.min_nights,
            max_nights=self.max_nights,
            cabin=self.cabin,
            max_stops=self.max_stops,
            passengers=self.passengers,
            currency=self.currency,
            airlines=self.airlines,
            departure_window=self.departure_window,
        )
        for field_name in (
            "origin",
            "destination",
            "currency",
            "airlines",
        ):
            object.__setattr__(self, field_name, getattr(query, field_name))
        if self.target_price is not None and self.target_price < 0:
            raise ValueError("target price must not be negative")
        if self.drop_percent is not None and not 0 < self.drop_percent <= 100:
            raise ValueError("drop percent must be greater than 0 and at most 100")

    def to_flexible_search_query(self) -> FlexibleSearchQuery:
        """Return the search portion of the watch for future check operations."""
        return FlexibleSearchQuery(
            origin=self.origin,
            destination=self.destination,
            start_date=self.start_date,
            end_date=self.end_date,
            min_nights=self.min_nights,
            max_nights=self.max_nights,
            cabin=self.cabin,
            max_stops=self.max_stops,
            passengers=self.passengers,
            currency=self.currency,
            airlines=self.airlines,
            departure_window=self.departure_window,
        )


@dataclass(frozen=True, slots=True)
class PriceObservation:
    """The lowest observed price for a watch during one check."""

    checked_at: datetime
    watch_id: str
    price: Decimal
    currency: str
    departure_date: date
    return_date: date
    airlines: tuple[str, ...] = ()
    stops: int | None = None
    source: str = "fli"

    def __post_init__(self) -> None:
        if self.price < 0:
            raise ValueError("observation price must not be negative")
        if self.return_date <= self.departure_date:
            raise ValueError("observation return date must be after departure date")
        if self.stops is not None and self.stops < 0:
            raise ValueError("observation stops must not be negative")
        if not self.source:
            raise ValueError("observation source must not be empty")


@dataclass(frozen=True, slots=True)
class AlertRecord:
    """A persisted alert used to suppress duplicate notifications."""

    watch_id: str
    price: Decimal
    departure_date: date
    return_date: date
    alerted_at: datetime


@dataclass(frozen=True, slots=True)
class Deal:
    """A deterministic alert-worthy price change."""

    watch_id: str
    price: Decimal
    currency: str
    departure_date: date
    return_date: date
    previous_best: Decimal | None
    drop_percent: Decimal | None
    reasons: tuple[str, ...]
    airlines: tuple[str, ...] = ()
    stops: int | None = None


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The structured outcome of checking every saved watch."""

    checked: int
    alerts: tuple[Deal, ...]


def new_watch_id(origin: str, destination: str) -> str:
    """Create a concise, user-visible identifier for a new watch."""
    return f"{origin.lower()}-{destination.lower()}-{uuid4().hex[:8]}"
