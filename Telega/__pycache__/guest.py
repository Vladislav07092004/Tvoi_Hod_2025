# guest.py
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from database import session, Guest
from datetime import datetime, timedelta

# Состояния для сбора данных от гостя
class GuestForm(StatesGroup):
    waiting_for_full_name = State()  # Ожидание ФИО
    waiting_for_region = State()    # Ожидание региона
    waiting_for_city = State()      # Ожидание города

async def guest_start(message: types.Message, state: FSMContext):
    """
    Приветствие для гостя и начало регистрации.
    """
    await message.reply("Введите ваше ФИО:")
    await GuestForm.waiting_for_full_name.set()

async def process_full_name(message: types.Message, state: FSMContext):
    """
    Обработка ввода ФИО.
    """
    full_name = message.text.strip()
    await state.update_data(full_name=full_name)
    await message.reply("Введите ваш регион:")
    await GuestForm.waiting_for_region.set()

async def process_region(message: types.Message, state: FSMContext):
    """
    Обработка ввода региона.
    """
    region = message.text.strip()
    await state.update_data(region=region)
    await message.reply("Введите ваш город:")
    await GuestForm.waiting_for_city.set()

async def process_city(message: types.Message, state: FSMContext):
    """
    Обработка ввода города и завершение регистрации.
    """
    city = message.text.strip()
    user_data = await state.get_data()

    # Сохраняем данные гостя в базу данных
    new_guest = Guest(
        full_name=user_data['full_name'],
        region=user_data['region'],
        city=city,
        created_at=datetime.utcnow(),
        is_active=True
    )
    session.add(new_guest)
    session.commit()

    await message.reply("Спасибо! Вы успешно зарегистрированы как гость.")
    await state.finish()

async def check_guest_activity(guest_id: int) -> bool:
    """
    Проверяет, активен ли аккаунт гостя.
    Если с момента регистрации прошло более 12 часов, деактивирует аккаунт.
    """
    guest = session.query(Guest).filter_by(id=guest_id).first()
    if not guest:
        return False

    # Проверяем, прошло ли 12 часов с момента регистрации
    if datetime.utcnow() - guest.created_at > timedelta(hours=12):
        guest.is_active = False
        session.commit()
        return False

    return True