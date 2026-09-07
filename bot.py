import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from database import (
    init_db,
    add_task,
    get_tasks_for_date,
    mark_task_done,
    create_task_list,
    get_task_lists,
    get_tasks_for_list,
    get_task_by_id,
    init_bot_settings,
    save_chat_id,
    get_chat_id,
    init_sent_notifications,
    init_omgtu_snapshot,
    get_task_list_by_id,
    get_child_lists,
    delete_task,
    ensure_default_task_lists,
    update_task,
)

from services.statistics import build_statistics_text
from services.homework import (
    extract_homework,
    extract_lesson_date,
    find_next_omgtu_lesson,
)
from services.day_plan import get_day_plan

from services.omgtu import (
    get_brother_schedule,
    get_day_info,
)

from services.notifications import (
    send_morning_plan,
    send_tomorrow_plan,
    send_homework_tomorrow,
    check_hour_before_reminders,
    check_omgtu_changes,
    send_once,
)
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = os.getenv(
    "TIMEZONE",
    "Asia/Omsk",
)

STUDY_CHAT_ID = -1004336656486

STUDY_TOPICS = {
    193: {
        "short": "ЦГ",
        "subject": "Цифровая грамотность",
        "university": "ОмГТУ",
        "schedule_names": [
            "Цифровая грамотность",
        ],
    },
    272: {
        "short": "Математика",
        "subject": "Математика",
        "university": "ОмГТУ",
        "schedule_names": [
            "Математика",
        ],
    },
    263: {
        "short": "Физ-ра",
        "subject": "Физкультура",
        "university": "ОмГТУ",
        "schedule_names": [
            "Физическая культура",
            "Физкультура",
        ],
    },
    253: {
        "short": "ИИКГ",
        "subject": (
            "Инженерная и компьютерная "
            "графика"
        ),
        "university": "ОмГТУ",
        "schedule_names": [
            (
                "Инженерная и компьютерная "
                "графика"
            ),
        ],
    },
    180: {
        "short": "ОРГ",
        "subject": (
            "Основы российской "
            "государственности"
        ),
        "university": "ОмГТУ",
        "schedule_names": [
            (
                "Основы российской "
                "государственности"
            ),
        ],
    },
}

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден в .env"
    )

tz = ZoneInfo(TIMEZONE)

bot = Bot(token=TOKEN)
dp = Dispatcher()

scheduler = AsyncIOScheduler(
    timezone=TIMEZONE
)

class AddTaskForm(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()
    choosing_time = State()
    entering_time = State()
    choosing_list = State()
    entering_title = State()

class ListTaskForm(StatesGroup):
    entering_title = State()
    entering_description = State()
    choosing_date = State()
    entering_custom_date = State()
    choosing_time = State()
    entering_time = State()


class EditTaskForm(StatesGroup):
    entering_title = State()
    entering_description = State()
    entering_date = State()
    entering_time = State()


def now():
    return datetime.now(tz)


# =====================================
# ГЛАВНАЯ КЛАВИАТУРА
# =====================================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(
                text="📅 Сегодня"
            ),
            KeyboardButton(
                text="➡️ Завтра"
            ),
        ],
        [
            KeyboardButton(
                text="🗓 Недели"
            ),
            KeyboardButton(
                text="👨 Брат"
            ),
        ],
        [
            KeyboardButton(
                text="📂 Списки"
            ),
            KeyboardButton(
                text="📊 Статистика"
            ),
        ],
    ],
    resize_keyboard=True,
)

@dp.message(
    lambda message:
    message.text == "📊 Статистика"
)
async def statistics_handler(
    message: Message,
):
    try:
        text = await build_statistics_text(
            now()
        )

        await message.answer(text)

    except Exception as error:
        print(
            "Ошибка статистики:",
            error,
        )

        await message.answer(
            "❌ Не удалось собрать статистику."
        )

@dp.message(
    lambda message:
    message.text == "/topicid"
)
async def topic_id_handler(
    message: Message,
):
    await message.answer(
        "🔎 Данные темы:\n"
        f"chat_id: {message.chat.id}\n"
        f"thread_id: {message.message_thread_id}"
    )

@dp.message(
    lambda message:
    message.chat.id == STUDY_CHAT_ID
    and message.message_thread_id
    in STUDY_TOPICS
)
@dp.message(
    lambda message:
    message.chat.id == STUDY_CHAT_ID
    and message.message_thread_id
    in STUDY_TOPICS
)
async def homework_message_handler(
    message: Message,
):
    homework = extract_homework(
        message.text
    )

    if homework is None:
        return

    topic = STUDY_TOPICS[
        message.message_thread_id
    ]

    source_date = extract_lesson_date(
        message.text
    )

    if source_date is None:
        source_date = now().date()

    search_after_date = max(
        source_date,
        now().date(),
    )

    next_lesson = (
        await find_next_omgtu_lesson(
            topic["schedule_names"],
            search_after_date,
        )
    )

    if next_lesson is not None:
        task_date = next_lesson[
            "date"
        ].isoformat()

        next_lesson_text = (
            f"{next_lesson['date']:%d.%m.%Y}"
        )

        if next_lesson["time"]:
            next_lesson_text += (
                f" в {next_lesson['time']}"
            )
    else:
        task_date = source_date.isoformat()
        next_lesson_text = (
            "не удалось определить"
        )

    task_lists = await get_task_lists()

    homework_list_id = None

    for (
        list_id,
        list_name,
        parent_id,
    ) in task_lists:
        if list_name == "ДЗ":
            homework_list_id = list_id
            break

    if homework_list_id is None:
        homework_list_id = (
            await create_task_list("ДЗ")
        )

    description = (
        f"🎓 {topic['university']}\n"
        f"📚 {topic['subject']}\n"
        f"📝 Пара: {source_date:%d.%m.%Y}\n"
        f"➡️ Следующая: "
        f"{next_lesson_text}\n\n"
        f"{homework}"
    )

    await add_task(
        title=f"{topic['short']} — ДЗ",
        task_date=task_date,
        category="ДЗ",
        list_id=homework_list_id,
        description=description,
    )

    await message.reply(
        "📚 ДЗ добавлено в CloutDuck.\n"
        f"📅 Следующая пара: "
        f"{next_lesson_text}"
    )
# =====================================
# START
# =====================================

@dp.message(CommandStart())
async def start_handler(
    message: Message
):
    await save_chat_id(
        message.chat.id
    )

    await message.answer(
        "🦆 CloutDuck Planner\n\n"
        "Можно пользоваться кнопками снизу "
        "или командами:\n\n"
        "/today — сегодня\n"
        "/tomorrow — завтра\n"
        "/week — текущая неделя\n"
        "/nextweek — следующая неделя\n"
        "/brother — брат сегодня\n"
        "/brotherweek — брат на неделю\n"
        "/add — добавить задачу\n"
	"/adddate — задача на будущую дату\n"
	"/newlist — создать список\n"
	"/lists — показать списки\n"
	"/newsublist — вложенный список\n"
	"/addtolist — добавить задачу в список\n"
	"/subtask — создать подзадачу\n"
	"/list — открыть список\n",
        reply_markup=main_keyboard,
    )


# =====================================
# ДОБАВИТЬ ЗАДАЧУ
# =====================================

