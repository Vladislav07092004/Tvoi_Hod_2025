from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import logging
import os
logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# Настройка базы данных SQLite
DATABASE_URL = "sqlite:///database.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()

# Определение таблиц базы данных
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    full_name = Column(String)
    role = Column(String)  # "student" или "teacher"
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    password = Column(String)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    name = Column(String)
    description = Column(Text)
    deadline = Column(DateTime)

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

class CreateGroup(StatesGroup):
    waiting_for_group_name = State()

class CreateTask(StatesGroup):
    waiting_for_group_id = State()
    waiting_for_task_name = State()
    waiting_for_task_description = State()
    waiting_for_task_deadline = State()

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
@dp.message_handler(lambda message: message.text in ["Студент", "Преподаватель"])
async def register_user(message: types.Message):
    role = "student" if message.text == "Студент" else "teacher"
    user = User(telegram_id=str(message.from_user.id), full_name=message.from_user.full_name, role=role)
    session.add(user)
    session.commit()
    if role == "teacher":
        await message.reply("Вы зарегистрированы как преподаватель! Используйте /create_group для создания группы.")
    else:
        await message.reply("Вы зарегистрированы как студент! Введите пароль вашей группы:")

# Создание группы
@dp.message_handler(commands=['create_group'])
async def create_group(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "teacher":
        await message.reply("Эта команда доступна только для преподавателей.")
        return
    await message.reply("Введите название группы:")
    await CreateGroup.waiting_for_group_name.set()

@dp.message_handler(state=CreateGroup.waiting_for_group_name, content_types=types.ContentTypes.TEXT)
async def save_group_name(message: types.Message, state: FSMContext):
    group_name = message.text.strip()
    password = os.urandom(4).hex()
    group = Group(name=group_name, password=password)
    session.add(group)
    session.commit()
    await message.reply(f"Группа '{group_name}' создана. Пароль для учеников: {password}")
    await state.finish()

# Присоединение ученика к группе
@dp.message_handler(lambda message: not message.text.startswith("Группа: ") and len(message.text) == 8)
async def join_group(message: types.Message):
    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
    if not user or user.role != "student":
        await message.reply("Эта команда доступна только для студентов.")
        return
    group = session.query(Group).filter_by(password=message.text).first()
    if group:
        user.group_id = group.id
        session.commit()
        await message.reply(f"Вы присоединились к группе '{group.name}'.")
    else:
        await message.reply("Неверный пароль группы.")

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
    group_id = int(message.text)
    group = session.query(Group).filter_by(id=group_id).first()
    if not group:
        await message.reply("Группа с таким ID не найдена. Попробуйте ещё раз.")
        return
    await state.update_data(group_id=group_id)
    await message.reply("Введите название задания:")
    await CreateTask.waiting_for_task_name.set()

@dp.message_handler(state=CreateTask.waiting_for_task_name, content_types=types.ContentTypes.TEXT)
async def set_task_name(message: types.Message, state: FSMContext):
    await state.update_data(task_name=message.text.strip())
    await message.reply("Введите описание задания:")
    await CreateTask.waiting_for_task_description.set()

@dp.message_handler(state=CreateTask.waiting_for_task_description, content_types=types.ContentTypes.TEXT)
async def set_task_description(message: types.Message, state: FSMContext):
    await state.update_data(task_description=message.text.strip())
    await message.reply("Введите дедлайн задания в формате YYYY-MM-DD HH:MM:")
    await CreateTask.waiting_for_task_deadline.set()

@dp.message_handler(state=CreateTask.waiting_for_task_deadline, content_types=types.ContentTypes.TEXT)
async def save_task(message: types.Message, state: FSMContext):
    try:
        deadline = datetime.datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        data = await state.get_data()
        task = Task(
            group_id=data["group_id"],
            name=data["task_name"],
            description=data["task_description"],
            deadline=deadline
        )
        session.add(task)
        session.commit()
        await message.reply(f"Задание '{task.name}' успешно создано.")
        await state.finish()
    except ValueError:
        await message.reply("Неверный формат даты. Попробуйте ещё раз (формат: YYYY-MM-DD HH:MM).")

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

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
