# Минимальный образ: только база Vast + git/curl. torch и ComfyUI ставит
# onstart-скрипт с быстрых CDN (PyPI сохраняет скорость), чтобы pull образа
# занимал секунды, а не 10+ минут.
FROM vastai/base-image:cuda-12.1.1-auto

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/*

WORKDIR /workspace
CMD ["sleep", "infinity"]