@dp.message(Command("add"))
async def add_handler(
    message: Message
):
    text = (
        message.text
        .removeprefix("/add")
        .strip()
    )

    if not text:
        await message.answer(
            "Пока формат такой:\n\n"
            "/add 18:30 Сделать монтаж\n"
            "/add Купить кабель"
        )
        return

    today = (
        now()
        .date()
        .isoformat()
    )

    parts = text.split(
        maxsplit=1
    )

    task_time = None
    title = text

    if (
        len(parts) == 2
        and ":" in parts[0]
    ):
        task_time = parts[0]
        title = parts[1]

    await add_task(
        title=title,
        task_date=today,
        task_time=task_time,
    )

    if task_time:
        await message.answer(
            f"✅ Добавлено:\n"
            f"{task_time} — {title}"
        )
    else:
        await message.answer(
            f"✅ Добавлено:\n"
            f"{title}"
        )


@dp.message(
    lambda message:
    message.text == "➕ Добавить задачу"
)
async def add_button_handler(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await show_list_choice(
        message,
        state,
    )
@dp.callback_query(
    AddTaskForm.choosing_date,
    lambda callback:
    callback.data
    and callback.data.startswith("taskdate:")
)
async def choose_task_date(
    callback: CallbackQuery,
    state: FSMContext,
):
    choice = callback.data.split(":")[1]

    if choice == "today":
        selected_date = now().date()

    elif choice == "tomorrow":
        selected_date = (
            now().date()
            + timedelta(days=1)
        )

    else:
        await state.set_state(
            AddTaskForm.entering_custom_date
        )

        await callback.message.edit_text(
            "Напиши дату:\n\n"
            "Например:\n"
            "15.09\n"
            "или\n"
            "15.09.2026"
        )

        await callback.answer()
        return

    await state.update_data(
        task_date=selected_date.isoformat()
    )

    await show_time_choice(
        callback.message,
        state,
    )

    await callback.answer()


@dp.message(
    AddTaskForm.entering_custom_date
)
async def custom_task_date(
    message: Message,
    state: FSMContext,
):
    text = message.text.strip()

    try:
        if text.count(".") == 1:
            selected_date = datetime.strptime(
                f"{text}.{now().year}",
                "%d.%m.%Y",
            ).date()
        else:
            selected_date = datetime.strptime(
                text,
                "%d.%m.%Y",
            ).date()

    except ValueError:
        await message.answer(
            "Не понял дату.\n\n"
            "Напиши, например:\n"
            "15.09"
        )
        return

    await state.update_data(
        task_date=selected_date.isoformat()
    )

    await show_time_choice(
        message,
        state,
    )


async def show_time_choice(
    message: Message,
    state: FSMContext,
):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Без времени",
                    callback_data="tasktime:none",
                ),
                InlineKeyboardButton(
                    text="🕒 Указать время",
                    callback_data="tasktime:custom",
                ),
            ],
        ]
    )

    await state.set_state(
        AddTaskForm.choosing_time
    )

    await message.answer(
        "🕒 У задачи есть время?",
        reply_markup=keyboard,
    )

@dp.callback_query(
    AddTaskForm.choosing_time,
    lambda callback:
    callback.data
    and callback.data.startswith("tasktime:")
)
async def choose_task_time(
    callback: CallbackQuery,
    state: FSMContext,
):
    choice = callback.data.split(":")[1]

    if choice == "none":
        await state.update_data(
            task_time=None
        )

        await state.set_state(
            AddTaskForm.entering_title
        )

        await callback.message.edit_text(
            "✏️ Напиши название задачи:"
        )

    else:
        await state.set_state(
            AddTaskForm.entering_time
        )

        await callback.message.edit_text(
            "Напиши время:\n\n"
            "Например:\n"
            "18:30"
        )

    await callback.answer()

@dp.message(
    AddTaskForm.entering_time
)
async def custom_task_time(
    message: Message,
    state: FSMContext,
):
    text = message.text.strip()

    try:
        datetime.strptime(
            text,
            "%H:%M",
        )

    except ValueError:
        await message.answer(
            "Не понял время.\n\n"
            "Напиши, например:\n"
            "18:30"
        )
        return

    await state.update_data(
        task_time=text
    )

    await state.set_state(
        AddTaskForm.entering_title
    )

    await message.answer(
        "✏️ Напиши название задачи:"
    )


async def show_list_choice(
    message: Message,
    state: FSMContext,
):
    task_lists = await get_task_lists()

    icons = {
        "Личные": "👤",
        "По учёбе": "🎓",
        "Студия": "🎬",
    }

    buttons = []

    for (
        list_id,
        name,
        parent_id,
    ) in task_lists:

        if parent_id is not None:
            continue

        if name not in icons:
            continue

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{icons[name]} {name}",
                    callback_data=(
                        f"tasklist:{list_id}"
                    ),
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await state.set_state(
        AddTaskForm.choosing_list
    )

    await message.answer(
        "📂 Куда добавить задачу?",
        reply_markup=keyboard,
    )
@dp.callback_query(
    AddTaskForm.choosing_list,
    lambda callback:
    callback.data
    and callback.data.startswith("tasklist:")
)
async def choose_task_list(
    callback: CallbackQuery,
    state: FSMContext,
):
    list_id = int(
        callback.data.split(":")[1]
    )

    await state.update_data(
        list_id=list_id
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Сегодня",
                    callback_data="taskdate:today",
                ),
                InlineKeyboardButton(
                    text="➡️ Завтра",
                    callback_data="taskdate:tomorrow",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗓 Другая дата",
                    callback_data="taskdate:custom",
                ),
            ],
        ]
    )

    await state.set_state(
        AddTaskForm.choosing_date
    )

    await callback.message.edit_text(
        "📅 На когда задача?",
        reply_markup=keyboard,
    )

    await callback.answer()
@dp.message(
    AddTaskForm.entering_title
)
async def finish_new_task(
    message: Message,
    state: FSMContext,
):
    title = message.text.strip()

    if not title:
        await message.answer(
            "Название не может быть пустым."
        )
        return

    data = await state.get_data()

    task_date = data["task_date"]
    task_time = data.get("task_time")
    list_id = data["list_id"]

    task_list = await get_task_list_by_id(
        list_id
    )

    if not task_list:
        await message.answer(
            "❌ Список не найден."
        )
        await state.clear()
        return

    list_name = task_list[1]

    category = {
        "Личные": "Личное",
        "По учёбе": "Учёба",
        "Студия": "Студия",
    }.get(
        list_name,
        list_name,
    )

    await add_task(
        title=title,
        task_date=task_date,
        task_time=task_time,
        category=category,
        list_id=list_id,
    )

    parsed_date = datetime.strptime(
        task_date,
        "%Y-%m-%d",
    ).date()

    icons = {
        "Личные": "👤",
        "По учёбе": "🎓",
        "Студия": "🎬",
    }

    lines = [
        "✅ Задача создана",
        "",
        f"📅 {parsed_date.strftime('%d.%m.%Y')}",
    ]

    if task_time:
        lines.append(
            f"🕒 {task_time}"
        )

    lines.append(
        f"{icons.get(list_name, '📂')} {list_name}"
    )

    lines.append(
        f"☐ {title}"
    )

    await message.answer(
        "\n".join(lines),
        reply_markup=main_keyboard,
    )

    await state.clear()
