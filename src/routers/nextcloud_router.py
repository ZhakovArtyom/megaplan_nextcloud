import asyncio
import json
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import aioschedule
import requests
from aiojobs import Scheduler
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from config import settings

router = APIRouter()

JOURNAL_FILE = "/app/logs/tasks_journal.json"
file_lock = asyncio.Lock()
periodic_recovery_running = False  # Глобальный флаг для контроля запуска


@router.get("/crm/test")
async def test_endpoint():
    logging.info(f"Received test request")
    return JSONResponse(status_code=200, content={"message": "Test request successful!"})


# Функция для загрузки журнала задач как словаря
async def load_tasks_journal():
    async with file_lock:
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "r") as file:
                return json.load(file)
        else:
            return {}


# Функция для сохранения журнала задач как словаря
async def save_tasks_journal(tasks_journal):
    async with file_lock:
        with open(JOURNAL_FILE, "w") as file:
            json.dump(tasks_journal, file, indent=4, ensure_ascii=False)


# Удаление задачи из словаря
async def delete_task_from_journal(task_id, not_found_share_id=None):
    tasks_journal = await load_tasks_journal()
    task_info = tasks_journal.get(task_id)

    if task_info:
        share_id = task_info["share_id"]
        if not_found_share_id is not None:
            share_id = not_found_share_id
        if share_id:
            await revoke_public_link(share_id)

        del tasks_journal[task_id]
        await save_tasks_journal(tasks_journal)
        logging.info(f"Задача с ID {task_id} удалена из журнала.")
    else:
        logging.warning(f"Задача с ID {task_id} не найдена в журнале.")


@router.post("/crm/tasks")
async def create_folder_and_share_link(request: Request):
    # Получаем данные запроса
    try:
        task_data = await request.json()
        logging.info(f"Получен вебхук задачи")
    except Exception:
        return JSONResponse(status_code=200, content={"message": "Запрос без тела JSON"})

    # Проверяем тип события
    event_type = task_data.get("event")
    if event_type == "on_after_create":
        # Создаем асинхронную задачу для обработки создания задачи
        asyncio.create_task(process_task_creation(task_data))
        return JSONResponse(status_code=200, content={"message": "Задача принята в обработку"})

    elif event_type == "on_after_drop":
        asyncio.create_task(process_task_deletion(task_data))
        return JSONResponse(status_code=200, content={"message": "Удаление задачи принято в обработку"})

    else:
        logging.info(f"Игнорируем событие: {event_type}")
        return JSONResponse(status_code=200, content={"message": "Событие не поддерживается"})


async def process_task_creation(task_data):
    try:
        # Логика обработки создания/переименования задачи
        task_id = task_data["data"]["id"]
        task_humannumber = task_data["data"]["humanNumber"]
        task_name = task_data["data"]["name"]
        is_rename = task_data["data"].get("rename", False)
        is_create_again = task_data["data"].get("create_again", False)

        logging.info(f"Получен task ID: {task_id}, название: {task_name}")

        new_folder_name = f"{task_humannumber}. {task_name}"
        catalog_folder = "/КАТАЛОГ"
        new_folder_path = f"{catalog_folder}/{new_folder_name}"

        tasks_journal = await load_tasks_journal()

        if is_rename and task_id in tasks_journal:
            old_folder_path = tasks_journal[task_id]["folder_path"]
            await rename_folder_in_nextcloud(old_folder_path, new_folder_path)
            tasks_journal[task_id]["folder_path"] = new_folder_path
            await save_tasks_journal(tasks_journal)
        else:
            if not is_create_again and task_id in tasks_journal:
                logging.info(f"Задача с ID {task_id} уже существует в журнале.")
                return
            elif is_create_again and task_id in tasks_journal:
                # Если is_create_again, сначала отзываем старую ссылку
                old_share_id = tasks_journal[task_id]["share_id"]
                if old_share_id:
                    await revoke_public_link(old_share_id)
                    logging.info(f"Старая ссылка для задачи {task_id} отозвана.")

            task_info = {
                "task_id": task_id,
                "folder_path": new_folder_path,
                "share_id": None  # пока нет ссылки на папку
            }
            tasks_journal[task_id] = task_info

            await save_tasks_journal(tasks_journal)

            create_folder_url = f"{settings.NEXTCLOUD_URL}/remote.php/dav/files/{settings.NEXTCLOUD_USERNAME}{new_folder_path}"
            response = requests.request("MKCOL", create_folder_url,
                                        auth=(settings.NEXTCLOUD_USERNAME, settings.NEXTCLOUD_PASSWORD))

            if response.status_code == 201:
                logging.info(f"Папка успешно создана: {new_folder_path}")
            elif response.status_code == 405:
                logging.info(f"Папка уже существует: {new_folder_path}")
            else:
                logging.error(f"Ошибка при создании папки: {response.status_code, response.text}")

        share_id, share_url = await create_public_link(task_id, new_folder_path)
        if share_id and share_url:
            logging.info(f"Публичная ссылка для задачи {task_id}: {share_url}")
            tasks_journal[task_id]["share_id"] = share_id
            await save_tasks_journal(tasks_journal)

    except Exception as e:
        logging.exception(f"Ошибка при обработке создания/переименования задачи: {str(e)}")


