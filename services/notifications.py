import json
from datetime import datetime, timedelta, date

from aiogram import Bot

from database import (
    get_chat_id,
    was_notification_sent,
    mark_notification_sent,
    get_omgtu_snapshot,
    save_omgtu_snapshot,
    get_tasks_for_date,
    get_homework_tasks_for_date,
)

from services.day_plan import get_day_plan
from services.omgtu import (
    get_my_schedule,
    get_brother_schedule,
    parse_lesson_date,
)
from services.omsu import get_omsu_events
from services.recurring import get_recurring_events


# =====================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================

def make_notification_key(
    kind: str,
    target_date: date,
    extra: str = "",
) -> str:
    return (
        f"{kind}:"
        f"{target_date.isoformat()}:"
        f"{extra}"
    )


def parse_time_for_day(
    target_day: date,
    time_text: str,
) -> datetime:
    hours, minutes = map(
        int,
        time_text.split(":")
    )

    return datetime(
        target_day.year,
        target_day.month,
        target_day.day,
        hours,
        minutes,
    )


async def send_once(
    bot: Bot,
    key: str,
    text: str,
    now_dt: datetime,
):
    if await was_notification_sent(key):
        return

    chat_id = await get_chat_id()

    if not chat_id:
        return

    await bot.send_message(
        chat_id=chat_id,
        text=text,
    )

    await mark_notification_sent(
        key,
        now_dt.isoformat(),
    )


# =====================================
# УТРЕННИЙ ПЛАН
# =====================================

async def send_morning_plan(
    bot: Bot,
    now_dt: datetime,
):
    target_day = now_dt.date()

    key = make_notification_key(
        "morning_plan",
        target_day,
    )

    if await was_notification_sent(key):
        return

    chat_id = await get_chat_id()

    if not chat_id:
        return

    text = await get_day_plan(
        target_day
    )

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🌅 План на сегодня\n\n"
            + text
        ),
    )

    await mark_notification_sent(
        key,
        now_dt.isoformat(),
    )


# =====================================
# ПЛАН НА ЗАВТРА
# =====================================

async def send_tomorrow_plan(
    bot: Bot,
    now_dt: datetime,
):
    target_day = (
        now_dt.date()
        + timedelta(days=1)
    )

    key = make_notification_key(
        "tomorrow_plan",
        target_day,
    )

    if await was_notification_sent(key):
        return

    chat_id = await get_chat_id()

    if not chat_id:
        return

    text = await get_day_plan(
        target_day
    )

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🌙 План на завтра\n\n"
            + text
        ),
    )

    await mark_notification_sent(
        key,
        now_dt.isoformat(),
    )

# =====================================
# ДЗ НА ЗАВТРА
# =====================================

async def send_homework_tomorrow(
    bot: Bot,
    now_dt: datetime,
):
    target_day = (
        now_dt.date()
        + timedelta(days=1)
    )

    tasks = (
        await get_homework_tasks_for_date(
            target_day.isoformat()
        )
    )

    if not tasks:
        return

    key = make_notification_key(
        "homework_tomorrow",
        target_day,
    )

    if await was_notification_sent(key):
        return

    chat_id = await get_chat_id()

    if not chat_id:
        return

    lines = [
        "📚 ДЗ НА ЗАВТРА",
        "",
    ]

    for (
        task_id,
        title,
        description,
    ) in tasks:
        lines.append(
            f"• {title}"
        )

    await bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
    )

    await mark_notification_sent(
        key,
        now_dt.isoformat(),
    )

# =====================================
# НАПОМИНАНИЯ ЗА ЧАС
# =====================================

