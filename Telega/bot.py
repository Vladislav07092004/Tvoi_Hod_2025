from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.orm import sessionmaker
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import ParseMode
from datetime import datetime
from aiogram.types import ContentType
import logging
import os
import random
import string
import re
import hashlib
import zipfile
import io

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка базы данных SQLite
DATABASE_URL = "sqlite:///database.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()


# Определение таблиц базы данных

class EducationalInstitution(Base):
    __tablename__ = "educational_institutions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    full_name = Column(String)
    role = Column(String)  # "student" или "teacher"
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    region = Column(String, nullable=True)  # Новый столбец для региона
    city = Column(String, nullable=True)    # Новый столбец для города
    educational_institution_id = Column(Integer, ForeignKey("educational_institutions.id"), nullable=True)
    educational_institution = relationship("EducationalInstitution")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    password = Column(String)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Сделано nullable=True


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    name = Column(String)
    description = Column(Text)
    deadline = Column(DateTime)
    input_data = Column(Text, nullable=True)
    expected_result = Column(String, nullable=True)

class SupportRequest(Base):
    __tablename__ = "support_requests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    assigned_support_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Кто отвечает за запрос
    message = Column(Text)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="open")  # open, in_progress, closed

    user = relationship("User", foreign_keys=[user_id])
    assigned_support = relationship("User", foreign_keys=[assigned_support_id])

# Состояние для выбора группы
class WatchGroup(StatesGroup):
    waiting_for_group_id = State()

# Создание таблиц базы данных
Base.metadata.create_all(bind=engine)

# Настройка Telegram-бота
API_TOKEN = "7202246841:AAHFaSOPlpIJTRjzSKx-HEVXt65axfJPz_Q"
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class Form(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_region = State()
    waiting_for_city = State()
    waiting_for_educational_institution = State()
    waiting_for_teacher_confirmation = State()  # Новое состояние для подтверждения
    waiting_for_group_id = State()  # Добавляем новое состояние

class CreateGroup(StatesGroup):
    waiting_for_group_name = State()

class CreateTask(StatesGroup):
    waiting_for_group_id = State()
    waiting_for_task_name = State()
    waiting_for_task_description = State()
    waiting_for_task_deadline = State()
    waiting_for_number_of_tests = State()
    waiting_for_test_method = State()  # Новое состояние для выбора способа ввода тестов
    waiting_for_input_data = State()
    waiting_for_input_archive = State()
    waiting_for_output_data = State()
    waiting_for_output_archive = State()
    waiting_for_expected_result = State()
    waiting_for_test_input = State()

def get_back_button():
    return ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Назад"))

def get_input_data_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True).add(
        KeyboardButton("Назад"),
        KeyboardButton("Входных данных нет")
    )

def get_deadline_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True).add(
        KeyboardButton("Назад"),
        KeyboardButton("НЕТ ДЕДЛАЙНА")
    )

def generate_password(length=8):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for _ in range(length))

def escape_markdown(text: str) -> str:
    # Экранирование символов, которые могут нарушить разметку Markdown
    return re.sub(r'([\\_*[\]()>#+-.!|])', r'\\\1', text)

def get_test_method_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True).add(
        KeyboardButton("Ввести тесты через клавиатуру"),
        KeyboardButton("Загрузить тесты через архив"),
        KeyboardButton("Назад")
    )

# Команда /start
@dp.message_handler(commands=['start'], state="*")
async def start_command(message: types.Message, state: FSMContext):
    await state.finish()  # Завершаем текущее состояние пользователя, если оно есть

    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if user:
        await message.reply(f"Вы уже зарегистрированы как {user.role}.")
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Студент", "Преподаватель")
        await message.reply("Добро пожаловать! Выберите вашу роль:", reply_markup=markup)

# Регистрация пользователя
# Обработчик для регистрации пользователя (студент или преподаватель)
@dp.message_handler(lambda message: message.text in ["Студент", "Преподаватель"])
async def register_user(message: types.Message, state: FSMContext):
    role = "student" if message.text == "Студент" else "teacher"
    
    # Сохраняем роль в состоянии
    await state.update_data(role=role)
    
    # Запрашиваем Ф.И.О. для пользователя
    await state.set_state("waiting_for_full_name")  # Переход к состоянию для ввода Ф.И.О.
    
    await message.reply("Введите вашу фамилию и имя:" if role == "student" else "Введите вашу фамилию, имя и отчество:")


# Обработчик для ввода Ф.И.О. для студентов и преподавателей
@dp.message_handler(state="waiting_for_full_name", content_types=types.ContentTypes.TEXT)
async def save_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()

    # Получаем данные о пользователе из состояния
    user_data = await state.get_data()
    role = user_data.get('role')
    
    # Проверка для преподавателя, что введено полное Ф.И.О.
    if role == "teacher" and len(full_name.split()) < 3:
        await message.reply("Для преподавателей нужно ввести фамилию, имя и отчество.")
        return
    
    await state.update_data(full_name=full_name)
    
    # Запрашиваем регион
    await state.set_state("waiting_for_region")
    await message.reply("Введите ваш регион:")

# Обработчик для ввода региона
@dp.message_handler(state="waiting_for_region", content_types=types.ContentTypes.TEXT)
async def save_region(message: types.Message, state: FSMContext):
    region = message.text.strip()

    # Если регион — Москва, Санкт-Петербург или Севастополь, пропускаем ввод города и образовательной организации для студента
    if region in ["Москва", "Санкт-Петербург", "Севастополь"]:
        await state.update_data(region=region)
        await state.set_state("waiting_for_educational_institution")  # Переходим к следующему шагу
        await message.reply("Введите образовательную организацию:")
    else:
        # Сохраняем регион в базе
        await state.update_data(region=region)
        
        # Запрашиваем город для студента
        await state.set_state("waiting_for_city")
        await message.reply("Введите ваш город:")

