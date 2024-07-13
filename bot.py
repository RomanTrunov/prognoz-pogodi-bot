import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from datetime import datetime, timedelta
import aiohttp
import re
import asyncio

API_TOKEN = '7485854939:AAG2lgFEnJX-cxngmdT9xVqkTfWtveR4cfY'
WEATHER_API_KEY = 'e7d29518081a74729fa77b59c4d67381'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class WeatherForm(StatesGroup):
    waiting_for_city = State()
    waiting_for_custom_city = State()
    waiting_for_date = State()
    waiting_for_custom_date = State()
    waiting_for_time = State()

def get_city_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🏙️ Москва"), KeyboardButton(text="🏙️ Абакан"))
    builder.row(KeyboardButton(text="🌆 Другой город"))
    return builder.as_markup(resize_keyboard=True)

def get_date_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📅 Завтра"))
    builder.row(KeyboardButton(text="📆 Другая дата"))
    return builder.as_markup(resize_keyboard=True)

def get_time_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🌅 Утро"), KeyboardButton(text="☀️ День"), KeyboardButton(text="🌆 Вечер"))
    return builder.as_markup(resize_keyboard=True)

def get_final_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🔄 Новый прогноз погоды"))
    builder.row(KeyboardButton(text="🏁 Завершить"))
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command(commands=['start', 'help']))
async def send_welcome(message: types.Message, state: FSMContext):
    await message.reply("Привет! Я бот прогноза погоды. Выберите город:", reply_markup=get_city_keyboard())
    await state.set_state(WeatherForm.waiting_for_city)

@dp.message(WeatherForm.waiting_for_city)
async def process_city(message: types.Message, state: FSMContext):
    if message.text == "🌆 Другой город":
        await message.reply("Введите название города:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(WeatherForm.waiting_for_custom_city)
    else:
        city = message.text.split()[1]  # Убираем эмодзи
        await state.update_data(city=city)
        await message.reply("Выберите дату:", reply_markup=get_date_keyboard())
        await state.set_state(WeatherForm.waiting_for_date)

@dp.message(WeatherForm.waiting_for_custom_city)
async def process_custom_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.reply("Выберите дату:", reply_markup=get_date_keyboard())
    await state.set_state(WeatherForm.waiting_for_date)

@dp.message(WeatherForm.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    if message.text == "📆 Другая дата":
        await message.reply("Введите дату в формате ДД-ММ-ГГГГ:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(WeatherForm.waiting_for_custom_date)
    else:
        if message.text == "📅 Сегодня":
            date = datetime.now().strftime("%d-%m-%Y")
        elif message.text == "📅 Завтра":
            date = (datetime.now() + timedelta(days=1)).strftime("%d-%m-%Y")

        await state.update_data(date=date)
        await message.reply("Выберите время суток:", reply_markup=get_time_keyboard())
        await state.set_state(WeatherForm.waiting_for_time)

@dp.message(WeatherForm.waiting_for_custom_date)
async def process_custom_date(message: types.Message, state: FSMContext):
    date_input = message.text
    date_pattern = r'\d{1,2}[-./]\d{1,2}[-./]\d{4}'
    if re.match(date_pattern, date_input):
        date = re.sub(r'[-./]', '-', date_input)
        await state.update_data(date=date)
        await message.reply("Выберите время суток:", reply_markup=get_time_keyboard())
        await state.set_state(WeatherForm.waiting_for_time)
    else:
        await message.reply("Неверный формат даты. Пожалуйста, используйте формат ДД-ММ-ГГГГ.")

@dp.message(WeatherForm.waiting_for_time)
async def process_time(message: types.Message, state: FSMContext):
    time = message.text.split()[1]  # Убираем эмодзи
    data = await state.get_data()
    city = data['city']
    date = data['date']

    weather_data = await get_weather(city, date)
    if not weather_data:
        await message.reply("Не удалось получить данные о погоде для указанного города.")
        await ask_for_next_action(message, state)
        return

    forecast_index = {'Утро': 0, 'День': 1, 'Вечер': 2}
    forecast = weather_data[forecast_index[time]]

    temp = round(forecast['main']['temp'])
    description = forecast['weather'][0]['description']
    humidity = forecast['main']['humidity']
    wind_speed = forecast['wind']['speed']

    await message.reply(
        f"Прогноз на {date} ({time}) в городе {city}:\n"
        f"Погода: {description.capitalize()}\n"
        f"Температура: {temp}°C\n"
        f"Влажность: {humidity}%\n"
        f"Скорость ветра: {wind_speed} м/с",
        reply_markup=get_final_keyboard()
    )
    await state.set_state(WeatherForm.waiting_for_city)

@dp.message(F.text == "🔄 Новый прогноз погоды")
async def new_forecast(message: types.Message, state: FSMContext):
    await message.reply("Выберите город:", reply_markup=get_city_keyboard())
    await state.set_state(WeatherForm.waiting_for_city)

@dp.message(F.text == "🏁 Завершить")
async def end_session(message: types.Message, state: FSMContext):
    await message.reply("Спасибо за использование бота прогноза погоды! До свидания!",
                        reply_markup=ReplyKeyboardRemove())
    await state.clear()

async def get_weather(city: str, date: str):
    async with aiohttp.ClientSession() as session:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        async with session.get(url) as response:
            weather_data = await response.json()
            if weather_data.get("list"):
                target_date = datetime.strptime(date, "%d-%m-%Y").date()
                forecasts = [
                    forecast for forecast in weather_data["list"]
                    if datetime.fromtimestamp(forecast['dt']).date() == target_date
                ]
                if forecasts:
                    morning = next((f for f in forecasts if 6 <= datetime.fromtimestamp(f['dt']).hour < 12),
                                   forecasts[0])
                    day = next((f for f in forecasts if 12 <= datetime.fromtimestamp(f['dt']).hour < 18), forecasts[0])
                    evening = next((f for f in forecasts if 18 <= datetime.fromtimestamp(f['dt']).hour < 24),
                                   forecasts[-1])
                    return [morning, day, evening]
            return None

async def main():
    # Удаляем любые существующие вебхуки
    await bot.delete_webhook(drop_pending_updates=True)
    # Запускаем поллинг
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == '__main__':
    asyncio.run(main())
