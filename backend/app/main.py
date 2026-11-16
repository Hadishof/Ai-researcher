"""Creates the FastAPI app and connects all the routes."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, conversations, documents, health
from app.core.config import get_settings

# Load settings now, so a missing GOOGLE_API_KEY stops the server immediately
# with a clear message, instead of failing later on the first request.
settings = get_settings()

# Show our own log messages (e.g. retrieval distances at DEBUG) in the terminal.
# The level applies only to loggers under "app", so libraries stay quiet.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(settings.log_level)

app = FastAPI(
    title="AI Researcher API",
    version="2.0.0",
    description="Ask questions about your PDF documents in Hebrew or English, "
    "with page citations for every answer. Conversations are saved, and each one "
    "searches only the documents selected for it.",
)

# CORS: browsers block a website from calling an API on a different address,
# unless the API allows it. We allow only our own frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(conversations.router)
app.include_router(chat.router)
