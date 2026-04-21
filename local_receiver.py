"""
VAST Serverless Bridge — Local Receiver
Перехватывает Manager, создаёт стабы нод, синкает с сервером.
"""
import os
import json
import asyncio
import aiohttp
import traceback
import base64
import sys
import re
from server import PromptServer
from aiohttp import web
import folder_paths

from .config_loader import (
    LOCAL_DOCKER_TEST,
    LOCAL_WORKER_URL,
    VAST_API_KEY,
    VAST_ENDPOINT_NAME,
    DEBUG_SSE
)

current_log_task = None
_last_worker_url = ""
_last_auth_data = {}

STUB_MARKER = b"VAST_STUB"

_MODEL_DIR_MAP = {
    "audio_encoders": "audio", "checkpoints": "checkpoints", "clip": "clip",
    "clip_vision": "clip_vision", "configs": "configs", "controlnet": "controlnet",
    "diffusers": "diffusers", "diffusion_models": "diffusion_models",
    "embeddings": "embeddings", "gligen": "gligen", "hypernetworks": "hypernetworks",
    "latent_upscale_models": "latent_upscale_models", "loras": "loras",
    "model_patches": "model_patches", "photomaker": "photomaker",
    "style_models": "style_models", "text_encoders": "text_encoders",
    "unet": "unet", "upscale_models": "upscale_models", "vae": "vae",
    "vae_approx": "vae_approx",
}

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_MANIFEST_PATH = os.path.join(_PLUGIN_DIR, "vast_node_manifest.json")


# ── МАНИФЕСТ ──────────────────────────────────────────────────────────────────

def _load_manifest() -> dict:
    try:
        if os.path.exists(_MANIFEST_PATH):
            with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[VAST MANIFEST] Ошибка чтения: {e}")
    return {"packs": [], "classes": {}}


