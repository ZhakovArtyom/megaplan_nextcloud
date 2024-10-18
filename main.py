import logging
from logging.handlers import RotatingFileHandler

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.routers.nextcloud_router import router as nextcloud_router

# Настройка логирования с ротацией по размеру файла
logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = RotatingFileHandler('/app/logs/project.log', maxBytes=10 * 1024 * 1024, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger.addHandler(handler)

app = FastAPI()


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    # Логирование ошибки в файл
    logging.exception(f"An error occurred: {exc}", exc_info=exc)

    # Возвращаем JSON-ответ с ошибкой
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error"}
    )


# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(nextcloud_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=443, reload=True)
