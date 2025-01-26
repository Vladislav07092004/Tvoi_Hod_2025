import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import Message
from aiogram.filters import StateFilter
import random
import string
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Bot token
BOT_TOKEN = "7235928823:AAHS3cfYTA3S9IlpdGub8284WPdg5shbTzE"
PREDEFINED_ADMIN_IDS = [1760175851]


bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        role TEXT,
        last_name TEXT,
        first_name TEXT,
        middle_name TEXT,
        organization TEXT
    )''')
    
    # Таблица учебных групп
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        teacher_id INTEGER,
        max_members INTEGER DEFAULT 30, -- По умолчанию 30
        auth_method TEXT DEFAULT "Без пароля", -- По умолчанию "Без пароля"
        FOREIGN KEY (teacher_id) REFERENCES users (telegram_id)
    )''')
    
    conn.commit()
    conn.close()

init_db()

def add_max_members_column():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Проверяем существование колонки
    cursor.execute("PRAGMA table_info(groups);")
    columns = [col[1] for col in cursor.fetchall()]

    if "max_members" not in columns:
        cursor.execute("ALTER TABLE groups ADD COLUMN max_members INTEGER DEFAULT 30;")
        conn.commit()
        print("Колонка max_members успешно добавлена.")
    else:
        # Оставляем этот вывод только для отладки
        print("[DEBUG] Колонка max_members уже существует.")

    conn.close()

# Вызов функции
add_max_members_column()



# Keyboards
role_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Преподаватель")],
        [KeyboardButton(text="Ученик")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

organization_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Школа")],
        [KeyboardButton(text="Университет")],
        [KeyboardButton(text="Учебный центр")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Просмотреть пользователей")],
        [KeyboardButton(text="Назначить роль")]
    ],
    resize_keyboard=True
)

start_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Начать")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

teacher_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Создать учебную группу")],
        [KeyboardButton(text="Мои учебные группы")],
        [KeyboardButton(text="Удалить учебную группу")],
        [KeyboardButton(text="Настройки группы")]
    ],
    resize_keyboard=True
)


settings_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Изменить максимальное количество участников")],
        [KeyboardButton(text="Изменить способ аутентификации")],
        [KeyboardButton(text="Назад")]
    ],
    resize_keyboard=True
)

