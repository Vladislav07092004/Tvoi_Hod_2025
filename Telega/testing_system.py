from aiogram import types
from aiogram.dispatcher import FSMContext
from sqlalchemy.orm import Session  # Исправлено: orm вместо omn
from bot import User, Task  # Импортируем модели из основного файла
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestingSystem:
    def __init__(self, bot, session: Session):
        self.bot = bot
        self.session = session

    async def submit_solution(self, message: types.Message, state: FSMContext):
        """
        Обработчик для сбора решений от учеников.
        """
        user = self.session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
        if not user or user.role != "student":
            await message.reply("Эта команда доступна только для студентов.")
            return

        await message.reply("Отправьте ваше решение задания в виде файла .py.")
        await state.set_state("waiting_for_solution")

    async def handle_solution(self, message: types.Message, state: FSMContext):
        """
        Обработчик для получения решения и запуска тестирования.
        """
        if message.content_type == types.ContentType.DOCUMENT:
            file_name = message.document.file_name
            if not file_name.endswith(".py"):
                await message.reply("❌ Ошибка: файл должен иметь расширение .py.")
                return

            file_id = message.document.file_id
            file = await self.bot.get_file(file_id)
            file_path = file.file_path
            downloaded_file = await self.bot.download_file(file_path)
            solution = downloaded_file.read().decode("utf-8")

            # Сохраняем решение в состоянии
            await state.update_data(solution=solution)

            # Запуск тестирования
            await message.reply("Решение получено. Запускаю тестирование...")
            await self.test_solution(message, state)
        else:
            await message.reply("❌ Ошибка: отправьте файл .py.")

    async def test_solution(self, message: types.Message, state: FSMContext):
        """
        Запуск тестов для проверки решения.
        """
        data = await state.get_data()
        solution = data.get("solution")

        user = self.session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
        task = self.session.query(Task).filter_by(group_id=user.group_id).first()

        if not task:
            await message.reply("Ошибка: задание не найдено.")
            return

        # Запуск тестов
        result = self.run_tests(solution, task.expected_result)
        await message.reply(f"Результат тестирования:\n{result}")

        # Отправка результатов преподавателю
        await self.send_results_to_teacher(user, task, result)

        # Завершаем состояние
        await state.finish()

    def run_tests(self, solution: str, expected_result: str) -> str:
        """
        Функция для тестирования решений.
        """
        try:
            if solution.strip() == expected_result.strip():
                return "✅ Тест пройден! Ваше решение верное."
            else:
                return "❌ Тест не пройден. Ваше решение неверное."
        except Exception as e:
            return f"⚠️ Ошибка при тестировании: {str(e)}"

    async def send_results_to_teacher(self, user: User, task: Task, result: str):
        """
        Отправка результатов тестирования преподавателю.
        """
        teacher = self.session.query(User).filter_by(id=task.group.teacher_id).first()
        if teacher:
            await self.bot.send_message(
                teacher.telegram_id,
                f"📝 Результат тестирования ученика {user.full_name}:\n"
                f"Задание: {task.name}\n"
                f"Результат: {result}"
            )