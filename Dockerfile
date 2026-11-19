# Крошечный образ (~135 МБ): без CUDA-базы. torch ставится на старте —
# его cu121-колёса сами приносят CUDA-библиотеки, поэтому тяжёлый базовый
# образ не нужен. Такой образ скачивается за секунды на ЛЮБОМ хосте.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1

RUN mkdir -p /run/sshd /root/.ssh && chmod 700 /root/.ssh

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv git curl ca-certificates bash \
      libgl1 libglib2.0-0 openssh-server \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/*

WORKDIR /workspace
CMD ["sleep", "infinity"]
