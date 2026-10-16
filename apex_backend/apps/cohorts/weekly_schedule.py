from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone


EAT = ZoneInfo('Africa/Nairobi')
ACTIVITY_WEEKDAYS = {
    'tutorials': frozenset((0, 1, 2, 3)),
    'sponsored_view': frozenset((0, 1, 2, 3)),
    'main_contest': frozenset((4, 5, 6)),
}
IMPLEMENTED_ACTIVITIES = frozenset(('tutorials', 'sponsored_view', 'main_contest'))


def activity_window(activity, value=None):
    """Return the active week's [start, end) window for an activity, if open."""
    value = (value or timezone.now()).astimezone(EAT)
    if activity not in ACTIVITY_WEEKDAYS:
        raise ValueError(f'Unknown weekly activity: {activity}')
    if value.weekday() not in ACTIVITY_WEEKDAYS[activity]:
        return None

    start_day = 0 if activity != 'main_contest' else 4
    days_since_start = (value.weekday() - start_day) % 7
    start_date = value.date() - timedelta(days=days_since_start)
    end_date = start_date + timedelta(days=4 if activity != 'main_contest' else 3)
    start = timezone.make_aware(datetime.combine(start_date, time.min), EAT)
    end = timezone.make_aware(datetime.combine(end_date, time.min), EAT)
    return start, end


def next_opening(activity, value=None):
    value = (value or timezone.now()).astimezone(EAT)
    window = activity_window(activity, value)
    if window:
        return window[0] + timedelta(days=7)

    next_day = min(
        (weekday - value.weekday()) % 7 or 7
        for weekday in ACTIVITY_WEEKDAYS[activity]
    )
    opening_date = value.date() + timedelta(days=next_day)
    return timezone.make_aware(datetime.combine(opening_date, time.min), EAT)


def attempt_deadline(activity, started_at, duration_seconds=20 * 60):
    window = activity_window(activity, started_at)
    if window is None:
        raise ValueError('An attempt cannot start outside its activity window.')
    return min(started_at + timedelta(seconds=duration_seconds), window[1])


def activity_status(activity, value=None):
    value = (value or timezone.now()).astimezone(EAT)
    window = activity_window(activity, value)
    implemented = activity in IMPLEMENTED_ACTIVITIES
    return {
        'available_now': window is not None,
        'can_start': window is not None and implemented,
        'implemented': implemented,
        'opens_at': next_opening(activity, value),
        'closes_at': window[1] if window else None,
    }


def weekly_schedule(value=None):
    value = (value or timezone.now()).astimezone(EAT)
    return {
        'timezone': 'Africa/Nairobi',
        'server_time': value,
        'weekday': value.strftime('%A'),
        'activities': {
            activity: activity_status(activity, value)
            for activity in ACTIVITY_WEEKDAYS
        },
    }
