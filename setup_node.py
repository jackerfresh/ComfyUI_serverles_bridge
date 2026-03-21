import os
import subprocess
import re
from server import PromptServer

class ServerlessSetupNode:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "civitai_token": ("STRING", {"default": ""}),
                "hf_token": ("STRING", {"default": ""}),
                "pip_libs": ("STRING", {"multiline": True, "default": "onnxruntime\nmediapipe\nultralytics\ninsightface\ngit+https://github.com/huggingface/diffusers"}),
                "checkpoints": ("STRING", {"multiline": True, "default": ""}),
                "diffusion_models": ("STRING", {"multiline": True, "default": ""}),
                "vae": ("STRING", {"multiline": True, "default": ""}),
                "clip": ("STRING", {"multiline": True, "default": ""}),
                "text_encoders": ("STRING", {"multiline": True, "default": ""}),
                "loras": ("STRING", {"multiline": True, "default": ""}),
                "controlnets": ("STRING", {"multiline": True, "default": ""}),
                "custom_downloads": ("STRING", {"multiline": True, "default": "# ФОРМАТ: ССЫЛКА | ПОЛНЫЙ_ПУТЬ_К_ФАЙЛУ\n# https://huggingface.co/sam/sam3.pt | /workspace/ComfyUI/models/sams/sam3.pt\n"})
            }
        }
    
    RETURN_TYPES = ("STRING",)
    FUNCTION = "run_setup"
    CATEGORY = "Serverless/Setup"
    OUTPUT_NODE = True 

    def run_setup(self, civitai_token, hf_token, pip_libs, checkpoints, diffusion_models, vae, clip, text_encoders, loras, controlnets, custom_downloads):
        PromptServer.instance.send_sync("vast_log_message", {"text": "🔥 Формируем скрипт закачки...\n"})
        
        bash_script = "#!/bin/bash\n"
        # Устанавливаем библиотеки ПРЯМО НА ВЕЧНЫЙ ДИСК (через портал)
        bash_script += "mkdir -p /workspace/ComfyUI/models/my_libs\n"
        
        libs = " ".join([l.strip() for l in pip_libs.split("\n") if l.strip()])
        if libs:
            bash_script += f"pip install --target /workspace/ComfyUI/models/my_libs {libs}\n"
        
        def get_wget(url, out_dir=None, out_file=None):
            url = url.strip()
            if not url or url.startswith("#"): return ""
            auth_header = ""
            
            if "civitai.com" in url:
                if "/api/download/models/" not in url:
                    v_match = re.search(r'modelVersionId=(\d+)', url)
                    if v_match:
                        url = f"https://civitai.com/api/download/models/{v_match.group(1)}"
                    else:
                        m_match = re.search(r'/models/(\d+)', url)
                        if m_match:
                            url = f"https://civitai.com/api/download/models/{m_match.group(1)}"
                if civitai_token:
                    sep = "&" if "?" in url else "?"
                    url += f"{sep}token={civitai_token}"
                    
            if "huggingface.co" in url and hf_token:
                auth_header = f'--header="Authorization: Bearer {hf_token}"'
            
            if out_file:
                out_file = out_file.strip()
                d_name = os.path.dirname(out_file)
                cmd = f"mkdir -p {d_name}\n"
                cmd += f"if [ ! -f \"{out_file}\" ]; then wget {auth_header} -O \"{out_file}\" \"{url}\"; else echo \"✅ Пропускаем (уже есть): {out_file}\"; fi\n"
                return cmd
            elif out_dir:
                cmd = f"mkdir -p {out_dir}\n"
                cmd += f"wget -nc --content-disposition --trust-server-names {auth_header} -P {out_dir} \"{url}\"\n"
                return cmd
            return ""

        # Указываем правильные пути для всех категорий (через портал /workspace/)
        for link in checkpoints.split("\n"): bash_script += get_wget(link, out_dir="/workspace/ComfyUI/models/checkpoints")
        for link in diffusion_models.split("\n"): bash_script += get_wget(link, out_dir="/workspace/ComfyUI/models/diffusion_models")
        for link in vae.split("\n"): bash_script += get_wget(link, out_dir="/workspace/ComfyUI/models/vae")
        for link in clip.split("\n"): bash_script += get_wget(link, out_dir="/workspace/ComfyUI/models/clip")
        for link in text_encoders.split("\n"): bash_script += get_wget(link, out_dir="/workspace/ComfyUI/models/text_encoders")
        for link in loras.split("\n"): bash_script += get_wget(link, out_dir="/workspace/ComfyUI/models/loras")
        for link in controlnets.split("\n"): bash_script += get_wget(link, out_dir="/workspace/ComfyUI/models/controlnet")
            
        for line in custom_downloads.split("\n"):
            if "|" in line and not line.strip().startswith("#"):
                parts = line.split("|")
                if len(parts) == 2:
                    bash_script += get_wget(parts[0], out_file=parts[1])

        with open("/tmp/smart_setup.sh", "w") as f:
            f.write(bash_script)
        
        log_path = "/workspace/ComfyUI/models/setup_log.txt"
        PromptServer.instance.send_sync("vast_log_message", {"text": f"🚀 НАЧИНАЮ СКАЧИВАНИЕ! Лог также пишется в {log_path}\n"})
        
        process = subprocess.Popen(["bash", "/tmp/smart_setup.sh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        with open(log_path, "w", encoding="utf-8") as log_file:
            for line in iter(process.stdout.readline, ''):
                print(line, end="") 
                log_file.write(line)
                log_file.flush()
                PromptServer.instance.send_sync("vast_log_message", {"text": line})
                
        process.wait()
        PromptServer.instance.send_sync("vast_log_message", {"text": "✅✅✅ ВСЕ ФАЙЛЫ ЗАГРУЖЕНЫ УСПЕШНО!\n"})
        
        return ("Установка завершена!",)