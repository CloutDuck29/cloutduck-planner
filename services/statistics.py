from collections import Counter
from datetime import date, datetime, timedelta

from data.omsu_schedule import OMSU_SCHEDULE
from services.gym_planner import (
    FIXED_GYM_DAYS,
    AUTO_GYM_START,
    is_auto_gym_day,
)
from services.omgtu import (
    fetch_group_schedule,
    is_our_subgroup,
    MY_GROUP,
)


STUDY_START = date(2026, 9, 1)
CHINESE_START = date(2026, 9, 21)


def event_has_passed(
    event_date: date,
    event_time: str | None,
    current_dt: datetime,
) -> bool:
    if event_date < current_dt.date():
        return True

    if event_date > current_dt.date():
        return False

    if not event_time:
        return False

    event_dt = datetime.combine(
        event_date,
        datetime.strptime(
            event_time,
            "%H:%M",
        ).time(),
    )

    return event_dt <= current_dt.replace(
        tzinfo=None
    )


async def get_omgtu_statistics(
    current_dt: datetime,
) -> Counter:
    schedule = await fetch_group_schedule(
        MY_GROUP,
        STUDY_START,
        current_dt.date(),
    )

    counter = Counter()

    for lesson in schedule:
        if not is_our_subgroup(lesson):
            continue

        lesson_date = datetime.strptime(
            lesson["date"],
            "%Y.%m.%d",
        ).date()

        lesson_time = lesson.get(
            "endLesson"
        )

        if not event_has_passed(
            lesson_date,
            lesson_time,
            current_dt,
        ):
            continue

        subject = (
            lesson.get("discipline")
            or "Без названия"
        ).strip()

        counter[subject] += 1

    return counter


def get_omsu_statistics(
    current_dt: datetime,
) -> Counter:
    counter = Counter()

    for event in OMSU_SCHEDULE:
        event_date = datetime.strptime(
            event["date"],
            "%Y-%m-%d",
        ).date()

        if not event_has_passed(
            event_date,
            event.get("end"),
            current_dt,
        ):
            continue

        subject = (
            event.get("subject")
            or "Без названия"
        ).strip()

        counter[subject] += 1

    return counter


def get_chinese_count(
    current_dt: datetime,
) -> int:
    if current_dt.date() < CHINESE_START:
        return 0

    count = 0
    current_day = CHINESE_START

    while current_day <= current_dt.date():
        if current_day.weekday() in {
            1,
            3,
        }:
            if event_has_passed(
                current_day,
                "20:00",
                current_dt,
            ):
                count += 1

        current_day += timedelta(days=1)

    return count


async def get_gym_count(
    current_dt: datetime,
) -> int:
    count = 0

    for gym_day in FIXED_GYM_DAYS:
        if event_has_passed(
            gym_day,
            "20:40",
            current_dt,
        ):
            count += 1

    current_day = AUTO_GYM_START

    while current_day <= current_dt.date():
        if await is_auto_gym_day(
            current_day
        ):
            if event_has_passed(
                current_day,
                "20:40",
                current_dt,
            ):
                count += 1

        current_day += timedelta(days=1)

    return count


async def build_statistics_text(
    current_dt: datetime,
) -> str:
    omgtu = await get_omgtu_statistics(
        current_dt
    )

    omsu = get_omsu_statistics(
        current_dt
    )

    chinese_count = get_chinese_count(
        current_dt
    )

    gym_count = await get_gym_count(
        current_dt
    )

    lines = [
        "📊 СТАТИСТИКА",
        "",
        "🎓 ОмГТУ",
    ]

    if omgtu:
        for subject, count in sorted(
            omgtu.items()
        ):
            lines.append(
                f"• {subject} — {count}"
            )
    else:
        lines.append("• Пока нет")

    lines.extend(
        [
            "",
            "🏫 ОмГУ",
        ]
    )

    if omsu:
        for subject, count in sorted(
            omsu.items()
        ):
            lines.append(
                f"• {subject} — {count}"
            )
    else:
        lines.append("• Пока нет")

    lines.extend(
        [
            "",
            f"🇨🇳 Китайский — {chinese_count}",
            f"🏋️ Зал — {gym_count}",
            "",
            (
                "📚 Всего пар — "
                f"{sum(omgtu.values()) + sum(omsu.values())}"
            ),
        ]
    )

    return "\n".join(lines)