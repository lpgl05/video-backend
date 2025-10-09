from pydantic import BaseModel

class Task(BaseModel):
    id: int
    project_id: int
    status: str
    result_url: str = ""
    # ...可继续补充其他字段...
