import os
import aiohttp
import asyncio
from server import PromptServer

# Твой публичный URL от Ngrok или Cloudflare, куда Vast будет слать инфу
WEBHOOK_URL = os.environ.get("LOCAL_WEBHOOK_URL", "")

original_send_sync = PromptServer.instance.send_sync

def hooked_send_sync(event, data, sid=None):
    # Оставляем оригинальную функцию рабочей
    original_send_sync(event, data, sid)
    
    # Если URL задан, асинхронно пушим данные тебе на комп
    if WEBHOOK_URL:
        async def send_to_local():
            async with aiohttp.ClientSession() as session:
                payload = {"event": event, "data": data}
                try:
                    await session.post(WEBHOOK_URL, json=payload)
                except Exception as e:
                    pass # Игнорим, если сеть моргнула
        
        loop = asyncio.get_event_loop()
        loop.create_task(send_to_local())

# Подменяем системную функцию ComfyUI на нашу
PromptServer.instance.send_sync = hooked_send_sync