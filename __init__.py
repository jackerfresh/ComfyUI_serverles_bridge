import os

WEB_DIRECTORY = "./web"

# Грузим нашу ноду для скачивания 150 гигов, чтобы она появилась в меню
from .setup_node import ServerlessSetupNode
NODE_CLASS_MAPPINGS = {"ServerlessSetupNode": ServerlessSetupNode}
NODE_DISPLAY_NAME_MAPPINGS = {"ServerlessSetupNode": "🔥 Serverless Auto-Setup"}

if os.environ.get("IS_VAST_SERVER") == "1":
    print("🔥 VAST.AI MODE ACTIVE: Перехватываем данные и шлем на локалку...")
    from . import vast_sender
else:
    print("💻 LOCAL MODE ACTIVE: Ждем данные от Vast.ai...")
    from . import local_receiver