# =====================================
# ДОБАВИТЬ ЗАДАЧУ НА ЛЮБУЮ ДАТУ
# =====================================

@dp.message(Command("adddate"))
async def adddate_handler(
    message: Message,
):
    text = (
        message.text
        .removeprefix("/adddate")
        .strip()
    )

    if not text:
        await message.answer(
            "Формат:\n\n"
            "/adddate 15.09 18:30 Сделать монтаж\n"
            "/adddate 21.09 Купить подарок\n\n"
            "Год можно не писать — "
            "использую 2026."
        )
        return

    parts = text.split()

    if len(parts) < 2:
        await message.answer(
            "Не хватает данных.\n\n"
            "Например:\n"
            "/adddate 15.09 18:30 Сделать монтаж"
        )
        return

    date_text = parts[0]

    try:
        if date_text.count(".") == 1:
            parsed_date = datetime.strptime(
                f"{date_text}.2026",
                "%d.%m.%Y",
            ).date()

        else:
            parsed_date = datetime.strptime(
                date_text,
                "%d.%m.%Y",
            ).date()

    except ValueError:
        await message.answer(
            "Не понял дату.\n\n"
            "Используй:\n"
            "15.09\n"
            "или\n"
            "15.09.2026"
        )
        return

    remaining = parts[1:]

    task_time = None

    if (
        remaining
        and ":" in remaining[0]
    ):
        try:
            datetime.strptime(
                remaining[0],
                "%H:%M",
            )

            task_time = remaining[0]
            remaining = remaining[1:]

        except ValueError:
            pass

    title = " ".join(remaining).strip()

    if not title:
        await message.answer(
            "После даты нужно написать задачу."
        )
        return

    await add_task(
        title=title,
        task_date=parsed_date.isoformat(),
        task_time=task_time,
    )

    if task_time:
        await message.answer(
            "✅ Задача добавлена\n\n"
            f"📅 {parsed_date.strftime('%d.%m.%Y')}\n"
            f"🕒 {task_time}\n"
            f"📌 {title}"
        )
    else:
        await message.answer(
            "✅ Задача добавлена\n\n"
            f"📅 {parsed_date.strftime('%d.%m.%Y')}\n"
            f"📌 {title}"
        )


# =====================================
# СОЗДАТЬ СПИСОК
# =====================================

@dp.message(Command("newlist"))
async def newlist_handler(
    message: Message,
):
    name = (
        message.text
        .removeprefix("/newlist")
        .strip()
    )

    if not name:
        await message.answer(
            "Формат:\n"
            "/newlist Студия"
        )
        return

    list_id = await create_task_list(
        name=name
    )

    await message.answer(
        "✅ Список создан\n\n"
        f"#{list_id} — {name}"
    )


# =====================================
# ПОКАЗАТЬ СПИСКИ
# =====================================

@dp.message(Command("lists"))
async def lists_handler(
    message: Message,
):
    lists = await get_task_lists()

    if not lists:
        await message.answer(
            "Списков пока нет."
        )
        return

    lines = [
        "📂 СПИСКИ ЗАДАЧ",
        "",
    ]

    for (
        list_id,
        name,
        parent_id,
    ) in lists:

        if parent_id:
            lines.append(
                f"↳ #{list_id} {name} "
                f"(внутри #{parent_id})"
            )
        else:
            lines.append(
                f"#{list_id} {name}"
            )

    await message.answer(
        "\n".join(lines)
    )

@dp.message(
    lambda message:
    message.text == "📂 Списки"
)
async def lists_button_handler(
    message: Message,
):
    task_lists = await get_task_lists()

    if not task_lists:
        await message.answer(
            "📂 Списков пока нет."
        )
        return

    buttons = []

    for (
        list_id,
        name,
        parent_id,
    ) in task_lists:

        if parent_id is not None:
            continue

        button_text = {
            "Личные": "👤 Личные",
            "По учёбе": "🎓 По учёбе",
            "Студия": "🎬 Студия",
        }.get(
            name,
            f"📂 {name}",
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=(
                        f"openlist:{list_id}"
                    ),
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await message.answer(
        "📂 Твои списки:",
        reply_markup=keyboard,
    )
# =====================================
# ОТКРЫТЬ СПИСОК КНОПКОЙ
# =====================================

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith("openlist:")
)
async def open_list_callback(
    callback: CallbackQuery,
):
    list_id = int(
        callback.data.split(":")[1]
    )

    task_list = await get_task_list_by_id(
        list_id
    )

    if not task_list:
        await callback.answer(
            "Список не найден"
        )
        return

    (
        current_list_id,
        list_name,
        parent_id,
    ) = task_list

    tasks = await get_tasks_for_list(
        current_list_id
    )

    today = now().date()
    tomorrow = (
        today
        + timedelta(days=1)
    )

    active_tasks = [
        task
        for task in tasks
        if (
            task[5] is None
            and not task[4]
        )
    ]

    done_tasks = [
        task
        for task in tasks
        if (
            task[5] is None
            and task[4]
        )
    ]

    today_count = 0
    tomorrow_count = 0
    overdue_count = 0
    upcoming_count = 0

    for task in active_tasks:
        try:
            task_date = datetime.strptime(
                task[2],
                "%Y-%m-%d",
            ).date()

        except ValueError:
            continue

        if task_date == today:
            today_count += 1

        elif task_date == tomorrow:
            tomorrow_count += 1

        elif task_date < today:
            overdue_count += 1

        elif task_date > tomorrow:
            upcoming_count += 1

    icon = {
        "Личные": "👤",
        "По учёбе": "🎓",
        "Студия": "🎬",
    }.get(
        list_name,
        "📂",
    )

    text = (
        f"{icon} {list_name}\n\n"
        f"🔥 Сегодня — {today_count}\n"
        f"➡️ Завтра — {tomorrow_count}\n"
        f"⚠️ Просроченные — {overdue_count}\n"
        f"📅 Предстоящие — {upcoming_count}\n"
        f"✅ Выполненные — {len(done_tasks)}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔥 Сегодня · {today_count}",
                    callback_data=(
                        f"listview:{list_id}:today:0"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"➡️ Завтра · {tomorrow_count}",
                    callback_data=(
                        f"listview:{list_id}:tomorrow:0"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        f"⚠️ Просроченные · "
                        f"{overdue_count}"
                    ),
                    callback_data=(
                        f"listview:{list_id}:overdue:0"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        f"📅 Предстоящие · "
                        f"{upcoming_count}"
                    ),
                    callback_data=(
                        f"listview:{list_id}:upcoming:0"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        f"✅ Выполненные · "
                        f"{len(done_tasks)}"
                    ),
                    callback_data=(
                        f"listview:{list_id}:done:0"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить задачу",
                    callback_data=(
                        f"listadd:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Ко всем спискам",
                    callback_data="backtolists",
                )
            ],
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
    )

    await callback.answer()

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith("listview:")
)
async def list_view_callback(
    callback: CallbackQuery,
):
    parts = callback.data.split(":")

    list_id = int(parts[1])
    view = parts[2]
    page = int(parts[3])

    task_list = await get_task_list_by_id(
        list_id
    )

    if not task_list:
        await callback.answer(
            "Список не найден"
        )
        return

    list_name = task_list[1]

    tasks = await get_tasks_for_list(
        list_id
    )

    today = now().date()
    tomorrow = today + timedelta(days=1)

    filtered = []

    for task in tasks:
        (
            task_id,
            title,
            task_date_text,
            task_time,
            is_done,
            parent_task_id,
        ) = task

        if parent_task_id is not None:
            continue

        try:
            task_date = datetime.strptime(
                task_date_text,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            continue

        if view == "today":
            matches = (
                not is_done
                and task_date == today
            )

        elif view == "tomorrow":
            matches = (
                not is_done
                and task_date == tomorrow
            )

        elif view == "overdue":
            matches = (
                not is_done
                and task_date < today
            )

        elif view == "upcoming":
            matches = (
                not is_done
                and task_date > tomorrow
            )

        elif view == "done":
            matches = bool(is_done)

        else:
            matches = False

        if matches:
            filtered.append(task)

    filtered.sort(
        key=lambda task: (
            task[2],
            task[3] or "99:99",
            task[0],
        )
    )

    if view == "done":
        filtered.reverse()

    page_size = 10

    start = page * page_size
    end = start + page_size

    page_tasks = filtered[
        start:end
    ]

    titles = {
        "today": "🔥 Сегодня",
        "tomorrow": "➡️ Завтра",
        "overdue": "⚠️ Просроченные",
        "upcoming": "📅 Предстоящие",
        "done": "✅ Выполненные",
    }

    lines = [
        f"📂 {list_name}",
        f"{titles[view]}",
        "",
    ]

    buttons = []

    if not page_tasks:
        lines.append(
            "Задач здесь нет."
        )

    for task in page_tasks:
        (
            task_id,
            title,
            task_date,
            task_time,
            is_done,
            parent_task_id,
        ) = task

        try:
            formatted_date = datetime.strptime(
                task_date,
                "%Y-%m-%d",
            ).strftime("%d.%m")
        except ValueError:
            formatted_date = task_date

        time_text = (
            f" · {task_time}"
            if task_time
            else ""
        )

        status = (
            "✅"
            if is_done
            else "☐"
        )

        lines.append(
            f"{status} {formatted_date}"
            f"{time_text} — {title}"
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {title}",
                    callback_data=(
                        f"opentask:"
                        f"{task_id}:{list_id}"
                    ),
                )
            ]
        )

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=(
                    f"listview:"
                    f"{list_id}:{view}:{page - 1}"
                ),
            )
        )

    if end < len(filtered):
        navigation.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=(
                    f"listview:"
                    f"{list_id}:{view}:{page + 1}"
                ),
            )
        )

    if navigation:
        buttons.append(
            navigation
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ К разделу",
                callback_data=(
                    f"openlist:{list_id}"
                ),
            )
        ]
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
    )

    await callback.answer()