def _save_manifest(manifest: dict):
    try:
        with open(_MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        packs = len(manifest.get("packs", []))
        classes = len(manifest.get("classes", {}))
        print(f"[VAST MANIFEST] Сохранено: {packs} паков, {classes} классов")
    except Exception as e:
        print(f"[VAST MANIFEST] Ошибка записи: {e}")


def _make_stub_class(cls_name: str, info: dict):
    input_cfg = info.get("input") or {"required": {}}
    raw_output = info.get("output") or []
    raw_names = info.get("output_name") or []
    output = tuple(v if isinstance(v, str) else "*" for v in raw_output)
    out_names = tuple(v if isinstance(v, str) else "" for v in raw_names)
    category = info.get("category") or "Remote"
    is_output = bool(info.get("output_node", False))
    _output = output

    def execute_stub(self, **kwargs):
        n = len(_output) if _output else 1
        return tuple([None] * n)

    stub = type(cls_name, (), {
        "INPUT_TYPES": classmethod(lambda cls, cfg=input_cfg: cfg),
        "RETURN_TYPES": output, "RETURN_NAMES": out_names,
        "FUNCTION": "execute", "CATEGORY": category + " ☁️",
        "OUTPUT_NODE": is_output, "execute": execute_stub,
    })
    return stub


def _register_stubs_from_manifest():
    import nodes as comfy_nodes
    manifest = _load_manifest()
    classes = manifest.get("classes", {})
    if not classes:
        print("[VAST MANIFEST] Нет сохранённых нод")
        return
    SYSTEM_LOWER = {"comfyui-manager", "comfyui-serverless-bridge",
                    "comfyui_serverles_bridge", "comfyui_serverless_bridge",
                    "websocket_image_save"}
    packs = [p for p in manifest.get("packs", [])
             if p.lower().replace("-", "_") not in SYSTEM_LOWER]
    if len(packs) != len(manifest.get("packs", [])):
        manifest["packs"] = packs
        _save_manifest(manifest)
    registered = 0
    for cls_name, info in classes.items():
        if cls_name in comfy_nodes.NODE_CLASS_MAPPINGS:
            continue
        try:
            stub = _make_stub_class(cls_name, info)
            comfy_nodes.NODE_CLASS_MAPPINGS[cls_name] = stub
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS[cls_name] = \
                (info.get("display_name") or cls_name) + " ☁️"
            registered += 1
        except Exception as e:
            print(f"[VAST MANIFEST] {cls_name}: {e}")
    print(f"[VAST MANIFEST] ✅ {registered} стаб-нод")


_register_stubs_from_manifest()


# ── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ──────────────────────────────────────────────────

def _get_worker_url() -> str:
    global _last_worker_url
    if LOCAL_DOCKER_TEST:
        return LOCAL_WORKER_URL
    return _last_worker_url


def normalize(data, extra=None):
    if not isinstance(data, dict):
        return data or {}
    out = dict(data)
    out["prompt_id"] = "vast_job_from_ui"
    if "node_id" in out and "node" not in out:
        out["node"] = out.pop("node_id")
    if extra:
        out.update(extra)
    return out


async def _fetch_server_object_info(worker_url: str) -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                worker_url.rstrip("/") + "/object_info",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        print(f"[VAST] object_info недоступен: {e}")
    return {}


# ── УСТАНОВКА НОДЫ ──────────────────────────────────────────────────────────

async def _install_node_on_server(git_url: str):
    worker_url = _get_worker_url()
    pack_name = git_url.rstrip("/").split("/")[-1].replace(".git", "")

    print(f"[VAST] 📦 Установка: {pack_name}")
    PromptServer.instance.send_sync("vast_install_progress", {
        "text": f"📦 Установка {pack_name} на сервере..."})

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                worker_url.rstrip("/") + "/install_node",
                json={"git_url": git_url},
                timeout=aiohttp.ClientTimeout(total=180)
            ) as resp:
                print(f"[VAST] Сервер install: {resp.status} {(await resp.text())[:100]}")
    except Exception as e:
        print(f"[VAST] ❌ Ошибка установки: {e}")
        PromptServer.instance.send_sync("vast_install_done", {"text": f"❌ {e}"})
        return

    PromptServer.instance.send_sync("vast_install_progress", {"text": "🔄 Рестарт ComfyUI..."})
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                worker_url.rstrip("/") + "/kill_comfy",
                timeout=aiohttp.ClientTimeout(total=10))
    except Exception:
        pass

    import nodes as comfy_nodes
    known = set(comfy_nodes.NODE_CLASS_MAPPINGS.keys())

    for attempt in range(24):
        await asyncio.sleep(5)
        PromptServer.instance.send_sync("vast_install_progress", {
            "text": f"⏳ Ждём ComfyUI... ({attempt+1}/24)"})
        info = await _fetch_server_object_info(worker_url)
        if info:
            new = {k: v for k, v in info.items() if k not in known}
            if new:
                print(f"[VAST] ✅ {len(new)} новых классов")
                break
    else:
        PromptServer.instance.send_sync("vast_install_done", {
            "text": f"⚠️ {pack_name} установлен, ноды не найдены"})
        return

    manifest = _load_manifest()
    if pack_name not in manifest["packs"]:
        manifest["packs"].append(pack_name)
    reg = 0
    for cls_name, cls_info in info.items():
        if cls_name in known:
            continue
        manifest["classes"][cls_name] = {
            "pack": pack_name,
            "input": cls_info.get("input", {"required": {}}),
            "output": cls_info.get("output", []),
            "output_name": cls_info.get("output_name", []),
            "category": cls_info.get("category", "remote"),
            "output_node": cls_info.get("output_node", False),
            "display_name": cls_info.get("display_name") or cls_name,
        }
        try:
            stub = _make_stub_class(cls_name, manifest["classes"][cls_name])
            comfy_nodes.NODE_CLASS_MAPPINGS[cls_name] = stub
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS[cls_name] = \
                (cls_info.get("display_name") or cls_name) + " ☁️"
            reg += 1
        except Exception as e:
            print(f"[VAST] {cls_name}: {e}")

    _save_manifest(manifest)
    print(f"[VAST] ✅ {pack_name}: {reg} нод")
    PromptServer.instance.send_sync("vast_install_done", {
        "text": f"✅ {pack_name}: {reg} нод", "count": reg, "pack": pack_name})


async def _uninstall_node(pack_name: str):
    import nodes as comfy_nodes
    worker_url = _get_worker_url()
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                worker_url.rstrip("/") + "/customnode/uninstall",
                data=pack_name, headers={"Content-Type": "text/plain"},
                timeout=aiohttp.ClientTimeout(total=60))
    except Exception as e:
        print(f"[VAST] Uninstall: {e}")

    manifest = _load_manifest()
    removed = [c for c, i in manifest["classes"].items() if i.get("pack") == pack_name]
    for c in removed:
        manifest["classes"].pop(c, None)
        comfy_nodes.NODE_CLASS_MAPPINGS.pop(c, None)
        comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.pop(c, None)
    if pack_name in manifest["packs"]:
        manifest["packs"].remove(pack_name)
    _save_manifest(manifest)
    print(f"[VAST] 🗑 {pack_name}: {len(removed)} классов")
    PromptServer.instance.send_sync("vast_install_done", {
        "text": f"🗑 {pack_name} ({len(removed)} нод)"})


