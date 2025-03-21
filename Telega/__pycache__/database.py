from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

# Настройка базы данных SQLite
DATABASE_URL = "sqlite:///databaseTEST.db"
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

    # Добавьте это свойство для связи с Task
    tasks = relationship("Task", back_populates="group")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    name = Column(String)
    description = Column(Text)
    deadline = Column(DateTime, nullable=True)
    input_data = Column(Text, nullable=True)
    output_data = Column(Text, nullable=True)
    expected_result = Column(String, nullable=True)

    # Связь с группой
    group = relationship("Group", back_populates="tasks")

    # Связь с кодами студентов (добавляем правильное имя)
    student_codes = relationship("StudentCode", back_populates="task")


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

class StudentCode(Base):
    __tablename__ = "student_codes"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False)  # ID студента
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)  # ID задания
    submitted_code = Column(Text, nullable=False)  # Код, который отправил студент
    status = Column(String, default="pending")  # Статус: "pending", "accepted", "rework"

    # Связь с заданием
    task = relationship("Task", back_populates="student_codes")

class Guest(Base):
    __tablename__ = "guests"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)  # ФИО гостя
    region = Column(String, nullable=False)     # Регион
    city = Column(String, nullable=False)       # Город
    created_at = Column(DateTime, default=datetime.utcnow)  # Время регистрации
    is_active = Column(Boolean, default=True)   # Активен ли аккаунт

# Создание таблиц базы данных
Base.metadata.create_all(bind=engine)