# =====================================
# НАЗАД КО ВСЕМ СПИСКАМ
# =====================================

@dp.callback_query(
    lambda callback:
    callback.data == "backtolists"
)
async def back_to_lists_callback(
    callback: CallbackQuery,
):
    task_lists = await get_task_lists()

    buttons = []

    for (
        list_id,
        name,
        parent_id,
    ) in task_lists:

        if parent_id is not None:
            continue

        button_text = {
            "Личные": "👤 Личные",
            "По учёбе": "🎓 По учёбе",
            "Студия": "🎬 Студия",
        }.get(
            name,
            f"📂 {name}",
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=(
                        f"openlist:{list_id}"
                    ),
                )
            ]
        )

    if not buttons:
        await callback.message.edit_text(
            "📂 Списков пока нет."
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        "📂 Твои списки:",
        reply_markup=keyboard,
    )

    await callback.answer()
# =====================================
# СОЗДАТЬ ВЛОЖЕННЫЙ СПИСОК
# =====================================

@dp.message(Command("newsublist"))
async def newsublist_handler(
    message: Message,
):
    text = (
        message.text
        .removeprefix("/newsublist")
        .strip()
    )

    parts = text.split(
        maxsplit=1
    )

    if len(parts) != 2:
        await message.answer(
            "Формат:\n"
            "/newsublist 1 Клиенты"
        )
        return

    try:
        parent_id = int(
            parts[0]
        )
    except ValueError:
        await message.answer(
            "ID родительского списка "
            "должен быть числом."
        )
        return

    name = parts[1]

    list_id = await create_task_list(
        name=name,
        parent_id=parent_id,
    )

    await message.answer(
        "✅ Вложенный список создан\n\n"
        f"#{list_id} — {name}\n"
        f"Внутри списка #{parent_id}"
    )


# =====================================
# ДОБАВИТЬ ЗАДАЧУ В СПИСОК
# =====================================

@dp.message(Command("addtolist"))
async def addtolist_handler(
    message: Message,
):
    text = (
        message.text
        .removeprefix("/addtolist")
        .strip()
    )

    parts = text.split()

    if len(parts) < 3:
        await message.answer(
            "Формат:\n\n"
            "/addtolist 1 15.09 "
            "18:30 Сделать монтаж\n\n"
            "или:\n"
            "/addtolist 1 15.09 "
            "Сделать монтаж"
        )
        return

    try:
        list_id = int(
            parts[0]
        )
    except ValueError:
        await message.answer(
            "ID списка должен быть числом."
        )
        return

    date_text = parts[1]

    try:
        if date_text.count(".") == 1:
            parsed_date = datetime.strptime(
                f"{date_text}.2026",
                "%d.%m.%Y",
            ).date()
        else:
            parsed_date = datetime.strptime(
                date_text,
                "%d.%m.%Y",
            ).date()

    except ValueError:
        await message.answer(
            "Дата должна быть вида "
            "15.09 или 15.09.2026"
        )
        return

    remaining = parts[2:]

    task_time = None

    if (
        remaining
        and ":" in remaining[0]
    ):
        try:
            datetime.strptime(
                remaining[0],
                "%H:%M",
            )

            task_time = remaining[0]
            remaining = remaining[1:]

        except ValueError:
            pass

    title = " ".join(
        remaining
    ).strip()

    if not title:
        await message.answer(
            "Не указано название задачи."
        )
        return

    task_id = await add_task(
        title=title,
        task_date=parsed_date.isoformat(),
        task_time=task_time,
        list_id=list_id,
    )

    await message.answer(
        "✅ Добавлено в список\n\n"
        f"Задача #{task_id}\n"
        f"Список #{list_id}\n"
        f"📅 {parsed_date.strftime('%d.%m.%Y')}\n"
        + (
            f"🕒 {task_time}\n"
            if task_time
            else ""
        )
        + f"📌 {title}"
    )


# =====================================
# ДОБАВИТЬ ПОДЗАДАЧУ
# =====================================