auth_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Пароль")],
        [KeyboardButton(text="Без пароля")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


class Registration(StatesGroup):
    confirm_role = State()  # Состояние для выбора роли
    last_name = State()     # Состояние для ввода фамилии
    first_name = State()    # Состояние для ввода имени
    middle_name = State()   # Состояние для ввода отчества
    city = State()          # Состояние для ввода города
    organization = State()  # Состояние для ввода организации


class CreateGroup(StatesGroup):
    name = State()
    description = State()
    auth_method = State()  # Новый шаг для способа аутентификации


class DeleteGroup(StatesGroup):
    name = State()

class GroupSettings(StatesGroup):
    select_group = State()
    select_action = State()  # Состояние для выбора действия
    update_max_members = State()
    update_auth_method = State()


@dp.message(Command("start"))
async def start_command(message: types.Message):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Проверяем, зарегистрирован ли пользователь
    cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (message.from_user.id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        role = user[0]
        if role == "Преподаватель":
            await message.reply(
                "Добро пожаловать, Преподаватель! Выберите действие из меню ниже:",
                reply_markup=teacher_kb
            )
        elif role == "Ученик":
            await message.reply(
                "Добро пожаловать, Ученик! Вы можете использовать бота для просмотра своих групп."
            )
        else:
            await message.reply("Добро пожаловать! Ваша роль не определена.")
    else:
        await message.answer(
            "Добро пожаловать! Вы ещё не зарегистрированы. Выберите вашу роль:",
            reply_markup=role_kb
        )




@dp.message(lambda message: message.text == "Начать")
async def start_registration(message: types.Message, state: FSMContext):
    # Проверяем, находится ли пользователь в состоянии start_registration
    current_state = await state.get_state()
    print(f"[DEBUG] Текущее состояние: {current_state}")
    if current_state == "start_registration":
        await message.answer("Введите вашу фамилию:")
        await state.set_state(Registration.last_name)
    else:
        await message.answer("Что-то пошло не так. Попробуйте снова.")


@dp.message(Registration.last_name)
async def process_last_name(message: types.Message, state: FSMContext):
    last_name = message.text.strip()
    await state.update_data(last_name=last_name)

    await message.answer("Введите ваше имя:")
    await state.set_state(Registration.first_name)  # Переходим к вводу имени
    print(f"[DEBUG] Фамилия сохранена: {last_name}. Ожидание ввода имени.")  # Отладка

@dp.message(Registration.first_name)
async def process_first_name(message: types.Message, state: FSMContext):
    first_name = message.text.strip()
    await state.update_data(first_name=first_name)

    await message.answer("Введите ваше отчество:")
    await state.set_state(Registration.middle_name)  # Переходим к вводу отчества
    print(f"[DEBUG] Имя сохранено: {first_name}. Ожидание ввода отчества.")  # Отладка

@dp.message(Registration.middle_name)
async def process_middle_name(message: types.Message, state: FSMContext):
    middle_name = message.text.strip()
    await state.update_data(middle_name=middle_name)

    await message.answer("Введите ваш город:")
    await state.set_state(Registration.city)  # Переходим к вводу города
    print(f"[DEBUG] Отчество сохранено: {middle_name}. Ожидание ввода города.")  # Отладка


@dp.message(Registration.city)
async def process_city(message: types.Message, state: FSMContext):
    city = message.text.strip()
    await state.update_data(city=city)

    await message.answer("Введите название вашей образовательной организации:")
    await state.set_state(Registration.organization)  # Переходим к вводу организации
    print(f"[DEBUG] Город сохранён: {city}. Ожидание ввода организации.")  # Отладка

@dp.message(Registration.organization)
async def process_organization(message: types.Message, state: FSMContext):
    organization = message.text.strip()
    await state.update_data(organization=organization)

    # Получаем все данные пользователя из FSM
    user_data = await state.get_data()

    # Сохраняем данные в базу данных
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (telegram_id, username, role, last_name, first_name, middle_name, organization) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                message.from_user.id,
                message.from_user.username or "Нет имени пользователя",
                user_data.get("role"),
                user_data.get("last_name"),
                user_data.get("first_name"),
                user_data.get("middle_name"),
                f"{user_data.get('city')}, {organization}",  # Город + организация
            )
        )
        conn.commit()
        await message.answer("Регистрация завершена! Спасибо!")
        print(f"[DEBUG] Пользователь зарегистрирован: {user_data}")  # Отладка
    except sqlite3.IntegrityError:
        await message.answer("Ошибка: Вы уже зарегистрированы.")
        print(f"[DEBUG] Пользователь с telegram_id={message.from_user.id} уже зарегистрирован.")  # Отладка
    finally:
        conn.close()

    # Показываем клавиатуру на основе роли
    role = user_data.get("role")
    if role == "Преподаватель":
        await message.answer(
            "Добро пожаловать, Преподаватель! Выберите действие из меню ниже:",
            reply_markup=teacher_kb  # Клавиатура для преподавателя
        )
    elif role == "Ученик":
        await message.answer(
            "Добро пожаловать, Ученик! Вы можете использовать бота для просмотра своих групп."
        )

    # Очищаем состояние
    await state.clear()

@dp.message(Registration.confirm_role)
async def process_role_selection(message: types.Message, state: FSMContext):
    role = message.text.strip()
    if role not in ["Преподаватель", "Ученик"]:
        await message.answer("Пожалуйста, выберите роль из предложенных вариантов.", reply_markup=role_kb)
        return

    # Сохраняем выбранную роль в состояние FSM
    await state.update_data(role=role)
    await message.answer(f"Вы выбрали роль: {role}. Теперь введите вашу фамилию.")
    await state.set_state(Registration.last_name)  # Переходим к следующему шагу
    print(f"[DEBUG] Пользователь выбрал роль: {role}. Перевод в состояние ввода фамилии.")  # Отладка



