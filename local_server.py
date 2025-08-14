import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import asyncio

from packages.HomiAI.bot.bot import process_update


app = FastAPI(title="HomiAI Telegram Bot (Local)")


@app.get("/")
async def root():
    return {"ok": True, "message": "HomiAI local server running"}


@app.post("/webhook")
async def webhook(request: Request):
    update = await request.json()
    # Run sync processing in a thread to avoid blocking the event loop
    await asyncio.to_thread(process_update, update)
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
