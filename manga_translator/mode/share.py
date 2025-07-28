import base64
from io import BytesIO

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from manga_translator import MangaTranslator
from manga_translator.config import Config
from PIL import Image

class MethodCall(BaseModel):
    method_name: str
    attributes: bytes


class MangaShare:
    def __init__(self, params: dict = None):
        self.manga = MangaTranslator(params)
        self.host = params.get('host', '127.0.0.1')
        self.port = int(params.get('port', '5003'))
        self.nonce = params.get('nonce', None)

    def check_nonce(self, request: Request):
        if self.nonce:
            nonce = request.headers.get('X-Nonce')
            if nonce != self.nonce:
                raise HTTPException(401, detail="Nonce does not match")

    def get_fn(self, method_name: str):
        if method_name.startswith("__"):
            raise HTTPException(status_code=403, detail="These functions are not allowed to be executed remotely")
        method = getattr(self.manga, method_name, None)
        if not method:
            raise HTTPException(status_code=404, detail="Method not found")
        return method

    async def listen(self, translation_params: dict = None):
        app = FastAPI()

        @app.get("/health")
        async def health(request: Request):
            return Response(content="OK", media_type="text/plain")

        @app.post("/simple_execute/translate")
        async def translate(request: Request):
            self.check_nonce(request)
            method = self.get_fn("translate")
            payload = await request.json()
            if "image" not in payload or "config" not in payload:
                raise HTTPException(status_code=400, detail="Missing image or config")

            image = Image.open(BytesIO(base64.b64decode(payload["image"])))
            config = Config(**payload["config"])
            ctx = await method(image, config)

            result_image: Image.Image = ctx.result
            image_bytes_io = BytesIO()
            result_image.save(image_bytes_io, format="PNG")
            result_image_bytes = image_bytes_io.getvalue()

            return Response(content=result_image_bytes, media_type="image/png")

        config = uvicorn.Config(app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        await server.serve()
