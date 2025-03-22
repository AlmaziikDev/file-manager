import os
import logging
import json
import zipfile
import fnmatch
import re
from datetime import datetime, timedelta
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    MessageHandler,
    filters,
)
import shutil
import asyncio
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Токен вашего бота
TOKEN = os.getenv("TOKEN")

# Ваш айди в телеграме
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))

# Настройка логирования
logging.getLogger("httpx").setLevel(logging.WARNING)

# Основная настройка логирования для бота
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Файл для логирования действий
LOG_FILE = os.getenv("LOG_FILE")

# Файл для базы настроек
SETTINGS_DB_FILE = os.getenv("SETTINGS_DB_FILE")

# Локальная база настроек
user_settings = {}

# Словарь эмодзи для расширений
EMOJI_MAP = {
    ".appinstaller": "📥",
    ".torrent": "📥",
    ".sql": "🗄️",
    ".txt": "📄",
    ".jpg": "🖼️",
    ".png": "🖼️",
    ".mp3": "🎵",
    ".mp4": "🎥",
    ".pdf": "📖",
    ".zip": "📦",
    ".rar": "📦",
    ".gz": "📦",
    ".exe": "⚙️",
    ".msi": "🖥️",
    ".py": "🐍",
    ".luac": "🌙",
    ".lua": "🌙",
    ".jar": "☕",
    ".json": "🔧",
    ".md": "📝",
    ".docx": "📋",
    ".doc": "📋",
    ".xlsx": "📊",
    ".pptx": "📊",
    ".csv": "📊",
}

# Хранение текущей директории для каждого пользователя
current_dirs = {}

# Загрузка настроек из файла
def load_settings_db():
    global user_settings
    if os.path.exists(SETTINGS_DB_FILE):
        try:
            with open(SETTINGS_DB_FILE, "r", encoding="utf-8") as f:
                user_settings = json.load(f)
        except Exception as e:
            logger.error("Ошибка загрузки настроек: %s", e)
            user_settings = {}
    else:
        user_settings = {}

