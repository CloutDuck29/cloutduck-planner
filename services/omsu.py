from datetime import date, timedelta

from data.omsu_schedule import OMSU_SCHEDULE


def get_omsu_events(target_date: date) -> list[dict]:
    """
    Возвращает все пары ОмГУ на выбранную дату.
    """

    date_string = target_date.isoformat()

    events = [
        lesson.copy()
        for lesson in OMSU_SCHEDULE
        if lesson["date"] == date_string
    ]

    events.sort(
        key=lambda lesson: lesson["start"]
    )

    return events


def has_omsu(target_date: date) -> bool:
    """
    Есть ли вообще ОмГУ в этот день.
    """

    return bool(
        get_omsu_events(target_date)
    )


def has_live_omsu(target_date: date) -> bool:
    """
    Есть ли обязательная живая пара
    или зачёт.
    """

    events = get_omsu_events(target_date)

    return any(
        event["format"] in {"live", "exam"}
        for event in events
    )


def get_omsu_day_info(target_date: date) -> dict:
    events = get_omsu_events(target_date)

    if not events:
        return {
            "lesson_count": 0,
            "first_lesson": None,
            "last_lesson": None,
            "events": [],
        }

    return {
        "lesson_count": len(events),
        "first_lesson": events[0]["start"],
        "last_lesson": events[-1]["end"],
        "events": events,
    }


def get_omsu_week(any_day: date) -> dict:
    monday = any_day - timedelta(
        days=any_day.weekday()
    )

    result = {}

    for offset in range(7):
        current_day = monday + timedelta(
            days=offset
        )

        result[current_day] = (
            get_omsu_day_info(current_day)
        )

    return result


def get_format_emoji(event: dict) -> str:
    format_name = event.get("format")

    if format_name == "live":
        return "🔴"

    if format_name == "recorded":
        return "🎞"

    if format_name == "exam":
        return "📝"

    return "💻"