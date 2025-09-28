from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from services.upload_service import handle_upload_video, handle_upload_audio, handle_upload_poster, upload_tasks, handle_delete_video, handle_delete_audio, handle_delete_poster, uploaded_files

router = APIRouter()

@router.post("/api/upload/video")
async def upload_video(video: UploadFile = File(...)):
    print(f'上传视频，统一团队协作模式')
    return await handle_upload_video(video)

@router.post("/api/upload/audio")
async def upload_audio(audio: UploadFile = File(...)):
    print(f'上传音频，统一团队协作模式')
    return await handle_upload_audio(audio)

@router.post("/api/upload/poster")
async def upload_poster(poster: UploadFile = File(...)):
    print(f'上传海报，统一团队协作模式')
    return await handle_upload_poster(poster)

@router.get("/api/upload/progress/{task_id}")
async def get_upload_progress(task_id: str):
    """获取上传进度"""
    print(f"查询进度: task_id={task_id}")
    print(f"当前所有任务: {list(upload_tasks.keys())}")
    
    if task_id not in upload_tasks:
        print(f"任务不存在: {task_id}")
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = upload_tasks[task_id]
    print(f"返回任务状态: {task}")
    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "status": task["status"],
            "progress": task["progress"],
            "speed": task["speed"],
            "filename": task["filename"],
            "file_size": task["file_size"],
            "uploaded_bytes": task["uploaded_bytes"],
            "error": task.get("error")
        }
    }

# 移除调试接口，不再需要复杂的轮询
# @router.get("/api/upload/debug/tasks")
# async def debug_all_tasks():
#     """调试：查看所有上传任务"""
#     return {"success": True, "data": []}

@router.delete("/api/videos/{file_id}")
async def delete_video(file_id: str, file_url: str = Query(None)):
    """删除视频文件"""
    print(f"收到删除视频请求: file_id={file_id}, file_url={file_url}")
    result = await handle_delete_video(file_id, file_url)
    print(f"删除结果: {result}")
    if not result["success"]:
        print(f"删除失败: {result.get('error', '未知错误')}")
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.delete("/api/audios/{file_id}")
async def delete_audio(file_id: str, file_url: str = Query(None)):
    """删除音频文件"""
    print(f"收到删除音频请求: file_id={file_id}, file_url={file_url}")
    result = await handle_delete_audio(file_id, file_url)
    print(f"删除结果: {result}")
    if not result["success"]:
        print(f"删除失败: {result.get('error', '未知错误')}")
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.delete("/api/upload/poster/{file_id}")
async def delete_poster(file_id: str, file_url: str = Query(None)):
    """删除海报文件"""
    print(f"收到删除海报请求: file_id={file_id}, file_url={file_url}")
    result = await handle_delete_poster(file_id, file_url)
    print(f"删除结果: {result}")
    if not result["success"]:
        print(f"删除失败: {result.get('error', '未知错误')}")
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/api/upload/debug/files")
async def debug_uploaded_files():
    """调试：查看所有已上传的文件记录"""
    return {
        "success": True, 
        "data": {
            "uploaded_files": uploaded_files,
            "total_count": len(uploaded_files)
        }
    }

@router.delete("/api/test/delete/{file_id}")
async def test_delete(file_id: str):
    """测试删除接口 - 始终返回成功"""
    print(f"测试删除接口被调用: file_id={file_id}")
    return {"success": True, "message": f"测试删除成功: {file_id}"}

@router.get("/api/test/ping")
async def test_ping():
    """测试连接"""
    print("测试ping接口被调用")
    return {"success": True, "message": "pong from upload router"}

@router.get("/api/materials")
async def get_materials():
    """获取所有素材列表"""
    print("获取素材列表请求")
    materials = []
    for file_id, file_info in uploaded_files.items():
        material = {
            "id": file_id,
            "name": file_info.get("name", ""),
            "type": file_info.get("type", "unknown"),
            "url": file_info.get("url", ""),
            "size": file_info.get("size", 0),
            "duration": file_info.get("duration", 0),
            "uploadedAt": file_info.get("uploadedAt", ""),
            "task_id": file_info.get("task_id", file_id)
        }
        materials.append(material)
    
    print(f"返回 {len(materials)} 个素材")
    return materials