@dp.message(Command("subtask"))
async def subtask_handler(
    message: Message,
):
    text = (
        message.text
        .removeprefix("/subtask")
        .strip()
    )

    parts = text.split(
        maxsplit=1
    )

    if len(parts) != 2:
        await message.answer(
            "Формат:\n"
            "/subtask 4 Сделать обложку"
        )
        return

    try:
        parent_task_id = int(
            parts[0]
        )
    except ValueError:
        await message.answer(
            "ID родительской задачи "
            "должен быть числом."
        )
        return

    parent = await get_task_by_id(
        parent_task_id
    )

    if not parent:
        await message.answer(
            "Такой родительской задачи нет."
        )
        return

    (
        parent_id,
        parent_title,
        parent_description,
        parent_date,
        parent_time,
        parent_category,
        parent_done,
        parent_list_id,
        parent_parent_id,
    ) = parent

    title = parts[1]

    task_id = await add_task(
        title=title,
        task_date=parent_date,
        category=parent_category,
        list_id=parent_list_id,
        parent_task_id=parent_task_id,
    )

    await message.answer(
        "✅ Подзадача создана\n\n"
        f"↳ {title}\n"
        f"Внутри: {parent_title}\n"
        f"📅 {parent_date}"
    )


# =====================================
# ПОКАЗАТЬ ЗАДАЧИ СПИСКА
# =====================================

@dp.message(Command("list"))
async def list_handler(
    message: Message,
):
    text = (
        message.text
        .removeprefix("/list")
        .strip()
    )

    try:
        list_id = int(text)

    except ValueError:
        await message.answer(
            "Формат:\n"
            "/list 1"
        )
        return

    tasks = await get_tasks_for_list(
        list_id
    )

    if not tasks:
        await message.answer(
            f"В списке #{list_id} "
            "пока нет задач."
        )
        return

    lines = [
        f"📂 СПИСОК #{list_id}",
        "",
    ]

    for (
        task_id,
        title,
        task_date,
        task_time,
        is_done,
        parent_task_id,
    ) in tasks:

        status = (
            "✅"
            if is_done
            else "☐"
        )

        time_text = (
            f" {task_time}"
            if task_time
            else ""
        )

        if parent_task_id:
            prefix = "   ↳ "
        else:
            prefix = ""

        lines.append(
            f"{prefix}{status} "
            f"#{task_id} "
            f"{task_date}{time_text} — "
            f"{title}"
        )

    await message.answer(
        "\n".join(lines)
    )

# =====================================
# СЕГОДНЯ
# =====================================

async def send_today(
    message: Message
):
    target_day = now().date()

    text = await get_day_plan(
        target_day
    )

    keyboard = await get_task_keyboard(
        target_day
    )

    await message.answer(
        text,
        reply_markup=keyboard,
    )


@dp.message(Command("today"))
async def today_handler(
    message: Message
):
    await send_today(message)


@dp.message(
    lambda message:
    message.text == "📅 Сегодня"
)
async def today_button_handler(
    message: Message
):
    await send_today(message)


# =====================================
# ЗАВТРА
# =====================================

async def send_tomorrow(
    message: Message
):
    target_day = (
        now().date()
        + timedelta(days=1)
    )

    text = await get_day_plan(
        target_day
    )

    keyboard = await get_task_keyboard(
        target_day
    )

    await message.answer(
        text,
        reply_markup=keyboard,
    )


@dp.message(Command("tomorrow"))
async def tomorrow_handler(
    message: Message
):
    await send_tomorrow(message)


@dp.message(
    lambda message:
    message.text == "➡️ Завтра"
)
async def tomorrow_button_handler(
    message: Message
):
    await send_tomorrow(message)

@dp.message(
    lambda message:
    message.text == "🗓 Недели"
)
async def weeks_menu_handler(
    message: Message,
):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗓 Текущая неделя",
                    callback_data="weekmenu:current",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏭ Следующая неделя",
                    callback_data="weekmenu:next",
                )
            ],
        ]
    )

    await message.answer(
        "🗓 Какую неделю показать?",
        reply_markup=keyboard,
    )

# =====================================
# ТЕКУЩАЯ НЕДЕЛЯ
# =====================================

async def send_week(
    message: Message,
    next_week: bool = False,
):
    today = now().date()

    monday = (
        today
        - timedelta(
            days=today.weekday()
        )
    )

    if next_week:
        monday += timedelta(days=7)

    for offset in range(7):
        target_day = (
            monday
            + timedelta(days=offset)
        )

        text = await get_day_plan(
            target_day
        )

        await message.answer(text)


@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith("weekmenu:")
)
async def week_menu_callback(
    callback: CallbackQuery,
):
    choice = callback.data.split(":")[1]

    await callback.answer()

    await send_week(
        callback.message,
        next_week=(
            choice == "next"
        ),
    )

@dp.message(Command("week"))
async def week_handler(
    message: Message
):
    await send_week(
        message,
        next_week=False,
    )


@dp.message(
    lambda message:
    message.text == "🗓 Неделя"
)
async def week_button_handler(
    message: Message
):
    await send_week(
        message,
        next_week=False,
    )


# =====================================
# СЛЕДУЮЩАЯ НЕДЕЛЯ
# =====================================

@dp.message(Command("nextweek"))
async def nextweek_handler(
    message: Message
):
    await send_week(
        message,
        next_week=True,
    )


@dp.message(
    lambda message:
    message.text
    == "⏭ Следующая неделя"
)
async def nextweek_button_handler(
    message: Message
):
    await send_week(
        message,
        next_week=True,
    )


# =====================================
# РАСПИСАНИЕ БРАТА
# =====================================

@dp.message(
    lambda message:
    message.text == "👨 Брат"
)
async def brother_menu_handler(
    message: Message,
):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨 Брат сегодня",
                    callback_data="brothermenu:today",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗓 Брат неделя",
                    callback_data="brothermenu:week",
                )
            ],
        ]
    )

    await message.answer(
        "👨 Что показать?",
        reply_markup=keyboard,
    )

WEEKDAYS = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


async def get_brother_day_text(
    target_day,
) -> str:
    schedule = (
        await get_brother_schedule(
            target_day
        )
    )

    info = get_day_info(
        schedule,
        target_day,
    )

    weekday = WEEKDAYS[
        target_day.weekday()
    ]

    lines = [
        (
            f"👨 {weekday}, "
            f"{target_day.strftime('%d.%m.%Y')}"
        )
    ]

    count = info["lesson_count"]

    lines.append(
        f"🎓 МР-261 — {count} "
        f"{get_pair_word(count)}"
    )

    lessons = info["lessons"]

    if not lessons:
        lines.append("")
        lines.append(
            "Пар нет 👀"
        )

        return "\n".join(lines)

    lines.append("")

    for lesson in lessons:
        lines.append(
            f"{lesson['beginLesson']}–"
            f"{lesson['endLesson']} — "
            f"{lesson['discipline']}"
        )

        auditorium = lesson.get(
            "auditorium"
        )

        if auditorium:
            lines.append(
                f"   {auditorium}"
            )

    return "\n".join(lines)


def get_pair_word(
    count: int,
) -> str:
    if 11 <= count % 100 <= 14:
        return "пар"

    last = count % 10

    if last == 1:
        return "пара"

    if last in {2, 3, 4}:
        return "пары"

    return "пар"


async def send_brother_today(
    message: Message
):
    target_day = now().date()

    text = await get_brother_day_text(
        target_day
    )

    await message.answer(text)


@dp.message(Command("brother"))
async def brother_handler(
    message: Message
):
    await send_brother_today(
        message
    )


