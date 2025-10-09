from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import requests
import logging
from urllib.parse import urlparse, parse_qs

router = APIRouter()

@router.get("/api/videos/download")
async def download_video(url: str, filename: str = "video.mp4"):
    try:
        print(f"开始下载: {url}")
        
        # 检查是否是代理URL，如果是则提取真实的OSS URL
        if "/api/videos/oss-proxy?url=" in url:
            print("检测到代理URL，提取真实OSS URL")
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            if "url" in query_params:
                real_oss_url = query_params["url"][0]
                print(f"提取的真实OSS URL: {real_oss_url}")
                url = real_oss_url
            else:
                raise HTTPException(status_code=400, detail="代理URL格式错误")
        
        # 优化请求参数：增加超时时间，添加重试机制
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'video/mp4,*/*',
            'Accept-Encoding': 'identity',  # 禁用压缩，避免流式传输问题
            'Connection': 'keep-alive'
        }
        
        response = requests.get(url, stream=True, timeout=60, headers=headers)
        print(f"OSS响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            # 获取文件大小
            content_length = response.headers.get('content-length')
            if content_length:
                print(f"文件大小: {int(content_length) / 1024 / 1024:.2f}MB")
            
            return StreamingResponse(
                response.iter_content(chunk_size=65536),  # 增加块大小到64KB
                media_type="video/mp4",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{filename}\"",
                    "Content-Type": "video/mp4",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-cache",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                }
            )
        else:
            print(f"OSS返回错误状态码: {response.status_code}")
            raise HTTPException(status_code=404, detail="视频文件不存在")
    except requests.exceptions.Timeout:
        print(f"下载超时: {url}")
        raise HTTPException(status_code=408, detail="下载超时，请重试")
    except requests.exceptions.ConnectionError:
        print(f"连接错误: {url}")
        raise HTTPException(status_code=503, detail="网络连接错误，请检查网络")
    except requests.exceptions.RequestException as e:
        print(f"下载请求失败: {e}")
        raise HTTPException(status_code=500, detail=f"下载请求失败: {str(e)}")
    except Exception as e:
        print(f"下载异常: {e}")
        raise HTTPException(status_code=500, detail=f"下载异常: {str(e)}")
