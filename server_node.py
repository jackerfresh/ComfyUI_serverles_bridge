"""
ComfyUI-Serverless-Bridge: Server-side node stub
=================================================

This file provides stub nodes that exist on the SERVER (in Docker on Vast.ai)
so that workflows sent from the local ComfyUI can execute without
"missing_node_type" errors for nodes that are UI-only on the local side.

The real UI logic lives in local_receiver.py (local ComfyUI).
This file provides minimal stubs for server-side execution.
"""

try:
    import nodes as comfy_nodes
except Exception:
    comfy_nodes = None


class ServerlessSetupNode:
    """
    Stub node: Serverless Auto-Setup
    On the server side, this node does nothing.
    It exists only so the workflow validates successfully.
    The real setup happens in local_receiver.py on the local machine.
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_token": ("STRING", {"default": "", "multiline": False}),
                "hf_token": ("STRING", {"default": "", "multiline": False}),
                "pip_libs": ("STRING", {"default": "", "multiline": True}),
                "checkpoints": ("STRING", {"default": "", "multiline": True}),
                "loras": ("STRING", {"default": "", "multiline": True}),
                "controlnets": ("STRING", {"default": "", "multiline": True}),
                "upscale_models": ("STRING", {"default": "", "multiline": True}),
                "embeddings": ("STRING", {"default": "", "multiline": True}),
                "vaes": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": {},
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("checkpoints_out", "loras_out", "controlnets_out", "upscale_models_out", "embeddings_out", "vaes_out", "pip_result", "civitai_result", "status")
    FUNCTION = "execute"
    CATEGORY = "☁️ Serverless"
    OUTPUT_NODE = False

    def execute(self, civitai_token="", hf_token="", pip_libs="", checkpoints="", loras="", controlnets="", upscale_models="", embeddings="", vaes=""):
        return (
            checkpoints, loras, controlnets, upscale_models, embeddings, vaes,
            "NOTE: Server stubs do not download. Use local ComfyUI to download models.",
            "NOTE: Server stubs do not download. Use local ComfyUI to download models.",
            "stub_ok"
        )


NODE_CLASS_MAPPINGS = {
    "ServerlessSetupNode": ServerlessSetupNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ServerlessSetupNode": "🔥 Serverless Auto-Setup",
}

if comfy_nodes is not None:
    comfy_nodes.NODE_CLASS_MAPPINGS.update(NODE_CLASS_MAPPINGS)
    comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS.update(NODE_DISPLAY_NAME_MAPPINGS)

print("[Serverless-Bridge] Server stubs loaded.")