async def _ensure_server_has_workflow_nodes(worker_url: str, workflow: dict):
    manifest = _load_manifest()
    if not manifest["classes"]:
        return
    wtypes = {n["class_type"] for n in workflow.values()
              if isinstance(n, dict) and "class_type" in n}
    sinfo = await _fetch_server_object_info(worker_url)
    if not sinfo:
        return
    missing = {manifest["classes"][c]["pack"]
               for c in wtypes - set(sinfo)
               if c in manifest["classes"] and manifest["classes"][c].get("pack")}
    if not missing:
        return
    print(f"[VAST] ⚠️ Серверу нужны: {missing}")
    PromptServer.instance.send_sync("vast_install_progress", {
        "text": f"⚠️ Устанавливаем: {', '.join(missing)}"})
    urls = manifest.get("pack_urls", {})
    to_install = [urls[p] for p in missing if p in urls]
    if not to_install:
        PromptServer.instance.send_sync("vast_install_progress", {
            "text": f"❌ Нет URL для {missing}"})
        return
    try:
        async with aiohttp.ClientSession() as session:
            r = await (await session.post(
                worker_url.rstrip("/") + "/batch_install",
                json={"urls": to_install},
                timeout=aiohttp.ClientTimeout(total=60))).json()
            print(f"[VAST] batch_install: {r}")
        async with aiohttp.ClientSession() as session:
            await session.post(
                worker_url.rstrip("/") + "/kill_comfy",
                timeout=aiohttp.ClientTimeout(total=10))
        PromptServer.instance.send_sync("vast_install_progress", {
            "text": "🔄 Ждём перезапуск..."})
        for _ in range(30):
            await asyncio.sleep(4)
            try:
                async with aiohttp.ClientSession() as session:
                    rd = await (await session.get(
                        worker_url.rstrip("/") + "/health",
                        timeout=aiohttp.ClientTimeout(total=5))).json()
                    if rd.get("comfy_ready"):
                        break
            except Exception:
                pass
        PromptServer.instance.send_sync("vast_install_done", {
            "text": f"✅ Паки: {', '.join(missing)}"})
    except Exception as e:
        print(f"[VAST] Авто-установка: {e}")


# ── MIDDLEWARE ───────────────────────────────────────────────────────────────

@web.middleware
async def vast_manager_interceptor(request, handler):
    path = str(request.path)
    method = request.method

    if method == "POST" and path.endswith("/api/manager/queue/install"):
        try:
            data = await request.json()
            git_url = (data.get("repository") or data.get("reference")
                       or (data.get("files") or [""])[0])
            if git_url and ("github" in git_url or "gitlab" in git_url):
                print(f"\n[VAST] 📦 Manager V3 install: {git_url}")
                asyncio.create_task(_install_node_on_server(git_url))
                return web.json_response({"install": 1, "message": "Forwarded to Vast"})
        except Exception as e:
            print(f"[VAST] V3 install: {e}")

    if method == "POST" and path.endswith("/api/manager/queue/uninstall"):
        try:
            data = await request.json()
            node_id = data.get("id", "")
            if node_id:
                print(f"\n[VAST] 🗑 Manager V3 uninstall: {node_id}")
                asyncio.create_task(_uninstall_node(node_id))
                return web.json_response({"uninstall": 1})
        except Exception as e:
            print(f"[VAST] V3 uninstall: {e}")

    if method == "POST" and "install" in path and "customnode" in path and "model" not in path:
        try:
            body = await request.read()
            body_str = body.decode("utf-8", errors="replace")
            git_url = None
            try:
                data = json.loads(body_str)
                git_url = (data.get("repository") or data.get("git_url")
                           or data.get("url") or data.get("id"))
            except Exception:
                if body_str.startswith("http"):
                    git_url = body_str.strip()
            if git_url and ("github" in git_url or "gitlab" in git_url):
                print(f"\n[VAST] 📦 Manager V2 install: {git_url}")
                asyncio.create_task(_install_node_on_server(git_url))
                return web.json_response({
                    "status": "success", "task_id": "vast_install", "result": True})
        except Exception as e:
            print(f"[VAST] V2 install: {e}")

    return await handler(request)