@dp.callback_query(lambda c: c.data.startswith("confirm_"))
async def confirm_request(callback: types.CallbackQuery):
    try:
        # Отладочное сообщение
        print(f"Обработчик confirm вызван: {callback.data}")

        # Извлекаем Telegram ID пользователя из callback_data
        user_id = int(callback.data.split("_")[1])

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        # Обновляем роль пользователя в базе данных
        cursor.execute("UPDATE users SET role = 'Администратор' WHERE telegram_id = ?", (user_id,))
        conn.commit()

        # Уведомляем супер-администратора и пользователя
        await bot.send_message(user_id, "Ваш запрос на роль администратора подтверждён!")
        await callback.message.edit_text("Запрос подтверждён. Пользователь теперь Администратор.")
        conn.close()

        # Обязательный ответ на callback_query
        await callback.answer("Пользователь подтверждён!")
    except Exception as e:
        print(f"Ошибка в обработчике confirm: {e}")
        await callback.answer("Произошла ошибка, попробуйте ещё раз.")


@dp.callback_query(lambda c: c.data.startswith("reject_"))
async def reject_request(callback: types.CallbackQuery):
    try:
        # Отладочное сообщение
        print(f"Обработчик reject вызван: {callback.data}")

        # Извлекаем Telegram ID пользователя из callback_data
        user_id = int(callback.data.split("_")[1])

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        # Удаляем пользователя из базы данных
        cursor.execute("DELETE FROM users WHERE telegram_id = ?", (user_id,))
        conn.commit()

        # Уведомляем супер-администратора и пользователя
        await bot.send_message(user_id, "Ваш запрос на роль администратора отклонён.")
        await callback.message.edit_text("Запрос отклонён. Пользователь удалён из базы.")
        conn.close()

        # Обязательный ответ на callback_query
        await callback.answer("Пользователь отклонён!")
    except Exception as e:
        print(f"Ошибка в обработчике reject: {e}")
        await callback.answer("Произошла ошибка, попробуйте ещё раз.")



# View Users
@dp.message(lambda message: message.text == "Просмотреть пользователей")
async def view_users(message: types.Message):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT last_name, first_name, username, role, organization FROM users")
    users = cursor.fetchall()
    conn.close()

    if users:
        user_list = "\n".join([f"{u[0]} {u[1]} (@{u[2]}) - {u[3]} ({u[4]})" for u in users])
        await message.answer(f"Зарегистрированные пользователи:\n{user_list}")
    else:
        await message.answer("Пользователи не найдены.")



# Set Role (Existing functionality retained)
class SetRole(StatesGroup):
    username = State()
    role = State()

@dp.message(lambda message: message.text == "Назначить роль")
async def set_role_prompt(message: types.Message):
    await message.answer("Введите имя пользователя:")
    await SetRole.username.set()

@dp.message(SetRole.username)
async def set_role_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Выберите роль:", reply_markup=role_kb)
    await SetRole.role.set()

@dp.message(SetRole.role)
async def set_role_role(message: types.Message, state: FSMContext):
    role = message.text
    if role not in ["Администратор", "Преподаватель", "Ученик"]:
        await message.answer("Неверная роль. Попробуйте снова.")
        return

    user_data = await state.get_data()
    username = user_data['username']

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
    if cursor.rowcount == 0:
        await message.answer("Пользователь не найден.")
    else:
        conn.commit()
        await message.answer(f"Роль успешно обновлена. {username} теперь {role}.")
    conn.close()
    await state.clear()

@dp.message(CreateGroup.description)
async def group_description_step(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    group_name = user_data.get("name")
    description = message.text

    # Сохраняем группу в базу данных
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO groups (name, description, teacher_id) VALUES (?, ?, ?)",
            (group_name, description, message.from_user.id)
        )
        conn.commit()
        await message.answer(f"Учебная группа '{group_name}' успешно создана!", reply_markup=teacher_kb)
    except Exception as e:
        await message.answer(f"Ошибка при создании группы: {e}")
    finally:
        conn.close()

    # Завершаем процесс
    await state.clear()

