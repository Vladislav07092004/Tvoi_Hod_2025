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
from sqlalchemy.exc import SQLAlchemyError
from guest import guest_start, process_full_name
from database import Base, session, User, EducationalInstitution, Group, Task, SupportRequest, StudentCode
from guest import GuestForm, Guest, process_region, check_guest_activity, process_city
import logging
import os
import random
import string
import re
import json
import hashlib
import zipfile
import io

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SupportRequestTeacherStatus(StatesGroup):
    waiting_for_action = State()

# Состояние для выбора группы
class WatchGroup(StatesGroup):
    waiting_for_group_id = State()



# Настройка Telegram-бота
API_TOKEN = "8066140691:AAHr6xU4te-y3D78JacGhfd_R4knwEPu_EY"
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class Form(StatesGroup):
    waiting_for_full_name = State()  # Для ввода Ф.И.О.
    waiting_for_region = State()  # Для ввода региона
    waiting_for_city = State()  # Для ввода города
    waiting_for_educational_institution = State()  # Для выбора учебного заведения
    waiting_for_task = State()  # Для выбора задания
    waiting_for_task_id = State()  # Для ввода ID задания
    waiting_for_group_id = State()  # Для ввода ID группы
    waiting_for_input_data = State()  # Для ввода входных данных
    waiting_for_student_code = State()  # Для ввода кода студента
    waiting_for_test_results = State()  # Для вывода результатов тестов
    waiting_for_file = State()  # Ожидаем загрузки файла
    waiting_for_command = State()  # Ожидаем команды для обработки файла
    waiting_for_file = State()  # Ожидаем загрузки файла
    waiting_for_action = State()

class CreateGroup(StatesGroup):
    waiting_for_group_name = State()

class CreateTask(StatesGroup):
    waiting_for_group_id = State()  # Для выбора группы
    waiting_for_task_name = State()  # Для ввода названия задания
    waiting_for_task_description = State()  # Для ввода описания задания
    waiting_for_task_deadline = State()  # Для ввода дедлайна
    waiting_for_input_data = State()  # Для ввода входных данных
    waiting_for_output_data = State()  # Для ввода выходных данных
    waiting_for_number_of_tests = State()  # Для ввода количества тестов
    waiting_for_test_input = State()  # Для ввода входных данных тестов
    waiting_for_test_method = State()  # Для выбора способа ввода тестов
    waiting_for_student_code = State()  # Для ввода кода студента
    waiting_for_expected_result = State()  # Для ввода ожидаемых результатов
    waiting_for_input_archive = State()  # Для загрузки входного архива с тестами
    waiting_for_file_action = State()  # Для выбора действия с файлом
    waiting_for_output_archive = State()  # Для загрузки выходного архива

class StudentAttempt(Base):
    __tablename__ = "student_attempts"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Ссылка на студента
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)  # Ссылка на задание
    submitted_code = Column(Text, nullable=False)  # Код студента
    input_data = Column(Text, nullable=False)  # Входные данные
    expected_result = Column(Text, nullable=False)  # Ожидаемый результат
    output_data = Column(Text, nullable=True)  # Выходные данные
    status = Column(String, nullable=False)  # Статус: "удачно", "неудачно"

    student = relationship("User")
    task = relationship("Task")


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

def format_teacher_name(full_name):
    parts = full_name.split()
    if len(parts) >= 2:
        # Берем первую букву имени и фамилию
        first_name = parts[1][0].upper()
        last_name = parts[0]
        return f"{first_name}.{last_name}"
    return "Unknown"

def create_task_directory(educational_institution, teacher_name, group_id, task_id):
    """
    Создает структуру папок для хранения файлов задания.
    Формат: Образовательная организация/Преподаватель/Группа/Задание/
    """
    base_dir = "tasks"  # Базовая папка для всех заданий
    institution_dir = educational_institution.replace(" ", "_")  # Заменяем пробелы на подчеркивания
    teacher_dir = format_teacher_name(teacher_name)
    group_dir = f"Group_{group_id}"
    task_dir = f"Task_{task_id}"

    # Полный путь к папке задания
    full_path = os.path.join(base_dir, institution_dir, teacher_dir, group_dir, task_dir)

    # Создаем папки, если они не существуют
    os.makedirs(full_path, exist_ok=True)

    return full_path

def save_file_to_task_directory(task_directory, file_name, file_content):
    file_path = os.path.join(task_directory, file_name)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path

# Команда /start
@dp.message_handler(commands=['start'], state="*")
async def start_command(message: types.Message, state: FSMContext):
    await state.finish()  # Завершаем текущее состояние пользователя, если оно есть

    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if user:
        await message.reply(f"Вы уже зарегистрированы как {user.role}.")
    else:
        # У гостей будет доступ только к этим командам
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Гость", "Студент", "Преподаватель")
        await message.reply("Добро пожаловать! Выберите вашу роль:", reply_markup=markup)

# Обработчик для выбора роли "Гость"
@dp.message_handler(lambda message: message.text == "Гость", state="*")
async def handle_guest_role(message: types.Message, state: FSMContext):
    await guest_start(message, state)

# Обработчик для ввода ФИО
@dp.message_handler(state=GuestForm.waiting_for_full_name, content_types=types.ContentTypes.TEXT)
async def handle_full_name(message: types.Message, state: FSMContext):
    await process_full_name(message, state)

# Обработчик для ввода региона
@dp.message_handler(state=GuestForm.waiting_for_region, content_types=types.ContentTypes.TEXT)
async def handle_region(message: types.Message, state: FSMContext):
    await process_region(message, state)

