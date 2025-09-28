from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import requests

router = APIRouter()

@router.get("/api/videos/oss-proxy")
async def oss_proxy(url: str):
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            return StreamingResponse(
                response.iter_content(chunk_size=8192),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": "inline",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                }
            )
        else:
            raise HTTPException(status_code=404, detail="视频文件不存在")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理请求失败: {str(e)}")
