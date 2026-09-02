from datetime import date

from services.gym_planner import (
    is_auto_gym_day,
)


async def get_recurring_events(
    day: date,
) -> list[dict]:
    events = []

    # =====================================
    # КИТАЙСКИЙ
    # =====================================

    chinese_start = date(
        2026,
        9,
        21,
    )

    # Вторник и четверг
    if (
        day >= chinese_start
        and day.weekday() in {1, 3}
    ):
        events.append(
            {
                "time": "20:00",
                "title": "Китайский",
                "category": "Китайский",
                "emoji": "🇨🇳",
                "kind": "event",
            }
        )

    # =====================================
    # ЗАЛ
    # =====================================

    # Даты зала теперь определяет
    # gym_planner.py автоматически.
    if await is_auto_gym_day(day):
        events.append(
            {
                "time": "20:40",
                "title": "Зал",
                "category": "Зал",
                "emoji": "🏋️",
                "kind": "event",
            }
        )

    events.sort(
        key=lambda event: event["time"]
    )

    return events