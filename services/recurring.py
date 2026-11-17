from datetime import date

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

    # ЗАЛ — временно отключён до следующего семестра.
    # Алгоритм автоматического подбора сохранён
    # в services/gym_planner.py.

    events.sort(
        key=lambda event: event["time"]
    )

    return events