@dp.message(
    lambda message:
    message.text
    == "👨 Брат сегодня"
)
async def brother_button_handler(
    message: Message
):
    await send_brother_today(
        message
    )


# =====================================
# БРАТ — НЕДЕЛЯ
# =====================================

async def send_brother_week(
    message: Message
):
    today = now().date()

    monday = (
        today
        - timedelta(
            days=today.weekday()
        )
    )

    for offset in range(7):
        target_day = (
            monday
            + timedelta(days=offset)
        )

        text = await get_brother_day_text(
            target_day
        )

        await message.answer(text)

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith(
        "brothermenu:"
    )
)
async def brother_menu_callback(
    callback: CallbackQuery,
):
    choice = callback.data.split(":")[1]

    await callback.answer()

    if choice == "today":
        await send_brother_today(
            callback.message
        )
    else:
        await send_brother_week(
            callback.message
        )

@dp.message(Command("brotherweek"))
async def brotherweek_handler(
    message: Message
):
    await send_brother_week(
        message
    )


@dp.message(
    lambda message:
    message.text
    == "👨 Брат неделя"
)
async def brotherweek_button_handler(
    message: Message
):
    await send_brother_week(
        message
    )

# =====================================
# КНОПКИ ЗАДАЧ В ПЛАНЕ
# =====================================

async def get_task_keyboard(
    target_day,
):
    tasks = await get_tasks_for_date(
        target_day.isoformat()
    )

    buttons = []

    for (
        task_id,
        title,
        task_time,
        category,
        is_done,
    ) in tasks:

        if is_done:
            continue

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Выполнить: {title}",
                    callback_data=(
                        f"done:{task_id}:"
                        f"{target_day.isoformat()}"
                    ),
                )
            ]
        )

    if not buttons:
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

# =====================================
# ВЫПОЛНЕНО
# =====================================

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith(
        "done:"
    )
)
async def done_handler(
    callback: CallbackQuery
):
    parts = callback.data.split(":")

    task_id = int(parts[1])

    target_day = datetime.strptime(
        parts[2],
        "%Y-%m-%d",
    ).date()

    await mark_task_done(
        task_id
    )

    text = await get_day_plan(
        target_day
    )

    keyboard = await get_task_keyboard(
        target_day
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
    )

    await callback.answer(
        "✅ Выполнено"
    )

# =====================================
# ТЕСТЫ АВТОМАТИКИ
# =====================================

@dp.message(Command("testauto"))
async def test_auto_handler(
    message: Message,
):
    await message.answer(
        "🧪 Запускаю тест автоматики..."
    )

    test_now = now().replace(
        tzinfo=None
    )

    try:
        await send_morning_plan(
            bot,
            test_now,
        )

        await send_tomorrow_plan(
            bot,
            test_now,
        )

        await check_omgtu_changes(
            bot,
            test_now,
        )

        await check_hour_before_reminders(
            bot,
            test_now,
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка теста автоматики:\n\n"
            f"{repr(error)}"
        )
        return

    await message.answer(
        "✅ Тест автоматики завершён."
    )


@dp.message(Command("testreminder"))
async def test_reminder_handler(
    message: Message,
):
    test_now = now().replace(
        tzinfo=None
    )

    key = (
        "test_reminder:"
        + test_now.strftime(
            "%Y-%m-%d-%H-%M-%S"
        )
    )

    try:
        await send_once(
            bot,
            key,
            (
                "⏰ ТЕСТ НАПОМИНАНИЯ\n\n"
                "📌 Через час тестовое событие\n\n"
                "Если ты видишь это сообщение — "
                "механизм автоматической отправки "
                "работает."
            ),
            test_now,
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка теста напоминания:\n\n"
            f"{repr(error)}"
        )
        return

    await message.answer(
        "✅ Тест напоминания запущен."
    )

# =====================================
# АВТОМАТИЧЕСКИЕ УВЕДОМЛЕНИЯ
# =====================================

def notification_now():
    return now().replace(
        tzinfo=None
    )


async def reminder_job():
    try:
        await check_hour_before_reminders(
            bot,
            notification_now(),
        )
    except Exception as error:
        print(
            "Ошибка напоминаний:",
            repr(error),
        )


async def morning_plan_job():
    try:
        await send_morning_plan(
            bot,
            notification_now(),
        )
    except Exception as error:
        print(
            "Ошибка утреннего плана:",
            repr(error),
        )


async def tomorrow_plan_job():
    try:
        await send_tomorrow_plan(
            bot,
            notification_now(),
        )
    except Exception as error:
        print(
            "Ошибка плана на завтра:",
            repr(error),
        )

async def homework_tomorrow_job():

    try:

        await send_homework_tomorrow(
            bot,
            notification_now(),
        )

    except Exception as error:

        print(
            "Ошибка напоминания о ДЗ:",
            repr(error),
        )

async def omgtu_check_job():
    try:
        await check_omgtu_changes(
            bot,
            notification_now(),
        )
    except Exception as error:
        print(
            "Ошибка проверки ОмГТУ:",
            repr(error),
        )


def setup_scheduler():
    scheduler.add_job(
        reminder_job,
        trigger="cron",
        minute="*",
        id="hour_before_reminders",
        replace_existing=True,
    )

    scheduler.add_job(
        omgtu_check_job,
        trigger="cron",
        hour=7,
        minute=55,
        id="omgtu_morning_check",
        replace_existing=True,
    )

    scheduler.add_job(
        morning_plan_job,
        trigger="cron",
        hour=8,
        minute=0,
        id="morning_plan",
        replace_existing=True,
    )

    scheduler.add_job(
        omgtu_check_job,
        trigger="cron",
        hour=20,
        minute=0,
        id="omgtu_evening_check",
        replace_existing=True,
    )

    scheduler.add_job(
        tomorrow_plan_job,
        trigger="cron",
        hour=20,
        minute=5,
        id="tomorrow_plan",
        replace_existing=True,
    )

    scheduler.add_job(
        homework_tomorrow_job,
        trigger="cron",
        hour=20,
        minute=10,
        id="homework_tomorrow",
        replace_existing=True,
    )
# =====================================
# ДОБАВЛЕНИЕ ЗАДАЧИ ИЗ СПИСКА
# =====================================

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith("listadd:")
)
async def list_add_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    list_id = int(
        callback.data.split(":")[1]
    )

    task_list = await get_task_list_by_id(
        list_id
    )

    if not task_list:
        await callback.answer(
            "Список не найден"
        )
        return

    await state.clear()

    await state.update_data(
        list_id=list_id
    )

    await state.set_state(
        ListTaskForm.entering_title
    )

    await callback.message.answer(
        "📝 Напиши название задачи:"
    )

    await callback.answer()


@dp.message(
    ListTaskForm.entering_title
)
async def list_task_title_handler(
    message: Message,
    state: FSMContext,
):
    title = message.text.strip()

    if not title:
        await message.answer(
            "Название не может быть пустым."
        )
        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        ListTaskForm.entering_description
    )

    await message.answer(
        "📄 Напиши подробное описание.\n\n"
        "Если описание не нужно — отправь -"
    )