# Обработчик для ввода города
@dp.message_handler(state=GuestForm.waiting_for_city, content_types=types.ContentTypes.TEXT)
async def handle_city(message: types.Message, state: FSMContext):
    await process_city(message, state)

# Обработчик для проверки активности аккаунта
@dp.message_handler(lambda message: True, state="*")
async def check_activity_before_action(message: types.Message):
    # Получаем гостя по telegram_id
    guest = session.query(Guest).filter_by(telegram_id=str(message.from_user.id)).first()
    if guest:
        # Проверяем активность аккаунта
        if not check_guest_activity(guest.id):
            await message.reply("Ваш аккаунт деактивирован. С момента регистрации прошло более 12 часов.")
            return

    # Продолжаем выполнение других обработчиков
    await message.continue_propagation()

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

@dp.message_handler(state="waiting_for_region", content_types=types.ContentTypes.TEXT)
async def save_region(message: types.Message, state: FSMContext):
    region = message.text.strip()

    # Логирование для отладки
    logger.info(f"Получен регион: {region}")

    # Если регион — Москва, Санкт-Петербург или Севастополь, пропускаем ввод города
    if region in ["Москва", "Санкт-Петербург", "Севастополь", "гор. Москва", "гор. Санкт-Петербург", "гор. Севастополь", "г. Москва", "г. Санкт-Петербург", "г. Севастополь"]:
        await state.update_data(region=region)
        await state.set_state("waiting_for_educational_institution")  # Переход к следующему шагу
        await message.reply("Введите образовательную организацию:")
    else:
        # Сохраняем регион в состоянии
        await state.update_data(region=region)
        
        # Переход к следующему шагу — ввод города
        logger.info("Переход к состоянию ввода города.")
        await state.set_state("waiting_for_city")
        await message.reply("Введите ваш город:")

@dp.message_handler(state="waiting_for_city", content_types=types.ContentTypes.TEXT)
async def save_city(message: types.Message, state: FSMContext):
    city = message.text.strip()

    # Логирование для отладки
    logger.info(f"Получен город: {city}")

    # Сохраняем город в состоянии
    await state.update_data(city=city)

    # Переход к следующему шагу — ввод образовательного учреждения
    await state.set_state("waiting_for_educational_institution")
    await message.reply("Введите ваше образовательное учреждение:")

# Обработчик для ввода образовательной организации (для преподавателя или студента)
@dp.message_handler(state="waiting_for_educational_institution", content_types=types.ContentTypes.TEXT)
async def save_educational_institution(message: types.Message, state: FSMContext):
    educational_institution_name = message.text.strip()

    # Сохраняем название образовательного учреждения в состоянии
    await state.update_data(educational_institution=educational_institution_name)

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
    
    # Сохраняем название задания
    await state.update_data(task_name=message.text.strip())
    await message.reply("Введите описание задания:", reply_markup=get_back_button())
    await CreateTask.waiting_for_task_description.set()

@dp.message_handler(state=CreateTask.waiting_for_task_description, content_types=types.ContentTypes.TEXT)
async def set_task_description(message: types.Message, state: FSMContext):
    task_description = message.text.strip()

    # Получаем данные из состояния
    user_data = await state.get_data()
    group_id = user_data.get('group_id')

    # Сохраняем задание в базе данных
    new_task = Task(
        group_id=group_id,
        name=user_data.get('task_name'),
        description=task_description,
        deadline=user_data.get('task_deadline'),
        input_data=user_data.get('input_data'),
    )
    session.add(new_task)
    session.commit()

    # Обновляем состояние, чтобы сохранить task_id
    await state.update_data(task_id=new_task.id)

    await message.reply(f"Задание '{new_task.name}' успешно сохранено.")
    await CreateTask.waiting_for_task_deadline.set()  # Переход к вводу входных данных
    await message.reply("Укажите дедлайн или НЕТ ДЕДЛАЙНА:")