PromptServer.instance.app.middlewares.append(vast_manager_interceptor)
print("[VAST] 🔥 Manager interceptor installed!")


# ── МОДЕЛИ ──────────────────────────────────────────────────────────────────

async def sync_remote_models(worker_url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                worker_url.rstrip("/") + "/list_models",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    await _sync_from_data(await resp.json())
    except Exception as e:
        print(f"[VAST SYNC] {e}")


async def _sync_from_data(model_list: dict):
    created = 0
    for category, files in model_list.items():
        dir_key = _MODEL_DIR_MAP.get(category)
        if not dir_key:
            continue
        try:
            dirs = folder_paths.get_folder_paths(dir_key)
            local_dir = dirs[0] if dirs else None
        except Exception:
            local_dir = None
        if not local_dir:
            continue
        for rel_path in (files or []):
            lp = os.path.join(local_dir, rel_path)
            if os.path.exists(lp) and os.path.getsize(lp) > len(STUB_MARKER) * 2:
                continue
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            try:
                with open(lp, "wb") as f:
                    f.write(STUB_MARKER)
                created += 1
            except Exception:
                pass
    if created:
        print(f"[VAST SYNC] +{created} заглушек моделей")


# ── SSE СЛУШАТЕЛЬ ────────────────────────────────────────────────────────────

async def vast_log_listener(stream_url: str, auth_data: dict = None):
    print(f"[VAST LOGS] → {stream_url}")
    headers = {"Accept": "text/event-stream"}
    if auth_data and auth_data.get("signature"):
        headers["Authorization"] = f"Bearer {auth_data['signature']}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                stream_url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=None),
            ) as resp:
                # iter_chunks() yields (bytes, bool) tuples — unpack correctly.
                buf = b""
                async for chunk_data, _ in resp.content.iter_chunks():
                    buf += chunk_data
                    # Обрабатываем все законченные строки в буфере
                    while b"\n" in buf:
                        line_bytes, buf = buf.split(b"\n", 1)
                        line = line_bytes.decode("utf-8", errors="replace").rstrip("\r")
                        if not line:
                            # Пустая строка — конец события в SSE
                            continue

                        event_type = None
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                            continue

                        if not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if not data_str:
                            continue

                        try:
                            data = json.loads(data_str)
                        except Exception:
                            continue

                        if event_type: _dispatch_sse_event(event_type, data)

    except Exception as e:
        print(f"[VAST LOGS] Обрыв: {e}")
        traceback.print_exc()


