# Самодостаточный Dockerfile: собирается из одного файла (без контекста),
# удобно для сборки в Kaggle-ноутбуке через buildah и пуша в Docker Hub.
#
# Образ = base + torch + ComfyUI + cloudflared. Модели и ноды затем скачивает
# onstart от панели (~2–4 минуты на старте вместо 15–30).
#
# Сборка:
#   buildah build -t docker.io/<USER>/comfyui-bridge-worker:latest -f Dockerfile.prebuilt .
#   buildah login -u <USER> -p <TOKEN> docker.io
#   buildah push docker.io/<USER>/comfyui-bridge-worker:latest

FROM vastai/base-image:cuda-12.1.1-auto

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# torch для T4 (sm_75) — cu121
RUN python3 -m pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cu121 \
      torch torchvision torchaudio

# ComfyUI + зависимости
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /workspace/comfy \
 && cd /workspace/comfy \
 && python3 -m pip install --no-cache-dir -r requirements.txt

# cloudflared
RUN curl -sL -o /usr/local/bin/cloudflared \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
 && chmod +x /usr/local/bin/cloudflared

WORKDIR /workspace
CMD ["sleep", "infinity"]