@dp.message_handler(state=CreateTask.waiting_for_task_deadline, content_types=types.ContentTypes.TEXT)
async def set_task_deadline(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.reply("Вы вернулись на шаг ввода описания задания.", reply_markup=get_back_button())
        await CreateTask.waiting_for_task_description.set()
        return
    elif message.text == "НЕТ ДЕДЛАЙНА":
        # Устанавливаем дедлайн как None
        await state.update_data(task_deadline=None)
        await message.reply("Задание будет без дедлайна. Теперь введите входные данные.")
    else:
        try:
            # Пытаемся преобразовать введённую строку в формат даты
            deadline = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
            await state.update_data(task_deadline=deadline)
            await message.reply("Дедлайн установлен. Теперь введите входные данные.")
        except ValueError:
            # Если формат неправильный, отправляем ошибку
            await message.reply("Неверный формат даты. Пожалуйста, введите дедлайн в формате YYYY-MM-DD HH:MM.")
            return

    # Переход к вводу входных данных
    await CreateTask.waiting_for_input_data.set()



@dp.message_handler(commands=['help_student'])
async def help_student(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if not user or user.role != "student":
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return

    help_text = """
📚 **Список доступных команд для студентов:**

- `/view_tasks` — просмотреть задания своей группы.
- `/task_status` — узнать статус выполнения заданий.
- `/task_deadline` — посмотреть дедлайн для заданий.
- `/task_requirements` — получить требования для выполнения задания.
- `/my_group` — информация о вашей группе.
- `/submit` — отправить решение задания.
- `/link_group` — привязаться к группе (введите ID группы).

ℹ️ Если у вас возникли вопросы или проблемы, обратитесь к администратору.
    """
    await message.reply(help_text, parse_mode="Markdown")

@dp.message_handler(commands=['help_teacher'])
async def help_teacher(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if not user or user.role != "teacher":
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return

    help_text = """
📚 **Список доступных команд для преподавателей:**

- `/create_group` — создать новую группу.
- `/create_task` — создать задание для группы.
- `/watchgroup` — посмотреть участников группы.
- `/report` — получить отчёт о прогрессе учеников.
- `/view_tasks` — просмотреть задания своей группы.

ℹ️ Если у вас возникли вопросы или проблемы, обратитесь к администратору.
    """
    await message.reply(help_text, parse_mode="Markdown")


@dp.message_handler(commands=['help_support'])
async def help_support(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return

    help_text = """
🛠 **Панель техподдержки:**

👥 **Управление пользователями:**
- `/list_users` — показать всех пользователей.
- `/find_user <ID или имя>` — найти пользователя.
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
- `/help_support` — показать этот список команд.

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

@dp.message_handler(commands=['help'], state="*")  # state="*" обрабатывает команду /help в любом состоянии
async def help_command(message: types.Message, state: FSMContext):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if not user:
        await message.reply("❌ Вы не зарегистрированы в системе. Пожалуйста, завершите регистрацию.")
        return

    if user.role == "student":
        help_text = """
📚 **Список доступных команд для студентов:**

- `/start` — начать работу с ботом.
- `/view_tasks` — просмотреть задания своей группы.
- `/task_status` — узнать статус выполнения заданий.
- `/task_deadline` — посмотреть дедлайн для заданий.
- `/task_requirements` — получить требования для выполнения задания.
- `/my_group` — информация о вашей группе.
- `/submit` — отправить решение задания.
- `/link_group` — привязаться к группе (введите ID группы).
- `/help` — показать этот список команд.

ℹ️ Если у вас возникли вопросы или проблемы, обратитесь к преподавателю или техподдержке.
        """
        await message.reply(help_text, parse_mode="Markdown")
    
    elif user.role == "teacher":
        help_text = """
📚 **Список доступных команд для преподавателей:**

- `/start` — начать работу с ботом.
- `/create_group` — создать новую группу.
- `/create_task` — создать задание для группы.
- `/view_group` — посмотреть участников и задания группы.
- `/view_tasks` — просмотреть задания своей группы.
- `/view_student_codes` — просмотреть решения студентов.
- `/report` — получить отчёт о прогрессе учеников.
- `/help` — показать этот список команд.

ℹ️ Если у вас возникли вопросы или проблемы, обратитесь к техподдержке.
        """
        await message.reply(help_text, parse_mode="Markdown")
    
    elif user.role == "support":
        help_text = """
🛠 **Панель техподдержки:**

👥 **Управление пользователями:**
- `/list_users` — показать всех пользователей.
- `/find_user <ID или имя>` — найти пользователя.
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
- `/help` — показать этот список команд.

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
    
    else:
        await message.reply("❌ Роль пользователя не определена.")

@dp.message_handler(commands=['watchgroup'])
async def watch_group(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "teacher":
        await message.reply("Эта команда доступна только для преподавателей.")
        return

    # Получаем все группы, созданные преподавателем
    groups = session.query(Group).filter_by(teacher_id=user.id).all()
    if not groups:
        await message.reply("Вы ещё не создали ни одной группы. Используйте /create_group, чтобы создать группу.")
        return

    # Отправляем список групп преподавателю
    group_list = "\n".join([f"{group.id}: {group.name}" for group in groups])
    await message.reply(f"Выберите ID группы, чтобы посмотреть её участников:\n{group_list}")
    await WatchGroup.waiting_for_group_id.set()

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
            member_list = "\n".join([f"- {member.full_name} (ID: {member.id})" for member in members])
            await message.reply(f"Участники группы '{group.name}':\n{member_list}")

    except ValueError:
        await message.reply("Пожалуйста, введите корректный ID группы (число).")
    finally:
        # Завершаем состояние
        await state.finish()

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

# Обработчик для ввода входных данных
@dp.message_handler(state=CreateTask.waiting_for_input_data, content_types=types.ContentTypes.TEXT)
async def save_input_data(message: types.Message, state: FSMContext):
    input_data = message.text.strip()

    # Сохраняем входные данные в состояние
    await state.update_data(input_data=input_data)

    # Получаем данные из состояния
    user_data = await state.get_data()
    task_id = user_data.get("task_id")  # Получаем ID задания из состояния

    # Находим задание в базе данных
    task = session.query(Task).filter(Task.id == task_id).first()

    if task:
        task.input_data = input_data  # Сохраняем входные данные
        session.commit()  # Сохраняем изменения в базе данных
        await message.reply(f"Входные данные для задания '{task.name}' успешно сохранены.")
    else:
        await message.reply("Ошибка: задание не найдено в базе данных.")

    # Переход к следующему шагу для ввода выходных данных
    await CreateTask.waiting_for_output_data.set()
    await message.reply("Теперь введите выходные данные для задания.")

# Обработчик для ввода выходных данных
@dp.message_handler(state=CreateTask.waiting_for_output_data, content_types=types.ContentTypes.TEXT)
async def save_output_data(message: types.Message, state: FSMContext):
    output_data = message.text.strip()

    # Получаем task_id из состояния
    user_data = await state.get_data()
    task_id = user_data.get("task_id")

    # Находим задание в базе данных
    task = session.query(Task).filter(Task.id == task_id).first()
    if task:
        task.output_data = output_data  # Сохраняем выходные данные
        session.commit()
        await message.reply(f"Выходные данные для задания '{task.name}' успешно сохранены.")
    else:
        await message.reply("Ошибка: задание не найдено в базе данных.")

    await state.finish()  # Завершаем процесс

# Студентские команды

# Просмотр всех заданий для группы
@dp.message_handler(commands=['view_tasks'], state="*")
async def view_tasks(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    
    if user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return
    
    # Получаем все задания для студента
    tasks = session.query(Task).filter_by(group_id=user.group_id).all()
    if not tasks:
        await message.reply("Нет доступных заданий.")
        return
    
    task_list = "\n".join([f"{task.id}: {task.name}" for task in tasks])
    await message.reply(f"Выберите задание из списка:\n{task_list}")
    await Form.waiting_for_task.set()  # Переход к следующему состоянию


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
@dp.message_handler(commands=['submit'], state="*")
async def submit_solution(message: types.Message, state: FSMContext):
    # Запросить ID задания от студента
    await message.reply("Введите ID задания, к которому хотите прикрепить ваше решение:")
    # Переход к следующему состоянию для ввода ID задания
    await Form.waiting_for_task_id.set()

@dp.message_handler(state=Form.waiting_for_task_id, content_types=types.ContentTypes.TEXT)
async def process_task_id(message: types.Message, state: FSMContext):
    task_id = message.text.strip()

    # Логируем полученный ID
    logger.info(f"Получен ID задания: {task_id}")

    # Преобразуем task_id в целое число (если это необходимо)
    try:
        task_id = int(task_id)  # Если task_id является числом
        logger.info(f"ID задания после преобразования в число: {task_id}")
    except ValueError:
        await message.reply("Ошибка: Неверный формат ID задания. Пожалуйста, введите число.")
        return

    # Ищем задание по ID
    logger.info(f"Запрос к базе данных для поиска задания с ID: {task_id}")
    task = session.query(Task).filter(Task.id == task_id).first()

    # Логируем результат запроса
    if task:
        logger.info(f"Задание найдено: {task.name}")
    else:
        logger.error(f"Задание с ID {task_id} не найдено в базе данных.")

    # Если задание не найдено, сообщаем об этом
    if not task:
        await message.reply("Ошибка: Задание не найдено.")
        return

    # Сохраняем task_id в состоянии
    await state.update_data(task_id=task_id)

    # Переход к следующему шагу — ввод кода студента
    await message.reply(f"Вы выбрали задание: {task.name}. Теперь, пожалуйста, отправьте ваш код для выполнения задания.")
    await Form.waiting_for_student_code.set()



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
        await message.reply("❌ Вы не зарегистрированы в системе. Пожалуйста, завершите регистрацию.")
        return

    # Проверяем, что пользователь — студент
    if user.role != "student":
        await message.reply("❌ Эта команда доступна только для студентов.")
        return

    # Проверяем, что студент еще не привязан к группе
    if user.group_id:
        await message.reply(f"❌ Вы уже привязаны к группе с ID {user.group_id}.")
        return

    # Запрашиваем ID группы
    await message.reply("Введите ID группы, к которой вы хотите привязаться:")
    await Form.waiting_for_group_id.set()

@dp.message_handler(state=Form.waiting_for_group_id)
async def get_group_id(message: types.Message, state: FSMContext):
    group_id = message.text.strip()
    
    # Проверка на существование группы
    group = session.query(Group).filter_by(id=group_id).first()
    if not group:
        await message.reply("Группа с таким ID не найдена. Пожалуйста, попробуйте снова.")
        return
    
    # Сохраняем группу в состоянии
    await state.update_data(group_id=group.id)

    # Переход к следующему шагу
    await message.reply(f"Вы выбрали группу {group.name}. Теперь выберите задание.")
    await Form.waiting_for_task_name.set()  # Переход к следующему состоянию


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
    number_of_tests = message.text.strip()

    # Проверка на корректность ввода
    try:
        number_of_tests = int(number_of_tests)
        if number_of_tests <= 0:
            await message.reply("Количество тестов должно быть больше 0.")
            return
    except ValueError:
        await message.reply("Пожалуйста, введите корректное число.")
        return

    # Сохраняем количество тестов в состояние
    await state.update_data(number_of_tests=number_of_tests, current_test=1)

    # Переход к следующему шагу (ввод входных данных для первого теста)
    await message.reply(f"Количество тестов установлено: {number_of_tests}. Введите входные данные для теста 1:")
    await CreateTask.waiting_for_test_input.set()  # Переход к состоянию для ввода входных данных


@dp.message_handler(state=CreateTask.waiting_for_test_input, content_types=types.ContentTypes.TEXT)
async def set_test_input(message: types.Message, state: FSMContext):
    test_input = message.text.strip()

    # Сохраняем входные данные для теста
    user_data = await state.get_data()
    test_number = user_data.get("current_test", 1)  # Текущий номер теста
    
    if "test_inputs" not in user_data:
        user_data["test_inputs"] = []
    
    # Добавляем входные данные в список
    user_data["test_inputs"].append(test_input)
    await state.update_data(test_inputs=user_data["test_inputs"])

    # Проверка, все ли тесты введены
    number_of_tests = user_data.get("number_of_tests", 1)
    if test_number < number_of_tests:
        await state.update_data(current_test=test_number + 1)
        await message.reply(f"Введите входные данные для теста {test_number + 1}:")
        await CreateTask.waiting_for_test_input.set()
    else:
        # Все тесты введены, переходим к следующему шагу
        await message.reply("Все входные данные для тестов успешно добавлены.")
        await CreateTask.waiting_for_expected_result.set()  # Переход к следующему состоянию

@dp.message_handler(state=CreateTask.waiting_for_expected_result, content_types=types.ContentTypes.TEXT)
async def set_expected_result(message: types.Message, state: FSMContext):
    expected_result = message.text.strip()

    # Получаем данные о задании из состояния
    user_data = await state.get_data()
    task_id = user_data.get("task_id")

    # Получаем задание по task_id
    task = session.query(Task).filter_by(id=task_id).first()
    
    if not task:
        await message.reply("Ошибка: задание не найдено.")
        return

    # Обновляем задание, добавляем ожидаемый результат
    task.expected_result = expected_result
    session.commit()

    # Подтверждаем сохранение
    await message.reply(f"Ожидаемый результат для задания '{task.name}' успешно сохранен.")
    
    # Завершаем создание задания
    await state.finish()


@dp.message_handler(state=CreateTask.waiting_for_input_archive, content_types=[types.ContentType.DOCUMENT, types.ContentType.TEXT])
async def handle_input_archive(message: types.Message, state: FSMContext):
    if message.document:
        # Получаем файл
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        downloaded_file = await bot.download_file(file_path)

        # Сохраняем файл
        file_name = message.document.file_name
        file_path_to_save = f"downloads/{file_name}"
        
        # Сохраняем файл на диск
        with open(file_path_to_save, "wb") as f:
            f.write(downloaded_file.read())

        await message.reply(f"Файл {file_name} успешно загружен.")
        
        # Переход к следующему шагу для выбора действия с файлом
        await message.reply("Что вы хотите делать с загруженным файлом? Выберите действие:")
        await CreateTask.waiting_for_file_action.set()  # Переход к состоянию для выбора действия
    else:
        await message.reply("Пожалуйста, загрузите архив с входными данными.")

@dp.message_handler(state=CreateTask.waiting_for_file_action, content_types=types.ContentTypes.TEXT)
async def handle_file_action(message: types.Message, state: FSMContext):
    action = message.text.strip()

    if action == "Считать данные из файла":
        # Обработка файла и считывание данных
        await message.reply("Теперь считываем данные из файла...")
        await CreateTask.waiting_for_input_data.set()  # Переход к следующему шагу для ввода данных
    elif action == "Сохранить файл на диск":
        # Сохранение файла на диск
        await message.reply("Файл сохранен на диск. Переход к следующему шагу.")
        await CreateTask.waiting_for_output_data.set()  # Переход к следующему шагу для ввода выходных данных
    else:
        await message.reply("Пожалуйста, выберите одно из предложенных действий: 'Считать данные из файла' или 'Сохранить файл на диск'.")

@dp.message_handler(state=CreateTask.waiting_for_output_archive, content_types=types.ContentType.DOCUMENT)
async def handle_output_archive(message: types.Message, state: FSMContext):
    if message.document:
        # Получаем файл
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        downloaded_file = await bot.download_file(file_path)

        # Сохраняем файл
        file_name = message.document.file_name
        file_path_to_save = f"downloads/{file_name}"
        
        # Сохраняем файл на диск
        with open(file_path_to_save, "wb") as f:
            f.write(downloaded_file.read())

        await message.reply(f"Выходной файл {file_name} успешно загружен.")
        
        # Переход к следующему шагу (например, завершение создания задания)
        await message.reply("Задание успешно создано!")
        await state.finish()  # Завершаем процесс
    else:
        await message.reply("Пожалуйста, загрузите выходной архив.")

@dp.message_handler(state=CreateTask.waiting_for_input_archive, content_types=[types.ContentType.DOCUMENT])
async def handle_input_archive(message: types.Message, state: FSMContext):
    if message.document:
        # Получаем файл
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        downloaded_file = await bot.download_file(file_path)

        # Сохраняем файл
        file_name = message.document.file_name
        file_path_to_save = f"downloads/{file_name}"
        
        # Сохраняем файл на диск
        with open(file_path_to_save, "wb") as f:
            f.write(downloaded_file.read())

        await message.reply(f"Файл {file_name} успешно загружен.")
        
        # Переход к следующему шагу для выбора действия с файлом
        await message.reply("Что вы хотите делать с загруженным файлом? Выберите действие:")
        await CreateTask.waiting_for_file_action.set()  # Переход к состоянию для выбора действия
    else:
        await message.reply("Пожалуйста, загрузите архив с входными данными.")



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

@dp.message_handler(commands=['view_teacher_requests'])
async def view_teacher_requests(message: types.Message):
    # Проверяем, что пользователь является техподдержкой
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для просмотра заявок на статус преподавателя.")
        return

    # Получаем все заявки на статус преподавателя
    teacher_requests = session.query(User).filter_by(role="pending_teacher").all()

    if not teacher_requests:
        await message.reply("📌 Нет заявок на статус преподавателя.")
        return

    # Формируем список заявок
    request_list = "\n".join([f"🆔 **ID:** {r.id} | 👤 **{r.full_name}** | 🏫 {r.educational_institution.name}" for r in teacher_requests])

    await message.reply(f"📋 **Заявки на статус преподавателя:**\n\n{request_list}")

@dp.message_handler(commands=['approve_teacher_request'])
async def approve_teacher_request(message: types.Message):
    # Проверяем, что пользователь является техподдержкой
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для подтверждения заявок.")
        return

    # Получаем ID преподавателя из команды
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("📌 Использование: `/approve_teacher_request <ID преподавателя>`")
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
    await bot.send_message(teacher.telegram_id, "✅ Ваша заявка на статус преподавателя подтверждена!")

    # Уведомляем техподдержку
    await message.reply(f"✅ Преподаватель {teacher.full_name} успешно подтвержден.")

@dp.message_handler(commands=['reject_teacher_request'])
async def reject_teacher_request(message: types.Message):
    # Проверяем, что пользователь является техподдержкой
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "support":
        await message.reply("❌ У вас нет прав для отклонения заявок.")
        return

    # Получаем ID преподавателя из команды
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("📌 Использование: `/reject_teacher_request <ID преподавателя>`")
        return

    teacher_id = args[1]
    teacher = session.query(User).filter_by(id=teacher_id, role="pending_teacher").first()

    if not teacher:
        await message.reply("❌ Преподаватель с таким ID не найден или уже подтвержден.")
        return

    # Удаляем пользователя
    session.delete(teacher)
    session.commit()

    # Уведомляем преподавателя
    await bot.send_message(teacher.telegram_id, "❌ Ваша заявка на статус преподавателя отклонена.")

    # Уведомляем техподдержку
    await message.reply(f"❌ Преподаватель {teacher.full_name} отклонен.")

@dp.message_handler(state=Form.waiting_for_input_data, content_types=types.ContentTypes.TEXT)
async def input_data(message: types.Message, state: FSMContext):
    input_data = message.text.strip()
    
    # Сохраняем входные данные
    await state.update_data(input_data=input_data)
    
    # Переход к следующему шагу для ввода кода
    await message.reply("Теперь введите свой код для выполнения задания:")
    await Form.waiting_for_student_code.set()  # Переход к состоянию для ввода кода студента

# Функция для получения входных и выходных данных для задачи
def get_task_data(task_id: int):
    # Получаем задание по ID из базы данных
    task = session.query(Task).filter(Task.id == task_id).first()

    if not task:
        return None, None

    # Получаем входные данные и ожидаемый результат
    input_data = task.input_data  # входные данные
    expected_result = task.expected_result  # ожидаемый результат

    # Проверяем, что входные данные и результат существуют
    if not input_data or not expected_result:
        logger.error(f"Для задания {task_id} отсутствуют входные данные или ожидаемый результат.")
        return None, None

    return input_data, expected_result

@dp.message_handler(state=Form.waiting_for_group_id, content_types=types.ContentTypes.TEXT)
async def handle_group_id(message: types.Message, state: FSMContext):
    group_id = message.text.strip()

    # Проверяем, что введенный ID группы — число
    if not group_id.isdigit():
        await message.reply("❌ ID группы должен быть числом. Попробуйте снова.")
        return

    group_id = int(group_id)

    # Проверяем, существует ли группа с таким ID
    group = session.query(Group).filter_by(id=group_id).first()
    if not group:
        await message.reply("❌ Группа с таким ID не найдена. Пожалуйста, проверьте ID и попробуйте снова.")
        return

    # Получаем пользователя
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return

    # Привязываем студента к группе
    try:
        user.group_id = group_id
        session.commit()  # Сохраняем изменения в базе данных
        await message.reply(f"✅ Вы успешно привязаны к группе '{group.name}' (ID: {group.id}).")
    except Exception as e:
        session.rollback()  # Откатываем изменения в случае ошибки
        logger.error(f"Ошибка при сохранении данных: {e}")
        await message.reply("❌ Произошла ошибка при привязке к группе. Попробуйте снова.")

    # Завершаем состояние
    await state.finish()

@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_python_file(message: types.Message):
    logger.info(f"Получен файл: {message.document.file_name}")

    # Проверка MIME типа файла
    if message.document.mime_type == "application/x-python-code":
        # Получаем file_id и скачиваем файл
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        downloaded_file = await bot.download_file(file_path)

        # Проверяем папку для сохранения
        download_folder = "downloads"
        if not os.path.exists(download_folder):
            os.makedirs(download_folder)  # Создаем папку, если ее нет

        # Сохраняем файл
        file_name = message.document.file_name
        file_path_to_save = os.path.join(download_folder, file_name)
        with open(file_path_to_save, "wb") as f:
            f.write(downloaded_file.read())

        logger.info(f"Файл сохранен по пути: {file_path_to_save}")

        # Попытка выполнения кода из файла
        try:
            with open(file_path_to_save, "r") as f:
                code = f.read()
                logger.info(f"Исполняем следующий код:\n{code}")
                exec(code)  # Запуск кода (предупреждение: это небезопасно)
            
            await message.reply("Файл был успешно выполнен!")
        except Exception as e:
            logger.error(f"Ошибка при выполнении кода: {e}")
            await message.reply(f"Произошла ошибка при выполнении кода: {e}")
    else:
        await message.reply("Пожалуйста, загрузите файл Python с расширением `.py`.")

async def run_tests(message: types.Message, task_id: int, student_code: str):
    # Логируем получение ID задания
    logger.info(f"Получен ID задания: {task_id}")

    # Выполним простой запрос к базе данных для поиска задания по task_id
    task = session.query(Task).filter_by(id=task_id).first()

    if not task:
        logger.error(f"Задание с ID {task_id} не найдено в базе данных.")
        await message.reply("Ошибка: Задание не найдено.")
        return

    # Логируем, если задание найдено
    logger.info(f"Задание найдено: {task.name}")

    # Получаем входные данные и ожидаемый результат для задания
    input_data, expected_result = get_task_data(task_id)

    # Логируем входные данные и результат
    logger.info(f"Входные данные: {input_data}")
    logger.info(f"Ожидаемый результат: {expected_result}")

    if not input_data or not expected_result:
        await message.reply("Ошибка: Задание не найдено или отсутствуют входные данные.")
        return

    try:
        # Логируем код студента
        logger.info(f"Код студента:\n{student_code}")

        # Преобразуем входные данные в список строк
        input_data_lines = input_data.splitlines()  # Разделяем строки входных данных

        # Подготовка переменных для выполнения кода
        local_vars = {
            "input_data": input_data_lines,  # Список строк для симуляции ввода
            "output_data": None  # Переменная для результата
        }

        # Функция для имитации ввода (взамен встроенной input())
        def mock_input():
            if local_vars["input_data"]:
                return local_vars["input_data"].pop(0)  # Возвращаем первый элемент и удаляем его
            return ''  # Если данных больше нет, возвращаем пустую строку

        # Используем mock_input в качестве функции input()
        original_input = __builtins__.input  # Сохраняем оригинальную функцию input()
        __builtins__.input = mock_input  # Подменяем input() на mock_input

        # Попробуем выполнить код студента
        exec(student_code, {}, local_vars)  # Запуск кода студента

        # Получаем результат из переменной, которую использует студент
        result = local_vars.get("output_data")

        if result is None:
            await message.reply("Ошибка: Студент должен сохранить результат в переменную 'output_data'.")
            return

        # Логируем результат
        logger.info(f"Полученный результат: {result}")

        # Убираем пробелы и символы новой строки перед сравнением
        if str(result).strip() == str(expected_result).strip():
            await message.reply("Поздравляем! Ваш код прошел все тесты.")
        else:
            await message.reply(f"Ваш код не прошел тесты. Ожидаемый результат: {expected_result}. Ваш результат: {result}")

    except SyntaxError as e:
        # Ловим синтаксическую ошибку в коде
        await message.reply(f"Ошибка синтаксиса в коде: {e.msg}. Пожалуйста, исправьте код и попробуйте снова.")
    except Exception as e:
        # Ловим другие ошибки при выполнении кода
        await message.reply(f"Произошла ошибка при выполнении кода: {e}")
    finally:
        # Восстановим оригинальную функцию input() после выполнения кода
        __builtins__.input = original_input

def check_syntax(student_code: str) -> bool:
    try:
        compile(student_code, "<string>", "exec")
        return True  # Код компилируется без ошибок
    except SyntaxError as e:
        return False  # Возникла ошибка синтаксиса

def check_syntax(student_code: str) -> bool:
    try:
        compile(student_code, "<string>", "exec")
        return True  # Код компилируется без ошибок
    except SyntaxError as e:
        return False  # Возникла ошибка синтаксиса

@dp.message_handler(state=Form.waiting_for_student_code, content_types=types.ContentTypes.TEXT)
async def get_student_code(message: types.Message, state: FSMContext):
    student_code = message.text.strip()

    # Проверяем, что синтаксис кода верен
    if not is_valid_python_code(student_code):
        await message.reply("Ошибка синтаксиса в коде. Пожалуйста, исправьте и попробуйте снова.")
        return

    # Получаем task_id из состояния
    user_data = await state.get_data()
    task_id = user_data.get("task_id")

    if not task_id:
        await message.reply("Ошибка: не найдено задание. Пожалуйста, попробуйте снова.")
        return

    # Сохраняем код студента в базе данных
    student_code_entry = StudentCode(student_id=message.from_user.id, task_id=task_id, submitted_code=student_code)
    session.add(student_code_entry)
    session.commit()

    # Переход к выполнению тестов
    await message.reply("Ваш код сохранен. Запускаем тесты...")
    await run_tests(message, task_id, student_code)


def run_code_in_safe_env(student_code: str):
    try:
        compiled_code = compile(student_code, "<string>", "exec")
        exec(compiled_code, {}, {})
    except SyntaxError as e:
        return f"Ошибка синтаксиса: {e.msg} на строке {e.lineno}"
    except Exception as e:
        return f"Ошибка при выполнении кода: {e}"
    return "Код выполнен успешно!"

def is_valid_python_code(code: str) -> bool:
    try:
        compile(code, "<string>", "exec")  # Проверка синтаксиса без выполнения кода
        return True
    except SyntaxError:
        return False

# Папка для сохранения файлов
DOWNLOADS_FOLDER = "downloads"

@dp.message_handler(content_types=types.ContentType.DOCUMENT, state=Form.waiting_for_file)
async def handle_python_file(message: types.Message, state: FSMContext):
    # Проверка MIME типа файла
    if message.document.mime_type != "application/x-python-code":
        await message.reply("Пожалуйста, загрузите файл Python с расширением `.py`.")
        return

    # Получаем file_id и скачиваем файл
    file_id = message.document.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    downloaded_file = await bot.download_file(file_path)

    # Проверка папки для сохранения
    if not os.path.exists(DOWNLOADS_FOLDER):
        os.makedirs(DOWNLOADS_FOLDER)  # Создаем папку, если её нет

    # Сохраняем файл
    file_name = message.document.file_name
    file_path_to_save = os.path.join(DOWNLOADS_FOLDER, file_name)
    with open(file_path_to_save, "wb") as f:
        f.write(downloaded_file.read())

    logger.info(f"Файл сохранен: {file_path_to_save}")

    # Сохраняем путь к файлу в состоянии
    await state.update_data(file_path=file_path_to_save)

    # Просим пользователя ввести команду
    await message.reply("Файл загружен. Введите команду для продолжения (например, /execute для выполнения файла).")
    await Form.waiting_for_command.set()

@dp.message_handler(commands=['execute'], state=Form.waiting_for_command)
async def execute_code(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    file_path = user_data.get("file_path")

    if not file_path:
        await message.reply("Ошибка: не найден файл для выполнения.")
        return

    try:
        # Открываем файл и выполняем его код
        with open(file_path, "r") as f:
            code = f.read()
            exec(code)  # Важно: exec() может быть опасным, используйте с осторожностью

        await message.reply("Файл был успешно выполнен!")
    except Exception as e:
        logger.error(f"Ошибка при выполнении кода: {e}")
        await message.reply(f"Произошла ошибка при выполнении кода: {e}")

    # После выполнения кода возвращаем пользователя в начальное состояние
    await state.finish()

@dp.message_handler(commands=['view_student_codes'])
async def view_student_codes(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "teacher":
        await message.reply("Эта команда доступна только для преподавателей.")
        return

    # Получаем все задания для преподавателя
    tasks = session.query(Task).filter_by(group_id=user.group_id).all()
    if not tasks:
        await message.reply("У вашей группы нет заданий.")
        return

    # Формируем список заданий
    task_list = "\n".join([f"{task.id}: {task.name}" for task in tasks])
    await message.reply(f"Выберите задание для просмотра попыток сдачи:\n{task_list}")
    await Form.waiting_for_task_id.set()

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_accept_rework_buttons(code_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    accept_button = InlineKeyboardButton("Принять", callback_data=f"accept_code_{code_id}")
    rework_button = InlineKeyboardButton("Отправить на доработку", callback_data=f"rework_code_{code_id}")
    keyboard.add(accept_button, rework_button)
    return keyboard

@dp.message_handler(state=Form.waiting_for_action)
async def handle_code_action(message: types.Message, state: FSMContext):
    # Now 'state' is correctly recognized
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "teacher":
        await message.reply("Эта команда доступна только для преподавателей.")
        return

    # Get data stored in the state
    user_data = await state.get_data()  # This works as 'state' is passed correctly
    task_id = user_data.get('task_id')

    if not task_id:
        await message.reply("Ошибка: не найдено задание. Попробуйте снова.")
        return

    # Retrieve all student code submissions for the given task
    student_codes = session.query(StudentCode).filter_by(task_id=task_id).all()
    if not student_codes:
        await message.reply(f"Нет попыток сдачи для задания с ID {task_id}.")
        return

    # Iterate through the student submissions and send the code with buttons
    for code in student_codes:
        # If you need to send large codes, you might want to limit the length for display
        code_preview = code.submitted_code[:50]  # Display only the first 50 characters for brevity

        # Sending the code with "Accept" and "Rework" buttons
        await message.reply(
            f"Код студента {code.student_id}:\n{code_preview}...",
            reply_markup=get_accept_rework_buttons(code.id)
        )


@dp.callback_query_handler(lambda c: c.data.startswith("accept_code_"))
async def accept_code(callback_query: types.CallbackQuery):
    code_id = int(callback_query.data.split("_")[2])

    # Обновляем статус кода на "accepted"
    student_code = session.query(StudentCode).filter_by(id=code_id).first()
    if student_code:
        student_code.status = "accepted"
        session.commit()
        await callback_query.answer(f"Код принят. Статус: {student_code.status}")
    else:
        await callback_query.answer("Ошибка: код не найден.")

@dp.callback_query_handler(lambda c: c.data.startswith("rework_code_"))
async def rework_code(callback_query: types.CallbackQuery):
    code_id = int(callback_query.data.split("_")[2])

    # Обновляем статус кода на "rework"
    student_code = session.query(StudentCode).filter_by(id=code_id).first()
    if student_code:
        student_code.status = "rework"
        session.commit()
        await callback_query.answer(f"Код отправлен на доработку. Статус: {student_code.status}")
    else:
        await callback_query.answer("Ошибка: код не найден.")

@dp.message_handler(commands=['view_group_tasks'])
async def view_group_tasks(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "teacher":
        await message.reply("Эта команда доступна только для преподавателей.")
        return

    # Получаем все группы, созданные преподавателем
    groups = session.query(Group).filter_by(teacher_id=user.id).all()
    if not groups:
        await message.reply("Вы ещё не создали ни одной группы. Используйте /create_group, чтобы создать группу.")
        return

    # Отправляем список групп преподавателю
    group_list = "\n".join([f"{group.id}: {group.name}" for group in groups])
    await message.reply(f"Выберите ID группы, чтобы посмотреть её задания:\n{group_list}")
    await WatchGroup.waiting_for_group_id.set()

@dp.message_handler(state=WatchGroup.waiting_for_group_id, content_types=types.ContentTypes.TEXT)
async def show_group_tasks(message: types.Message, state: FSMContext):
    try:
        group_id = int(message.text.strip())
        group = session.query(Group).filter_by(id=group_id).first()

        if not group:
            await message.reply("Группа с таким ID не найдена. Попробуйте ещё раз.")
            return

        # Получаем все задания для выбранной группы
        tasks = session.query(Task).filter_by(group_id=group.id).all()
        if not tasks:
            await message.reply(f"В группе '{group.name}' пока нет заданий.")
        else:
            task_list = "\n".join([f"{task.id}: {task.name}" for task in tasks])
            await message.reply(f"Задания для группы '{group.name}':\n{task_list}")

    except ValueError:
        await message.reply("Пожалуйста, введите корректный ID группы (число).")
    finally:
        # Завершаем состояние
        await state.finish()


# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)