# Сохранение настроек в файл
def save_settings_db():
    with open(SETTINGS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(user_settings, f, ensure_ascii=False, indent=2)

# Получение текущей директории пользователя
def get_current_dir(user_id):
    return current_dirs.get(str(user_id), os.getcwd())

# Получение настроек пользователя
def get_user_settings(user_id):
    uid = str(user_id)
    if uid not in user_settings:
        user_settings[uid] = {
            "default_path": None,
            "filtering": "off",  # режимы: "off", "name", "date"
            "grouping": "off",  # режимы: "off", "date"
        }
        save_settings_db()
    return user_settings[uid]

# Логирование действий
def log_action(user_id, command, details):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "command": command,
        "details": details,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [User ID: {user_id}] - {command} {details}")
    except Exception as e:
        logger.error("Ошибка логирования: %s", e)

# Вспомогательная функция для отправки сообщений и логирования
async def send_message_and_log(update: Update, text: str, command: str, details: dict):
    await update.message.reply_text(text)
    log_action(update.effective_user.id, command, details)

# Функция для определения группы по дате изменения
def get_date_group(mod_time: float) -> str:
    dt = datetime.fromtimestamp(mod_time)
    today = datetime.today()
    if dt.date() == today.date():
        return "Сегодня"
    # Если в той же неделе (но не сегодня)
    if dt.isocalendar()[1] == today.isocalendar()[1] and dt.date() < today.date():
        return "Ранее на этой неделе"
    # Если в предыдущей неделе
    if dt.isocalendar()[1] == (today.isocalendar()[1] - 1):
        return "На прошлой неделе"
    # Если в этом месяце
    if dt.year == today.year and dt.month == today.month:
        return "Ранее в этом месяце"
    # Если в прошлом месяце
    last_month = today.month - 1 if today.month > 1 else 12
    last_month_year = today.year if today.month > 1 else today.year - 1
    if dt.year == last_month_year and dt.month == last_month:
        return "В прошлом месяце"
    return "Давно"

# Декоратор для проверки прав доступа
def authorized_only(func):
    async def wrapper(update: Update, context: CallbackContext):
        if update.effective_user.id != AUTHORIZED_USER_ID:
            await update.message.reply_text("Нет доступа.")
            return
        return await func(update, context)

    return wrapper

# Команда /create
@authorized_only
async def create_file(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /create <имя_файла> \"текст\" (переносы строк поддерживаются)")
        return
    file_name = context.args[0]
    content = "\n".join(context.args[1:])
    current_dir = get_current_dir(user_id)
    full_path = os.path.join(current_dir, file_name)
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        await send_message_and_log(update, f"Файл создан: {file_name}", "create", {"file": full_path, "content": content})
    except Exception as e:
        await send_message_and_log(update, f"Ошибка создания файла: {e}", "create", {"error": str(e), "file": full_path})

# Команда /edit
@authorized_only
async def edit_file(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /edit <имя_файла> \"текст\" (переносы строк поддерживаются)")
        return
    file_name = context.args[0]
    content = "\n".join(context.args[1:])  # Сохраняем переносы строк
    current_dir = get_current_dir(user_id)
    full_path = os.path.join(current_dir, file_name)
    if not os.path.isfile(full_path):
        await update.message.reply_text("Файл не найден.")
        return
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        await update.message.reply_text(f"Файл отредактирован: {file_name}")
        log_action(user_id, "edit", {"file": full_path, "content": content})
    except Exception as e:
        await update.message.reply_text(f"Ошибка редактирования файла: {e}")
        log_action(user_id, "edit", {"error": str(e), "file": full_path})

# Команда /view
@authorized_only
async def view_file(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Использование: /view <имя_файла>")
        return
    file_name = ' '.join(context.args)
    current_dir = get_current_dir(user_id)
    full_path = os.path.join(current_dir, file_name)
    if not os.path.isfile(full_path):
        await update.message.reply_text("Файл не найден.")
        return
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Разбиение текста на части
        MAX_MESSAGE_LENGTH = 4096
        messages = []
        buffer = ""
        lines = content.split("\n")
        for line in lines:
            escaped_line = escape_markdown_v2(line)  # Экранируем строку
            if len(buffer) + len(escaped_line) + 1 > MAX_MESSAGE_LENGTH:
                if buffer.startswith("```") and not buffer.endswith("```"):
                    buffer += "\n```"  # Закрываем блок, если он открыт
                messages.append(buffer)
                buffer = ""
            buffer += escaped_line + "\n"
        if buffer:
            if buffer.startswith("```") and not buffer.endswith("```"):
                buffer += "\n```"  # Закрываем блок, если он открыт
            messages.append(buffer)
        # Отправка всех частей
        for i, message in enumerate(messages):
            if i == 0:
                text = f"{file_name}\n```\n{message}\n```"
            else:
                text = f"```\n{message}\n```"
            await update.message.reply_text(text, parse_mode="Markdown")
        log_action(user_id, "view", {"file": full_path})
    except Exception as e:
        await update.message.reply_text(f"Ошибка просмотра файла: {e}")
        log_action(user_id, "view", {"error": str(e), "file": full_path})

def escape_markdown_v2(text):
    """
    Экранирует все зарезервированные символы для MarkdownV2.
    """
    reserved_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(reserved_chars)}])", r"\\\1", text)