# Обработчик для ввода образовательной организации (для преподавателя или студента)
@dp.message_handler(state="waiting_for_educational_institution", content_types=types.ContentTypes.TEXT)
async def save_educational_institution(message: types.Message, state: FSMContext):
    educational_institution_name = message.text.strip()

    # Получаем данные о пользователе из состояния
    user_data = await state.get_data()
    role = user_data.get('role')

    # Проверяем, существует ли уже образовательная организация в базе данных
    institution = session.query(EducationalInstitution).filter_by(name=educational_institution_name).first()

    # Если образовательная организация не найдена, создаем новую
    if not institution:
        institution = EducationalInstitution(name=educational_institution_name)
        session.add(institution)
        session.commit()

    # Логика для студента
    if role == "student":
        user = User(
            telegram_id=str(message.from_user.id),
            full_name=user_data.get('full_name'),
            role="student",
            region=user_data.get('region'),
            city=user_data.get('city'),
            educational_institution_id=institution.id,
        )
        session.add(user)
        session.commit()
        await message.reply(f"Вы выбрали образовательную организацию: {institution.name}. Регистрация завершена!")
        await state.finish()
    else:
        # Логика для преподавателя
        user = User(
            telegram_id=str(message.from_user.id),
            full_name=user_data.get('full_name'),
            role="pending_teacher",  # Роль "pending_teacher" — ожидает подтверждения
            region=user_data.get('region'),
            city=user_data.get('city'),
            educational_institution_id=institution.id,
        )
        session.add(user)
        session.commit()

        # Уведомляем техподдержку о новом запросе
        support_users = session.query(User).filter_by(role="support").all()
        for support in support_users:
            await bot.send_message(
                support.telegram_id,
                f"📩 Новый запрос на регистрацию преподавателя:\n"
                f"👤 Имя: {user.full_name}\n"  # Добавляем имя пользователя
                f"🏫 Образовательное учреждение: {institution.name}\n"
                f"🆔 ID: {user.id}\n"
                f"✅ Подтвердить: /confirm_teacher {user.id}\n"
                f"❌ Отклонить: /reject_teacher {user.id}"
            )

        await message.reply(
            f"Вы выбрали образовательную организацию: {institution.name}. "
            "Ваша регистрация отправлена на подтверждение техподдержке. Ожидайте ответа."
        )
        await state.finish()

# Шаг 3: Обработка выбора преподавателя (для студента)
@dp.callback_query_handler(lambda c: c.data.startswith("teacher_"), state="waiting_for_teacher")
async def handle_teacher(callback_query: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback_query.data.split("_")[1])
    teacher = session.query(User).filter_by(id=teacher_id).first()

    if not teacher:
        await callback_query.message.reply("Ошибка. Преподаватель с таким ID не найден.")
        return

    # Сохраняем выбор преподавателя в состоянии
    await state.update_data(teacher_id=teacher_id)

    # Шаг 4: Вывод групп, которые ведет выбранный преподаватель
    groups = session.query(Group).filter_by(teacher_id=teacher_id).all()
    if not groups:
        await callback_query.message.reply(f"Этот преподаватель {teacher.full_name} не ведет ни одной группы.")
        return

    group_list = "\n".join([f"{group.id}: {group.name}" for group in groups])
    await callback_query.message.reply(f"Вы выбрали преподавателя: {teacher.full_name}. Теперь выберите группу по ID:\n{group_list}")
    await state.set_state("waiting_for_group")

# Шаг 5: Обработка выбора группы по ID (для студента)
@dp.message_handler(lambda message: message.text.isdigit(), state="waiting_for_group")
async def handle_group(message: types.Message, state: FSMContext):
    group_id = int(message.text.strip())
    group = session.query(Group).filter_by(id=group_id).first()

    if not group:
        await message.reply("Ошибка. Группа с таким ID не найдена.")
        return

    # Сохраняем выбор группы в состоянии
    await state.update_data(group_id=group_id)

    # Шаг 6: Завершаем регистрацию студента в группе
    user_data = await state.get_data()
    user = User(
        telegram_id=str(message.from_user.id),
        full_name=user_data.get('full_name'),
        role="student",  # Студент
        region=user_data.get('region'),
        city=user_data.get('city'),
        educational_institution_id=user_data.get('educational_institution_id'),  # Ссылка на образовательную организацию
        group_id=group.id  # Привязка к группе
    )
    session.add(user)
    session.commit()  # Сохраняем студента в базе данных

    # Завершаем процесс регистрации
    await state.finish()
    await message.reply(f"Вы успешно зарегистрированы как студент в группе {group.name}. Добро пожаловать!")

@dp.message_handler(commands=['create_group'])
async def cmd_create_group(message: types.Message, state: FSMContext):
    # Получаем пользователя из базы данных по telegram_id
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    # Проверка прав доступа (только администратор или преподаватель)
    if not user or user.role not in ["admin", "teacher"]:
        await message.reply("У вас нет прав для создания группы.")
        return

    # Переход к состоянию для ввода названия группы
    await state.set_state("waiting_for_group_name")
    await message.reply("Введите название новой группы:")

# Обработчик для ввода названия группы
# Обработчик для ввода названия группы
@dp.message_handler(state="waiting_for_group_name", content_types=types.ContentTypes.TEXT)
async def process_group_name(message: types.Message, state: FSMContext):
    group_name = message.text.strip()

    # Проверка, что название группы не пустое
    if not group_name:
        await message.reply("Название группы не может быть пустым. Попробуйте снова.")
        return

    # Получаем данные о преподавателе (например, текущий пользователь)
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    # Проверка, что пользователь является преподавателем
    if not user or user.role != "teacher":
        await message.reply("Только преподаватели могут создавать группы.")
        return

    # Сохраняем название группы в состоянии
    await state.update_data(group_name=group_name)  # Сохраняем название группы
    
    # Создаем группу с привязкой к преподавателю
    new_group = Group(name=group_name, password=None, teacher_id=user.id)
    session.add(new_group)
    session.commit()
    await message.reply(f"Группа '{group_name}' успешно создана без пароля.")

    # Завершаем процесс создания группы
    await state.finish()