@dp.message(
    ListTaskForm.entering_description
)
async def list_task_description_handler(
    message: Message,
    state: FSMContext,
):
    description = message.text.strip()

    if description == "-":
        description = None

    await state.update_data(
        description=description
    )

    await state.set_state(
        ListTaskForm.choosing_date
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Сегодня",
                    callback_data="listtaskdate:today",
                ),
                InlineKeyboardButton(
                    text="➡️ Завтра",
                    callback_data="listtaskdate:tomorrow",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗓 Другая дата",
                    callback_data="listtaskdate:custom",
                )
            ],
        ]
    )

    await message.answer(
        "📅 На какую дату задача?",
        reply_markup=keyboard,
    )


@dp.callback_query(
    ListTaskForm.choosing_date,
    lambda callback:
    callback.data
    and callback.data.startswith("listtaskdate:")
)
async def list_task_date_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    choice = callback.data.split(":")[1]

    if choice == "today":
        task_date = now().date()

    elif choice == "tomorrow":
        task_date = (
            now().date()
            + timedelta(days=1)
        )

    else:
        await state.set_state(
            ListTaskForm.entering_custom_date
        )

        await callback.message.answer(
            "📅 Введи дату в формате:\n"
            "15.09.2026"
        )

        await callback.answer()
        return

    await state.update_data(
        task_date=task_date.isoformat()
    )

    await show_list_task_time_choice(
        callback.message,
        state,
    )

    await callback.answer()


@dp.message(
    ListTaskForm.entering_custom_date
)
async def list_task_custom_date_handler(
    message: Message,
    state: FSMContext,
):
    try:
        task_date = datetime.strptime(
            message.text.strip(),
            "%d.%m.%Y",
        ).date()

    except ValueError:
        await message.answer(
            "❌ Неверная дата.\n\n"
            "Напиши так: 15.09.2026"
        )
        return

    await state.update_data(
        task_date=task_date.isoformat()
    )

    await show_list_task_time_choice(
        message,
        state,
    )


async def show_list_task_time_choice(
    message: Message,
    state: FSMContext,
):
    await state.set_state(
        ListTaskForm.choosing_time
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Без времени",
                    callback_data="listtasktime:none",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕒 Указать время",
                    callback_data="listtasktime:custom",
                )
            ],
        ]
    )

    await message.answer(
        "🕒 Указать время?",
        reply_markup=keyboard,
    )


@dp.callback_query(
    ListTaskForm.choosing_time,
    lambda callback:
    callback.data
    and callback.data.startswith("listtasktime:")
)
async def list_task_time_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    choice = callback.data.split(":")[1]

    if choice == "custom":
        await state.set_state(
            ListTaskForm.entering_time
        )

        await callback.message.answer(
            "🕒 Введи время в формате:\n"
            "18:30"
        )

        await callback.answer()
        return

    await save_list_task(
        callback.message,
        state,
        task_time=None,
    )

    await callback.answer()


@dp.message(
    ListTaskForm.entering_time
)
async def list_task_custom_time_handler(
    message: Message,
    state: FSMContext,
):
    try:
        parsed_time = datetime.strptime(
            message.text.strip(),
            "%H:%M",
        )

        task_time = parsed_time.strftime(
            "%H:%M"
        )

    except ValueError:
        await message.answer(
            "❌ Неверное время.\n\n"
            "Напиши так: 18:30"
        )
        return

    await save_list_task(
        message,
        state,
        task_time=task_time,
    )


async def save_list_task(
    message: Message,
    state: FSMContext,
    task_time: str | None,
):
    data = await state.get_data()

    list_id = data["list_id"]

    task_list = await get_task_list_by_id(
        list_id
    )

    list_name = task_list[1]

    category = {
        "Личные": "Личное",
        "По учёбе": "Учёба",
        "Студия": "Студия",
    }.get(
        list_name,
        list_name,
    )

    task_id = await add_task(
        title=data["title"],
        description=data.get("description"),
        task_date=data["task_date"],
        task_time=task_time,
        category=category,
        list_id=list_id,
    )

    description = data.get(
        "description"
    )

    text = (
        "✅ Задача создана\n\n"
        f"📌 {data['title']}\n"
        f"📅 {data['task_date']}\n"
    )

    if task_time:
        text += f"🕒 {task_time}\n"

    if description:
        text += (
            f"\n📄 {description}\n"
        )

    text += f"\n📂 {list_name}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📌 Открыть задачу",
                    callback_data=(
                        f"opentask:{task_id}:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку",
                    callback_data=(
                        f"openlist:{list_id}"
                    ),
                )
            ],
        ]
    )

    await state.clear()

    await message.answer(
        text,
        reply_markup=keyboard,
    )
# =====================================
# КАРТОЧКА ЗАДАЧИ
# =====================================

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith("opentask:")
)
async def open_task_callback(
    callback: CallbackQuery,
):
    _, task_id_str, list_id_str = (
        callback.data.split(":")
    )

    task_id = int(task_id_str)
    list_id = int(list_id_str)

    task = await get_task_by_id(
        task_id
    )

    if not task:
        await callback.answer(
            "Задача не найдена"
        )
        return

    (
        task_id,
        title,
        description,
        task_date,
        task_time,
        category,
        is_done,
        task_list_id,
        parent_task_id,
    ) = task

    status = (
        "✅ Выполнено"
        if is_done
        else "⏳ Не выполнено"
    )

    try:
        formatted_date = datetime.strptime(
            task_date,
            "%Y-%m-%d",
        ).strftime("%d.%m.%Y")
    except ValueError:
        formatted_date = task_date

    text = (
        f"📌 {title}\n\n"
        f"{status}\n"
        f"📅 {formatted_date}\n"
    )

    if task_time:
        text += f"🕒 {task_time}\n"

    if description:
        text += (
            "\n"
            f"📄 {description}\n"
        )

    buttons = []

    if not is_done:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✅ Выполнить",
                    callback_data=(
                        f"taskdone:{task_id}:{list_id}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="✏️ Редактировать",
                callback_data=(
                    f"taskedit:{task_id}:{list_id}"
                ),
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(
                text="🗑 Удалить",
                callback_data=(
                    f"taskdelete:{task_id}:{list_id}"
                ),
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=(
                    f"openlist:{list_id}"
                ),
            )
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        ),
    )

    await callback.answer()


# =====================================
# ВЫПОЛНИТЬ ЗАДАЧУ ИЗ СПИСКА
# =====================================

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith("taskdone:")
)
async def task_done_callback(
    callback: CallbackQuery,
):
    _, task_id_str, list_id_str = (
        callback.data.split(":")
    )

    task_id = int(task_id_str)
    list_id = int(list_id_str)

    await mark_task_done(
        task_id
    )

    task = await get_task_by_id(
        task_id
    )

    if not task:
        await callback.answer()
        return

    (
        task_id,
        title,
        description,
        task_date,
        task_time,
        category,
        is_done,
        task_list_id,
        parent_task_id,
    ) = task

    try:
        formatted_date = datetime.strptime(
            task_date,
            "%Y-%m-%d",
        ).strftime("%d.%m.%Y")
    except ValueError:
        formatted_date = task_date

    text = (
        f"📌 {title}\n\n"
        "✅ Выполнено\n"
        f"📅 {formatted_date}\n"
    )

    if task_time:
        text += f"🕒 {task_time}\n"

    if description:
        text += (
            "\n"
            f"📄 {description}\n"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать",
                    callback_data=(
                        f"taskedit:{task_id}:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=(
                        f"taskdelete:{task_id}:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=(
                        f"openlist:{list_id}"
                    ),
                )
            ],
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
    )

    await callback.answer(
        "✅ Выполнено"
    )

