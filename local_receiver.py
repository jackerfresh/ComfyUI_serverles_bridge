import aiohttp
import traceback
import asyncio
import json
from server import PromptServer
from aiohttp import web
import sys

# ----------------------------------------------------
VAST_ENDPOINT_NAME = "zalupa"  # <--- ПРОВЕРЬ ИМЯ ЭНДПОИНТА
VAST_API_KEY = "5c89cd3a7c5dc0b8d84a3cb00030fe6d116554c967305ff1e2371c0956f09a0c"
SMEE_URL = "https://smee.io/bRWvacytzAfXqA8"
# ----------------------------------------------------

@PromptServer.instance.routes.post("/vast_forward")
async def vast_forward(request):
    try:
        data = await request.json()
        prompt_workflow = data.get("prompt")
        
        route_url = "https://run.vast.ai/route/"
        
        payload = {
            "endpoint": VAST_ENDPOINT_NAME,
            "api_key": VAST_API_KEY,
            "cost": 1.0
        }
        
        print(f"\n🚀 [SERVERLESS] Будим Васт (Endpoint: {VAST_ENDPOINT_NAME})...")
        
        async with aiohttp.ClientSession() as session:
            worker_url = None
            signature = None
            reqnum = None
            
            while not worker_url:
                async with session.post(route_url, json=payload, ssl=False) as resp:
                    resp_text = await resp.text()
                    
                    if resp.status in[502, 503, 504] or "loading" in resp_text.lower() or "no workers" in resp_text.lower():
                        print(f"⏳[SERVERLESS] Машина прогревается (Код {resp.status}). Ждем 5 секунд...")
                        await asyncio.sleep(5)
                        continue
                        
                    if resp.status != 200:
                        raise Exception(f"Ошибка роутера ({resp.status}): {resp_text}")
                    
                    route_data = json.loads(resp_text) if "{" in resp_text else {}
                    worker_url = route_data.get("url")
                    signature = route_data.get("signature")
                    reqnum = route_data.get("reqnum")
                    
                    if not worker_url:
                        print(f"⏳ [SERVERLESS] Васт ищет машину... Ждем 5 секунд...")
                        await asyncio.sleep(5)
            
            print(f"🎯 [SERVERLESS] Машина готова! Выдан IP-адрес: {worker_url}")
            
            target_url = worker_url.rstrip("/") + "/generate/sync"
            
            worker_payload = {
                "auth_data": {
                    "signature": signature,
                    "cost": 1.0,
                    "reqnum": reqnum,
                    "endpoint": VAST_ENDPOINT_NAME
                },
                "input": {
                    "workflow_json": prompt_workflow
                }
            }
            
            print(f"📦 [SERVERLESS] Отправляю задачу в {target_url} ... (СМОТРИ ЛОГИ С СЕРВЕРА НИЖЕ 👇)")
            
            async with session.post(target_url, json=worker_payload, ssl=False, timeout=0) as worker_resp:
                worker_text = await worker_resp.text()
                
                if worker_resp.status != 200:
                    raise Exception(f"Ошибка видюхи ({worker_resp.status}): {worker_text}")
                    
                print("\n✅ [SERVERLESS] ЗАДАЧА ВЫПОЛНЕНА УСПЕШНО!")
                
                try:
                    worker_data = json.loads(worker_text) if "{" in worker_text else {}
                except:
                    worker_data = {}
                    
        return web.json_response({"status": "ok", "task_id": worker_data.get("id", "vast_task")})
        
    except Exception as e:
        print(f"\n❌ [SERVERLESS] ОШИБКА:")
        traceback.print_exc()
        return web.json_response({"status": "error", "message": str(e)}, status=500)


# --- ФОНОВЫЙ СЛУШАТЕЛЬ SMEE.IO (ТЕПЕРЬ ПЕЧАТАЕТ В ЧЕРНУЮ КОНСОЛЬ!) ---
async def smee_listener():
    if not SMEE_URL or "СЮДА_ВСТАВЬ" in SMEE_URL:
        return

    while True:
        try:
            print(f"🔌 [SMEE] Подключаемся к облаку {SMEE_URL} для перехвата логов...")
            async with aiohttp.ClientSession() as session:
                async with session.get(SMEE_URL, headers={"Accept": "text/event-stream"}) as resp:
                    async for line_bytes in resp.content:
                        line = line_bytes.decode('utf-8').strip()
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "ready": continue
                            try:
                                payload = json.loads(data_str)
                                body = payload.get("body", {}) 
                                if "event" in body and "data" in body:
                                    # Оставляем прокидывание в браузер на всякий случай
                                    PromptServer.instance.send_sync(body["event"], body["data"])
                                    
                                    # !!! ВЫВОДИМ В ЧЕРНУЮ КОНСОЛЬ ВИНДЫ !!!
                                    if body["event"] == "vast_log_message":
                                        text = body["data"].get("text", "")
                                        sys.stdout.write(f"☁️[VAST]: {text}")
                                        sys.stdout.flush()
                            except:
                                pass
        except Exception as e:
            print(f"❌ [SMEE] Обрыв связи. Переподключение через 5 секунд...")
            await asyncio.sleep(5)

PromptServer.instance.loop.create_task(smee_listener())