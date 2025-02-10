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
import logging
import os
import random
import string
import re


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


# Состояние для выбора группы
class WatchGroup(StatesGroup):
    waiting_for_group_id = State()

# Создание таблиц базы данных
Base.metadata.create_all(bind=engine)

# Настройка Telegram-бота
API_TOKEN = "7235928823:AAHS3cfYTA3S9IlpdGub8284WPdg5shbTzE"
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class Form(StatesGroup):
    waiting_for_group_id = State()


class CreateGroup(StatesGroup):
    waiting_for_group_name = State()

""""
class CreateTask(StatesGroup):
    waiting_for_group_id = State()
    waiting_for_task_name = State()
    waiting_for_task_description = State()
    waiting_for_task_deadline = State()
    waiting_for_input_data = State()  # Новый шаг для ввода входных данных
    waiting_for_expected_result = State()  # Новый шаг для ввода ожидаемого результата
"""

class CreateTask(StatesGroup):
    waiting_for_group_id = State()
    waiting_for_task_name = State()
    waiting_for_task_description = State()
    waiting_for_task_deadline = State()  # Добавляем состояние для дедлайна
    waiting_for_input_data = State()  # Исправлено имя состояния
    waiting_for_expected_result = State()  # Исправлено имя состояния


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

# Команда /start
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
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
# Обработчик для ввода образовательной организации (для преподавателя или студента)
@dp.message_handler(state="waiting_for_educational_institution", content_types=types.ContentTypes.TEXT)
async def save_educational_institution(message: types.Message, state: FSMContext):
    educational_institution_name = message.text.strip()

    # Получаем данные о пользователе из состояния
    user_data = await state.get_data()

    # Проверяем, существует ли уже образовательная организация в базе данных
    institution = session.query(EducationalInstitution).filter_by(name=educational_institution_name).first()

    # Если образовательная организация не найдена, создаем новую
    if not institution:
        institution = EducationalInstitution(name=educational_institution_name)
        session.add(institution)
        session.commit()  # Сохраняем образовательную организацию в базе данных

    # Сохраняем ID образовательной организации в данных
    await state.update_data(educational_institution_id=institution.id)

    # Логика для студента
    role = user_data.get('role')
    if role == "student":
        # Сохраняем студента в базе данных
        user = User(
            telegram_id=str(message.from_user.id),
            full_name=user_data.get('full_name'),
            role="student",  # Студент
            region=user_data.get('region'),
            city=user_data.get('city'),
            educational_institution_id=institution.id,  # Ссылка на образовательную организацию
        )
        session.add(user)
        session.commit()  # Сохраняем студента в базе данных

        # Завершаем регистрацию
        await message.reply(f"Вы выбрали образовательную организацию: {institution.name}. Регистрация завершена! Пожалуйста, используйте команду /help для получения доступных вам команд.")
        await state.finish()
    else:
        # Логика для преподавателя
        user = User(
            telegram_id=str(message.from_user.id),
            full_name=user_data.get('full_name'),
            role="teacher",  # Преподаватель
            region=user_data.get('region'),
            city=user_data.get('city'),
            educational_institution_id=institution.id,  # Ссылка на образовательную организацию
        )
        session.add(user)
        session.commit()  # Сохраняем преподавателя в базе данных

        await message.reply(f"Вы выбрали образовательную организацию: {institution.name}. Регистрация завершена! Пожалуйста, используйте команду /help для получения доступных вам команд.")
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


# Обработчик для выбора пароля
"""
@dp.message_handler(state="waiting_for_password_choice", content_types=types.ContentTypes.TEXT)
async def process_password_choice(message: types.Message, state: FSMContext):
    password_choice = message.text.strip().lower()

    if password_choice not in ["да", "нет"]:
        await message.reply("Пожалуйста, ответьте 'да' или 'нет'.")
        return

    group_name = (await state.get_data())["group_name"]
    
    if password_choice == "нет":
        # Если без пароля, создаем группу без пароля
        new_group = Group(name=group_name, password=None)
        session.add(new_group)
        session.commit()
        await message.reply(f"Группа '{group_name}' успешно создана без пароля.")
    else:
        # Если с паролем, просим задать пароль или генерируем его
        await state.set_state("waiting_for_password")
        await message.reply(f"Введите пароль для группы '{group_name}' или отправьте 'генерировать' для автоматического пароля.")
"""

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

