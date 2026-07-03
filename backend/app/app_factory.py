from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from app.routes import router
from app.socketio_app import sio, cleanup_zombie_connections
from app.socket_handlers import *  # noqa: F401,F403


def create_app() -> FastAPI:
    app = FastAPI(title="Hackathon Backend")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.on_event("startup")
    async def startup_event():
        import asyncio
        asyncio.create_task(cleanup_zombie_connections())

    return app


app = create_app()
ASGIApp = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path='socket.io')
