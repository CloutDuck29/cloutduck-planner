import os
from collections import defaultdict
from datetime import date, datetime, timedelta

import aiohttp


BASE_URL = "https://rasp.omgtu.ru/api"

MY_GROUP = os.getenv("OMGTU_GROUP", "АТП-261")
BROTHER_GROUP = "МР-261"


async def find_group_id(group_name: str) -> int | None:
    url = f"{BASE_URL}/search"

    params = {
        "term": group_name,
        "type": "group",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

    for item in data:
        label = (
            item.get("label")
            or item.get("value")
            or item.get("name")
            or ""
        )

        if group_name.lower() in str(label).lower():
            group_id = item.get("id")

            if group_id is not None:
                return int(group_id)

    return None


async def fetch_group_schedule(
    group_name: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    group_id = await find_group_id(group_name)

    if group_id is None:
        raise RuntimeError(
            f"Не удалось найти группу {group_name}"
        )

    url = f"{BASE_URL}/schedule/group/{group_id}"

    params = {
        "start": start_date.isoformat(),
        "finish": end_date.isoformat(),
        "lng": 1,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()


def is_our_subgroup(lesson: dict) -> bool:
    # Собираем всю информацию о паре в одну строку
    lesson_text = " ".join(
        str(value or "")
        for value in lesson.values()
    ).upper()

    # Немецкий поток нам не нужен
    if "НЕМ ЯЗ" in lesson_text:
        return False

    # Вторая подгруппа нам не нужна
    if "АТП-261/2" in lesson_text:
        return False

    # Если API отдельно передал подгруппу
    subgroup = str(lesson.get("subGroup") or "").strip()

    if subgroup:
        if subgroup.endswith("/2") or subgroup == "2":
            return False

    return True


def is_brother_subgroup(
    lesson: dict,
) -> bool:
    lesson_text = " ".join(
        str(value or "")
        for value in lesson.values()
    ).upper()

    # Немецкий брату не нужен
    if "НЕМ ЯЗ" in lesson_text:
        return False

    # Первая подгруппа МР-261 брату не нужна
    if "МР-261/1" in lesson_text:
        return False

    subgroup = str(
        lesson.get("subGroup") or ""
    ).strip()

    if subgroup:
        if (
            subgroup == "1"
            or subgroup.endswith("/1")
        ):
            return False

    return True

async def get_week_schedule(
    group_name: str,
    any_day: date,
) -> list[dict]:
    monday = any_day - timedelta(
        days=any_day.weekday()
    )

    sunday = monday + timedelta(days=6)

    schedule = await fetch_group_schedule(
        group_name,
        monday,
        sunday,
    )

    return [
        lesson
        for lesson in schedule
        if is_our_subgroup(lesson)
    ]


async def get_my_schedule(any_day: date) -> list[dict]:
    return await get_week_schedule(
        MY_GROUP,
        any_day,
    )


async def get_brother_schedule(
    any_day: date,
) -> list[dict]:

    monday = any_day - timedelta(
        days=any_day.weekday()
    )

    sunday = monday + timedelta(
        days=6
    )

    schedule = await fetch_group_schedule(
        BROTHER_GROUP,
        monday,
        sunday,
    )

    return [
        lesson
        for lesson in schedule
        if is_brother_subgroup(lesson)
    ]


def parse_lesson_date(value: str) -> date:
    return datetime.strptime(
        value,
        "%Y.%m.%d",
    ).date()


def group_schedule_by_day(
    schedule: list[dict],
) -> dict[date, list[dict]]:
    days = defaultdict(list)

    for lesson in schedule:
        lesson_date = parse_lesson_date(
            lesson["date"]
        )

        days[lesson_date].append(lesson)

    for lessons in days.values():
        lessons.sort(
            key=lambda lesson: lesson["beginLesson"]
        )

    return dict(days)


def get_day_info(
    schedule: list[dict],
    target_date: date,
) -> dict:
    """
    Возвращает информацию об учебном дне.

    Например:
    {
        "lesson_count": 3,
        "first_lesson": "09:40",
        "last_lesson": "16:40",
        "lessons": [...]
    }
    """

    days = group_schedule_by_day(schedule)

    lessons = days.get(
        target_date,
        [],
    )

    if not lessons:
        return {
            "lesson_count": 0,
            "first_lesson": None,
            "last_lesson": None,
            "lessons": [],
        }

    return {
        "lesson_count": len(lessons),
        "first_lesson": lessons[0]["beginLesson"],
        "last_lesson": lessons[-1]["endLesson"],
        "lessons": lessons,
    }


async def get_both_week_info(
    any_day: date,
) -> dict:
    my_schedule = await get_my_schedule(
        any_day
    )

    brother_schedule = await get_brother_schedule(
        any_day
    )

    monday = any_day - timedelta(
        days=any_day.weekday()
    )

    result = {}

    for offset in range(7):
        current_day = monday + timedelta(
            days=offset
        )

        result[current_day] = {
            "me": get_day_info(
                my_schedule,
                current_day,
            ),
            "brother": get_day_info(
                brother_schedule,
                current_day,
            ),
        }

    return result