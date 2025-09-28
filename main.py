from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# CORS 配置，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes.generation import router as generation_router
app.include_router(generation_router)
from routes.ai import router as ai_router
app.include_router(ai_router)
from routes.upload import router as upload_router
app.include_router(upload_router)
from routes.clip import router as clip_router
from routes.video import router as video_router
from routes.download import router as download_router
from routes.projects import router as projects_router
app.include_router(video_router)
app.include_router(download_router)
app.include_router(clip_router)
app.include_router(projects_router)

# 注释掉本地文件服务 - 团队协作模式统一使用OSS存储
# import os
# app.mount("/local-files", StaticFiles(directory="uploads"), name="local-files")                                                                       

@app.get("/api/ping")
def ping():
    return {"msg": "pong"}

if __name__ == "__main__":
    import uvicorn
    import os
    # 动态获取端口，支持生产环境(8000)和测试环境(9000)
    port = int(os.getenv("BACKEND_PORT", "9000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