@dp.message(lambda message: message.text == "Мои учебные группы")
async def view_groups(message: types.Message):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Получаем группы, созданные преподавателем
    cursor.execute("SELECT name, description, auth_method, max_members FROM groups WHERE teacher_id = ?", (message.from_user.id,))
    groups = cursor.fetchall()
    conn.close()

    if groups:
        group_list = "\n\n".join([
            f"Название: {g[0]}\nОписание: {g[1]}\nАутентификация: {'Пароль' if g[2] != 'Без пароля' else 'Без пароля'}{f' (Пароль: {g[2]})' if g[2] != 'Без пароля' else ''}\nМакс. участников: {g[3]}"
            for g in groups
        ])
        await message.answer(f"Ваши группы:\n\n{group_list}")
    else:
        await message.answer("У вас ещё нет созданных групп.")



@dp.message(lambda message: message.text == "Создать учебную группу")
async def create_group_prompt(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Проверяем, является ли пользователь преподавателем
    cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (message.from_user.id,))
    user = cursor.fetchone()
    conn.close()

    if user and user[0] == "Преподаватель":
        await message.answer("Введите название группы:")
        await state.set_state(CreateGroup.name)
    else:
        await message.answer("Вы не имеете прав для создания учебных групп.")


@dp.message(CreateGroup.name)
async def group_name_step(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Введите описание группы:")
    await state.set_state(CreateGroup.description)

@dp.message(CreateGroup.description)
async def group_description_step(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())

    # Показать клавиатуру для выбора способа аутентификации
    await message.answer(
        "Выберите способ аутентификации для группы:",
        reply_markup=auth_method_kb
    )
    await state.set_state(CreateGroup.auth_method)



@dp.message(lambda message: message.text == "Мои учебные группы")
async def view_groups(message: types.Message):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Получаем группы, созданные преподавателем
    cursor.execute("SELECT name, description FROM groups WHERE teacher_id = ?", (message.from_user.id,))
    groups = cursor.fetchall()
    conn.close()

    if groups:
        group_list = "\n\n".join([f"Название: {g[0]}\nОписание: {g[1]}" for g in groups])
        await message.answer(f"Ваши группы:\n\n{group_list}")
    else:
        await message.answer("У вас ещё нет созданных групп.")

@dp.message(lambda message: message.text == "Удалить учебную группу")
async def delete_group_prompt(message: types.Message, state: FSMContext):
    await message.answer("Введите название группы, которую вы хотите удалить:")
    await state.set_state(DeleteGroup.name)

@dp.message(DeleteGroup.name)
async def delete_group_step(message: types.Message, state: FSMContext):
    group_name = message.text

    # Удаляем группу из базы данных
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE name = ? AND teacher_id = ?", (group_name, message.from_user.id))
    if cursor.rowcount > 0:
        conn.commit()
        await message.answer(f"Группа '{group_name}' успешно удалена.")
    else:
        await message.answer(f"Группа '{group_name}' не найдена или вы не являетесь её создателем.")
    conn.close()

    # Завершаем процесс
    await state.clear()

@dp.message(lambda message: message.text == "Настройки группы")
async def group_settings_prompt(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Получаем группы преподавателя
    cursor.execute("SELECT name FROM groups WHERE teacher_id = ?", (message.from_user.id,))
    groups = cursor.fetchall()
    conn.close()

    if groups:
        group_names = "\n".join([g[0] for g in groups])
        await message.answer(
            f"Ваши группы:\n{group_names}\n\nВведите название группы, которую хотите настроить:"
        )
        await state.set_state(GroupSettings.select_group)
    else:
        await message.answer("У вас нет созданных групп.")

@dp.message(GroupSettings.select_group)
async def select_group(message: types.Message, state: FSMContext):
    group_name = message.text.strip()

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Сравниваем без учёта регистра
    cursor.execute("""
        SELECT id FROM groups 
        WHERE LOWER(name) = LOWER(?) AND teacher_id = ?
    """, (group_name.lower(), message.from_user.id))
    group = cursor.fetchone()
    conn.close()

    if group:
        # Сохраняем данные группы в FSM
        await state.update_data(group_id=group[0], group_name=group_name)
        print(f"[DEBUG] Группа найдена и сохранена в FSM: {group_name} (ID = {group[0]})")

        # Предлагаем выбрать действие и переключаем состояние
        await message.answer("Что вы хотите изменить?", reply_markup=settings_kb)
        await state.set_state(GroupSettings.update_max_members)  # Установим следующее состояние
    else:
        print("[DEBUG] Группа не найдена.")
        await message.answer("Группа не найдена. Попробуйте снова. Введите корректное название группы:")



@dp.message(lambda message: message.text == "Изменить максимальное количество участников")
async def update_max_members_prompt(message: types.Message, state: FSMContext):
    # Извлекаем данные из FSM
    user_data = await state.get_data()
    group_id = user_data.get("group_id")
    group_name = user_data.get("group_name")

    # Логирование для проверки
    print(f"[DEBUG] Данные из FSM: group_id={group_id}, group_name={group_name}")

    if not group_id:
        await message.answer("Ошибка: Сначала выберите группу. Попробуйте снова.")
        return

    # Переходим к вводу нового значения
    await message.answer(f"Введите новое максимальное количество участников для группы '{group_name}':")
    await state.set_state(GroupSettings.update_max_members)


@dp.message(GroupSettings.update_max_members)
async def update_max_members(message: types.Message, state: FSMContext):
    try:
        max_members = int(message.text.strip())
        if max_members < 1:
            raise ValueError("Количество участников должно быть больше 0.")

        # Извлекаем данные из FSM
        user_data = await state.get_data()
        group_id = user_data.get("group_id")
        group_name = user_data.get("group_name")

        # Логируем данные
        print(f"[DEBUG] Изменение группы: group_id={group_id}, group_name={group_name}, max_members={max_members}")

        if not group_id:
            await message.answer("Ошибка: ID группы не найден. Попробуйте снова.")
            return

        # Обновляем данные в базе
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE groups SET max_members = ? WHERE id = ?", (max_members, group_id))
        conn.commit()
        conn.close()

        await message.answer(f"Максимальное количество участников для группы '{group_name}' обновлено на {max_members}.", reply_markup=teacher_kb)
        await state.clear()
    except ValueError:
        await message.answer("Введите корректное число.")
    except Exception as e:
        print(f"[ERROR] {e}")
        await message.answer("Произошла ошибка. Попробуйте снова.")


@dp.message(CreateGroup.auth_method)
async def group_auth_method_step(message: types.Message, state: FSMContext):
    auth_method = message.text.strip()
    if auth_method not in ["Пароль", "Без пароля"]:
        await message.answer("Неверный выбор. Пожалуйста, выберите 'Пароль' или 'Без пароля'.", reply_markup=auth_method_kb)
        return

    # Генерация случайного пароля, если выбран метод "Пароль"
    random_password = None
    if auth_method == "Пароль":
        random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

    # Получаем данные группы из FSM
    user_data = await state.get_data()
    group_name = user_data.get("name")
    description = user_data.get("description")

    # Сохраняем данные группы в базу
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO groups (name, description, teacher_id, auth_method, max_members) VALUES (?, ?, ?, ?, ?)",
            (group_name, description, message.from_user.id, random_password or "Без пароля", 30)
        )
        conn.commit()

        # Подтверждаем создание группы
        await message.answer(
            f"Группа '{group_name}' успешно создана!\n"
            f"Описание: {description}\n"
            f"Аутентификация: {'Пароль' if random_password else 'Без пароля'}"
            f"{f' (Пароль: {random_password})' if random_password else ''}"
        )
    except Exception as e:
        await message.answer(f"Ошибка при создании группы: {e}")
    finally:
        conn.close()

    # Завершаем процесс
    await state.clear()


@dp.message()
async def debug_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    print(f"[DEBUG] Получено сообщение: {message.text}, Состояние: {current_state}")

@dp.message(lambda message: message.text in ["Преподаватель", "Ученик"])
async def process_role_selection(message: types.Message, state: FSMContext):
    role = message.text
    await state.update_data(role=role)
    await message.answer(f"Вы выбрали роль: {role}. Теперь введите вашу фамилию.")
    await state.set_state(Registration.last_name)

# Run bot
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 