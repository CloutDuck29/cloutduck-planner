from datetime import date

from data.omgtu_buildings import OMGTU_BUILDINGS
from database import get_tasks_for_date

from services.omgtu import (
    get_my_schedule,
    parse_lesson_date,
)
from services.omsu import (
    get_omsu_events,
    get_format_emoji,
)
from services.recurring import get_recurring_events


WEEKDAYS = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


# =====================================
# КОРПУС ОМГТУ
# =====================================

def get_building_text(
    auditorium: str | None,
) -> str | None:

    if not auditorium:
        return None

    if "-" not in auditorium:
        return None

    prefix = auditorium.split(
        "-",
        1,
    )[0].strip()

    building = OMGTU_BUILDINGS.get(
        prefix
    )

    if not building:
        return None

    return building["address"]


# =====================================
# ПЛАН ДНЯ
# =====================================

def get_lesson_number(begin_time: str) -> str:
    lesson_numbers = {
        "08:00": "1️⃣",
        "09:40": "2️⃣",
        "11:35": "3️⃣",
        "13:15": "4️⃣",
        "15:00": "5️⃣",
        "16:40": "6️⃣",
        "18:20": "7️⃣",
        "20:00": "8️⃣",
    }

    return lesson_numbers.get(begin_time, "▫️")

async def get_day_plan(
    target_day: date,
) -> str:

    lines = []

    weekday = WEEKDAYS[
        target_day.weekday()
    ]

    lines.append(
        f"📅 {weekday}, "
        f"{target_day.strftime('%d.%m.%Y')}"
    )

    # =================================
    # ОМГТУ
    # =================================

    omgtu_week = await get_my_schedule(
        target_day
    )

    omgtu_events = [
        lesson
        for lesson in omgtu_week
        if parse_lesson_date(
            lesson["date"]
        ) == target_day
    ]

    omgtu_events.sort(
        key=lambda lesson: (
            lesson["beginLesson"]
        )
    )

    if omgtu_events:
        lines.append("")
        lines.append("🎓 ОМГТУ")

        for lesson in omgtu_events:
            start = lesson[
                "beginLesson"
            ]

            lesson_number = get_lesson_number(start)

            end = lesson[
                "endLesson"
            ]

            subject = lesson[
                "discipline"
            ]

            lines.append(
                f"{lesson_number} {start}–{end} — "
                f"{subject}"
            )

            room = lesson.get(
                "auditorium"
            )

            if room:
                building = (
                    get_building_text(
                        room
                    )
                )

                if building:
                    lines.append(
                        f"   {room} • "
                        f"{building}"
                    )
                else:
                    lines.append(
                        f"   Аудитория: "
                        f"{room}"
                    )

    # =================================
    # ОМГУ
    # =================================

    omsu_events = get_omsu_events(
        target_day
    )

    if omsu_events:
        lines.append("")
        lines.append("💻 ОМГУ")

        for event in omsu_events:
            emoji = get_format_emoji(
                event
            )

            lines.append(
                f"{emoji} "
                f"{event['start']}–"
                f"{event['end']} — "
                f"{event['subject']}"
            )

    # =================================
    # КИТАЙСКИЙ + ЗАЛ
    # =================================

    recurring_events = (
    await get_recurring_events(
        target_day
    )
)

    chinese_events = [
        event
        for event in recurring_events
        if event["category"]
        == "Китайский"
    ]

    gym_events = [
        event
        for event in recurring_events
        if event["category"]
        == "Зал"
    ]

    if chinese_events:
        lines.append("")
        lines.append(
            "🇨🇳 КИТАЙСКИЙ"
        )

        for event in chinese_events:
            lines.append(
                f"{event['time']} — "
                f"{event['title']}"
            )

    if gym_events:
        lines.append("")
        lines.append(
            "🏋️ ЗАЛ"
        )

        for event in gym_events:
            lines.append(
                f"{event['time']} — "
                "Тренировка"
            )

    # =================================
    # ЗАДАЧИ
    # =================================

    tasks = await get_tasks_for_date(
        target_day.isoformat()
    )

    if tasks:
        lines.append("")
        lines.append("📌 ЗАДАЧИ")

        for (
            task_id,
            title,
            task_time,
            category,
            is_done,
        ) in tasks:

            status = (
                "✅"
                if is_done
                else "☐"
            )

            if task_time:
                lines.append(
                    f"{status} "
                    f"{task_time} — "
                    f"{title}"
                )
            else:
                lines.append(
                    f"{status} "
                    f"{title}"
                )

    # =================================
    # ПУСТОЙ ДЕНЬ
    # =================================

    if (
        not omgtu_events
        and not omsu_events
        and not recurring_events
        and not tasks
    ):
        lines.append("")
        lines.append(
            "Свободный день 👀"
        )

    return "\n".join(lines)