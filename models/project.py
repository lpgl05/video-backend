from pydantic import BaseModel

class Project(BaseModel):
    id: int
    name: str
    description: str = ""
    # ...可继续补充其他字段...