@authorized_only
async def search(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Использование: /search <текст или маска>")
        return
    current_dir = get_current_dir(user_id)
    results = {}
    try:
        # Разбор параметров запроса
        depth = 1000  # По умолчанию без ограничений
        file_type = None
        regex_mode = False
        content_search = False
        sort_by = "name"  # По умолчанию сортировка по имени
        if "--depth=" in query:
            depth_str = query.split("--depth=")[1].split()[0]
            depth = int(depth_str)
            query = query.replace(f"--depth={depth_str}", "").strip()
        if "--type=" in query:
            file_type = query.split("--type=")[1].split()[0]
            query = query.replace(f"--type={file_type}", "").strip()
        if "--sort=" in query:
            sort_by = query.split("--sort=")[1].split()[0]
            query = query.replace(f"--sort={sort_by}", "").strip()
        if query.startswith("regex:"):
            regex_mode = True
            query = query[6:]  # Убираем префикс "regex:"
        if query.startswith("content:"):
            content_search = True
            query = query[8:]  # Убираем префикс "content:"
        # Рекурсивный обход всех файлов и папок
        current_depth = 0
        for root, dirs, files in os.walk(current_dir):
            if current_depth > depth:
                break
            for file in files:
                full_path = os.path.join(root, file)
                # Пропускаем файлы, не соответствующие типу
                if file_type and not file.endswith(f".{file_type}"):
                    continue
                # Проверка на соответствие маске
                if not regex_mode and fnmatch.fnmatch(file.lower(), query.lower()):
                    results.setdefault(root, []).append(file)
                    continue
                # Проверка на вхождение текста в имя файла
                if not regex_mode and query.lower() in file.lower():
                    results.setdefault(root, []).append(file)
                    continue
                # Проверка на соответствие регулярному выражению
                if regex_mode:
                    pattern = re.compile(query, re.IGNORECASE)
                    if pattern.match(file):
                        results.setdefault(root, []).append(file)
                        continue
                # Поиск по содержимому файла
                if content_search:
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            if query in f.read():
                                results.setdefault(root, []).append(file)
                    except Exception:
                        continue  # Пропускаем файлы, которые невозможно прочитать
            current_depth += 1
        # Если результаты найдены
        if results:
            # Сортировка результатов
            sorted_results = {}
            for directory, files in results.items():
                if sort_by == "date":
                    sorted_files = sorted(
                        files,
                        key=lambda x: os.path.getmtime(os.path.join(directory, x)),
                        reverse=True
                    )
                else:
                    sorted_files = sorted(files, key=lambda x: x.lower())
                sorted_results[directory] = sorted_files
        # Формирование вывода
        output_blocks = []
        for directory, files in sorted_results.items():
            # Здесь можно экранировать только имя директории, если это необходимо
            block = f"```\nДиректория: {directory}\n"
            block += "\n".join([
                f"{EMOJI_MAP.get(os.path.splitext(f)[1].lower(), '📄')} {escape_markdown_v2(f)}"
                for f in files
            ])
            block += "\n```"
            output_blocks.append(block)
        final_text = "\n".join(output_blocks)

        # Разбиение текста на части (без повторного экранирования)
        MAX_MESSAGE_LENGTH = 4096
        messages = []
        buffer = ""
        for line in final_text.split("\n"):
            # Не применяем escape_markdown_v2 к строке, чтобы сохранить маркдаун-разметку
            if len(buffer) + len(line) + 1 > MAX_MESSAGE_LENGTH:
                # Если блок открыт, закрываем его
                if buffer.startswith("```") and not buffer.endswith("```"):
                    buffer += "\n```"
                messages.append(buffer)
                buffer = ""
            buffer += line + "\n"
        if buffer:
            if buffer.startswith("```") and not buffer.endswith("```"):
                buffer += "\n```"
            messages.append(buffer)

        # Отправка всех частей
        for message in messages:
            await update.message.reply_text(message, parse_mode="Markdown")
        else:
            await update.message.reply_text("Файлы не найдены.")
        log_action(user_id, "search", {"query": query, "results": results})
    except Exception as e:
        await update.message.reply_text(f"Ошибка поиска: {e}")
        log_action(user_id, "search", {"error": str(e), "query": query})

# Вспомогательная функция для смены директории
async def change_directory(update: Update, context: CallbackContext, path: str) -> None:
    user_id = update.effective_user.id
    current_dir = get_current_dir(user_id)
    if not path:
        await update.message.reply_text('Укажите путь после команды cd или установите дефолтный путь через /settings')
        return
    new_path = os.path.normpath(os.path.join(current_dir, path))
    if os.path.isdir(new_path):
        current_dirs[str(user_id)] = new_path
        await update.message.reply_text(f'Текущая директория изменена на: {new_path}')
        log_action(user_id, "cd", {"from": current_dir, "to": new_path})
        return
    # Если путь не содержит разделителей, пробуем найти папку по имени (без учёта регистра)
    if ('/' not in path) and ('\\' not in path):
        for folder in os.listdir(current_dir):
            full_folder_path = os.path.join(current_dir, folder)
            if os.path.isdir(full_folder_path) and folder.lower() == path.lower():
                current_dirs[str(user_id)] = full_folder_path
                await update.message.reply_text(f'Текущая директория изменена на: {full_folder_path}')
                log_action(user_id, "cd", {"from": current_dir, "to": full_folder_path})
                return
    await update.message.reply_text('Указанная директория не существует.')

# Команды управления файлами

# Команда /mv
@authorized_only
async def mv(update: Update, context: CallbackContext) -> None:
    """Перемещает (переименовывает) файл или папку. Использование: /mv <источник> <назначение>"""
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /mv <источник> <назначение>")
        return
    src = context.args[0]
    dst = context.args[1]
    current_dir = get_current_dir(user_id)
    src_path = os.path.normpath(os.path.join(current_dir, src))
    dst_path = os.path.normpath(os.path.join(current_dir, dst))
    try:
        shutil.move(src_path, dst_path)  # Использование shutil.move
        await update.message.reply_text(f"Перемещено: {src} -> {dst}")
        log_action(user_id, "mv", {"src": src_path, "dst": dst_path})
    except Exception as e:
        await update.message.reply_text(f"Ошибка перемещения: {e}")

@authorized_only
async def cp(update: Update, context: CallbackContext) -> None:
    """Копирует файл или папку. Использование: /cp <источник> <назначение>"""
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /cp <источник> <назначение>")
        return
    src = context.args[0]
    dst = context.args[1]
    current_dir = get_current_dir(user_id)
    src_path = os.path.normpath(os.path.join(current_dir, src))
    dst_path = os.path.normpath(os.path.join(current_dir, dst))
    try:
        if os.path.isfile(src_path):
            shutil.copy2(src_path, dst_path)
        elif os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path)
        else:
            await update.message.reply_text("Источник не найден")
            return
        await update.message.reply_text(f"Скопировано: {src} -> {dst}")
        log_action(user_id, "cp", {"src": src_path, "dst": dst_path})
    except Exception as e:
        await update.message.reply_text(f"Ошибка копирования: {e}")

