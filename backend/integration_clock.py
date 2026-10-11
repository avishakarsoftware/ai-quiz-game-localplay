"""Format the durable database clock shared by callbacks and provider snapshots."""
from datetime import datetime, timedelta, timezone


def resource_updated_at(resource: dict | None) -> str | None:
    if not isinstance(resource, dict):
        return None
    microseconds = resource.get("integration_updated_at_us")
    if isinstance(microseconds, int) and not isinstance(microseconds, bool) and microseconds > 0:
        instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=microseconds)
        return instant.isoformat(timespec="microseconds").replace("+00:00", "Z")
    # Existing rows have no new clock until their next durable mutation. Keep
    # their historical resource time; receipt/delivery time is never a fallback.
    legacy = resource.get("updated_at")
    if isinstance(legacy, str):
        return legacy or None
    if isinstance(legacy, (int, float)) and not isinstance(legacy, bool) and legacy > 0:
        return datetime.fromtimestamp(legacy, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return None
