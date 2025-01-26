from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import aiohttp
import sqlite3
import asyncio
from datetime import datetime
import json


DB_FILE = "weather.db"

class UserWeatherRequest(BaseModel):
    user_id: int
    time: str
    parameters: Optional[List[str]] = Query(default=["temperature", "humidity", "wind_speed", "precipitation"])

class UserRegisterRequest(BaseModel):
    name: str

class City(BaseModel):
    name: str
    lat: float
    lon: float

class Coordinates(BaseModel):
    lat: float
    lon: float

class WeatherRequest(BaseModel):
    city_name: str
    parameters: Optional[List[str]] = Query(default=["temperature", "humidity", "wind_speed", "precipitation"])
    time: Optional[str] = None

class WeatherRequest1(BaseModel):
    user_id: int
    city_id: int
    time: str  # Формат времени: YYYY-MM-DDTHH:MM

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Таблица для пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)

    # Таблица для городов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            lat REAL,
            lon REAL
        )
    """)

    # Таблица для связи пользователей и городов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_cities (
            user_id INTEGER,
            city_id INTEGER,
            PRIMARY KEY (user_id, city_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (city_id) REFERENCES cities (id)
        )
    """)

    # Таблица для хранения прогноза погоды
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id INTEGER,
            forecast_time TEXT,
            temperature REAL,
            humidity REAL,
            wind_speed REAL,
            precipitation REAL,
            FOREIGN KEY (city_id) REFERENCES cities (id)
        )
    """)

    conn.commit()
    conn.close()


# Запуск фоновой задачи при старте приложения
async def lifespan(app: FastAPI):
    print("Инициализация базы данных...")
    init_db()

    # Запуск фоновой задачи
    task = asyncio.create_task(background_task())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)

# Фоновая задача для обновления данных
async def background_task():
    while True:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Получаем список всех городов
        cursor.execute("SELECT id, lat, lon FROM cities")
        cities = cursor.fetchall()
        conn.close()

        for city in cities:
            city_id, lat, lon = city
            try:
                # Получаем данные погоды
                weather_data = await fetch_weather(lat, lon, current_weather=False)
                hourly = weather_data.get("hourly", {})
                times = hourly.get("time", [])
                temperatures = hourly.get("temperature_2m", [])
                humidities = hourly.get("relative_humidity_2m", [])
                wind_speeds = hourly.get("windspeed_10m", [])
                precipitations = hourly.get("precipitation", [])

                # Сохраняем данные в базу
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                for i, time in enumerate(times):
                    cursor.execute("""
                        REPLACE INTO weather (city_id, forecast_time, temperature, humidity, wind_speed, precipitation)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        city_id,
                        time,
                        temperatures[i] if i < len(temperatures) else None,
                        humidities[i] if i < len(humidities) else None,
                        wind_speeds[i] if i < len(wind_speeds) else None,
                        precipitations[i] if i < len(precipitations) else None
                    ))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Ошибка при обновлении прогноза для города {city_id}: {e}")

        # Ждём 15 минут
        await asyncio.sleep(15 * 60)


# Open-Meteo API
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

async def fetch_weather(lat, lon, current_weather=True):
    print(f"Запрашиваем погоду для координат: {lat}, {lon}")
    async with aiohttp.ClientSession() as session:
        query = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true" if current_weather else "false",
            "hourly": "temperature_2m,relative_humidity_2m,windspeed_10m,precipitation"
        }
        async with session.get(OPEN_METEO_URL, params=query) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch weather data")
            return await resp.json()

def get_weather_data(city_name: str, time: str, parameters: list):
    conn = sqlite3.connect("weather.db")
    cursor = conn.cursor()

    # Получаем ID города
    cursor.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
    city = cursor.fetchone()
    if not city:
        raise HTTPException(status_code=404, detail="City not found.")
    city_id = city[0]

    # Получаем данные погоды
    cursor.execute("""
        SELECT forecast_time, temperature, humidity, wind_speed, precipitation
        FROM weather
        WHERE city_id = ? AND forecast_time = ?
    """, (city_id, time))
    weather = cursor.fetchone()
    conn.close()

    if not weather:
        raise HTTPException(status_code=404, detail="Weather data not found for the specified time.")

    # Формируем ответ
    available_params = ["temperature", "humidity", "wind_speed", "precipitation"]
    weather_data = dict(zip(available_params, weather[1:]))
    response = {"city": city_name, "time": weather[0]}
    for param in parameters:
        if param in weather_data:
            response[param] = weather_data[param]
    return response



# Маршруты
@app.post("/weather/current/")
async def get_current_weather(coords: Coordinates):
    weather = await fetch_weather(coords.lat, coords.lon)
    current_weather = weather.get("current_weather", {})
    return {
        "temperature": current_weather.get("temperature"),
        "wind_speed": current_weather.get("windspeed"),
        "wind_direction": current_weather.get("winddirection")
    }

