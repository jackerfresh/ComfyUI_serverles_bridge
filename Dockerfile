# Самодостаточный образ для Vast: base + torch + ComfyUI + cloudflared.
# Модели и ноды докачиваются onstart-скриптом панели (~2–4 мин).

FROM vastai/base-image:cuda-12.1.1-auto

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/*

# torch для T4 (sm_75) — cu121
RUN python3 -m pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cu121 \
      torch torchvision torchaudio \
 && rm -rf /root/.cache/pip /tmp/*

# ComfyUI + зависимости, без .git и тестов
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /workspace/comfy \
 && cd /workspace/comfy \
 && python3 -m pip install --no-cache-dir -r requirements.txt \
 && rm -rf /workspace/comfy/.git /workspace/comfy/tests /workspace/comfy/.github \
 && find / -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true \
 && rm -rf /root/.cache /tmp/* /var/tmp/*

RUN curl -sL -o /usr/local/bin/cloudflared \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
 && chmod +x /usr/local/bin/cloudflared

WORKDIR /workspace
CMD ["sleep", "infinity"]