@authorized_only
async def rm(update: Update, context: CallbackContext) -> None:
    """Удаляет файл или папку. Использование: /rm <путь>"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Использование: /rm <путь>")
        return
    target = ' '.join(context.args)
    current_dir = get_current_dir(user_id)
    target_path = os.path.normpath(os.path.join(current_dir, target))
    try:
        if os.path.isfile(target_path):
            os.remove(target_path)
        elif os.path.isdir(target_path):
            shutil.rmtree(target_path)
        else:
            await update.message.reply_text("Файл или папка не найдены")
            return
        await update.message.reply_text(f"Удалено: {target}")
        log_action(user_id, "rm", {"target": target_path})
    except Exception as e:
        await update.message.reply_text(f"Ошибка удаления: {e}")

@authorized_only
async def mkdir(update: Update, context: CallbackContext) -> None:
    """Создаёт новую папку. Использование: /mkdir <имя_папки>"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Использование: /mkdir <имя_папки>")
        return
    folder_name = ' '.join(context.args)
    current_dir = get_current_dir(user_id)
    folder_path = os.path.normpath(os.path.join(current_dir, folder_name))
    try:
        os.makedirs(folder_path, exist_ok=False)
        await update.message.reply_text(f"Папка создана: {folder_name}")
        log_action(user_id, "mkdir", {"folder": folder_path})
    except Exception as e:
        await update.message.reply_text(f"Ошибка создания папки: {e}")

