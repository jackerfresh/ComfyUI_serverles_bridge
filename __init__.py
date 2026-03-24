import os

WEB_DIRECTORY = "./web"

# Грузим нашу ноду для скачивания 150 гигов, чтобы она появилась в меню
from .setup_node import ServerlessSetupNode
NODE_CLASS_MAPPINGS = {"ServerlessSetupNode": ServerlessSetupNode}
NODE_DISPLAY_NAME_MAPPINGS = {"ServerlessSetupNode": "🔥 Serverless Auto-Setup"}
from . import local_receiver
