"""Deterministic post-processing for flexible-date searches."""

from __future__ import annotations

from datetime import date

from hermes_flight_tracker.models import FlexibleDateOffer, FlexibleSearchQuery
from hermes_flight_tracker.providers.base import FlightProvider


class FlexibleSearchService:
    """Merge, deduplicate, and order flexible-date offers."""

    def __init__(self, provider: FlightProvider) -> None:
        self._provider = provider

    def search(self, query: FlexibleSearchQuery) -> list[FlexibleDateOffer]:
        """Choose the lowest price for duplicate date pairs and sort by price."""
        lowest_by_dates: dict[tuple[date, date, str | None], FlexibleDateOffer] = {}
        for offer in self._provider.search_dates(query):
            key = (offer.departure_date, offer.return_date, offer.currency)
            current = lowest_by_dates.get(key)
            if current is None or offer.price < current.price:
                lowest_by_dates[key] = offer
        return sorted(
            lowest_by_dates.values(),
            key=lambda offer: (offer.price, offer.departure_date, offer.return_date),
        )
