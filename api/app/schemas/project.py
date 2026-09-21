from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime

    # Lets Pydantic build this schema directly from a SQLAlchemy Project
    # instance (reading its attributes) instead of requiring a dict.
    model_config = ConfigDict(from_attributes=True)
