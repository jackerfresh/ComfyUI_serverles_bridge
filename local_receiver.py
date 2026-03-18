import aiohttp
from server import PromptServer
from aiohttp import web

VAST_API_ENDPOINT = "https://<ТУТ_ТВОЙ_VAST_ENDPOINT>"
VAST_API_KEY = "<ТУТ_ТВОЙ_VAST_API_KEY>"

# 1. Отправляем задачу на Vast
@PromptServer.instance.routes.post("/vast_forward")
async def vast_forward(request):
    data = await request.json()
    prompt_workflow = data.get("prompt")
    
    payload = {"workflow": prompt_workflow}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            VAST_API_ENDPOINT, 
            json=payload, 
            headers={"Authorization": f"Bearer {VAST_API_KEY}"}
        ) as resp:
            vast_response = await resp.json()
            
    return web.json_response({"status": "ok", "task_id": vast_response.get("id")})

# 2. Ловим апдейты от сервера Vast и пушим в твой браузер
@PromptServer.instance.routes.post("/vast_webhook")
async def vast_webhook(request):
    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data")
    
    # Симулируем локальную работу
    PromptServer.instance.send_sync(event, data)
    
    return web.Response(status=200)