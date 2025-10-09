from fastapi import APIRouter

router = APIRouter()

@router.get("/api/projects")
def get_projects():
    # TODO: 查询项目列表
    return {"projects": []}

@router.post("/api/projects")
def create_project():
    # TODO: 创建新项目
    return {"msg": "项目创建成功"}

# ...可继续补充其他项目相关接口...
