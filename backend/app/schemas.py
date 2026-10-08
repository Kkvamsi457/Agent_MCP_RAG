from pydantic import BaseModel, Field
from typing import List, Optional

class ChatRequest(BaseModel):
    message: str
    history: List[dict] = Field(default_factory=list)
    selected_tool: Optional[str] = None

class RouteRequest(BaseModel):
    message: str
    history: List[dict] = Field(default_factory=list)

class RouteResponse(BaseModel):
    tool: str
    tool_label: str
    reason: str
    input: str

class Citation(BaseModel):
    document: str
    page: int
    section: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    tool: str
    tool_label: str
    citations: List[Citation] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