async def check_hour_before_reminders(
    bot: Bot,
    now_dt: datetime,
):
    target_day = now_dt.date()

    # ---------------------------------
    # ОМГТУ
    # ---------------------------------

    omgtu_schedule = await get_my_schedule(
        target_day
    )

    omgtu_today = [
        lesson
        for lesson in omgtu_schedule
        if parse_lesson_date(
            lesson["date"]
        ) == target_day
    ]

    omgtu_today.sort(
        key=lambda lesson:
        lesson["beginLesson"]
    )

    if omgtu_today:
        first = omgtu_today[0]

        event_time = parse_time_for_day(
            target_day,
            first["beginLesson"],
        )

        reminder_time = (
            event_time
            - timedelta(hours=1)
        )

        delta = abs(
            (now_dt - reminder_time)
            .total_seconds()
        )

        if delta <= 90:
            key = make_notification_key(
                "omgtu",
                target_day,
                first["beginLesson"],
            )

            await send_once(
                bot,
                key,
                (
                    "🎓 Через час первая пара ОмГТУ\n\n"
                    f"{first['beginLesson']} — "
                    f"{first['discipline']}"
                ),
                now_dt,
            )

    # ---------------------------------
    # ОМГУ
    # ---------------------------------

    omsu_events = get_omsu_events(
        target_day
    )

    if omsu_events:
        first = omsu_events[0]

        event_time = parse_time_for_day(
            target_day,
            first["start"],
        )

        reminder_time = (
            event_time
            - timedelta(hours=1)
        )

        delta = abs(
            (now_dt - reminder_time)
            .total_seconds()
        )

        if delta <= 90:
            key = make_notification_key(
                "omsu",
                target_day,
                first["start"],
            )

            await send_once(
                bot,
                key,
                (
                    "💻 Через час первая пара ОмГУ\n\n"
                    f"{first['start']} — "
                    f"{first['subject']}"
                ),
                now_dt,
            )

    # ---------------------------------
    # КИТАЙСКИЙ / ЗАЛ
    # ---------------------------------

    recurring = await get_recurring_events(
        target_day
    )

    for event in recurring:
        event_time = parse_time_for_day(
            target_day,
            event["time"],
        )

        reminder_time = (
            event_time
            - timedelta(hours=1)
        )

        delta = abs(
            (now_dt - reminder_time)
            .total_seconds()
        )

        if delta > 90:
            continue

        category = event["category"]

        if category == "Китайский":
            emoji = "🇨🇳"
            text = (
                "🇨🇳 Через час китайский\n\n"
                f"{event['time']} — "
                f"{event['title']}"
            )

        elif category == "Зал":
            emoji = "🏋️"
            text = (
                "🏋️ Через час зал\n\n"
                f"{event['time']} — "
                "Тренировка"
            )

        else:
            continue

        key = make_notification_key(
            category.lower(),
            target_day,
            event["time"],
        )

        await send_once(
            bot,
            key,
            text,
            now_dt,
        )

    # ---------------------------------
    # КАСТОМНЫЕ ЗАДАЧИ
    # ---------------------------------

    tasks = await get_tasks_for_date(
        target_day.isoformat()
    )

    for (
        task_id,
        title,
        task_time,
        category,
        is_done,
    ) in tasks:

        if is_done:
            continue

        if not task_time:
            continue

        event_time = parse_time_for_day(
            target_day,
            task_time,
        )

        reminder_time = (
            event_time
            - timedelta(hours=1)
        )

        delta = abs(
            (now_dt - reminder_time)
            .total_seconds()
        )

        if delta > 90:
            continue

        key = make_notification_key(
            "task",
            target_day,
            str(task_id),
        )

        await send_once(
            bot,
            key,
            (
                "📌 Через час задача\n\n"
                f"{task_time} — {title}"
            ),
            now_dt,
        )


# =====================================
# SNAPSHOT ОМГТУ
# =====================================

def normalize_schedule(
    schedule: list[dict],
) -> list[dict]:
    result = []

    for lesson in schedule:
        result.append(
            {
                "date": lesson.get("date"),
                "beginLesson": lesson.get(
                    "beginLesson"
                ),
                "endLesson": lesson.get(
                    "endLesson"
                ),
                "discipline": lesson.get(
                    "discipline"
                ),
                "auditorium": lesson.get(
                    "auditorium"
                ),
                "subGroup": lesson.get(
                    "subGroup"
                ),
            }
        )

    result.sort(
        key=lambda item: (
            item["date"] or "",
            item["beginLesson"] or "",
            item["discipline"] or "",
        )
    )

    return result


def lesson_key(
    lesson: dict,
) -> tuple:
    return (
        lesson.get("date") or "",
        lesson.get("discipline") or "",
    )


def lesson_details(
    lesson: dict,
) -> tuple:
    return (
        lesson.get("beginLesson") or "",
        lesson.get("endLesson") or "",
        lesson.get("auditorium") or "",
    )


def format_lesson_short(
    lesson: dict,
) -> str:
    raw_date = lesson.get("date") or ""

    try:
        pretty_date = datetime.strptime(
            raw_date,
            "%Y.%m.%d",
        ).strftime("%d.%m")
    except ValueError:
        pretty_date = raw_date

    begin = lesson.get(
        "beginLesson"
    ) or "?"

    end = lesson.get(
        "endLesson"
    ) or "?"

    discipline = lesson.get(
        "discipline"
    ) or "Без названия"

    auditorium = lesson.get(
        "auditorium"
    )

    text = (
        f"{pretty_date} "
        f"{begin}–{end} — "
        f"{discipline}"
    )

    if auditorium:
        text += (
            f" • {auditorium}"
        )

    return text


