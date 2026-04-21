import os
import subprocess
import re
from server import PromptServer

class ServerlessSetupNode:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "civitai_token": ("STRING", {"default": "", "tooltip": "Токен CivitAI (без пробелов)"}),
                "hf_token":      ("STRING", {"default": "", "tooltip": "Токен HuggingFace"}),
            },
            "optional": {
                # ── Pip библиотеки ────────────────────────────────────────────
                "pip_libs": ("STRING", {"multiline": True, "default":
                    "# по одной на строку, поддерживает git+https://\n"
                    "# onnxruntime\n# mediapipe\n# insightface\n"
                }),

                # ── Модели — каждое поле принимает ссылки по одной на строку ─
                # Поддерживаемые форматы:
                #   https://civitai.com/models/12345
                #   https://civitai.com/models/12345?modelVersionId=67890
                #   https://civitai.com/api/download/models/67890
                #   https://huggingface.co/author/repo/resolve/main/file.safetensors
                #   https://любой-прямой-url.com/file.safetensors
                "checkpoints": ("STRING", {"multiline": True, "default":
                    "# CivitAI: https://civitai.com/models/4384\n"
                    "# HF: https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned.safetensors\n"
                }),
                "loras": ("STRING", {"multiline": True, "default":
                    "# CivitAI LoRA: https://civitai.com/models/12345?modelVersionId=67890\n"
                }),
                "diffusion_models": ("STRING", {"multiline": True, "default": ""}),
                "vae":              ("STRING", {"multiline": True, "default": ""}),
                "clip":             ("STRING", {"multiline": True, "default": ""}),
                "text_encoders":    ("STRING", {"multiline": True, "default": ""}),
                "controlnets":      ("STRING", {"multiline": True, "default": ""}),
                "upscale_models":   ("STRING", {"multiline": True, "default": ""}),

                # ── Произвольные загрузки ────────────────────────────────────
                "custom_downloads": ("STRING", {"multiline": True, "default":
                    "# ФОРМАТ: URL | /полный/путь/к/файлу\n"
                    "# https://example.com/model.safetensors | /workspace/ComfyUI/models/sams/model.safetensors\n"
                }),

                # ── Кастомные ноды ───────────────────────────────────────────
                "custom_nodes": ("STRING", {"multiline": True, "default":
                    "# Git URL кастомных нод, по одной на строку\n"
                    "# https://github.com/ltdrdata/ComfyUI-Impact-Pack\n"
                }),

                # ── Флаги ────────────────────────────────────────────────────
                "force_reinstall": ("BOOLEAN", {"default": False,
                    "tooltip": "Перескачать все файлы даже если они есть"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "run_setup"
    CATEGORY = "Serverless/Setup"
    OUTPUT_NODE = True

    def _log(self, text):
        print(text, end="")
        PromptServer.instance.send_sync("vast_log_message", {"text": text})

    def run_setup(self, civitai_token, hf_token,
                  pip_libs="", checkpoints="", diffusion_models="",
                  vae="", clip="", text_encoders="", loras="",
                  controlnets="", upscale_models="", custom_downloads="",
                  custom_nodes="", force_reinstall=False):

        civitai_token = civitai_token.strip()
        hf_token      = hf_token.strip()

        self._log("🔥 Формируем скрипт закачки...\n")

        bash = "#!/bin/bash\nset -e\n"
        bash += "mkdir -p /workspace/ComfyUI/models/my_libs\n"

        # ── pip ───────────────────────────────────────────────────────────────
        libs = [l.strip() for l in pip_libs.split("\n")
                if l.strip() and not l.strip().startswith("#")]
        if libs:
            bash += (f"pip install --retries 1 --default-timeout 30 "
                     f"--target /workspace/ComfyUI/models/my_libs "
                     f"{' '.join(libs)}\n")

        # ── кастомные ноды ────────────────────────────────────────────────────
        node_urls = [l.strip() for l in custom_nodes.split("\n")
                     if l.strip() and not l.strip().startswith("#")]
        for url in node_urls:
            name = url.rstrip("/").split("/")[-1].replace(".git", "")
            dest = f"/workspace/ComfyUI/custom_nodes/{name}"
            bash += (
                f"if [ ! -d \"{dest}\" ]; then\n"
                f"  echo \"📦 Клонируем ноду: {name}\"\n"
                f"  git clone --depth 1 \"{url}\" \"{dest}\"\n"
                f"  if [ -f \"{dest}/requirements.txt\" ]; then\n"
                f"    pip install --retries 1 --default-timeout 30 "
                f"--target /workspace/ComfyUI/models/my_libs "
                f"-r \"{dest}/requirements.txt\" || true\n"
                f"  fi\n"
                f"else\n"
                f"  echo \"✅ Уже есть: {name}\"\n"
                f"fi\n"
            )

        # ── вспомогательная функция wget ──────────────────────────────────────
        def get_wget(url, out_dir=None, out_file=None):
            url = url.strip()
            if not url or url.startswith("#"):
                return ""

            # Конвертируем CivitAI веб-ссылки в API
            if "civitai.com" in url and "/api/download/" not in url:
                v = re.search(r'modelVersionId=(\d+)', url)
                m = re.search(r'/models/(\d+)', url)
                if v:
                    url = f"https://civitai.com/api/download/models/{v.group(1)}"
                elif m:
                    url = f"https://civitai.com/api/download/models/{m.group(1)}"

            auth = ""
            if "civitai.com" in url and civitai_token:
                sep = "&" if "?" in url else "?"
                url += f"{sep}token={civitai_token}"
            if "huggingface.co" in url and hf_token:
                auth = f'--header="Authorization: Bearer {hf_token}"'

            nc_flag = "" if force_reinstall else "--no-clobber"

            if out_file:
                out_file = out_file.strip()
                d = os.path.dirname(out_file)
                skip = "" if force_reinstall else f'[ -f "{out_file}" ] && echo "✅ Пропуск: {out_file}" ||'
                return (
                    f"mkdir -p {d}\n"
                    f"{skip} wget --tries=2 --timeout=60 {auth} "
                    f"-O \"{out_file}\" \"{url}\" || "
                    f"{{ rm -f \"{out_file}\"; echo \"❌ Ошибка: {url}\"; exit 1; }}\n"
                )
            elif out_dir:
                return (
                    f"mkdir -p {out_dir}\n"
                    f"wget --tries=2 --timeout=60 --content-disposition "
                    f"--trust-server-names {nc_flag} {auth} -P {out_dir} \"{url}\" || "
                    f"{{ echo \"❌ Ошибка: {url}\"; exit 1; }}\n"
                )
            return ""

        # ── модели по категориям ──────────────────────────────────────────────
        categories = [
            (checkpoints,      "/workspace/ComfyUI/models/checkpoints"),
            (diffusion_models, "/workspace/ComfyUI/models/diffusion_models"),
            (vae,              "/workspace/ComfyUI/models/vae"),
            (clip,             "/workspace/ComfyUI/models/clip"),
            (text_encoders,    "/workspace/ComfyUI/models/text_encoders"),
            (loras,            "/workspace/ComfyUI/models/loras"),
            (controlnets,      "/workspace/ComfyUI/models/controlnet"),
            (upscale_models,   "/workspace/ComfyUI/models/upscale_models"),
        ]
        for field, out_dir in categories:
            for link in field.split("\n"):
                bash += get_wget(link, out_dir=out_dir)

        # ── custom_downloads (URL | /path) ────────────────────────────────────
        for line in custom_downloads.split("\n"):
            line = line.strip()
            if "|" in line and not line.startswith("#"):
                parts = line.split("|", 1)
                if len(parts) == 2:
                    bash += get_wget(parts[0], out_file=parts[1])

        # ── запускаем ─────────────────────────────────────────────────────────
        with open("/tmp/vast_setup.sh", "w") as f:
            f.write(bash)

        log_path = "/workspace/ComfyUI/models/setup_log.txt"
        self._log(f"🚀 Запускаем скрипт. Лог → {log_path}\n")

        proc = subprocess.Popen(
            ["bash", "/tmp/vast_setup.sh"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )

        with open(log_path, "w", encoding="utf-8") as log_f:
            for line in iter(proc.stdout.readline, ""):
                print(line, end="")
                log_f.write(line)
                log_f.flush()
                PromptServer.instance.send_sync("vast_log_message", {"text": line})

        proc.wait()

        if proc.returncode != 0:
            self._log("❌ ОШИБКА! Смотри логи выше.\n")
            raise RuntimeError("setup_node: script failed")

        self._log("✅✅✅ ВСЕ ЗАГРУЖЕНО УСПЕШНО!\n")
        return ("OK",)
