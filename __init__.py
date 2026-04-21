import os

# Говорим Комфи, где лежит наш JS-шпион
WEB_DIRECTORY = "./web"

# Грузим твою ноду для скачивания (setup_node.py)
from .setup_node import ServerlessSetupNode
NODE_CLASS_MAPPINGS = {"ServerlessSetupNode": ServerlessSetupNode}
NODE_DISPLAY_NAME_MAPPINGS = {"ServerlessSetupNode": "🔥 Serverless Auto-Setup"}

# Если мы на Васте (в Докере) - нам локальный мост не нужен, только нода!
if os.environ.get("IS_VAST_SERVER") != "1":
    print("💻[LOCAL MODE] Грузим мост для перехвата данных на Vast.ai...")
    
    # Грузим мост - он сам создаст заглушки при старте
    from . import local_receiver

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