def _dispatch_sse_event(event_type: str, data: dict):
    """Диспетчеризация SSE-события в ComfyUI UI."""
    if event_type == "vast_log_message":
        txt = data.get("text", "")
        sys.stdout.write(f"[VAST]: {txt}")
        sys.stdout.flush()
        PromptServer.instance.send_sync("vast_log_message", data)
    elif event_type == "node_preview":
        try:
            img = base64.b64decode(data["image_b64"])
            nid = data.get("node_id", data.get("node", "img"))
            fn = data.get("filename", f"vast_{nid}.png")
            out_dir = folder_paths.get_output_directory()
            fp = os.path.join(out_dir, fn)
            with open(fp, "wb") as f:
                f.write(img)
            if data.get("type") == "image_output":
                PromptServer.instance.send_sync("executed", {
                    "node": nid, "prompt_id": "vast_job_from_ui",
                    "output": {"images": [{
                        "filename": fn, "type": "output", "subfolder": ""}]},
                })
        except Exception as ex:
            print(f"[VAST PREVIEW] {ex}")
    elif event_type == "workflow_start":
        PromptServer.instance.send_sync("execution_start", {"prompt_id": "vast_job_from_ui"})
    elif event_type in ("node_executing", "executing"):
        PromptServer.instance.send_sync("executing", normalize(data))
    elif event_type in ("node_progress", "progress"):
        PromptServer.instance.send_sync("progress", normalize(data))
    elif event_type in ("node_done", "executed"):
        PromptServer.instance.send_sync("executed", normalize(data))
    elif event_type == "execution_error":
        nd = normalize(data)
        print(f"[VAST] execution_error: {nd}")
        PromptServer.instance.send_sync("execution_error", nd)
    elif event_type == "workflow_done":
        print("[VAST] ✅ workflow_done!")
        PromptServer.instance.send_sync("workflow_done", data)
        PromptServer.instance.send_sync("status", {"status": {"exec_info": {"queue_remaining": 0}}})
        PromptServer.instance.send_sync("executing", {"node": None, "prompt_id": "vast_job_from_ui"})
        asyncio.create_task(sync_remote_models(_get_worker_url()))
    elif event_type == "workflow_error":
        print(f"[VAST] workflow_error: {data}")
        PromptServer.instance.send_sync("workflow_error", data)
        PromptServer.instance.send_sync("executing", {"node": None, "prompt_id": "vast_job_from_ui"})
    elif event_type == "download_start":
        fn = data.get("file", "file")
        print(f"[VAST] ⬇️ {fn} — скачивание")
        PromptServer.instance.send_sync("progress", {
            "value": 0, "max": 100, "node": "download",
            "prompt_id": "vast_job_from_ui"})
    elif event_type == "download_progress":
        pct = data.get("percent", 0)
        fn = data.get("file", "file")
        sys.stdout.write(f"\r[VAST] ⬇️ {fn}: {pct}%")
        sys.stdout.flush()
    elif event_type == "download_done":
        fn = data.get("file", "file")
        print(f"\n[VAST] ✅ {fn} скачан")
    elif event_type == "download_error":
        fn = data.get("file", "file")
        err = data.get("error", "")
        print(f"[VAST] ❌ {fn}: {err}")
    elif event_type == "queued":
        print(f"[VAST] ⏳ Workflow в очереди: {data.get('prompt_id','')}")
    elif event_type == "comfy_status":
        print(f"[VAST] ComfyUI: {data.get('status','')}")
    elif event_type == "model_list_update":
        asyncio.create_task(_sync_from_data(data))
    elif DEBUG_SSE:
        print(f"[SSE] {event_type}: {str(data)[:80]}")


# ── HTTP ЭНДПОИНТЫ ────────────────────────────────────────────────────────────