# =====================================
# РЕДАКТИРОВАНИЕ ЗАДАЧИ
# =====================================

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith("taskedit:")
)
async def task_edit_callback(
    callback: CallbackQuery,
):
    _, task_id_str, list_id_str = (
        callback.data.split(":")
    )

    task_id = int(task_id_str)
    list_id = int(list_id_str)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Название",
                    callback_data=(
                        f"taskeditfield:title:"
                        f"{task_id}:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 Описание",
                    callback_data=(
                        f"taskeditfield:description:"
                        f"{task_id}:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Дата",
                    callback_data=(
                        f"taskeditfield:date:"
                        f"{task_id}:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕒 Время",
                    callback_data=(
                        f"taskeditfield:time:"
                        f"{task_id}:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=(
                        f"opentask:{task_id}:{list_id}"
                    ),
                )
            ],
        ]
    )

    await callback.message.edit_text(
        "✏️ Что изменить?",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith(
        "taskeditfield:"
    )
)
async def task_edit_field_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    parts = callback.data.split(":")

    field = parts[1]
    task_id = int(parts[2])
    list_id = int(parts[3])

    await state.clear()

    await state.update_data(
        task_id=task_id,
        list_id=list_id,
    )

    if field == "title":
        await state.set_state(
            EditTaskForm.entering_title
        )

        text = "📝 Напиши новое название:"

    elif field == "description":
        await state.set_state(
            EditTaskForm.entering_description
        )

        text = (
            "📄 Напиши новое описание.\n\n"
            "Чтобы удалить описание — отправь -"
        )

    elif field == "date":
        await state.set_state(
            EditTaskForm.entering_date
        )

        text = (
            "📅 Напиши новую дату:\n"
            "15.09.2026"
        )

    else:
        await state.set_state(
            EditTaskForm.entering_time
        )

        text = (
            "🕒 Напиши новое время:\n"
            "18:30\n\n"
            "Чтобы убрать время — отправь -"
        )

    await callback.message.answer(text)
    await callback.answer()


async def save_edited_task_field(
    state: FSMContext,
    **changes,
):
    data = await state.get_data()

    task_id = data["task_id"]

    task = await get_task_by_id(
        task_id
    )

    if not task:
        return None

    (
        task_id,
        title,
        description,
        task_date,
        task_time,
        category,
        is_done,
        list_id,
        parent_task_id,
    ) = task

    await update_task(
        task_id=task_id,
        title=changes.get(
            "title",
            title,
        ),
        description=changes.get(
            "description",
            description,
        ),
        task_date=changes.get(
            "task_date",
            task_date,
        ),
        task_time=changes.get(
            "task_time",
            task_time,
        ),
        category=category,
        list_id=list_id,
    )

    return (
        task_id,
        list_id,
    )


async def send_edit_success(
    message: Message,
    state: FSMContext,
    result,
):
    if not result:
        await message.answer(
            "❌ Задача не найдена."
        )
        await state.clear()
        return

    task_id, list_id = result

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📌 Открыть задачу",
                    callback_data=(
                        f"opentask:{task_id}:{list_id}"
                    ),
                )
            ]
        ]
    )

    await message.answer(
        "✅ Задача обновлена.",
        reply_markup=keyboard,
    )

    await state.clear()


@dp.message(
    EditTaskForm.entering_title
)
async def edit_task_title_handler(
    message: Message,
    state: FSMContext,
):
    title = message.text.strip()

    if not title:
        await message.answer(
            "Название не может быть пустым."
        )
        return

    result = await save_edited_task_field(
        state,
        title=title,
    )

    await send_edit_success(
        message,
        state,
        result,
    )


@dp.message(
    EditTaskForm.entering_description
)
async def edit_task_description_handler(
    message: Message,
    state: FSMContext,
):
    description = message.text.strip()

    if description == "-":
        description = None

    result = await save_edited_task_field(
        state,
        description=description,
    )

    await send_edit_success(
        message,
        state,
        result,
    )


@dp.message(
    EditTaskForm.entering_date
)
async def edit_task_date_handler(
    message: Message,
    state: FSMContext,
):
    try:
        task_date = datetime.strptime(
            message.text.strip(),
            "%d.%m.%Y",
        ).date()

    except ValueError:
        await message.answer(
            "❌ Неверная дата.\n"
            "Напиши так: 15.09.2026"
        )
        return

    result = await save_edited_task_field(
        state,
        task_date=task_date.isoformat(),
    )

    await send_edit_success(
        message,
        state,
        result,
    )


@dp.message(
    EditTaskForm.entering_time
)
async def edit_task_time_handler(
    message: Message,
    state: FSMContext,
):
    text = message.text.strip()

    if text == "-":
        task_time = None

    else:
        try:
            task_time = datetime.strptime(
                text,
                "%H:%M",
            ).strftime("%H:%M")

        except ValueError:
            await message.answer(
                "❌ Неверное время.\n"
                "Напиши так: 18:30\n\n"
                "Или - чтобы убрать время."
            )
            return

    result = await save_edited_task_field(
        state,
        task_time=task_time,
    )

    await send_edit_success(
        message,
        state,
        result,
    )

# =====================================
# УДАЛЕНИЕ ЗАДАЧИ
# =====================================

@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith("taskdelete:")
)
async def task_delete_callback(
    callback: CallbackQuery,
):
    _, task_id_str, list_id_str = (
        callback.data.split(":")
    )

    task_id = int(task_id_str)
    list_id = int(list_id_str)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data=(
                        f"taskdeleteconfirm:"
                        f"{task_id}:{list_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Отмена",
                    callback_data=(
                        f"opentask:{task_id}:{list_id}"
                    ),
                )
            ],
        ]
    )

    await callback.message.edit_text(
        "🗑 Точно удалить задачу?",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(
    lambda callback:
    callback.data
    and callback.data.startswith(
        "taskdeleteconfirm:"
    )
)
async def task_delete_confirm_callback(
    callback: CallbackQuery,
):
    _, task_id_str, list_id_str = (
        callback.data.split(":")
    )

    task_id = int(task_id_str)
    list_id = int(list_id_str)

    await delete_task(
        task_id
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ К списку",
                    callback_data=(
                        f"openlist:{list_id}"
                    ),
                )
            ]
        ]
    )

    await callback.message.edit_text(
        "✅ Задача удалена.",
        reply_markup=keyboard,
    )

    await callback.answer()

# =====================================
# START BOT
# =====================================

async def main():
    await init_db()
    await ensure_default_task_lists()
    await init_bot_settings()
    await init_sent_notifications()
    await init_omgtu_snapshot()

    setup_scheduler()
    scheduler.start()

    print(
        "Бот запущен.\n"
        "Автоматические уведомления включены.\n"
        "Для остановки нажми Ctrl+C."
    )

    try:
        await dp.start_polling(bot)

    finally:
        scheduler.shutdown(
            wait=False
        )


if __name__ == "__main__":
    asyncio.run(main())