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

MODE_SHADOW = "shadow"

OVERRIDE_REASONS = [
    {"code": "pace_strategy", "label": "Booking pace strategy"},
    {"code": "competitor_pricing", "label": "Competitor pricing"},
    {"code": "property_knowledge", "label": "Property-specific knowledge"},
    {"code": "promotion", "label": "Promotion"},
    {"code": "special_event", "label": "Special event"},
    {"code": "owner_constraint", "label": "Owner constraint"},
    {"code": "channel_mix", "label": "Channel / OTA mix"},
    {"code": "my_judgment", "label": "My judgment"},
    {"code": "other", "label": "Other"},
]
OVERRIDE_REASON_CODES = {r["code"] for r in OVERRIDE_REASONS}

EVENT_IMPACT_LEVELS = [
    {"code": "low", "label": "Low"},
    {"code": "medium", "label": "Medium"},
    {"code": "high", "label": "High"},
]
EVENT_TYPES = [
    {"code": "holiday", "label": "Public holiday"},
    {"code": "concert", "label": "Concert"},
    {"code": "conference", "label": "Conference"},
    {"code": "festival", "label": "Festival"},
    {"code": "sport", "label": "Sporting event"},
    {"code": "other", "label": "Other"},
]

CONFIDENCE_LEVELS = [
    {"code": "HIGH", "label": "High"},
    {"code": "MEDIUM", "label": "Medium"},
    {"code": "LOW", "label": "Low"},
    {"code": "UNUSABLE", "label": "Unusable"},
]
PRICE_BASES = [
    {"code": "NET", "label": "NET to property"},
    {"code": "OTA_SELL", "label": "OTA sell price"},
    {"code": "UNKNOWN", "label": "Unknown"},
]
INCLUSION_OPTIONS = [
    {"code": "INCLUSIVE", "label": "Included"},
    {"code": "EXCLUSIVE", "label": "Excluded"},
    {"code": "UNKNOWN", "label": "Unknown"},
]
PROMOTION_OPTIONS = [
    {"code": "NONE", "label": "No promotion"},
    {"code": "PROMOTIONAL", "label": "Promotional rate"},
    {"code": "UNKNOWN", "label": "Unknown"},
]

# Human-friendly copy for each pricing step, so the operator never sees a code.
FACTOR_COPY = {
    "rate_band": "Seasonal base rate",
    "pace": "Pace position",
    "recent_pickup": "Recent pickup",
    "event": "Event",
    "market": "Market signal",
    "day_of_week": "Day of week",
    "dynamic_bound": "Total adjustment bound",
    "band_min_clamp": "Seasonal MIN floor",
    "band_max_clamp": "Seasonal MAX ceiling",
    "rounding": "Rounding",
}