async def rename_folder_in_nextcloud(old_folder_path, new_folder_path):
    move_url = f"{settings.NEXTCLOUD_URL}/remote.php/dav/files/{settings.NEXTCLOUD_USERNAME}/{old_folder_path}"
    destination_url = f"{settings.NEXTCLOUD_URL}/remote.php/dav/files/{settings.NEXTCLOUD_USERNAME}/{new_folder_path}"
    headers = {
        "Destination": destination_url.encode('utf-8')
    }
    response = requests.request("MOVE", move_url, auth=(settings.NEXTCLOUD_USERNAME, settings.NEXTCLOUD_PASSWORD),
                                headers=headers)

    if response.status_code == 201:
        logging.info(f"Папка успешно переименована: {old_folder_path} -> {new_folder_path}")
    else:
        logging.error(f"Ошибка при переименовании папки: {response.status_code, response.text}")


async def process_task_deletion(task_data):
    try:
        # Логика обработки удаления задачи
        task_id = task_data["data"]["id"]
        logging.info(f"Удаление задачи с ID: {task_id}")

        await delete_task_from_journal(task_id)

    except Exception as e:
        logging.exception(f"Ошибка при обработке удаления задачи: {str(e)}")


async def create_public_link(task_id, folder_path):
    share_url = f"{settings.NEXTCLOUD_URL}/ocs/v2.php/apps/files_sharing/api/v1/shares?format=xml"
    headers = {
        "OCS-APIRequest": "true",
        "Content-Type": "application/x-www-form-urlencoded",
        "requesttoken": settings.NEXTCLOUD_CSRF_TOKEN
    }
    data = {
        "path": folder_path,
        "shareType": 3,
        "publicUpload": "true",
        "permissions": 15,
    }

    response = requests.post(share_url, auth=(settings.NEXTCLOUD_USERNAME, settings.NEXTCLOUD_PASSWORD),
                             headers=headers, data=data)

    if response.status_code == 200:
        xml_response = ET.fromstring(response.content)
        share_id = xml_response.find(".//data/id").text
        share_url = xml_response.find(".//data/url").text
        logging.info(f"Общий доступ к папке предоставлен. URL общего доступа: {share_url}")

        current_date_utc = datetime.now(timezone.utc)
        msk_offset = timedelta(hours=3)
        current_date_msk = current_date_utc + msk_offset
        formatted_date_msk = current_date_msk.strftime("%d.%m.%Y")

        link_text = f"Ссылка на каталог от {formatted_date_msk}"

        # Загрузка ссылки в кастомное поле задачи
        update_task_url = f"{settings.MEGAPLAN_API_URL}/api/v3/task/{task_id}"
        task_data = {
            "Category130CustomFieldKatalog": f'<a href="{share_url}" target="_blank">{link_text}</a>'
        }

        update_headers = {
            "Authorization": f"Bearer {settings.MEGAPLAN_API_KEY}",
            "Content-Type": "application/json"
        }
        update_response = requests.post(update_task_url, headers=update_headers, json=task_data)

        if update_response.status_code == 200:
            logging.info(f"Ссылка успешно добавлена в кастомное поле задачи {task_id}")
        elif update_response.status_code == 404:
            logging.warning(f"Задача с ID {task_id} не найдена. Удаление задачи из журнала.")
            await delete_task_from_journal(task_id, not_found_share_id=share_id)
        else:
            logging.error(
                f"Ошибка при добавлении ссылки в кастомное поле задачи {task_id}: {update_response.status_code}")

        return share_id, share_url
    else:
        logging.error(f"Ошибка при предоставлении общего доступа к папке: {response.status_code}")
        return None, None