@authorized_only
async def rmdir(update: Update, context: CallbackContext) -> None:
    """Удаляет пустую папку. Использование: /rmdir <имя_папки>"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Использование: /rmdir <имя_папки>")
        return
    folder_name = ' '.join(context.args)
    current_dir = get_current_dir(user_id)
    folder_path = os.path.normpath(os.path.join(current_dir, folder_name))
    try:
        os.rmdir(folder_path)
        await update.message.reply_text(f"Папка удалена: {folder_name}")
        log_action(user_id, "rmdir", {"folder": folder_path})
    except Exception as e:
        await update.message.reply_text(f"Ошибка удаления папки: {e}")

# Прочие команды

@authorized_only
async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    current_dirs[str(user_id)] = os.getcwd()  # Начинаем с текущей директории сервера
    await update.message.reply_text('Привет! Используй /help чтобы увидеть доступные команды.')
    log_action(user_id, "start", {"cwd": os.getcwd()})

@authorized_only
async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "Доступные команды:\n"
        "/start - Начать\n"
        "/help - Помощь\n"
        "/pwd - Показать текущую директорию\n"
        "/ls - Показать содержимое директории\n"
        "/cd <путь> - Сменить директорию (без аргументов – дефолтный путь из настроек)\n"
        "/back - Вернуться на уровень выше\n"
        "/download <имя_файла> - Скачать файл\n"
        "/search --depth=(глубина поиска) --type=(расширение файла) --sort=(date) regex: (регулярные выражения) content: (поиск по содержимому) <текст или маска>\n\n"
        "/view <имя файла> - Посмотреть содержимое файла\n"
        "/create <имя_файла> \"текст\"\n"
        "/edit <имя_файла> \"новый_текст\"\n"
        "/settings - Настройки (дефолтный путь, фильтрация, группировка)\n"
        "/mv <src> <dst> - Переместить/переименовать\n"
        "/cp <src> <dst> - Скопировать\n"
        "/rm <путь> - Удалить файл/папку\n"
        "/mkdir <имя> - Создать папку\n"
        "/rmdir <имя> - Удалить пустую папку\n"
        "\nТакже можно вводить команды без слеша, например: cd SomeGame"
    )
    await update.message.reply_text(help_text)
    log_action(update.effective_user.id, "help", {})

@authorized_only
async def pwd(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    current_dir = get_current_dir(user_id)
    await update.message.reply_text(f'Текущая директория: {current_dir}')
    log_action(user_id, "pwd", {"cwd": current_dir})

# Команда /download (с поддержкой ZIP)
@authorized_only
async def download_file(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    files = context.args
    if not files:
        await update.message.reply_text("Укажите имя(я) файла(ов) после команды /download")
        return

    current_dir = get_current_dir(user_id)
    zip_path = os.path.join(current_dir, f"user_{user_id}_files.zip")

    # Создаем ZIP-архив
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for file_name in files:
            full_path = os.path.join(current_dir, file_name)
            if os.path.isfile(full_path):
                zipf.write(full_path, arcname=file_name)
            else:
                await update.message.reply_text(f"Файл не найден: {file_name}")

    # Отправляем ZIP-архив
    if os.path.getsize(zip_path) > 0:
        with open(zip_path, "rb") as zf:
            await update.message.reply_document(document=zf, filename="files.zip")
        log_action(user_id, "download", {"files": files})
    else:
        await update.message.reply_text("Нет файлов для скачивания.")

    # Удаляем временный ZIP-файл
    os.remove(zip_path)

# Команда /ls
@authorized_only
async def ls(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    current_dir = get_current_dir(user_id)
    try:
        items = os.listdir(current_dir)
        item_list = []
        for item in items:
            full_path = os.path.join(current_dir, item)
            is_dir = os.path.isdir(full_path)
            mtime = os.path.getmtime(full_path)
            ext = os.path.splitext(item)[1].lower()
            emoji = EMOJI_MAP.get(ext, "📄") if not is_dir else "📂"
            item_list.append({"name": item, "is_dir": is_dir, "mtime": mtime, "emoji": emoji})
        settings = get_user_settings(user_id)
        filtering = settings.get("filtering", "off")
        grouping = settings.get("grouping", "off")
        if filtering == "name":
            item_list.sort(key=lambda x: x["name"].lower())
        elif filtering == "date":
            item_list.sort(key=lambda x: x["mtime"], reverse=True)
        else:
            item_list.sort(key=lambda x: x["name"].lower())
        if grouping == "date":
            groups = {}
            now = datetime.now()
            date_ranges = {
                "Сегодня": now.date(),
                "Ранее на этой неделе": now.date() - timedelta(days=now.weekday()),
                "На прошлой неделе": now.date() - timedelta(days=now.weekday() + 7),
                "Ранее в этом месяце": now.replace(day=1).date(),
                "В прошлом месяце": (now.replace(day=1) - timedelta(days=1)).replace(day=1).date(),
                "Давно": datetime.min.date(),
            }
            for item in item_list:
                item_date = datetime.fromtimestamp(item["mtime"]).date()
                for label, start_date in date_ranges.items():
                    if item_date >= start_date:
                        groups.setdefault(label, []).append(item)
                        break
            output_blocks = []
            for label in date_ranges.keys():
                if label in groups:
                    block = f"```\n{label}:\n"
                    block += "\n".join([f"  {item['emoji']} {item['name']}" for item in groups[label]])
                    block += "\n```"
                    output_blocks.append(block)
            final_text = "\n".join(output_blocks)
        else:
            folders = [f"{item['emoji']} {item['name']}" for item in item_list if item["is_dir"]]
            files = [f"{item['emoji']} {item['name']}" for item in item_list if not item["is_dir"]]
            block1 = "```\nFolders:\n" + "\n".join(folders) + "\n```" if folders else ""
            block2 = "```\nFiles:\n" + "\n".join(files) + "\n```" if files else ""
            final_text = "\n".join(filter(None, [block1, block2]))
        await update.message.reply_text(final_text, parse_mode="Markdown")
        log_action(user_id, "ls", {"cwd": current_dir, "items": items})
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
        log_action(user_id, "ls", {"error": str(e)})

@authorized_only
async def cd(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not context.args:
        settings = get_user_settings(user_id)
        default_path = settings.get("default_path")
        if default_path:
            await change_directory(update, context, default_path)
        else:
            await update.message.reply_text("Укажите путь после команды cd или установите дефолтный путь через /settings")
        return
    path = ' '.join(context.args)
    await change_directory(update, context, path)

@authorized_only
async def back(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    current_dir = get_current_dir(user_id)
    parent_dir = os.path.dirname(current_dir)
    if parent_dir and parent_dir != current_dir:
        current_dirs[str(user_id)] = parent_dir
        await update.message.reply_text(f'Теперь вы в: {parent_dir}')
        log_action(user_id, "back", {"from": current_dir, "to": parent_dir})
    else:
        await update.message.reply_text('Вы уже в корневой директории.')

@authorized_only
async def settings_command(update: Update, context: CallbackContext) -> None:
    """
    /settings без аргументов – вывод настроек.
    Подкоманды:
      • default_path <путь> – установить дефолтный путь для cd (без аргументов).
      • filtering <name/date/off> – установить режим фильтрации.
      • grouping <date/off> – установить режим группировки.
    """
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    args = context.args
    if not args:
        text = "Текущие настройки:\n"
        text += f"Дефолтный путь: {settings.get('default_path')}\n"
        text += f"Фильтрация: {settings.get('filtering')}\n"
        text += f"Группировка: {settings.get('grouping')}\n"
        text += "\nИспользуйте:\n"
        text += "/settings default_path <путь>\n"
        text += "/settings filtering <name/date/off>\n"
        text += "/settings grouping <date/off>\n"
        await update.message.reply_text(text)
        log_action(user_id, "settings", {"action": "show", "settings": settings})
        return
    subcommand = args[0].lower()
    if subcommand == "default_path":
        if len(args) < 2:
            await update.message.reply_text("Укажите путь, например: /settings default_path D:\\Games")
        else:
            new_default = " ".join(args[1:])
            settings["default_path"] = new_default
            await update.message.reply_text(f"Дефолтный путь установлен: {new_default}")
            log_action(user_id, "settings", {"default_path": new_default})
            save_settings_db()
    elif subcommand == "filtering":
        if len(args) < 2:
            await update.message.reply_text("Укажите режим фильтрации: name, date или off, например: /settings filtering name")
            return
        mode = args[1].lower()
        if mode not in ("name", "date", "off"):
            await update.message.reply_text("Режим фильтрации должен быть: name, date или off")
            return
        settings["filtering"] = mode
        await update.message.reply_text(f"Режим фильтрации установлен: {mode}")
        log_action(user_id, "settings", {"filtering": mode})
        save_settings_db()
    elif subcommand == "grouping":
        if len(args) < 2:
            await update.message.reply_text("Укажите режим группировки: date или off, например: /settings grouping date")
            return
        mode = args[1].lower()
        if mode not in ("date", "off"):
            await update.message.reply_text("Режим группировки должен быть: date или off")
            return
        settings["grouping"] = mode
        await update.message.reply_text(f"Режим группировки установлен: {mode}")
        log_action(user_id, "settings", {"grouping": mode})
        save_settings_db()
    else:
        await update.message.reply_text("Неизвестная настройка. Используйте default_path, filtering или grouping.")
        log_action(user_id, "settings", {"error": "Неизвестная настройка", "args": args})

# Обработчик текстовых сообщений (без слеша)
@authorized_only
async def text_handler(update: Update, context: CallbackContext) -> None:
    text = update.message.text.strip()
    if not text:
        return
    parts = text.split()
    command = parts[0].lower()
    args = parts[1:]
    context.args = args  # для совместимости с командами
    if command == 'cd':
        await cd(update, context)
    elif command == 'ls':
        await ls(update, context)
    elif command == 'pwd':
        await pwd(update, context)
    elif command == 'help':
        await help_command(update, context)
    elif command == 'back':
        await back(update, context)
    elif command == 'download':
        await download_file(update, context)
    elif command == 'search':
        await search(update, context)
    elif command == 'view':
        await view_file(update, context)
    elif command == 'create':
        await create_file(update, context)
    elif command == 'edit':
        await edit_file(update, context)
    elif command == 'settings':
        await settings_command(update, context)
    elif command == 'mv':
        await mv(update, context)
    elif command == 'cp':
        await cp(update, context)
    elif command == 'rm':
        await rm(update, context)
    elif command == 'mkdir':
        await mkdir(update, context)
    elif command == 'rmdir':
        await rmdir(update, context)
    else:
        await update.message.reply_text('Неизвестная команда.')
        log_action(update.effective_user.id, "unknown", {"text": text})

def main() -> None:
    load_settings_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("pwd", pwd))
    app.add_handler(CommandHandler("ls", ls))
    app.add_handler(CommandHandler("cd", cd))
    app.add_handler(CommandHandler("back", back))
    app.add_handler(CommandHandler("download", download_file))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("view", view_file))
    app.add_handler(CommandHandler("create", create_file))
    app.add_handler(CommandHandler("edit", edit_file))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("mv", mv))
    app.add_handler(CommandHandler("cp", cp))
    app.add_handler(CommandHandler("rm", rm))
    app.add_handler(CommandHandler("mkdir", mkdir))
    app.add_handler(CommandHandler("rmdir", rmdir))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))

    commands = [
        BotCommand("start", "Начать"),
        BotCommand("help", "Помощь"),
        BotCommand("pwd", "Показать текущую директорию"),
        BotCommand("ls", "Показать содержимое директории"),
        BotCommand("cd", "Сменить директорию"),
        BotCommand("back", "Вернуться на уровень выше"),
        BotCommand("download", "Скачать файл"),
        BotCommand("search", "Поиск файлов"),
        BotCommand("create", "Создать файл"),
        BotCommand("edit", "Редактировать файл"),
        BotCommand("settings", "Настройки"),
        BotCommand("mv", "Переместить/переименовать"),
        BotCommand("cp", "Скопировать"),
        BotCommand("rm", "Удалить файл/папку"),
        BotCommand("mkdir", "Создать папку"),
        BotCommand("rmdir", "Удалить папку")
    ]
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.set_my_commands(commands))

    print("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()