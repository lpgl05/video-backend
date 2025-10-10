from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
import requests
import logging
import os
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

# 增加一个接口，用户处理POST请求，url格式为：http://39.96.187.7:5555/api/videos/batch-download
# {"videoUrls":["http://39.96.187.7:9999/api/videos/oss-proxy?url=https://tian-jiu-video.oss-cn-beijing.aliyuncs.com/final/videos/hash_080998e28e9cd73ea0a211dee5e054f4.mp4","http://39.96.187.7:9999/api/videos/oss-proxy?url=https://tian-jiu-video.oss-cn-beijing.aliyuncs.com/final/videos/hash_6c87a60d9791f6b34c2eb0226260ecc0.mp4","http://39.96.187.7:9999/api/videos/oss-proxy?url=https://tian-jiu-video.oss-cn-beijing.aliyuncs.com/final/videos/hash_4378d8012c6f523c227d6b945a1d4723.mp4"],"fileName":"20251009项目.zip"}
@router.post("/api/videos/batch-download")
async def batch_download_videos(request: dict, background_tasks: BackgroundTasks):
    try:
        video_urls = request.get("videoUrls", [])
        zip_filename = request.get("fileName", "videos.zip")
        
        if not video_urls:
            raise HTTPException(status_code=400, detail="视频URL列表不能为空")
        
        print(f"开始批量下载 {len(video_urls)} 个视频")
        # 获取video的真实下载地址
        real_url = []
        for url in video_urls:
            if "/api/videos/oss-proxy?url=" in url:
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                if "url" in query_params:
                    real_oss_url = query_params["url"][0]
                    real_url.append(real_oss_url)
                else:
                    raise HTTPException(status_code=400, detail="代理URL格式错误")
            else:
                real_url.append(url)
        # 使用zipstream打包下载
        import zipstream
        import asyncio
        import tempfile
        import httpx

        temp_files = []
        temp_dir = tempfile.gettempdir()

        async def download_to_temp(client, video_url, index):
            filename_prefix = video_url.split("/")[-1].split(".")[0]
            temp_file = tempfile.NamedTemporaryFile(delete=False, dir=temp_dir, suffix='.mp4')
            temp_files.append(temp_file.name)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'video/mp4,*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive'
            }
            async with client.stream('GET', video_url, headers=headers, timeout=60.0) as response:
                if response.status_code != 200:
                    raise HTTPException(status_code=404, detail=f"视频 {video_url} 下载失败")
                with open(temp_file.name, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
            return temp_file.name, f"{filename_prefix}_{index}.mp4"

        async with httpx.AsyncClient() as client:
            # 并发下载所有视频到临时文件
            tasks = [download_to_temp(client, url, i) for i, url in enumerate(real_url)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 检查是否有异常
            for result in results:
                if isinstance(result, Exception):
                    raise result
            
            z = zipstream.ZipFile(mode='w', compression=zipstream.ZIP_DEFLATED)
            for temp_file, zip_filename in results:
                z.write(temp_file, zip_filename)

        # 对 zip_filename 进行 URL 编码以避免编码问题
        from urllib.parse import quote
        encoded_filename = quote(zip_filename.encode('utf-8'))
        
        # 添加后台任务清理临时文件
        background_tasks.add_task(cleanup_temp_files, temp_files)
        
        return StreamingResponse(z, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"})

    except Exception as e:
        print(f"批量下载异常: {e}")
        raise HTTPException(status_code=500, detail=f"批量下载异常: {str(e)}")


def cleanup_temp_files(files):
    for f in files:
        try:
            os.unlink(f)
        except OSError:
            pass