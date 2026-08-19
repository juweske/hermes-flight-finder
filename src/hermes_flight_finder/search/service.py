"""Provider-independent flight search operations."""

from __future__ import annotations

from decimal import Decimal
from itertools import product

from hermes_flight_finder.models import BookingStrategy, FlightOffer, FlightQuery
from hermes_flight_finder.providers.base import FlightProvider


class SearchService:
    """Search and sort offers returned by a provider."""

    def __init__(self, provider: FlightProvider) -> None:
        self._provider = provider

    def search(self, query: FlightQuery) -> list[FlightOffer]:
        """Return priced offers first, ordered from least to most expensive."""
        offers = self._provider.search(query)
        if not offers and query.is_open_jaw:
            offers = self._separate_ticket_fallback(query)
        return sorted(offers, key=_offer_sort_key)

    def _separate_ticket_fallback(self, query: FlightQuery) -> list[FlightOffer]:
        outbound = sorted(self._provider.search(query.outbound_query()), key=_offer_sort_key)
        inbound = sorted(self._provider.search(query.inbound_query()), key=_offer_sort_key)
        if not outbound or not inbound:
            return []
        combined = [
            _combine_separate_tickets(first, second)
            for first, second in product(outbound[:5], inbound[:5])
        ]
        return sorted(combined, key=_offer_sort_key)[:5]


_SEPARATE_TICKET_WARNING = (
    "No matching multi-city itinerary was found. These flights are independent one-way "
    "bookings that require separate purchases and may have different baggage, change, "
    "cancellation, and support conditions. Changes to one booking do not protect the other."
)


def _combine_separate_tickets(outbound: FlightOffer, inbound: FlightOffer) -> FlightOffer:
    same_currency = outbound.currency == inbound.currency
    price = (
        outbound.price + inbound.price
        if same_currency and outbound.price is not None and inbound.price is not None
        else None
    )
    return FlightOffer(
        price=price,
        currency=outbound.currency if same_currency else None,
        duration_minutes=outbound.duration_minutes + inbound.duration_minutes,
        stops=outbound.stops + inbound.stops,
        legs=outbound.legs + inbound.legs,
        journeys=outbound.journeys + inbound.journeys,
        booking_strategy=BookingStrategy.SEPARATE_TICKETS,
        component_prices=(outbound.price, inbound.price),
        component_booking_urls=(outbound.booking_url, inbound.booking_url),
        booking_warning=_SEPARATE_TICKET_WARNING,
    )


def _offer_sort_key(offer: FlightOffer) -> tuple[bool, Decimal, int]:
    return (offer.price is None, offer.price or Decimal(), offer.duration_minutes)
