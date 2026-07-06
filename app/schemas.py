from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    code: str = Field(..., min_length=1)
    language: str = "auto"
    model: str = "qwen2.5-coder"


class FixRequest(ReviewRequest):
    pass


class Issue(BaseModel):
    title: str
    severity: str = "medium"
    category: str = "quality"
    section: str = "general"
    detail: str
    line: int = 1
    column: int = 1
    end_line: int | None = None
    end_column: int | None = None
    source: str = "avatar"
    fix_hint: str = ""


class ToolStatus(BaseModel):
    name: str
    available: bool
    message: str = ""


class ReviewResponse(BaseModel):
    summary: str
    issue_count: int
    confidence: int
    estimated_fix_time: str
    severity: str
    affected_sections: list[str]
    issues: list[Issue]
    ollama_available: bool
    language: str
    tool_status: list[ToolStatus] = []
    pipeline: list[str] = []


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    code: str = ""
    language: str = "auto"
    model: str = "qwen2.5-coder"
    history: list[dict[str, str]] = []
    project_context: str = ""
    project_id: str = ""


class SaveRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    code: str = Field(...)


class ErrorReportRequest(BaseModel):
    filename: str
    error: str


class DesktopCommandRequest(BaseModel):
    command: str
    model: str = "Avatar coding model"


class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool
    children: list["FileNode"] | None = None


class FileTreeResponse(BaseModel):
    files: list[FileNode]


class ProjectFixRequest(BaseModel):
    model: str = "qwen2.5-coder"

