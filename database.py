import aiosqlite

DB_PATH = "planner.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # =====================================
        # СПИСКИ ЗАДАЧ
        # =====================================

        await db.execute("""
        CREATE TABLE IF NOT EXISTS task_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            FOREIGN KEY (parent_id)
                REFERENCES task_lists(id)
        )
        """)

        # =====================================
        # ЗАДАЧИ
        # =====================================

        await db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            task_date TEXT NOT NULL,
            task_time TEXT,
            category TEXT DEFAULT 'Личное',
            is_done INTEGER DEFAULT 0,
            list_id INTEGER,
            parent_task_id INTEGER,
            FOREIGN KEY (list_id)
                REFERENCES task_lists(id),
            FOREIGN KEY (parent_task_id)
                REFERENCES tasks(id)
        )
        """)

        # =====================================
        # МИГРАЦИЯ СТАРОЙ БАЗЫ
        # =====================================

        cursor = await db.execute(
            "PRAGMA table_info(tasks)"
        )

        columns = await cursor.fetchall()

        column_names = {
            column[1]
            for column in columns
        }

        if "list_id" not in column_names:
            await db.execute(
                """
                ALTER TABLE tasks
                ADD COLUMN list_id INTEGER
                """
            )

        if "parent_task_id" not in column_names:
            await db.execute(
                """
                ALTER TABLE tasks
                ADD COLUMN parent_task_id INTEGER
                """
            )

        await db.commit()


# =====================================
# ДОБАВИТЬ ЗАДАЧУ
# =====================================

async def add_task(
    title: str,
    task_date: str,
    task_time: str | None = None,
    category: str = "Личное",
    list_id: int | None = None,
    parent_task_id: int | None = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO tasks (
                title,
                task_date,
                task_time,
                category,
                list_id,
                parent_task_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                task_date,
                task_time,
                category,
                list_id,
                parent_task_id,
            ),
        )

        await db.commit()

        return cursor.lastrowid


# =====================================
# ЗАДАЧИ НА ДАТУ
# =====================================

async def get_tasks_for_date(
    task_date: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                title,
                task_time,
                category,
                is_done
            FROM tasks
            WHERE task_date = ?
            ORDER BY
                CASE
                    WHEN task_time IS NULL
                    THEN 1
                    ELSE 0
                END,
                task_time,
                id
            """,
            (task_date,),
        )

        return await cursor.fetchall()


# =====================================
# ВЫПОЛНЕНО
# =====================================

async def mark_task_done(
    task_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE tasks
            SET is_done = 1
            WHERE id = ?
            """,
            (task_id,),
        )

        await db.commit()


# =====================================
# СПИСКИ
# =====================================

async def create_task_list(
    name: str,
    parent_id: int | None = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO task_lists (
                name,
                parent_id
            )
            VALUES (?, ?)
            """,
            (
                name,
                parent_id,
            ),
        )

        await db.commit()

        return cursor.lastrowid


async def get_task_lists():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                name,
                parent_id
            FROM task_lists
            ORDER BY id
            """
        )

        return await cursor.fetchall()


# =====================================
# ВСЕ ЗАДАЧИ СПИСКА
# =====================================

async def get_tasks_for_list(
    list_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                title,
                task_date,
                task_time,
                is_done,
                parent_task_id
            FROM tasks
            WHERE list_id = ?
            ORDER BY
                parent_task_id,
                id
            """,
            (list_id,),
        )

        return await cursor.fetchall()

async def get_task_by_id(
    task_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                title,
                task_date,
                task_time,
                category,
                is_done,
                list_id,
                parent_task_id
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )

        return await cursor.fetchone()

# =====================================
# НАСТРОЙКИ БОТА
# =====================================

async def init_bot_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            chat_id INTEGER
        )
        """)

        await db.execute("""
        INSERT OR IGNORE INTO bot_settings (
            id,
            chat_id
        )
        VALUES (1, NULL)
        """)

        await db.commit()


async def save_chat_id(
    chat_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE bot_settings
            SET chat_id = ?
            WHERE id = 1
            """,
            (chat_id,),
        )

        await db.commit()


async def get_chat_id():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT chat_id
            FROM bot_settings
            WHERE id = 1
            """
        )

        row = await cursor.fetchone()

        if not row:
            return None

        return row[0]


# =====================================
# ОТПРАВЛЕННЫЕ НАПОМИНАНИЯ
# =====================================

async def init_sent_notifications():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS sent_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_key TEXT UNIQUE NOT NULL,
            sent_at TEXT NOT NULL
        )
        """)

        await db.commit()


async def was_notification_sent(
    notification_key: str,
) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id
            FROM sent_notifications
            WHERE notification_key = ?
            """,
            (notification_key,),
        )

        row = await cursor.fetchone()

        return row is not None


async def mark_notification_sent(
    notification_key: str,
    sent_at: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO sent_notifications (
                notification_key,
                sent_at
            )
            VALUES (?, ?)
            """,
            (
                notification_key,
                sent_at,
            ),
        )

        await db.commit()


# =====================================
# SNAPSHOT ОМГТУ
# =====================================

async def init_omgtu_snapshot():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS omgtu_snapshot (
            snapshot_key TEXT PRIMARY KEY,
            snapshot_json TEXT NOT NULL
        )
        """)

        await db.commit()


async def get_omgtu_snapshot(
    snapshot_key: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT snapshot_json
            FROM omgtu_snapshot
            WHERE snapshot_key = ?
            """,
            (snapshot_key,),
        )

        row = await cursor.fetchone()

        if not row:
            return None

        return row[0]


async def save_omgtu_snapshot(
    snapshot_key: str,
    snapshot_json: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO omgtu_snapshot (
                snapshot_key,
                snapshot_json
            )
            VALUES (?, ?)
            ON CONFLICT(snapshot_key)
            DO UPDATE SET
                snapshot_json = excluded.snapshot_json
            """,
            (
                snapshot_key,
                snapshot_json,
            ),
        )

        await db.commit()

async def get_task_list_by_id(
    list_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, name, parent_id
            FROM task_lists
            WHERE id = ?
            """,
            (list_id,),
        )

        return await cursor.fetchone()


async def get_child_lists(
    parent_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, name, parent_id
            FROM task_lists
            WHERE parent_id = ?
            ORDER BY id
            """,
            (parent_id,),
        )

        return await cursor.fetchall()


async def delete_task(
    task_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        # Сначала удаляем прямые подзадачи.
        await db.execute(
            """
            DELETE FROM tasks
            WHERE parent_task_id = ?
            """,
            (task_id,),
        )

        await db.execute(
            """
            DELETE FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )

        await db.commit()