# Обработчик для ввода пароля
@dp.message_handler(state="waiting_for_password", content_types=types.ContentTypes.TEXT)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()

    if password.lower() == 'генерировать':
        # Генерация случайного пароля
        password = generate_password()
    
    group_name = (await state.get_data())["group_name"]

    # Экранируем название группы и пароль для использования в Markdown
    group_name = escape_markdown(group_name)
    password = escape_markdown(password)

    # Проверяем, существует ли группа с таким названием в базе данных
    existing_group = session.query(Group).filter_by(name=group_name).first()
    if existing_group:
        await message.reply(f"Группа с названием '{group_name}' уже существует. Пожалуйста, выберите другое название.")
        return

    # Сохраняем группу с паролем
    new_group = Group(name=group_name, password=password)
    session.add(new_group)
    try:
        session.commit()
        await message.reply(f"Группа '{group_name}' успешно создана с паролем: {password}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        # В случае ошибки с коммитом выводим сообщение
        await message.reply("Произошла ошибка при создании группы. Пожалуйста, попробуйте снова.")
        session.rollback()

    # Завершаем процесс создания группы
    await state.finish()


# Обработчик для изменения пароля
@dp.message_handler(commands=['change_password'])
async def cmd_change_password(message: types.Message, state: FSMContext):
    # Проверяем роль пользователя (должен быть преподавателем или администратором)
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if not user or user.role not in ["admin", "teacher"]:
        await message.reply("У вас нет прав для изменения пароля группы.")
        return

    # Запросить название группы для изменения пароля
    await state.set_state("waiting_for_group_name_for_password_change")
    await message.reply("Введите название группы, для которой хотите изменить пароль:")

# Обработчик для выбора группы для изменения пароля
@dp.message_handler(state="waiting_for_group_name_for_password_change", content_types=types.ContentTypes.TEXT)
async def process_group_name_for_password_change(message: types.Message, state: FSMContext):
    group_name = message.text.strip()

    # Проверяем, существует ли такая группа
    group = session.query(Group).filter_by(name=group_name).first()
    if not group:
        await message.reply(f"Группа с названием '{group_name}' не найдена.")
        return

    # Переход к состоянию для ввода нового пароля
    await state.update_data(group_name=group_name)
    await state.set_state("waiting_for_new_password")
    await message.reply(f"Введите новый пароль для группы '{group_name}'.")

# Обработчик для ввода нового пароля
@dp.message_handler(state="waiting_for_new_password", content_types=types.ContentTypes.TEXT)
async def process_new_password(message: types.Message, state: FSMContext):
    new_password = message.text.strip()
    
    group_name = (await state.get_data())["group_name"]

    # Обновляем пароль группы
    group = session.query(Group).filter_by(name=group_name).first()
    group.password = new_password
    session.commit()
    
    await message.reply(f"Пароль для группы '{group_name}' успешно изменен.", parse_mode=ParseMode.MARKDOWN)

    # Завершаем процесс изменения пароля
    await state.finish()

# Присоединение ученика к группе
@dp.message_handler(lambda message: not message.text.startswith("Группа: ") and len(message.text) == 8)
async def join_group(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return
    group = session.query(Group).filter_by(password=None).first()  # Ищем группу без пароля
    if group:
        user.group_id = group.id
        session.commit()
        await message.reply(f"Вы присоединились к группе '{group.name}'.")
    else:
        await message.reply("Группа с таким паролем не найдена.")


# Создание задания
@dp.message_handler(commands=['create_task'])
async def create_task(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "teacher":
        await message.reply("Эта команда доступна только для преподавателей.")
        return
    groups = session.query(Group).all()
    if not groups:
        await message.reply("Сначала создайте группу с помощью /create_group.")
        return
    group_list = "\n".join([f"{g.id}: {g.name}" for g in groups])
    await message.reply(f"Выберите ID группы для задания:\n{group_list}")
    await CreateTask.waiting_for_group_id.set()

@dp.message_handler(state=CreateTask.waiting_for_group_id, content_types=types.ContentTypes.TEXT)
async def set_task_group(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.reply("Вы вернулись на начало.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Назад")))
        await CreateTask.waiting_for_group_id.set()
        return
    group_id = int(message.text)
    group = session.query(Group).filter_by(id=group_id).first()
    if not group:
        await message.reply("Группа с таким ID не найдена. Попробуйте ещё раз.")
        return
    await state.update_data(group_id=group_id)
    await message.reply("Введите название задания:", reply_markup=get_back_button())
    await CreateTask.waiting_for_task_name.set()

@dp.message_handler(state=CreateTask.waiting_for_task_name, content_types=types.ContentTypes.TEXT)
async def set_task_name(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.reply("Вы вернулись на шаг выбора группы.", reply_markup=get_back_button())
        await CreateTask.waiting_for_group_id.set()
        return
    await state.update_data(task_name=message.text.strip())
    await message.reply("Введите описание задания:", reply_markup=get_back_button())
    await CreateTask.waiting_for_task_description.set()

@dp.message_handler(state=CreateTask.waiting_for_task_description, content_types=types.ContentTypes.TEXT)
async def set_task_description(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.reply("Вы вернулись на шаг ввода названия задания.", reply_markup=get_back_button())
        await CreateTask.waiting_for_task_name.set()
        return
    await state.update_data(task_description=message.text.strip())
    await message.reply("Введите дедлайн задания в формате YYYY-MM-DD HH:MM или выберите 'НЕТ ДЕДЛАЙНА'.", reply_markup=get_deadline_keyboard())
    await CreateTask.waiting_for_task_deadline.set()  # Переходим к вводу дедлайна

@dp.message_handler(state=CreateTask.waiting_for_task_deadline, content_types=types.ContentTypes.TEXT)
async def set_task_deadline(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.reply("Вы вернулись на шаг ввода описания задания.", reply_markup=get_back_button())
        await CreateTask.waiting_for_task_description.set()
        return
    elif message.text == "НЕТ ДЕДЛАЙНА":
        # Устанавливаем дедлайн как None
        await state.update_data(task_deadline=None)
        await message.reply("Выберите способ ввода тестов:", reply_markup=get_test_method_keyboard())
        await CreateTask.waiting_for_test_method.set()  # Переходим к выбору способа ввода тестов
        return

    try:
        # Пытаемся преобразовать введённую строку в формат даты
        deadline = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        await state.update_data(task_deadline=deadline)
        await message.reply("Выберите способ ввода тестов:", reply_markup=get_test_method_keyboard())
        await CreateTask.waiting_for_test_method.set()  # Переходим к выбору способа ввода тестов
    except ValueError:
        # Если формат неправильный, отправляем ошибку
        await message.reply("Неверный формат даты. Пожалуйста, введите дедлайн в формате YYYY-MM-DD HH:MM.")

@dp.message_handler(state=CreateTask.waiting_for_expected_result, content_types=types.ContentTypes.TEXT)
async def set_test_output(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_number = data.get("current_test", 1)
    number_of_tests = data.get("number_of_tests")

    # Сохраняем ожидаемые результаты
    if "test_outputs" not in data:
        data["test_outputs"] = []
    data["test_outputs"].append(message.text)
    await state.update_data(test_outputs=data["test_outputs"])

    # Проверяем, все ли тесты введены
    if test_number < number_of_tests:
        await state.update_data(current_test=test_number + 1)
        await message.reply(f"Введите входные данные для теста {test_number + 1}:")
        await CreateTask.waiting_for_test_input.set()
    else:
        # Все тесты введены, завершаем процесс
        await message.reply("Все тесты успешно добавлены.")
        await state.finish()

@dp.message_handler(commands=['help'], state="*")
async def help_command(message: types.Message, state: FSMContext):
    help_text = """
📚 **Список доступных команд:**

👨‍🏫 **Для преподавателей:**
- `/create_group` — создать новую группу.
- `/create_task` — создать задание для группы.
- `/watchgroup` — посмотреть участников группы.
- `/report` — получить отчёт о прогрессе учеников.

👨‍🎓 **Для студентов:**
- Введите пароль группы, чтобы присоединиться.
- `/submit` — отправить решение задания.
- `/view_tasks` — просмотреть задания своей группы.
- `/task_status` — узнать статус выполнения заданий.
- `/task_deadline` — посмотреть дедлайн для заданий.
- `/task_requirements` — получить требования для выполнения задания.
- `/my_group` — информация о вашей группе.

ℹ️ **Общие команды:**
- `/help` — показать это сообщение.
- `/start` — начать работу с ботом.

💡 Если у вас возникли вопросы или проблемы, обратитесь к администратору.
    """
    await message.reply(help_text, parse_mode="Markdown")

    # Проверяем, есть ли активное состояние у пользователя
    current_state = await state.get_state()
    if current_state:
        await message.reply("Вы можете продолжить с того места, где остановились. Просто продолжите ввод.")

@dp.message_handler(commands=['help_admin'])
async def help_admin_command(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return

    help_text = """
🛠 **Панель техподдержки** 🛠

👥 **Управление пользователями:**
- `/list_users` — показать всех пользователей.
- `/find_user <ID | имя>` — найти пользователя.
- `/edit_user <ID> <student/teacher/support>` — изменить роль пользователя.
- `/delete_user <ID>` — удалить пользователя.

🏫 **Управление группами:**
- `/list_groups` — показать все группы.
- `/reset_group_password <ID группы>` — сброс пароля группы.

📩 **Запросы в поддержку:**
- `/list_open_requests` — список всех открытых запросов.
- `/take_request <ID>` — взять запрос в работу.
- `/transfer_request <ID> <@username>` — передать запрос другому специалисту.
- `/my_requests_admin` — список запросов, назначенных на вас.
- `/reply_request <ID> <ответ>` — ответить пользователю на запрос.

📊 **Отчёты и статистика:**
- `/support_report` — общий отчёт по пользователям, группам и активности.

⚙️ **Дополнительно:**
- `/help_admin` — показать этот список команд.

💡 **Как работать с запросами?**
1️⃣ Запросы пользователей видны в `/list_open_requests`.  
2️⃣ Чтобы взять запрос себе, используйте `/take_request <ID>`.  
3️⃣ Если не можете ответить, передайте запрос через `/transfer_request <ID> <@username>`.  
4️⃣ Чтобы ответить пользователю, используйте `/reply_request <ID> <ответ>`.  
5️⃣ Просмотреть свои активные запросы — `/my_requests_admin`.  
6️⃣ Получить статистику по системе — `/support_report`.  

📌 **Если у вас возникли вопросы, обратитесь к главному администратору.**
"""
    await message.reply(help_text, parse_mode="Markdown")

# Обработчик команды /watchgroup
@dp.message_handler(commands=['watchgroup'])
async def watch_group(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "teacher":
        await message.reply("Эта команда доступна только для преподавателей.")
        return

    # Получение всех групп, созданных преподавателем
    groups = session.query(Group).all()
    if not groups:
        await message.reply("Вы ещё не создали ни одной группы. Используйте /create_group, чтобы создать группу.")
        return

    # Отправляем список групп преподавателю
    group_list = "\n".join([f"{group.id}: {group.name}" for group in groups])
    await message.reply(f"Выберите ID группы, чтобы посмотреть её участников:\n{group_list}")
    await WatchGroup.waiting_for_group_id.set()

# Обработчик выбора группы
@dp.message_handler(state=WatchGroup.waiting_for_group_id, content_types=types.ContentTypes.TEXT)
async def show_group_members(message: types.Message, state: FSMContext):
    try:
        group_id = int(message.text.strip())
        group = session.query(Group).filter_by(id=group_id).first()

        if not group:
            await message.reply("Группа с таким ID не найдена. Попробуйте ещё раз.")
            return

        # Получение участников группы
        members = session.query(User).filter_by(group_id=group.id).all()
        if not members:
            await message.reply(f"В группе '{group.name}' пока нет участников.")
        else:
            member_list = "\n".join([f"- {member.full_name}" for member in members])
            await message.reply(f"Участники группы '{group.name}':\n{member_list}")

    except ValueError:
        await message.reply("Пожалуйста, введите корректный ID группы (число).")
    finally:
        # Завершаем состояние
        await state.finish()


@dp.message_handler(lambda message: message.text.isdigit())
async def set_task_group(message: types.Message):
    group_id = int(message.text)
    group = session.query(Group).filter_by(id=group_id).first()
    if group:
        await message.reply("Введите название задания:")
    else:
        await message.reply("Группа с таким ID не найдена.")

@dp.message_handler(state=CreateTask.waiting_for_input_data, content_types=types.ContentTypes.TEXT)
async def set_task_input_data(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.reply("Вы вернулись на шаг выбора способа ввода тестов.", reply_markup=get_test_method_keyboard())
        await CreateTask.waiting_for_test_method.set()
        return

    # Получаем данные из состояния
    data = await state.get_data()
    number_of_tests = data.get("number_of_tests", 1)
    current_test = data.get("current_test", 1)

    # Сохраняем входные данные
    if "input_data" not in data:
        data["input_data"] = []
    data["input_data"].append(message.text.strip())
    await state.update_data(input_data=data["input_data"])

    # Проверяем, все ли тесты введены
    if current_test < number_of_tests:
        await state.update_data(current_test=current_test + 1)
        await message.reply(f"Введите входные данные для теста {current_test + 1}:")
    else:
        # Все тесты введены, переходим к вводу ожидаемых результатов
        await message.reply("Введите ожидаемый результат для теста 1:")
        await CreateTask.waiting_for_expected_result.set()


# Студентские команды

# Просмотр всех заданий для группы
@dp.message_handler(commands=['view_tasks'])
async def view_tasks(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return

    tasks = session.query(Task).filter_by(group_id=user.group_id).all()
    if not tasks:
        await message.reply("У вашей группы нет заданий.")
        return

    task_list = "\n".join([f"{task.id}: {task.name} (Дедлайн: {task.deadline})" for task in tasks])
    await message.reply(f"Доступные задания для вашей группы:\n{task_list}")

# Информация о группе
@dp.message_handler(commands=['my_group'])
async def my_group(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return

    if not user.group_id:
        await message.reply("Вы ещё не присоединились к группе.")
        return

    group = session.query(Group).filter_by(id=user.group_id).first()
    members = session.query(User).filter_by(group_id=user.group_id).all()
    member_list = "\n".join([f"- {member.full_name}" for member in members])

    await message.reply(f"Вы в группе '{group.name}'.\nУчастники группы:\n{member_list}")

# Отправить решение задания
@dp.message_handler(commands=['submit'])
async def submit_solution(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return

    await message.reply("Отправьте ваше решение задания (например, файл или текст).")

# Статус выполнения задания
@dp.message_handler(commands=['task_status'])
async def task_status(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return

    tasks = session.query(Task).filter_by(group_id=user.group_id).all()
    if not tasks:
        await message.reply("У вашей группы нет заданий.")
        return

    status_list = ""
    for task in tasks:
        status_list += f"{task.name}: Статус выполнения - Не сдано\n"  # Пример статуса
    await message.reply(f"Статусы заданий:\n{status_list}")

# Дедлайны для заданий
@dp.message_handler(commands=['task_deadline'])
async def task_deadline(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return

    tasks = session.query(Task).filter_by(group_id=user.group_id).all()
    if not tasks:
        await message.reply("У вашей группы нет заданий.")
        return

    deadline_list = "\n".join([f"{task.name}: {task.deadline}" for task in tasks])
    await message.reply(f"Дедлайны для заданий:\n{deadline_list}")

# Требования к заданиям
@dp.message_handler(commands=['task_requirements'])
async def task_requirements(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return

    tasks = session.query(Task).filter_by(group_id=user.group_id).all()
    if not tasks:
        await message.reply("У вашей группы нет заданий.")
        return

    requirements_list = "\n".join([f"{task.name}: {task.description}" for task in tasks])
    await message.reply(f"Требования к заданиям:\n{requirements_list}")

@dp.message_handler(commands=['link_group'])
async def link_group_command(message: types.Message):
    # Проверяем, есть ли пользователь в базе данных
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user:
        await message.reply("Вы не зарегистрированы в системе. Пожалуйста, сначала завершите регистрацию.")
        return

    # Запрашиваем ID группы
    await message.reply("Введите ID группы, к которой вы хотите привязаться:")

    # Переходим к следующему состоянию для ввода ID группы
    await Form.waiting_for_group_id.set()

@dp.message_handler(state=Form.waiting_for_group_id)
async def process_group_id(message: types.Message, state: FSMContext):
    group_id = message.text.strip()

    # Проверка на корректность введенного ID
    if not group_id.isdigit():
        await message.reply("Пожалуйста, введите корректный ID группы.")
        return

    # Проверяем, существует ли группа с таким ID
    group = session.query(Group).filter_by(id=int(group_id)).first()
    if not group:
        await message.reply("Группа с таким ID не найдена. Пожалуйста, проверьте введенные данные.")
        return

    # Привязываем пользователя к группе
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if user:
        user.group_id = int(group_id)
        session.commit()
        await message.reply(f"Вы успешно привязались к группе с ID: {group_id}")
    else:
        await message.reply("Ошибка: Не удалось найти пользователя. Попробуйте снова.")

    # Завершаем состояние
    await state.finish()

# Обработчик для ввода ID группы
@dp.message_handler(state="waiting_for_group_id", content_types=types.ContentTypes.TEXT)
async def save_group_id(message: types.Message, state: FSMContext):
    group_id = message.text.strip()

    # Проверяем, существует ли группа в базе данных
    group = session.query(Group).filter_by(id=group_id).first()
    if not group:
        await message.reply("Группа с таким ID не найдена. Пожалуйста, убедитесь, что ID введен корректно.")
        return

    # Привязываем пользователя к группе без запроса пароля
    user_data = await state.get_data()
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    # Привязываем пользователя к группе
    user.group_id = group.id
    session.commit()

    # Завершаем процесс
    await message.reply(f"Вы успешно привязаны к группе {group.name}. Пожалуйста, используйте команду /help для получения доступных вам команд.")
    await state.finish()


# Обработчик для ввода пароля группы
@dp.message_handler(state="waiting_for_group_password", content_types=types.ContentTypes.TEXT)
async def verify_group_password(message: types.Message, state: FSMContext):
    # Получаем данные о группе из состояния
    user_data = await state.get_data()
    group_id = user_data.get('group_id')

    # Ищем группу в базе данных по ID
    group = session.query(Group).filter_by(id=group_id).first()
    if not group:
        await message.reply("Ошибка! Группа не найдена.")
        await state.finish()
        return

    # Привязываем пользователя к группе
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if user:
        user.group_id = group.id
        session.commit()

        # Завершаем процесс
        await message.reply(f"Вы успешно привязаны к группе {group.name}. Пожалуйста, используйте команду /help для получения доступных вам команд.")
        await state.finish()
    else:
        await message.reply("Ошибка: Не удалось найти пользователя. Попробуйте снова.")
        await state.finish()

@dp.message_handler(commands=['list_users'])
async def list_users(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для просмотра пользователей.")
        return

    users = session.query(User).all()
    user_list = "\n".join([f"{u.id}: {u.full_name} ({u.role})" for u in users])
    await message.reply(f"👥 **Список пользователей:**\n{user_list}", parse_mode="Markdown")

@dp.message_handler(commands=['find_user'])
async def find_user(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для поиска пользователей.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("📌 Использование: `/find_user <ID или имя>`", parse_mode="Markdown")
        return

    search_term = args[1]
    found_users = session.query(User).filter(User.full_name.ilike(f"%{search_term}%")).all()

    if not found_users:
        await message.reply("🔍 Пользователь не найден.")
        return

    user_info = "\n".join([f"{u.id}: {u.full_name} ({u.role})" for u in found_users])
    await message.reply(f"🔎 **Найденные пользователи:**\n{user_info}", parse_mode="Markdown")

@dp.message_handler(commands=['edit_user'])
async def edit_user(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для редактирования пользователей.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("📌 Использование: `/edit_user <ID> <новая роль>`", parse_mode="Markdown")
        return

    user_id, new_role = args[1], args[2]
    target_user = session.query(User).filter_by(id=user_id).first()

    if not target_user:
        await message.reply("🔍 Пользователь не найден.")
        return

    if new_role not in ["student", "teacher", "support"]:
        await message.reply("⚠️ Роль должна быть: `student`, `teacher` или `support`", parse_mode="Markdown")
        return

    target_user.role = new_role
    session.commit()
    await message.reply(f"✅ Пользователь `{target_user.full_name}` теперь `{new_role}`.", parse_mode="Markdown")

@dp.message_handler(commands=['list_groups'])
async def list_groups(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для просмотра групп.")
        return

    groups = session.query(Group).all()
    group_list = "\n".join([f"{g.id}: {g.name}" for g in groups])
    await message.reply(f"🏫 **Список групп:**\n{group_list}", parse_mode="Markdown")

@dp.message_handler(commands=['support_request'])
async def send_support_request(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    if not user:
        await message.reply("❌ Вы не зарегистрированы в системе.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("📌 Использование: `/support_request <ваш вопрос>`")
        return

    user_message = args[1]

    support_request = SupportRequest(
        user_id=user.id,
        message=user_message,
        status="open"
    )
    session.add(support_request)
    session.commit()

    await message.reply("✅ Ваш запрос отправлен в техподдержку. Ожидайте ответа.")

    support_users = session.query(User).filter_by(role="support").all()
    for support in support_users:
        await bot.send_message(support.telegram_id, f"📩 Новый запрос: {user.full_name}:\n{user_message}\nОтвет: `/reply_request {support_request.id} <ответ>`")

@dp.message_handler(commands=['reply_request'])
async def reply_to_support_request(message: types.Message):
    support = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not support or support.role != "support":
        await message.reply("❌ У вас нет прав для ответа на запросы.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("📌 Использование: `/reply_request <ID запроса> <ответ>`")
        return

    request_id, response_text = args[1], args[2]
    support_request = session.query(SupportRequest).filter_by(id=request_id, status="open").first()

    if not support_request:
        await message.reply("❌ Запрос не найден или уже закрыт.")
        return

    support_request.response = response_text
    support_request.support_id = support.id
    support_request.status = "closed"
    session.commit()

    user = session.query(User).filter_by(id=support_request.user_id).first()
    if user:
        await bot.send_message(user.telegram_id, f"📩 Ответ техподдержки:\n❓ {support_request.message}\n✅ {response_text}")

    await message.reply(f"✅ Ответ отправлен пользователю {user.full_name}.")

@dp.message_handler(commands=['list_open_requests'])
async def list_open_requests(message: types.Message):
    support = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    if not support or support.role != "support":
        await message.reply("❌ У вас нет прав для просмотра запросов.")
        return

    requests = session.query(SupportRequest).filter_by(status="open").all()

    if not requests:
        await message.reply("📌 Нет открытых запросов в поддержку.")
        return

    request_list = "\n".join(
        [f"🆔 **ID:** {r.id} | 👤 **{r.user.full_name}** | ❓ {r.message}" for r in requests]
    )
    
    await message.reply(f"📋 **Открытые запросы:**\n\n{request_list}\n\nОтветить: `/reply_request <ID запроса> <ответ>`", parse_mode="Markdown")

@dp.message_handler(commands=['take_request'])
async def take_request(message: types.Message):
    support = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if not support or support.role != "support":
        await message.reply("❌ У вас нет прав для работы с запросами.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("📌 Использование: `/take_request <ID запроса>`")
        return

    request_id = args[1]
    support_request = session.query(SupportRequest).filter_by(id=request_id, status="open").first()

    if not support_request:
        await message.reply("❌ Запрос не найден или уже обрабатывается.")
        return

    support_request.assigned_support_id = support.id
    support_request.status = "in_progress"
    session.commit()

    await message.reply(f"✅ Запрос `{request_id}` теперь в вашей зоне ответственности.", parse_mode="Markdown")

@dp.message_handler(commands=['transfer_request'])
async def transfer_request(message: types.Message):
    support = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if not support or support.role != "support":
        await message.reply("❌ У вас нет прав для передачи запросов.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("📌 Использование: `/transfer_request <ID запроса> <@username>`")
        return

    request_id, new_support_username = args[1], args[2].replace("@", "")

    # Ищем специалиста по username
    new_support = session.query(User).filter_by(full_name=new_support_username, role="support").first()
    support_request = session.query(SupportRequest).filter_by(id=request_id, assigned_support_id=support.id).first()

    if not support_request:
        await message.reply("❌ Запрос не найден или не назначен вам.")
        return

    if not new_support:
        await message.reply("❌ Специалист техподдержки с таким именем не найден.")
        return

    support_request.assigned_support_id = new_support.id
    session.commit()

    await message.reply(f"✅ Запрос `{request_id}` передан специалисту **{new_support.full_name}**.", parse_mode="Markdown")
    await bot.send_message(new_support.telegram_id, f"🔄 Вам передан запрос `{request_id}` от **{support.full_name}**.")

@dp.message_handler(commands=['my_requests_admin'])
async def my_requests_admin(message: types.Message):
    support = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    if not support or support.role != "support":
        await message.reply("❌ У вас нет прав для просмотра запросов.")
        return

    # Получаем все запросы, назначенные на данного специалиста и не закрытые
    requests = session.query(SupportRequest).filter(
        SupportRequest.assigned_support_id == support.id,
        SupportRequest.status.in_(["open", "in_progress"])
    ).all()

    if not requests:
        await message.reply("📌 У вас нет активных запросов.")
        return

    request_list = "\n\n".join([
        f"🆔 **ID:** {r.id}\n👤 **Пользователь:** {r.user.full_name}\n❓ **Запрос:** {r.message}\n📅 **Дата:** {r.created_at.strftime('%Y-%m-%d %H:%M')}\n📌 **Статус:** {r.status.upper()}"
        for r in requests
    ])

    await message.reply(f"📋 **Ваши активные запросы:**\n\n{request_list}", parse_mode="Markdown")


@dp.message_handler(commands=['list_open_requests'])
async def list_open_requests(message: types.Message):
    support = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    if not support or support.role != "support":
        await message.reply("❌ У вас нет прав для просмотра запросов.")
        return

    requests = session.query(SupportRequest).filter(SupportRequest.status.in_(["open", "in_progress"])).all()

    if not requests:
        await message.reply("📌 Нет открытых запросов.")
        return

    request_list = "\n".join(
        [f"🆔 **ID:** {r.id} | 👤 {r.user.full_name} | ❓ {r.message} | 🛠 {r.assigned_support.full_name if r.assigned_support else '❌ Не назначен'}"
         for r in requests]
    )
    
    await message.reply(f"📋 **Открытые запросы:**\n\n{request_list}\n\nВзять запрос: `/take_request <ID>`", parse_mode="Markdown")

@dp.message_handler(commands=['confirm_teacher'])
async def confirm_teacher(message: types.Message):
    # Проверяем, что пользователь — техподдержка
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для подтверждения преподавателей.")
        return

    # Получаем ID преподавателя из команды
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("📌 Использование: `/confirm_teacher <ID преподавателя>`")
        return

    teacher_id = args[1]
    teacher = session.query(User).filter_by(id=teacher_id, role="pending_teacher").first()

    if not teacher:
        await message.reply("❌ Преподаватель с таким ID не найден или уже подтвержден.")
        return

    # Меняем роль на "teacher"
    teacher.role = "teacher"
    session.commit()

    # Уведомляем преподавателя
    await bot.send_message(teacher.telegram_id, "✅ Ваша регистрация подтверждена! Теперь вы можете создавать группы и задания.")

    # Уведомляем техподдержку
    await message.reply(f"✅ Преподаватель {teacher.full_name} успешно подтвержден.")

@dp.message_handler(commands=['reject_teacher'])
async def reject_teacher(message: types.Message):
    # Проверяем, что пользователь — техподдержка
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для отклонения преподавателей.")
        return

    # Получаем ID преподавателя из команды
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("📌 Использование: `/reject_teacher <ID преподавателя>`")
        return

    teacher_id = args[1]
    teacher = session.query(User).filter_by(id=teacher_id, role="pending_teacher").first()

    if not teacher:
        await message.reply("❌ Преподаватель с таким ID не найден или уже подтвержден.")
        return

    # Удаляем пользователя или меняем роль на "student" (в зависимости от логики)
    session.delete(teacher)
    session.commit()

    # Уведомляем преподавателя
    await bot.send_message(teacher.telegram_id, "❌ Ваша регистрация отклонена техподдержкой.")

    # Уведомляем техподдержку
    await message.reply(f"❌ Преподаватель {teacher.full_name} отклонен.")

@dp.message_handler(state=CreateTask.waiting_for_number_of_tests, content_types=types.ContentTypes.TEXT)
async def set_number_of_tests(message: types.Message, state: FSMContext):
    # Обработка команды "Назад"
    if message.text and message.text.strip().lower() == "назад":
        await message.reply("Вы вернулись на шаг выбора способа ввода тестов.", reply_markup=get_test_method_keyboard())
        await CreateTask.waiting_for_test_method.set()
        return  # Завершаем выполнение функции

    try:
        number_of_tests = int(message.text.strip())
        if number_of_tests <= 0:
            await message.reply("Количество тестов должно быть больше 0.")
            return

        # Сохраняем количество тестов в состоянии
        await state.update_data(number_of_tests=number_of_tests, current_test=1)

        # Переходим к вводу входных данных
        await message.reply(f"Введите входные данные для теста 1:", reply_markup=get_back_button())
        await CreateTask.waiting_for_input_data.set()
    except ValueError:
        await message.reply("Пожалуйста, введите число или используйте кнопку 'Назад'.")

@dp.message_handler(state=CreateTask.waiting_for_test_input, content_types=types.ContentTypes.TEXT)
async def set_test_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_number = data.get("current_test", 1)
    number_of_tests = data.get("number_of_tests")

    # Проверяем, что number_of_tests не None
    if number_of_tests is None:
        await message.reply("Ошибка: количество тестов не указано. Пожалуйста, начните заново.")
        await state.finish()
        return

    # Сохраняем входные данные
    if "test_inputs" not in data:
        data["test_inputs"] = []
    data["test_inputs"].append(message.text)
    await state.update_data(test_inputs=data["test_inputs"])

    # Переходим к вводу ожидаемых результатов
    await message.reply(f"Введите ожидаемый результат для теста {test_number}:")
    await CreateTask.waiting_for_expected_result.set()

@dp.message_handler(state=CreateTask.waiting_for_expected_result, content_types=types.ContentTypes.TEXT)
async def set_test_output(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_number = data.get("current_test", 1)
    number_of_tests = data.get("number_of_tests")

    # Проверяем, что number_of_tests не None
    if number_of_tests is None:
        await message.reply("Ошибка: количество тестов не указано. Пожалуйста, начните заново.")
        await state.finish()
        return

    # Сохраняем ожидаемые результаты
    if "test_outputs" not in data:
        data["test_outputs"] = []
    data["test_outputs"].append(message.text)
    await state.update_data(test_outputs=data["test_outputs"])

    # Проверяем, все ли тесты введены
    if test_number < number_of_tests:
        await state.update_data(current_test=test_number + 1)
        await message.reply(f"Введите входные данные для теста {test_number + 1}:")
        await CreateTask.waiting_for_test_input.set()
    else:
        # Все тесты введены, завершаем процесс
        await message.reply("Все тесты успешно добавлены.")
        await state.finish()

@dp.message_handler(state=CreateTask.waiting_for_input_archive, content_types=[types.ContentType.DOCUMENT, types.ContentType.TEXT])
async def handle_input_archive(message: types.Message, state: FSMContext):
    # Обработка команды "Назад"
    if message.text and message.text.strip().lower() == "назад":
        await message.reply("Вы вернулись на шаг выбора способа ввода тестов.", reply_markup=get_test_method_keyboard())
        await CreateTask.waiting_for_test_method.set()
        return  # Завершаем выполнение функции

    # Обработка загрузки архива
    if message.document:
        if message.document.mime_type != "application/zip":
            await message.reply("❌ Ошибка: загрузите архив в формате .zip.")
            return

        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        downloaded_file = await bot.download_file(file_path)

        # Чтение архива с входными данными
        with zipfile.ZipFile(io.BytesIO(downloaded_file.read())) as archive:
            input_files = [name for name in archive.namelist() if name.endswith(".txt")]
            if not input_files:
                await message.reply("❌ Ошибка: в архиве нет файлов .txt.")
                return

            # Сохраняем входные данные и количество тестов
            input_data = []
            for input_file in input_files:
                with archive.open(input_file) as file:
                    content = file.read().decode("utf-8")
                    input_data.append(content)

            # Количество тестов равно количеству файлов
            number_of_tests = len(input_files)

            # Сохраняем данные в состоянии
            await state.update_data(
                input_data=input_data,
                number_of_tests=number_of_tests,
                current_test=1
            )

        # Переходим к загрузке архива с выходными данными
        await message.reply("✅ Архив с входными данными успешно загружен. Теперь загрузите архив с выходными данными.")
        await CreateTask.waiting_for_output_archive.set()

    # Игнорируем любые другие текстовые сообщения, кроме "Назад"
    elif message.text:
        await message.reply("Пожалуйста, загрузите архив в формате .zip или используйте кнопку 'Назад'.")

@dp.message_handler(state=CreateTask.waiting_for_output_archive, content_types=types.ContentType.DOCUMENT)
async def handle_output_archive(message: types.Message, state: FSMContext):
    if message.document.mime_type != "application/zip":
        await message.reply("❌ Ошибка: загрузите архив в формате .zip.")
        return

    file_id = message.document.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    downloaded_file = await bot.download_file(file_path)

    # Чтение архива с выходными данными
    with zipfile.ZipFile(io.BytesIO(downloaded_file.read())) as archive:
        output_files = [name for name in archive.namelist() if name.endswith(".txt")]
        if not output_files:
            await message.reply("❌ Ошибка: в архиве нет файлов .txt.")
            return

        # Сохраняем выходные данные
        output_data = []
        for output_file in output_files:
            with archive.open(output_file) as file:
                content = file.read().decode("utf-8")
                output_data.append(content)

        await state.update_data(output_data=output_data, output_files_count=len(output_files))

    # Проверяем, что количество файлов совпадает
    data = await state.get_data()
    if data.get("input_files_count") != data.get("output_files_count"):
        await message.reply("❌ Ошибка: количество файлов во входных и выходных данных не совпадает.")
        return

    # Сохраняем тесты в базе данных
    task = Task(
        group_id=data.get("group_id"),
        name=data.get("task_name"),
        description=data.get("task_description"),
        deadline=data.get("task_deadline"),
        input_data="|".join(data.get("input_data")),  # Сохраняем входные данные как строку с разделителем
        expected_result="|".join(data.get("output_data"))  # Сохраняем выходные данные как строку с разделителем
    )
    session.add(task)
    session.commit()

    # Завершаем процесс
    await message.reply("✅ Все тесты успешно загружены и сохранены.")
    await state.finish()

@dp.message_handler(state=CreateTask.waiting_for_test_method, content_types=types.ContentTypes.TEXT)
async def set_test_method(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.reply("Вы вернулись на шаг ввода дедлайна.", reply_markup=get_back_button())
        await CreateTask.waiting_for_task_deadline.set()
        return
    elif message.text == "Ввести тесты через клавиатуру":
        # Запрашиваем количество тестов
        await message.reply("Введите количество тестов для задания:")
        await CreateTask.waiting_for_number_of_tests.set()
    elif message.text == "Загрузить тесты через архив":
        # Пропускаем запрос количества тестов и переходим к загрузке архива
        await message.reply("Загрузите архив с входными данными (формат .zip):", reply_markup=get_back_button())
        await CreateTask.waiting_for_input_archive.set()
    else:
        await message.reply("Пожалуйста, выберите один из предложенных вариантов.")

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)