# Обработчик для просмотра паролей (только для преподавателя или администратора)
"""
@dp.message_handler(commands=['view_passwords'])
async def cmd_view_passwords(message: types.Message, state: FSMContext):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()

    if not user or user.role not in ["admin", "teacher"]:
        await message.reply("У вас нет прав для просмотра паролей групп.")
        return

    # Получаем список групп и их паролей
    groups = session.query(Group).all()
    response = "Пароли групп:\n"
    for group in groups:
        response += f"Группа: {group.name}, Пароль: {group.password}\n"

    await message.reply(response)
"""

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
        await message.reply("Введите входные данные для теста:", reply_markup=get_input_data_keyboard())
        await CreateTask.waiting_for_input_data.set()  # Переходим к вводу входных данных
        return

    try:
        # Пытаемся преобразовать введённую строку в формат даты
        deadline = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        await state.update_data(task_deadline=deadline)
        await message.reply("Введите входные данные для теста:", reply_markup=get_input_data_keyboard())
        await CreateTask.waiting_for_input_data.set()  # Переходим к вводу входных данных
    except ValueError:
        # Если формат неправильный, отправляем ошибку
        await message.reply("Неверный формат даты. Пожалуйста, введите дедлайн в формате YYYY-MM-DD HH:MM.")


@dp.message_handler(state=CreateTask.waiting_for_expected_result, content_types=types.ContentTypes.TEXT)
async def save_task(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.reply("Вы вернулись на шаг ввода входных данных.", reply_markup=get_back_button())
        await CreateTask.waiting_for_input_data.set()
        return

    try:
        # Получаем все данные из состояния
        data = await state.get_data()

        # Проверяем, все ли необходимые данные присутствуют
        if 'group_id' not in data or 'task_name' not in data or 'task_description' not in data:
            await message.reply("Не все данные были введены. Пожалуйста, вернитесь и заполните все поля.")
            return

        # Если входные данные нет, то присваиваем None
        input_data = data.get('input_data', None)
        expected_result = message.text.strip()  # Ожидаемый результат — это введённый текст

        task = Task(
            group_id=data["group_id"],
            name=data["task_name"],
            description=data["task_description"],
            deadline=data["task_deadline"],  # Дедлайн из состояния
            input_data=input_data,  # Входные данные, если они есть
            expected_result=expected_result  # Ожидаемый результат
        )

        session.add(task)
        session.commit()
        await message.reply(f"Задание '{task.name}' успешно создано.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Назад")))
        await state.finish()

    except ValueError:
        await message.reply("Произошла ошибка при создании задания.")


@dp.message_handler(commands=['help'])
async def help_command(message: types.Message):
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
        await message.reply("Вы вернулись на шаг ввода дедлайна.", reply_markup=get_back_button())
        await CreateTask.waiting_for_task_deadline.set()  # Возвращаемся на шаг ввода дедлайна
        return
    elif message.text == "Входных данных нет":
        await state.update_data(input_data=None)  # Если входных данных нет, сохраняем None
        await message.reply("Введите ожидаемый результат:", reply_markup=get_back_button())
        await CreateTask.waiting_for_expected_result.set()  # Переходим к вводу ожидаемого результата
        return

    # Если введены входные данные
    await state.update_data(input_data=message.text.strip())
    await message.reply("Введите ожидаемый результат:", reply_markup=get_back_button())
    await CreateTask.waiting_for_expected_result.set()  # Переходим к вводу ожидаемого результата

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

    # Запись в базу данных или другие действия с group_id
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    user.group_id = group_id
    session.commit()

    await message.reply(f"Вы успешно привязались к группе с ID: {group_id}")
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


# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
