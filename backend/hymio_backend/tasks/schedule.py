import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def normalize(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid schedule")
    mode = value.get("mode", "now")
    if mode not in {"now", "once", "daily", "weekly"}:
        raise ValueError("Invalid schedule mode")
    if mode != "now" and not value.get("timezone"):
        raise ValueError("Timed schedules require an explicit IANA timezone")
    zone = str(value.get("timezone", "UTC"))
    ZoneInfo(zone)
    result = {"mode": mode, "timezone": zone}
    if mode == "once":
        at = datetime.fromisoformat(str(value["at"]).replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("Schedule time must include timezone")
        result["at"] = at.isoformat()
    if mode in {"daily", "weekly"}:
        hour, minute = map(int, str(value.get("time", "09:00")).split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid schedule time")
        result["time"] = f"{hour:02d}:{minute:02d}"
    if mode == "weekly":
        day = int(value.get("weekday", 0))
        if not 0 <= day <= 6:
            raise ValueError("weekday must be 0..6, Monday first")
        result["weekday"] = day
    return result


def next_due(schedule, after=None):
    now = time.time() if after is None else after
    mode = schedule["mode"]
    if mode == "now":
        return now
    if mode == "once":
        return datetime.fromisoformat(schedule["at"]).timestamp()
    zone = ZoneInfo(schedule["timezone"])
    local = datetime.fromtimestamp(now, zone)
    hour, minute = map(int, schedule["time"].split(":"))
    for days in range(9):
        day = local.date() + timedelta(days=days)
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
        stamp = candidate.timestamp()
        # Skip nonexistent DST local times instead of shifting silently.
        if datetime.fromtimestamp(stamp, zone).strftime("%H:%M") != schedule["time"]:
            continue
        if mode == "weekly" and candidate.weekday() != schedule["weekday"]:
            continue
        if stamp > now:
            return stamp
    raise ValueError("Cannot find next schedule occurrence")
