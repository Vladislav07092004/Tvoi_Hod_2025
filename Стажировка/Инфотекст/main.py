print("Начало выполнения скрипта.")  # Проверка, запускается ли файл вообще

from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI!"}

if __name__ == "__main__":
    print("Скрипт выполняется...")  # Отладочное сообщение
    import uvicorn
    print("Запуск Uvicorn...")  # Отладочное сообщение
    uvicorn.run(
        "main:app",  # Имя файла : имя приложения
        host="127.0.0.1",
        port=8000,
        reload=True
    )