@PromptServer.instance.routes.post("/vast_forward")
async def vast_forward(request):
    global current_log_task, _last_worker_url, _last_auth_data
    try:
        data = await request.json()
        prompt_workflow = data.get("prompt")
        worker_url = None
        auth_data = {}

        if LOCAL_DOCKER_TEST:
            print(f"\n[VAST] LOCAL TEST → {LOCAL_WORKER_URL}")
            worker_url = LOCAL_WORKER_URL
        else:
            print(f"\n[VAST] Будим Vast ({VAST_ENDPOINT_NAME})...")
            async with aiohttp.ClientSession() as session:
                while not worker_url:
                    async with session.post(
                        "https://run.vast.ai/route/",
                        json={"endpoint": VAST_ENDPOINT_NAME, "api_key": VAST_API_KEY, "cost": 1.0}
                    ) as resp:
                        text = await resp.text()
                        if resp.status in (502, 503, 504) or "loading" in text.lower():
                            print("[VAST] Warming up... 5 sec")
                            await asyncio.sleep(5)
                            continue
                        if resp.status != 200:
                            raise Exception(f"Router ({resp.status}): {text}")

                        rd = json.loads(text)
                        worker_url = rd.get("url")

                        # ВАЖНО: /route/ возвращает auth_data ПЛОСКИМИ ключами в корне!
                        auth_data = {
                            "signature":   rd.get("signature"),
                            "endpoint":   rd.get("endpoint"),
                            "cost":        rd.get("cost"),
                            "reqnum":      rd.get("reqnum"),
                            "request_idx": rd.get("request_idx"),
                            "url":         rd.get("url"),
                        }

                        print(f"[VAST] /route/ keys: {list(rd.keys())}")
                        print(f"[VAST] auth_data: {auth_data}")
                        if auth_data.get("signature"):
                            print(f"[VAST] auth_data signature: {str(auth_data['signature'])[:20]}...")

                        if not worker_url:
                            print(f"[VAST] Нет URL: {rd}")
                            await asyncio.sleep(5)
                            continue

                        if re.match(r'https?://(172\.|10\.|192\.168\.|127\.|0\.0\.0\.0)', worker_url):
                            print(f"[VAST] Внутренний URL → публичный прокси")
                            worker_url = f"https://{VAST_ENDPOINT_NAME}.run.vast.ai"

        _last_worker_url = worker_url
        _last_auth_data = auth_data
        print(f"[VAST] URL: {worker_url}")

        await sync_remote_models(worker_url)
        if prompt_workflow:
            await _ensure_server_has_workflow_nodes(worker_url, prompt_workflow)

        stream_url = worker_url.rstrip("/") + "/logs"
        if current_log_task:
            current_log_task.cancel()
        current_log_task = asyncio.create_task(vast_log_listener(stream_url, auth_data))

        await asyncio.sleep(0.5)
        PromptServer.instance.send_sync("status", {"status": {"exec_info": {"queue_remaining": 1}}})
        PromptServer.instance.send_sync("execution_start", {"prompt_id": "vast_job_from_ui"})
        PromptServer.instance.send_sync("execution_cached", {"nodes": [], "prompt_id": "vast_job_from_ui"})

        run_body = {
            "auth_data": auth_data,
            "payload": {
                "id": "vast_job_from_ui",
                "workflow": prompt_workflow,
                "downloads": [],
            },
        }

        if auth_data.get("signature"):
            print(f"[VAST] ✅ auth_data с подписью: {str(auth_data['signature'])[:15]}...")
        else:
            print(f"[VAST] ⚠️ auth_data БЕЗ подписи — может вызвать ошибку на воркере")

        print(f"[VAST] → /run body keys: {list(run_body.keys())}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                worker_url.rstrip("/") + "/run",
                json=run_body,
                timeout=aiohttp.ClientTimeout(total=None),
            ) as wr:
                text = await wr.text()
                if wr.status != 202:
                    print(f"[VAST] Worker error ({wr.status}): {text}")
                    raise Exception(f"Worker ({wr.status}): {text}")

        return web.json_response({"status": "ok", "task_id": "vast_job_from_ui"})

    except Exception as e:
        print(f"\n[VAST] ❌ Error: {e}")
        traceback.print_exc()
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@PromptServer.instance.routes.post("/vast_interrupt")
async def vast_interrupt(request):
    worker_url = _get_worker_url()
    if not worker_url:
        return web.json_response({"status": "error", "message": "No active worker"}, status=400)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                worker_url.rstrip("/") + "/interrupt",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    PromptServer.instance.send_sync("vast_interrupt_done", {"text": "✅ Прервано!"})
                    return web.json_response({"status": "ok"})
                return web.json_response({"status": "error", "message": await resp.text()}, status=resp.status)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@PromptServer.instance.routes.post("/vast_install_node")
async def vast_install_node_endpoint(request):
    try:
        data = await request.json()
        git_url = data.get("git_url", "").strip()
        if not git_url:
            return web.json_response({"status": "error", "message": "git_url required"}, status=400)
    except Exception:
        return web.json_response({"status": "error", "message": "invalid json"}, status=400)
    asyncio.create_task(_install_node_on_server(git_url))
    return web.json_response({"status": "ok", "message": f"Установка {git_url} запущена"})


@PromptServer.instance.routes.get("/vast_server_nodes_list")
async def vast_server_nodes_list(request):
    manifest = _load_manifest()
    packs = [p for p in manifest.get("packs", [])
             if p.lower().replace("-", "_") not in {"__pycache__", "comfyui-manager",
                    "comfyui-serverless-bridge", "comfyui_serverles_bridge",
                    "websocket_image_save"}]
    worker_url = _get_worker_url()
    server_packs = []
    if worker_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    worker_url.rstrip("/") + "/installed_nodepacks",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status == 200:
                        server_packs = await resp.json()
        except Exception:
            pass

    def norm(s): return s.lower().replace("-", "").replace("_", "")
    canonical = {}
    for p in packs:
        k = norm(p)
        canonical[k] = {"name": p, "in_manifest": True, "on_server": False}
    for p in server_packs:
        if norm(p) not in {"comfyuimanager", "comfyuiserverlessbridge",
                             "comfyuiserverlesbridge", "websocketimagesave"}:
            k = norm(p)
            if k in canonical:
                canonical[k]["on_server"] = True
            else:
                canonical[k] = {"name": p, "in_manifest": False, "on_server": True}

    return web.json_response({"status": "ok", "nodes": list(canonical.values()), "count": len(canonical)})


