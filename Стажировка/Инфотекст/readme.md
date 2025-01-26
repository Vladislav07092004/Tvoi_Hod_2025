Инструкция по использованию script.py

Описание

Этот проект реализует HTTP-сервер для предоставления информации о погоде с использованием асинхронного фреймворка FastAPI. Данные о погоде предоставляются с помощью API Open-Meteo.

Сервер предоставляет возможности для управления пользователями и городами, а также позволяет получать актуальную информацию о погоде и прогнозы.

Требования к установке

Создание виртуального окружения:
Для изоляции зависимостей рекомендуется использовать виртуальное окружение. Выполните следующую команду:

python -m venv .venv

Если команда python не работает, попробуйте использовать python3:

python3 -m venv .venv

Активация виртуального окружения:

Windows:

.venv\Scripts\activate

Linux/macOS:

source .venv/bin/activate

Установка зависимостей:
Убедитесь, что файл requirements.txt находится в корне проекта, и выполните команду:

pip install -r requirements.txt

Запуск сервера:
Выполните следующую команду:

python script.py

Сервер будет запущен по адресу http://127.0.0.1:8000.

Описание API

1. Регистрация пользователя

Добавьте нового пользователя:

curl -X POST "http://127.0.0.1:8000/users/register/" \
-H "Content-Type: application/json" \
-d "{\"name\": \"ИмяПользователя\"}"

Параметры:

name — имя пользователя.

Пример:

curl -X POST "http://127.0.0.1:8000/users/register/" -H "Content-Type: application/json" -d "{\"name\": \"Vladislav\"}"

2. Добавление города для отслеживания погоды

a) Для всех пользователей:

curl -X POST "http://127.0.0.1:8000/users/cities/add_for_all/" \
-H "Content-Type: application/json" \
-d "{\"name\": \"НазваниеГорода\", \"lat\": Широта, \"lon\": Долгота}"

Параметры:

name — название города.

lat — широта.

lon — долгота.

Пример:

curl -X POST "http://127.0.0.1:8000/users/cities/add_for_all/" -H "Content-Type: application/json" -d "{\"name\": \"Saint-Peterburg\", \"lat\": 59.9386, \"lon\": 30.3141}"

b) Для определённого пользователя:

curl -X POST "http://127.0.0.1:8000/users/{id}/cities/add/" \
-H "Content-Type: application/json" \
-d "{\"name\": \"НазваниеГорода\", \"lat\": Широта, \"lon\": Долгота}"

Пример:

curl -X POST "http://127.0.0.1:8000/users/1/cities/add/" -H "Content-Type: application/json" -d "{\"name\": \"New York\", \"lat\": 40.7128, \"lon\": -74.0060}"

3. Получение списка городов

a) Для всех пользователей:

curl -X GET "http://127.0.0.1:8000/users/cities/?user_id=0"

b) Для конкретного пользователя:

curl -X GET "http://127.0.0.1:8000/users/cities/?user_id={id}"

Пример:

curl -X GET "http://127.0.0.1:8000/users/cities/?user_id=1"

4. Получение текущей погоды по координатам

curl -X POST "http://127.0.0.1:8000/weather/current/" \
-H "Content-Type: application/json" \
-d "{\"lat\": Широта, \"lon\": Долгота}"

Параметры:

lat — широта.

lon — долгота.

Пример:

curl -X POST "http://127.0.0.1:8000/weather/current/" -H "Content-Type: application/json" -d "{\"lat\": 41.0138, \"lon\": 28.9497}"

Ответ:

{
  "temperature": 15.2,
  "humidity": 60,
  "wind_speed": 5.4,
  "precipitation": 0.3
}

5. Получение прогноза погоды на текущий день

a) Для всех пользователей:

Получите список городов:

curl -X GET "http://127.0.0.1:8000/users/cities/?user_id=0"

Найдите ID нужного города и выполните команду:

curl -X POST "http://127.0.0.1:8000/users/weather/" \
-H "Content-Type: application/json" \
-d "{\"user_id\": 0, \"city_id\": ID_Города, \"time\": \"Дата и время\"}"

Пример:

curl -X POST "http://127.0.0.1:8000/users/weather/" -H "Content-Type: application/json" -d "{\"user_id\": 0, \"city_id\": 1, \"time\": \"2025-01-23T10:00\"}"

b) Для конкретного пользователя:

Получите список городов:

curl -X GET "http://127.0.0.1:8000/users/{id}/cities/"

Найдите ID нужного города и выполните команду:

curl -X POST "http://127.0.0.1:8000/users/weather/" \
-H "Content-Type: application/json" \
-d "{\"user_id\": ID_Пользователя, \"city_id\": ID_Города, \"time\": \"Дата и время\"}"

Пример:

curl -X POST "http://127.0.0.1:8000/users/weather/" -H "Content-Type: application/json" -d "{\"user_id\": 1, \"city_id\": 2, \"time\": \"2025-01-23T10:00\"}"

Обновление прогноза каждые 15 минут

Обновление данных реализовано с использованием планировщика задач (например, Celery или встроенные планировщики FastAPI). Сервер автоматически обновляет информацию для всех городов в базе каждые 15 минут.

Структура базы данных

users (пользователи):

id (INTEGER, PRIMARY KEY) — идентификатор пользователя.

name (TEXT) — имя пользователя.

cities (города):

id (INTEGER, PRIMARY KEY) — идентификатор города.

name (TEXT) — название города.

lat (REAL) — широта.

lon (REAL) — долгота.

weather (погода):

id (INTEGER, PRIMARY KEY) — идентификатор прогноза.

city_id (INTEGER, FOREIGN KEY) — идентификатор города.

forecast_time (TEXT) — время прогноза.

temperature (REAL) — температура.

humidity (REAL) — влажность.

wind_speed (REAL) — скорость ветра.

precipitation (REAL) — осадки.

user_cities (связь пользователей и городов):

user_id (INTEGER, FOREIGN KEY) — идентификатор пользователя.

city_id (INTEGER, FOREIGN KEY) — идентификатор города.

Примечания

Дата и время:

Формат: YYYY-MM-DDTHH:MM.

Данные о погоде:

Используются данные Open-Meteo, включая температуру, влажность, скорость ветра и осадки.

Планировщик обновлений:

Убедитесь, что сервер работает непрерывно для обновления данных каждые 15 минут.

Если у вас есть вопросы или требуется помощь с установкой, свяжитесь с разработчиком проекта.

