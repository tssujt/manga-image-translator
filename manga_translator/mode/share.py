import asyncio
import pickle

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Request, Response
from pydantic import BaseModel
import inspect

from manga_translator import MangaTranslator

class MethodCall(BaseModel):
    method_name: str
    attributes: bytes


async def load_data(request: Request, method):
    attributes_bytes = await request.body()
    attributes = pickle.loads(attributes_bytes)
    sig = inspect.signature(method)
    expected_args = set(sig.parameters.keys())
    provided_args = set(attributes.keys())

    if expected_args != provided_args:
        raise HTTPException(status_code=400, detail="Incorrect number or names of arguments")
    return attributes


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

        @app.post("/simple_execute/{method_name}")
        async def execute_method(request: Request, method_name: str = Path(...)):
            self.check_nonce(request)
            method = self.get_fn(method_name)
            attr = await load_data(request, method)
            try:
                if asyncio.iscoroutinefunction(method):
                    result = await method(**attr)
                else:
                    result = method(**attr)
                result_bytes = pickle.dumps(result)
                return Response(content=result_bytes, media_type="application/octet-stream")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        config = uvicorn.Config(app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        await server.serve()
