# db/sqlite/schemas.py

# ==================== USERS TABLE ====================

def create_users_table_sql() -> str:
    """Создание таблицы пользователей"""
    return """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER UNIQUE NOT NULL,
        tg_nick TEXT,
        email TEXT,
        google_id TEXT UNIQUE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """


def insert_user_sql() -> str:
    """Добавление нового пользователя"""
    return """
    INSERT INTO users (tg_id, tg_nick, email, google_id)
    VALUES (:tg_id, :tg_nick, :email, :google_id)
    """


def update_user_sql() -> str:
    """Обновление данных пользователя"""
    return """
    UPDATE users 
    SET tg_nick = :tg_nick,
        email = :email,
        google_id = :google_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE tg_id = :tg_id
    """


def select_user_by_tg_id_sql() -> str:
    """Получить пользователя по Telegram ID"""
    return "SELECT * FROM users WHERE tg_id = :tg_id"


def select_user_by_id_sql() -> str:
    """Получить пользователя по ID"""
    return "SELECT * FROM users WHERE id = :id"


def select_user_by_google_id_sql() -> str:
    """Получить пользователя по Google ID"""
    return "SELECT * FROM users WHERE google_id = :google_id"


def select_all_users_sql() -> str:
    """Получить всех пользователей"""
    return "SELECT * FROM users ORDER BY created_at DESC"


def delete_user_sql() -> str:
    """Удалить пользователя по tg_id"""
    return "DELETE FROM users WHERE tg_id = :tg_id"


def user_exists_by_tg_id_sql() -> str:
    """Проверить существование пользователя по tg_id"""
    return "SELECT 1 FROM users WHERE tg_id = :tg_id LIMIT 1"


def user_exists_by_google_id_sql() -> str:
    """Проверить существование пользователя по google_id"""
    return "SELECT 1 FROM users WHERE google_id = :google_id LIMIT 1"


# ==================== TOKENS TABLE ====================

def create_tokens_table_sql() -> str:
    """Создание таблицы токенов"""
    return """
    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        access_token TEXT NOT NULL,
        refresh_token TEXT,
        token_type TEXT DEFAULT 'Bearer',
        expires_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """


def insert_token_sql() -> str:
    """Добавление нового токена"""
    return """
    INSERT INTO tokens (user_id, access_token, refresh_token, token_type, expires_at)
    VALUES (:user_id, :access_token, :refresh_token, :token_type, :expires_at)
    """


def update_token_sql() -> str:
    """Обновление токена"""
    return """
    UPDATE tokens 
    SET access_token = :access_token,
        refresh_token = :refresh_token,
        token_type = :token_type,
        expires_at = :expires_at,
        updated_at = CURRENT_TIMESTAMP
    WHERE user_id = :user_id
    """


def select_token_by_user_id_sql() -> str:
    """Получить токен по user_id"""
    return "SELECT * FROM tokens WHERE user_id = :user_id"


def select_token_by_tg_id_sql() -> str:
    """Получить токен по Telegram ID (через JOIN)"""
    return """
    SELECT t.* 
    FROM tokens t
    INNER JOIN users u ON t.user_id = u.id
    WHERE u.tg_id = :tg_id
    ORDER BY t.created_at DESC
    LIMIT 1
    """


def delete_token_by_user_id_sql() -> str:
    """Удалить токен по user_id"""
    return "DELETE FROM tokens WHERE user_id = :user_id"


def token_exists_sql() -> str:
    """Проверить существование токена"""
    return "SELECT 1 FROM tokens WHERE user_id = :user_id LIMIT 1"


# ==================== HELPER QUERIES ====================

def create_indexes_sql() -> list:
    """Создание индексов для оптимизации"""
    return [
        "CREATE INDEX IF NOT EXISTS idx_users_tg_id ON users(tg_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id)",
        "CREATE INDEX IF NOT EXISTS idx_tokens_user_id ON tokens(user_id)",
    ]


def drop_all_tables_sql() -> list:
    """Удаление всех таблиц"""
    return [
        "DROP TABLE IF EXISTS tokens",
        "DROP TABLE IF EXISTS users"
    ]