async def revoke_public_link(share_id):
    delete_share_url = f"{settings.NEXTCLOUD_URL}/ocs/v2.php/apps/files_sharing/api/v1/shares/{share_id}"
    logging.info(f"Share_id, который будет отзываться {share_id}")
    headers = {
        "OCS-APIRequest": "true",
        "Content-Type": "application/x-www-form-urlencoded",
        "requesttoken": settings.NEXTCLOUD_CSRF_TOKEN
    }
    response = requests.delete(delete_share_url, auth=(settings.NEXTCLOUD_USERNAME, settings.NEXTCLOUD_PASSWORD),
                               headers=headers)

    if response.status_code == 200:
        logging.info(f"Общий доступ отозван.")
    else:
        logging.error(f"Ошибка при отзыве общего доступа: {response.status_code}")


async def update_public_link(task_id, share_id, folder_path):
    await revoke_public_link(share_id)
    new_share_id, new_share_url = await create_public_link(task_id, folder_path)
    logging.info(f"Новая публичная ссылка создана: {new_share_url}")
    return new_share_id


async def update_task(task_info, delay):
    await asyncio.sleep(delay)  # Ждём указанное время перед обновлением задачи
    task_id = task_info["task_id"]
    folder_path = task_info["folder_path"]
    share_id = task_info["share_id"]

    new_share_id = await update_public_link(task_id, share_id, folder_path)
    task_info["share_id"] = new_share_id
    share_id = new_share_id

    # Обновление журнала задач
    tasks_journal = await load_tasks_journal()

    # Проверяем, существует ли задача в журнале перед обновлением
    if task_id in tasks_journal:
        tasks_journal[task_id]["share_id"] = new_share_id
        await save_tasks_journal(tasks_journal)
        logging.info(f"Задача с ID {task_id} успешно обновлена в журнале.")
    else:
        logging.warning(f"Задача с ID {task_id} не найдена в журнале при попытке обновления.")


async def run_recovery():
    tasks_journal = await load_tasks_journal()

    logging.info(f"Всего задач в журнале: {len(tasks_journal)}")

    # Берем только последние 20000 задач из журнала
    recent_tasks = list(tasks_journal.values())[-20000:]

    logging.info(f"Количество задач для обновления: {len(recent_tasks)}")
    # logging.info(f"Задачи: {recent_tasks}")

    for i, task_info in enumerate(recent_tasks):
        delay = i * 4  # Вычисляем задержку для каждой задачи
        asyncio.create_task(update_task(task_info, delay))


async def startup_recovery():
    async def periodic_recovery():
        global periodic_recovery_running
        if periodic_recovery_running:
            logging.info("periodic_recovery уже запущен. Пропуск запуска.")
            return

        periodic_recovery_running = True

        try:
            aioschedule.every().day.at("23:00").do(run_recovery)  # время по UTC
            # aioschedule.every(5).minutes.do(run_recovery)

            while True:
                # Запускаем все отложенные задачи
                jobs = aioschedule.jobs.copy()
                for job in jobs:
                    if job.should_run:
                        # Явно создаём задачу для каждой отложенной функции
                        asyncio.create_task(job.run())

                await asyncio.sleep(1)
        finally:
            periodic_recovery_running = False

    scheduler = Scheduler()
    await scheduler.spawn(periodic_recovery())


@router.on_event("startup")
async def startup_event():
    # Проверяем, существует ли файл журнала, и если нет — создаём пустой словарь
    if not os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "w") as file:
            json.dump({}, file, ensure_ascii=False, indent=4)

    logging.info("Запуск recovery процесса")
    await startup_recovery()  # Запускаем только один раз
