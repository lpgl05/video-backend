from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import requests
import os
from urllib.parse import urlparse, unquote

router = APIRouter()

@router.get("/api/videos/oss-proxy")
async def oss_proxy(url: str, download: bool = Query(False, description="是否强制下载文件")):
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            # 从URL中智能提取文件名
            parsed_url = urlparse(url)
            filename = os.path.basename(unquote(parsed_url.path))
            
            # 如果无法从URL提取文件名，使用默认名称
            if not filename or filename == '/':
                filename = "video.mp4"
            
            # 根据download参数设置Content-Disposition
            if download:
                content_disposition = f'attachment; filename="{filename}"'
            else:
                content_disposition = "inline"
            
            return StreamingResponse(
                response.iter_content(chunk_size=8192),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": content_disposition,
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                }
            )
        else:
            raise HTTPException(status_code=404, detail="视频文件不存在")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理请求失败: {str(e)}")