@PromptServer.instance.routes.post("/vast_uninstall_server_node")
async def vast_uninstall_server_node(request):
    try:
        data = await request.json()
        pack_name = data.get("pack_name", "").strip()
        if not pack_name:
            return web.json_response({"status": "error", "message": "pack_name required"}, status=400)
    except Exception:
        return web.json_response({"status": "error", "message": "invalid json"}, status=400)
    asyncio.create_task(_uninstall_node(pack_name))
    return web.json_response({"status": "ok", "message": f"{pack_name} удаляется"})


@PromptServer.instance.routes.get("/vast_sync_nodes")
async def vast_sync_nodes(request):
    manifest = _load_manifest()
    worker_url = _get_worker_url()
    if not worker_url:
        return web.json_response({"status": "ok", "count": 0,
                                  "nodes": manifest.get("packs", []), "reload_required": False})
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                worker_url.rstrip("/") + "/vast_sync_nodes",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status != 200:
                    return web.json_response({"status": "ok", "count": 0,
                              "nodes": manifest.get("packs", []), "reload_required": False})
                remote = await resp.json()

        server_packs = remote.get("nodes", [])
        def norm(s): return s.lower().replace("-", "").replace("_", "")
        SKIP = {"comfyuimanager", "comfyuiserverlessbridge", "comfyuiserverlesbridge", "websocketimagesave"}
        server_packs = [p for p in server_packs if norm(p) not in SKIP]
        local_set = set(manifest.get("packs", []))
        new_packs = [p for p in server_packs if norm(p) not in {norm(x) for x in local_set}]

        if not new_packs:
            return web.json_response({"status": "ok", "count": 0,
                              "nodes": list(local_set), "reload_required": False})

        print(f"[VAST SYNC] Новые: {new_packs}")
        sinfo = await _fetch_server_object_info(worker_url)
        import nodes as comfy_nodes
        reg = 0
        for pack_name in new_packs:
            if pack_name not in manifest["packs"]:
                manifest["packs"].append(pack_name)
            for cls_name, info in sinfo.items():
                if cls_name in manifest["classes"] or cls_name in comfy_nodes.NODE_CLASS_MAPPINGS:
                    continue
                manifest["classes"][cls_name] = {
                    "pack": pack_name,
                    "input": info.get("input", {"required": {}}),
                    "output": info.get("output", []),
                    "output_name": info.get("output_name", []),
                    "category": info.get("category", "remote"),
                    "output_node": info.get("output_node", False),
                    "display_name": info.get("display_name") or cls_name,
                }
                try:
                    stub = _make_stub_class(cls_name, manifest["classes"][cls_name])
                    comfy_nodes.NODE_CLASS_MAPPINGS[cls_name] = stub
                    comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS[cls_name] = \
                        (info.get("display_name") or cls_name) + " ☁️"
                    reg += 1
                except Exception as e:
                    print(f"[VAST SYNC] {cls_name}: {e}")

        _save_manifest(manifest)
        print(f"[VAST SYNC] Зарегистрировано {reg} нод")
        return web.json_response({"status": "ok", "count": reg,
                          "nodes": manifest.get("packs", []), "reload_required": reg > 0})
    except Exception as e:
        print(f"[VAST SYNC] {e}")
        return web.json_response({"status": "ok", "count": 0,
                          "nodes": manifest.get("packs", []), "reload_required": False})


@PromptServer.instance.routes.get("/vast_sync_models")
async def vast_sync_models_route(request):
    worker_url = _get_worker_url()
    if worker_url:
        asyncio.create_task(sync_remote_models(worker_url))
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.get("/vast_manifest")
async def vast_manifest_route(request):
    return web.json_response(_load_manifest())


@PromptServer.instance.routes.get("/vast_ping")
async def vast_ping_route(request):
    global current_log_task
    worker_url = _get_worker_url()
    if not worker_url:
        return web.json_response({"status": "offline"})
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                worker_url.rstrip("/") + "/health",
                timeout=aiohttp.ClientTimeout(total=2)
            ) as resp:
                if resp.status == 200:
                    if not current_log_task or current_log_task.done():
                        print(f"\n[VAST] 🔄 Восстанавливаем логи: {worker_url}")
                        current_log_task = asyncio.create_task(
                            vast_log_listener(worker_url.rstrip("/") + "/logs", _last_auth_data))
                    return web.json_response({"status": "online"})
    except Exception:
        pass
    return web.json_response({"status": "offline"})


print("[VAST] ☁️ Serverless Bridge loaded!")
