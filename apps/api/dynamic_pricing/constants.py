"""Shared vocabulary. Defined once, served to the UI via the API.

Keeping these here (rather than duplicated in React) means the frontend never
becomes a second home for domain knowledge.
"""

from __future__ import annotations

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_OVERRIDDEN = "overridden"
STATUSES = [STATUS_PENDING, STATUS_ACCEPTED, STATUS_OVERRIDDEN]

DECISION_ACCEPTED = "accepted"
DECISION_OVERRIDDEN = "overridden"

OVERRIDE_REASONS = [
    {"code": "occupancy_strategy", "label": "Occupancy strategy"},
    {"code": "competitor_pricing", "label": "Competitor pricing"},
    {"code": "property_knowledge", "label": "Property-specific knowledge"},
    {"code": "promotion", "label": "Promotion"},
    {"code": "special_event", "label": "Special event"},
    {"code": "owner_constraint", "label": "Owner constraint"},
    {"code": "my_judgment", "label": "My judgment"},
    {"code": "other", "label": "Other"},
]
OVERRIDE_REASON_CODES = {r["code"] for r in OVERRIDE_REASONS}

# Human-friendly copy for each pricing factor, shown in the recommendation
# detail drawer so the operator never sees a bare code.
FACTOR_COPY = {
    "day_of_week": "Day of week",
    "occupancy": "Occupancy",
    "booking_pace": "Booking pace",
    "lead_time": "Lead time",
    "urgency_discount": "Unsold close to check-in",
    "season": "Season",
    "event": "Event",
    "market": "Market signal",
    "compounding_guardrail": "Compounding guardrail",
    "min_price_floor": "Minimum price floor",
    "max_price_cap": "Maximum price cap",
    "rounding": "Rounding",
}