@app.post("/users/{user_id}/cities/add/")
async def add_city_for_user(user_id: int, city: City):
    """Добавляет город в список пользователя"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Проверяем, существует ли пользователь
    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found.")

    # Добавляем город в таблицу городов
    try:
        cursor.execute("INSERT INTO cities (name, lat, lon) VALUES (?, ?, ?)", (city.name, city.lat, city.lon))
        city_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        # Если город уже существует, получаем его ID
        cursor.execute("SELECT id FROM cities WHERE name = ?", (city.name,))
        city_id = cursor.fetchone()[0]

    # Связываем пользователя с городом
    try:
        cursor.execute("INSERT INTO user_cities (user_id, city_id) VALUES (?, ?)", (user_id, city_id))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="City already linked to user.")
    finally:
        conn.close()

    return {"message": f"City {city.name} linked to user {user_id} successfully."}

@app.post("/users/cities/add_for_all/")
async def add_city_for_all_users(city: City):
    """
    Добавляет город в список для всех пользователей
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Добавляем город в таблицу городов
    try:
        cursor.execute("INSERT INTO cities (name, lat, lon) VALUES (?, ?, ?)", (city.name, city.lat, city.lon))
        city_id = cursor.lastrowid  # Получаем ID добавленного города
    except sqlite3.IntegrityError:
        # Если город уже существует, получаем его ID
        cursor.execute("SELECT id FROM cities WHERE name = ?", (city.name,))
        city_id = cursor.fetchone()[0]

    # Связываем город с user_id=0 (для всех пользователей)
    try:
        cursor.execute("INSERT INTO user_cities (user_id, city_id) VALUES (?, ?)", (0, city_id))
        conn.commit()
    except sqlite3.IntegrityError:
        # Если связь уже существует, ничего не делаем
        pass

    conn.close()

    return {"message": f"City {city.name} added for all users successfully."}


@app.get("/users/cities/")
async def get_cities(user_id: Optional[int] = None):
    """
    Возвращает список городов:
    - Для user_id=0: только города для всех пользователей.
    - Для конкретного user_id: только города, добавленные для этого пользователя.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if user_id == 0:
        # Города для всех пользователей
        cursor.execute("""
            SELECT cities.id, cities.name, cities.lat, cities.lon
            FROM cities
            INNER JOIN user_cities ON cities.id = user_cities.city_id
            WHERE user_cities.user_id = 0
        """)
    elif user_id:
        # Индивидуальные города для указанного пользователя
        cursor.execute("""
            SELECT cities.id, cities.name, cities.lat, cities.lon
            FROM cities
            INNER JOIN user_cities ON cities.id = user_cities.city_id
            WHERE user_cities.user_id = ?
        """, (user_id,))
    else:
        # Если user_id не указан, выбрасываем ошибку
        raise HTTPException(status_code=400, detail="You must specify user_id or use 0 for all users.")

    cities = cursor.fetchall()
    conn.close()

    if not cities:
        raise HTTPException(status_code=404, detail="No cities found.")

    return [{"id": city[0], "name": city[1], "lat": city[2], "lon": city[3]} for city in cities]



@app.get("/users/{user_id}/weather/")
async def get_user_weather(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Получаем список городов пользователя
    cursor.execute("""
        SELECT cities.name, cities.lat, cities.lon
        FROM cities
        INNER JOIN user_cities ON cities.id = user_cities.city_id
        WHERE user_cities.user_id = ?
    """, (user_id,))
    cities = cursor.fetchall()
    conn.close()
    if not cities:
        raise HTTPException(status_code=404, detail="No cities found for this user.")

    
    weather_data = []
    for city in cities:
        weather_data.append({
            "city": city[0],
            "lat": city[1],
            "lon": city[2],
            "forecast": {
                "temperature": 20,
                "humidity": 60,
                "wind_speed": 5
            }
        })
    return weather_data

@app.post("/weather/at-time/")
async def get_weather(request: WeatherRequest):
    return get_weather_data(request.city_name, request.time, request.parameters)




@app.post("/users/register/")
async def register_user(request: UserRegisterRequest):
    name = request.name
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)")
        cursor.execute("INSERT INTO users (name) VALUES (?)", (name,))
        conn.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists.")
    finally:
        conn.close()
    return {"user_id": user_id, "name": name}

@app.get("/users/{user_id}/cities/")
async def list_user_cities(user_id: int):
    conn = sqlite3.connect("weather.db")
    cursor = conn.cursor()

    
    cursor.execute("""
        SELECT cities.id, cities.name, cities.lat, cities.lon
        FROM cities
        INNER JOIN user_cities ON cities.id = user_cities.city_id
        WHERE user_cities.user_id = ?
    """, (user_id,))
    cities = cursor.fetchall()
    conn.close()

    if not cities:
        raise HTTPException(status_code=404, detail="No cities found for this user.")

    # Формируем ответ
    return [{"id": city[0], "name": city[1], "lat": city[2], "lon": city[3]} for city in cities]

# Маршрут для получения погоды
@app.post("/users/weather/")
async def get_weather_for_user(request: WeatherRequest1):
    conn = sqlite3.connect("weather.db")
    cursor = conn.cursor()

    # Проверяем, связан ли город с этим пользователем
    cursor.execute("""
        SELECT 1
        FROM user_cities
        WHERE user_id = ? AND city_id = ?
    """, (request.user_id, request.city_id))
    city_user_relation = cursor.fetchone()
    if not city_user_relation:
        conn.close()
        raise HTTPException(status_code=403, detail="This city is not associated with the user.")

    # Получаем данные о погоде
    cursor.execute("""
        SELECT forecast_time, temperature, humidity, wind_speed, precipitation
        FROM weather
        WHERE city_id = ? AND forecast_time = ?
    """, (request.city_id, request.time))
    weather = cursor.fetchall()
    conn.close()

    if not weather:
        raise HTTPException(status_code=404, detail="Weather data not found for the specified time.")

    response = [
        {
            "time": w[0],
            "temperature": w[1],
            "humidity": w[2],
            "wind_speed": w[3],
            "precipitation": w[4]
        }
        for w in weather
    ]

    return response





if __name__ == "__main__":
    import uvicorn
    uvicorn.run("script:app", host="127.0.0.1", port=8000, reload=True)
