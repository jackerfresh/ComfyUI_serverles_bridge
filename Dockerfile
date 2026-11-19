# РљСЂРѕС€РµС‡РЅС‹Р№ РѕР±СЂР°Р· (~250 РњР‘): Р±РµР· CUDA-Р±Р°Р·С‹. torch СЃС‚Р°РІРёС‚СЃСЏ РЅР° СЃС‚Р°СЂС‚Рµ вЂ”
# РµРіРѕ cu121-РєРѕР»С‘СЃР° СЃР°РјРё РїСЂРёРЅРѕСЃСЏС‚ CUDA-Р±РёР±Р»РёРѕС‚РµРєРё, РїРѕСЌС‚РѕРјСѓ С‚СЏР¶С‘Р»С‹Р№ Р±Р°Р·РѕРІС‹Р№
# РѕР±СЂР°Р· РЅРµ РЅСѓР¶РµРЅ. РўР°РєРѕР№ РѕР±СЂР°Р· СЃРєР°С‡РёРІР°РµС‚СЃСЏ Р·Р° СЃРµРєСѓРЅРґС‹ РЅР° Р›Р®Р‘РћРњ С…РѕСЃС‚Рµ,
# РєСЌС€ Docker Hub Р±РѕР»СЊС€Рµ РЅРµ РЅСѓР¶РµРЅ.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1

RUN mkdir -p /run/sshd /root/.ssh && chmod 700 /root/.ssh\n\nRUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv git curl ca-certificates bash libgl1 libglib2.0-0 openssh-server \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/*

WORKDIR /workspace
CMD ["sleep", "infinity"]
