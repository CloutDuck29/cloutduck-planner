from datetime import date, timedelta
from itertools import combinations, product

from services.omgtu import (
    get_my_schedule,
    get_brother_schedule,
    get_day_info,
)
from services.omsu import get_omsu_events


GYM_TIME = "20:40"

# На текущей неполной неделе уже решили сами.
FIXED_GYM_DAYS = {
    date(2026, 9, 3),
    date(2026, 9, 5),
}

AUTO_GYM_START = date(2026, 9, 7)


def has_chinese(target_day: date) -> bool:
    """
    Китайский начинается с 21.09.2026.
    Регулярно: вторник и четверг.
    """
    chinese_start = date(2026, 9, 21)

    return (
        target_day >= chinese_start
        and target_day.weekday() in {1, 3}
    )


def has_blocking_omsu(target_day: date) -> bool:
    """
    Live и зачёт пока блокируют вечерний зал.

    Запись не блокирует:
    её можно посмотреть в другое время.
    """
    events = get_omsu_events(target_day)

    return any(
        event["format"] in {"live", "exam"}
        for event in events
    )


async def get_week_candidates(
    monday: date,
) -> list[dict]:
    """
    Возвращает дни недели,
    в которые потенциально можно поставить зал.
    """

    my_schedule = await get_my_schedule(
        monday
    )

    brother_schedule = await get_brother_schedule(
        monday
    )

    candidates = []

    for offset in range(7):
        current_day = monday + timedelta(
            days=offset
        )

        if current_day < AUTO_GYM_START:
            continue

        # Китайский полностью запрещает зал.
        if has_chinese(current_day):
            continue

        # Live ОмГУ / зачёт пока запрещают
        # вечернюю тренировку.
        if has_blocking_omsu(current_day):
            continue

        my_info = get_day_info(
            my_schedule,
            current_day,
        )

        brother_info = get_day_info(
            brother_schedule,
            current_day,
        )

        my_count = my_info[
            "lesson_count"
        ]

        brother_count = brother_info[
            "lesson_count"
        ]

        total_load = (
            my_count
            + brother_count
        )

        heavy_penalty = 0

        # 4 пары ещё допустимы,
        # но 5+ уже сильно нежелательны.
        if my_count > 4:
            heavy_penalty += (
                my_count - 4
            ) * 5

        if brother_count > 4:
            heavy_penalty += (
                brother_count - 4
            ) * 5

        candidates.append(
            {
                "date": current_day,
                "load": total_load,
                "heavy": heavy_penalty,
            }
        )

    return candidates


def get_week_variants(
    candidates: list[dict],
) -> list[tuple]:
    """
    Все возможные варианты по 3 тренировки
    за неделю.
    """

    if len(candidates) < 3:
        return []

    variants = []

    for triple in combinations(
        candidates,
        3,
    ):
        variants.append(triple)

    return variants


def score_schedule(
    weeks: tuple,
    previous_gym_day: date | None,
) -> tuple:
    """
    Оцениваем сразу несколько соседних недель.

    Главная цель:
    максимально равномерные интервалы
    между ВСЕМИ тренировками, включая
    границы недель.
    """

    all_items = []

    for week in weeks:
        all_items.extend(week)

    all_items.sort(
        key=lambda item: item["date"]
    )

    all_days = [
        item["date"]
        for item in all_items
    ]

    if previous_gym_day:
        all_days = [
            previous_gym_day,
            *all_days,
        ]

    gaps = []

    for index in range(
        len(all_days) - 1
    ):
        gap = (
            all_days[index + 1]
            - all_days[index]
        ).days

        gaps.append(gap)

    # Очень плохо, если тренировки
    # оказались два дня подряд.
    consecutive_penalty = sum(
        100
        for gap in gaps
        if gap <= 1
    )

    # Чем сильнее отличаются интервалы,
    # тем хуже.
    if gaps:
        gap_unevenness = (
            max(gaps)
            - min(gaps)
        )
    else:
        gap_unevenness = 0

    # Идеальный ориентир — около 2 дней.
    distance_from_ideal = sum(
        abs(gap - 2)
        for gap in gaps
    )

    total_heavy = sum(
        item["heavy"]
        for item in all_items
    )

    total_load = sum(
        item["load"]
        for item in all_items
    )

    return (
        consecutive_penalty,
        gap_unevenness,
        distance_from_ideal,
        total_heavy,
        total_load,
    )


async def get_auto_gym_days(
    any_day: date,
) -> list[date]:

    monday = any_day - timedelta(
        days=any_day.weekday()
    )

    # =====================================
    # ТЕКУЩАЯ НЕДЕЛЯ 31.08–06.09
    # =====================================

    if monday < AUTO_GYM_START:
        return sorted(
            gym_day
            for gym_day in FIXED_GYM_DAYS
            if (
                gym_day >= monday
                and gym_day
                <= monday + timedelta(days=6)
            )
        )

    # =====================================
    # АВТОМАТИЧЕСКИЕ НЕДЕЛИ
    # =====================================

    # Смотрим текущую неделю
    # и ещё две следующие.
    #
    # Благодаря этому бот понимает,
    # что воскресенье текущей недели
    # может оказаться слишком близко
    # к понедельнику следующей.

    mondays = [
        monday,
        monday + timedelta(days=7),
        monday + timedelta(days=14),
    ]

    week_variants = []

    for week_monday in mondays:
        candidates = (
            await get_week_candidates(
                week_monday
            )
        )

        variants = get_week_variants(
            candidates
        )

        if not variants:
            return []

        week_variants.append(
            variants
        )

    # Для первой автоматической недели
    # предыдущая известная тренировка —
    # суббота 05.09.
    previous_gym_day = None

    if monday == date(2026, 9, 7):
        previous_gym_day = date(
            2026,
            9,
            5,
        )

    best_score = None
    best_schedule = None

    # Одновременно перебираем варианты
    # трёх соседних недель.
    for schedule in product(
        *week_variants
    ):
        score = score_schedule(
            schedule,
            previous_gym_day,
        )

        if (
            best_score is None
            or score < best_score
        ):
            best_score = score
            best_schedule = schedule

    if best_schedule is None:
        return []

    # Возвращаем только текущую неделю.
    current_week = best_schedule[0]

    return [
        item["date"]
        for item in current_week
    ]


async def is_auto_gym_day(
    target_day: date,
) -> bool:

    # Фиксированная первая неделя.
    if target_day in FIXED_GYM_DAYS:
        return True

    if target_day < AUTO_GYM_START:
        return False

    gym_days = await get_auto_gym_days(
        target_day
    )

    return target_day in gym_days