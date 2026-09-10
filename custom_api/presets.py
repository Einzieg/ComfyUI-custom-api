from copy import deepcopy


TEXT_PARAMS = [
    {"name": "temperature", "label": "Temperature", "type": "number", "default": 0.7, "min": 0, "max": 2},
    {"name": "max_tokens", "label": "Max output tokens", "type": "integer", "default": 1024, "min": 1},
]
IMAGE_PARAMS = [
    {"name": "size", "label": "Image size", "type": "enum", "default": "1024x1024", "options": ["1024x1024", "1536x1024", "1024x1536"]},
    {"name": "n", "label": "Image count", "type": "integer", "default": 1, "min": 1, "max": 8},
]


def request(path, body=None, encoding="json", method="POST"):
    return {"method": method, "path": path, "headers": {}, "query": {},
            "encoding": encoding, "body": body or {}, "files": []}


def presets():
    chat = {"id": "chat-completions", "name": "Chat Completions", "kind": "text",
            "request": request("/chat/completions", {"model": "{{model}}", "messages": "{{messages}}",
                               "temperature": "{{params.temperature}}", "max_tokens": "{{params.max_tokens}}", "stream": False}),
            "response": {"text": "$.choices[0].message.content", "error": "$.error.message"},
            "parameters": deepcopy(TEXT_PARAMS)}
    image = {"id": "images-generate", "name": "Images · Generate", "kind": "image",
             "request": request("/images/generations", {"model": "{{model}}", "prompt": "{{prompt}}",
                                "size": "{{params.size}}", "n": "{{params.n}}"}),
             "response": {"images": "$.data[*]", "image_value": "auto", "error": "$.error.message"},
             "parameters": deepcopy(IMAGE_PARAMS)}
    edit = deepcopy(image)
    edit.update(id="images-edit", name="Images · Edit")
    edit["request"]["path"] = "/images/edits"
    edit["request"]["encoding"] = "multipart"
    edit["request"]["files"] = [{"field": "image[]", "source": "images"}, {"field": "mask", "source": "mask", "optional": True}]
    async_image = {"id": "async-image-example", "name": "Async image · Customize before use", "kind": "image",
                   "request": request("/tasks", {"model": "{{model}}", "prompt": "{{prompt}}", "parameters": "{{params}}"}),
                   "response": {"images": "$.result.images[*]", "image_value": "auto", "error": "$.error.message"},
                   "parameters": deepcopy(IMAGE_PARAMS),
                   "poll": {"task_id": "$.task_id", "request": request("/tasks/{{task_id}}", method="GET"),
                            "status": "$.status", "success": ["succeeded", "completed"],
                            "failure": ["failed", "cancelled"], "interval": 2, "timeout": 600}}
    return [chat, image, edit, async_image]


def new_config():
    return {"version": 1, "revision": 0, "providers": [], "models": [], "templates": presets()}
