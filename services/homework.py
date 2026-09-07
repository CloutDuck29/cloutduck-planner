import re
from datetime import date, datetime, timedelta

from services.omgtu import (
    MY_GROUP,
    fetch_group_schedule,
    is_our_subgroup,
)


def extract_homework(
    text: str | None,
) -> str | None:
    if not text:
        return None

    match = re.search(
        r"(?:^|\n)\s*ДЗ\s*:\s*(.*)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return None

    homework = match.group(1).strip()

    if not homework:
        return None

    if homework in {
        "-",
        "—",
        "–",
    }:
        return None

    return homework


def extract_lesson_date(
    text: str | None,
) -> date | None:
    if not text:
        return None

    match = re.search(
        r"Пара\s+(\d{1,2})\.(\d{1,2})\.(\d{2,4})",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    if year < 100:
        year += 2000

    try:
        return date(
            year,
            month,
            day,
        )
    except ValueError:
        return None


async def find_next_omgtu_lesson(
    subject_names: list[str],
    after_date: date,
) -> dict | None:
    start_date = after_date + timedelta(
        days=1
    )

    end_date = start_date + timedelta(
        days=120
    )

    schedule = await fetch_group_schedule(
        MY_GROUP,
        start_date,
        end_date,
    )

    subject_names_lower = [
        name.lower()
        for name in subject_names
    ]

    candidates = []

    for lesson in schedule:
        if not is_our_subgroup(lesson):
            continue

        discipline = (
            lesson.get("discipline")
            or ""
        ).strip()

        discipline_lower = discipline.lower()

        if not any(
            name in discipline_lower
            or discipline_lower in name
            for name in subject_names_lower
        ):
            continue

        lesson_date = datetime.strptime(
            lesson["date"],
            "%Y.%m.%d",
        ).date()

        candidates.append(
            {
                "date": lesson_date,
                "time": lesson.get(
                    "beginLesson"
                ),
                "discipline": discipline,
            }
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item["date"],
            item["time"] or "",
        )
    )

    return candidates[0]