def build_schedule_changes(
    old_schedule: list[dict],
    new_schedule: list[dict],
) -> list[str]:

    changes = []

    old_used = set()
    new_used = set()

    # ---------------------------------
    # СНАЧАЛА ИЩЕМ ИЗМЕНЁННЫЕ ПАРЫ
    #
    # Та же дата + тот же предмет,
    # но поменялись время/аудитория.
    # ---------------------------------

    for old_index, old_lesson in enumerate(
        old_schedule
    ):
        for new_index, new_lesson in enumerate(
            new_schedule
        ):
            if new_index in new_used:
                continue

            if (
                lesson_key(old_lesson)
                != lesson_key(new_lesson)
            ):
                continue

            if (
                lesson_details(old_lesson)
                == lesson_details(new_lesson)
            ):
                old_used.add(
                    old_index
                )
                new_used.add(
                    new_index
                )
                break

            old_used.add(
                old_index
            )
            new_used.add(
                new_index
            )

            raw_date = (
                new_lesson.get("date")
                or old_lesson.get("date")
                or ""
            )

            try:
                pretty_date = datetime.strptime(
                    raw_date,
                    "%Y.%m.%d",
                ).strftime("%d.%m")
            except ValueError:
                pretty_date = raw_date

            discipline = (
                new_lesson.get(
                    "discipline"
                )
                or old_lesson.get(
                    "discipline"
                )
                or "Без названия"
            )

            changes.append(
                "🔄 Изменена пара\n"
                f"{pretty_date} — "
                f"{discipline}\n"
                "Было: "
                f"{old_lesson.get('beginLesson', '?')}"
                "–"
                f"{old_lesson.get('endLesson', '?')}"
                + (
                    f" • "
                    f"{old_lesson.get('auditorium')}"
                    if old_lesson.get(
                        "auditorium"
                    )
                    else ""
                )
                + "\n"
                "Стало: "
                f"{new_lesson.get('beginLesson', '?')}"
                "–"
                f"{new_lesson.get('endLesson', '?')}"
                + (
                    f" • "
                    f"{new_lesson.get('auditorium')}"
                    if new_lesson.get(
                        "auditorium"
                    )
                    else ""
                )
            )

            break

    # ---------------------------------
    # УДАЛЁННЫЕ ПАРЫ
    # ---------------------------------

    for index, lesson in enumerate(
        old_schedule
    ):
        if index in old_used:
            continue

        changes.append(
            "❌ Убрана пара\n"
            + format_lesson_short(
                lesson
            )
        )

    # ---------------------------------
    # ДОБАВЛЕННЫЕ ПАРЫ
    # ---------------------------------

    for index, lesson in enumerate(
        new_schedule
    ):
        if index in new_used:
            continue

        changes.append(
            "➕ Добавлена пара\n"
            + format_lesson_short(
                lesson
            )
        )

    return changes


async def check_omgtu_changes(
    bot: Bot,
    now_dt: datetime,
):
    chat_id = await get_chat_id()

    if not chat_id:
        return

    monday = (
        now_dt.date()
        - timedelta(
            days=now_dt.date().weekday()
        )
    )

    my_schedule = await get_my_schedule(
        monday
    )

    brother_schedule = (
        await get_brother_schedule(
            monday
        )
    )

    snapshots = {
        "me": normalize_schedule(
            my_schedule
        ),
        "brother": normalize_schedule(
            brother_schedule
        ),
    }

    for key_name, new_data in snapshots.items():

        snapshot_key = (
            f"{key_name}:"
            f"{monday.isoformat()}"
        )

        new_json = json.dumps(
            new_data,
            ensure_ascii=False,
            sort_keys=True,
        )

        old_json = await get_omgtu_snapshot(
            snapshot_key
        )

        # Первый запуск:
        # просто запоминаем расписание.
        if old_json is None:
            await save_omgtu_snapshot(
                snapshot_key,
                new_json,
            )
            continue

        if old_json == new_json:
            continue

        try:
            old_data = json.loads(
                old_json
            )
        except json.JSONDecodeError:
            old_data = []

        changes = build_schedule_changes(
            old_data,
            new_data,
        )

        await save_omgtu_snapshot(
            snapshot_key,
            new_json,
        )

        if key_name == "me":
            title = (
                "⚠️ Изменилось твоё "
                "расписание ОмГТУ"
            )
        else:
            title = (
                "⚠️ Изменилось расписание "
                "брата в ОмГТУ"
            )

        if not changes:
            text = (
                f"{title}\n\n"
                "Расписание обновилось."
            )

        else:
            text = (
                f"{title}\n\n"
                + "\n\n".join(
                    changes
                )
            )

        await bot.send_message(
            chat_id=chat_id,
            text=text,
        )