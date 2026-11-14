"""Shape of the data returned by GET /health."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
