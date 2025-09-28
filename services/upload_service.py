import os
from uuid import uuid4
from datetime import datetime
from models.oss_client import OSSClient
import asyncio
from typing import Dict, Any

# 团队协作模式：直接使用OSS存储目录
OSS_VIDEO_DIR = "uploads/videos"
OSS_AUDIO_DIR = "uploads/audios"
OSS_POSTER_DIR = "uploads/posters"
USE_OSS = True  # 团队协作模式强制使用OSS存储

oss_client = OSSClient()

# 全局上传任务追踪器
upload_tasks: Dict[str, Dict[str, Any]] = {}

# 文件存储映射 - 用于跟踪已上传的文件
uploaded_files: Dict[str, Dict[str, str]] = {}

async def handle_upload_video(video, task_id: str = None):
    if video is None:
        return {"success": False, "error": "未收到文件"}
    try:
        file_id = str(uuid4())
        file_name = video.filename
        
        # 确保文件名编码正确
        if file_name:
            try:
                # 如果是bytes，先解码为字符串
                if isinstance(file_name, bytes):
                    file_name = file_name.decode('utf-8')
                # 确保是UTF-8编码的字符串
                file_name = str(file_name)
                print(f"视频文件名处理: {file_name}")
            except Exception as name_error:
                print(f"视频文件名编码处理失败: {name_error}")
                file_name = f"video_{file_id}.mp4"  # 使用默认文件名
                print(f"使用默认文件名: {file_name}")
        
        # 如果没有提供task_id，生成一个
        if not task_id:
            task_id = file_id
        
        # 先创建任务状态（在读取文件之前）
        upload_tasks[task_id] = {
            "status": "receiving",
            "progress": 0,
            "speed": "0 MB/s",
            "filename": file_name,
            "file_size": 0,
            "uploaded_bytes": 0,
            "start_time": datetime.now(),
            "error": None,
            "stage": "http_receiving"  # 新增阶段标识
        }
        
        print(f"创建上传任务: {task_id}")
        print(f"开始接收文件: {file_name}")
        
        # 读取文件内容（这个过程前端无法感知进度）
        content = await video.read()
        if not content:
            return {"success": False, "error": "文件内容为空"}
        
        # 更新文件大小和状态
        upload_tasks[task_id].update({
            "file_size": len(content),
            "progress": 10,  # HTTP接收完成，给10%
            "stage": "oss_uploading",
            "status": "uploading"
        })
        
        print(f"文件接收完成，大小: {len(content) / (1024*1024):.2f}MB")
        print(f"统一团队协作模式")
        print(f"当前所有任务: {list(upload_tasks.keys())}")
        
        # 统一使用OSS存储
        use_oss = USE_OSS
        print(f"使用OSS: {'是' if use_oss else '否'} (统一团队协作模式)")
        
        if use_oss:
            print(f'开始上传视频到阿里云oss, task_id: {task_id}')
            
            # 更新状态为检查去重
            upload_tasks[task_id].update({
                "progress": 15,
                "status": "checking",
                "stage": "duplicate_checking"
            })
            
            start_time = datetime.now()
            
            def progress_callback(progress: float, uploaded_bytes: int, speed_mbps: float):
                """OSS上传进度回调"""
                if task_id in upload_tasks:
                    # 如果是去重跳过，快速完成
                    if progress == 100.0 and uploaded_bytes == len(content) and speed_mbps == 0:
                        upload_tasks[task_id].update({
                            "progress": 100,
                            "uploaded_bytes": uploaded_bytes,
                            "speed": "去重跳过",
                            "status": "completed"
                        })
                        print(f"任务 {task_id} 文件去重，瞬间完成")
                    else:
                        # 正常上传进度（从20%开始，为去重检查留空间）
                        adjusted_progress = 20 + (progress * 0.8)
                        upload_tasks[task_id].update({
                            "progress": adjusted_progress,
                            "uploaded_bytes": uploaded_bytes,
                            "speed": f"{speed_mbps:.2f} MB/s",
                            "status": "uploading"
                        })
                        # 只在关键进度点输出日志
                        if int(adjusted_progress) % 20 == 0 or adjusted_progress >= 95:
                            print(f"任务 {task_id} 进度: {adjusted_progress:.1f}%, 速度: {speed_mbps:.2f}MB/s")
                else:
                    print(f"警告: task_id {task_id} 不存在")
            
            # 上传到OSS（内置去重检查）
            file_url = await oss_client.upload_to_oss_with_progress(
                file_buffer=content,
                original_filename=file_name,
                folder=OSS_VIDEO_DIR,
                progress_callback=progress_callback
            )
            end_time = datetime.now()
            t = end_time - start_time
            print(f'上传视频到阿里云oss成功，文件url为：{file_url}, 上传耗时： {t}')
            
            # 更新任务状态为完成
            upload_tasks[task_id].update({
                "status": "completed",
                "progress": 100,
                "file_url": file_url
            })
        else:
            # 团队协作模式必须使用OSS，不允许本地存储
            error_msg = "OSS未配置或上传失败，团队协作模式不支持本地存储"
            print(f"❌ {error_msg}")
            upload_tasks[task_id].update({
                "status": "failed",
                "progress": 0,
                "error": error_msg
            })
            return {"success": False, "error": error_msg}
        # duration 字段可后续完善，这里先为 0
        video_file = {
            "id": file_id,
            "name": file_name,
            "url": file_url,
            "size": len(content),
            "duration": 0,
            "uploadedAt": datetime.now().isoformat(),
            "task_id": task_id  # 添加任务ID
        }
        
        # 记录文件信息用于删除
        # 从file_url中提取实际的OSS路径
        oss_file_path = None
        if USE_OSS and file_url:
            # 从URL中提取OSS对象key: https://bucket.endpoint/path -> path
            try:
                oss_file_path = file_url.split('.com/')[-1] if '.com/' in file_url else None
            except:
                oss_file_path = None
        
        uploaded_files[file_id] = {
            "type": "video",
            "filename": file_name,
            "url": file_url,
            "oss_path": oss_file_path if USE_OSS else (save_path if 'save_path' in locals() else None)
        }
        
        return {
            "success": True,
            "data": video_file
        }
    except Exception as e:
        return {"success": False, "error": f"上传失败: {str(e)}"}

async def handle_upload_audio(audio, task_id: str = None):
    if audio is None:
        return {"success": False, "error": "未收到文件"}
    try:
        file_id = str(uuid4())
        file_name = audio.filename
        
        # 确保文件名编码正确
        if file_name:
            try:
                # 如果是bytes，先解码为字符串
                if isinstance(file_name, bytes):
                    file_name = file_name.decode('utf-8')
                # 确保是UTF-8编码的字符串
                file_name = str(file_name)
                print(f"音频文件名处理: {file_name}")
            except Exception as name_error:
                print(f"音频文件名编码处理失败: {name_error}")
                file_name = f"audio_{file_id}.mp3"  # 使用默认文件名
                print(f"使用默认文件名: {file_name}")
        
        content = await audio.read()
        if not content:
            return {"success": False, "error": "文件内容为空"}
        
        # 如果没有提供task_id，生成一个
        if not task_id:
            task_id = file_id
            
        # 初始化任务状态
        upload_tasks[task_id] = {
            "status": "uploading",
            "progress": 0,
            "speed": "0 MB/s",
            "filename": file_name,
            "file_size": len(content),
            "uploaded_bytes": 0,
            "start_time": datetime.now(),
            "error": None
        }
        
        print(f"创建音频上传任务: {task_id}")
        print(f"音频统一团队协作模式")
        
        # 统一使用OSS存储
        use_oss = USE_OSS
        print(f"音频使用OSS: {'是' if use_oss else '否'} (统一团队协作模式)")
        
        if use_oss:
            print(f'开始上传音频到阿里云oss, task_id: {task_id}')
            
            # 更新状态为检查去重
            upload_tasks[task_id].update({
                "progress": 15,
                "status": "checking",
                "stage": "duplicate_checking"
            })
            
            start_time = datetime.now()
            
            def progress_callback(progress: float, uploaded_bytes: int, speed_mbps: float):
                """OSS音频上传进度回调"""
                if task_id in upload_tasks:
                    # 如果是去重跳过，快速完成
                    if progress == 100.0 and uploaded_bytes == len(content) and speed_mbps == 0:
                        upload_tasks[task_id].update({
                            "progress": 100,
                            "uploaded_bytes": uploaded_bytes,
                            "speed": "去重跳过",
                            "status": "completed"
                        })
                        print(f"音频任务 {task_id} 文件去重，瞬间完成")
                    else:
                        # 正常上传进度（从20%开始）
                        adjusted_progress = 20 + (progress * 0.8)
                        upload_tasks[task_id].update({
                            "progress": adjusted_progress,
                            "uploaded_bytes": uploaded_bytes,
                            "speed": f"{speed_mbps:.2f} MB/s",
                            "status": "uploading"
                        })
                        # 只在关键进度点输出日志
                        if int(adjusted_progress) % 20 == 0 or adjusted_progress >= 95:
                            print(f"音频任务 {task_id} 进度: {adjusted_progress:.1f}%, 速度: {speed_mbps:.2f}MB/s")
                else:
                    print(f"警告: 音频task_id {task_id} 不存在")
            
            file_url = await oss_client.upload_to_oss_with_progress(
                file_buffer=content,
                original_filename=file_name,
                folder=OSS_AUDIO_DIR,
                progress_callback=progress_callback
            )
            end_time = datetime.now()
            t = end_time - start_time
            print(f'上传音频到阿里云oss成功，文件url为：{file_url}, 上传耗时： {t}')
            
            # 更新任务状态为完成
            upload_tasks[task_id].update({
                "status": "completed",
                "progress": 100,
                "file_url": file_url
            })
        else:
            # 团队协作模式必须使用OSS，不允许本地存储
            error_msg = "OSS未配置或上传失败，团队协作模式不支持本地存储"
            print(f"❌ {error_msg}")
            upload_tasks[task_id].update({
                "status": "failed",
                "progress": 0,
                "error": error_msg
            })
            return {"success": False, "error": error_msg}
            
        # duration 字段可后续完善，这里先为 0
        audio_file = {
            "id": file_id,
            "name": file_name,
            "url": file_url,
            "size": len(content),
            "duration": 0,
            "uploadedAt": datetime.now().isoformat(),
            "task_id": task_id  # 添加task_id字段
        }
        
        # 记录文件信息用于删除
        # 从file_url中提取实际的OSS路径
        oss_file_path = None
        if USE_OSS and file_url:
            # 从URL中提取OSS对象key: https://bucket.endpoint/path -> path
            try:
                oss_file_path = file_url.split('.com/')[-1] if '.com/' in file_url else None
            except:
                oss_file_path = None
        
        uploaded_files[file_id] = {
            "type": "audio",
            "filename": file_name,
            "url": file_url,
            "oss_path": oss_file_path if USE_OSS else (save_path if 'save_path' in locals() else None)
        }
        
        return {
            "success": True,
            "data": audio_file
        }
    except Exception as e:
        if task_id and task_id in upload_tasks:
            upload_tasks[task_id].update({
                "status": "failed",
                "error": str(e)
            })
        return {"success": False, "error": f"上传失败: {str(e)}"}

async def handle_upload_poster(poster, task_id: str = None):
    if poster is None:
        return {"success": False, "error": "未收到文件"}
    try:
        file_id = str(uuid4())
        file_name = poster.filename
        
        # 确保文件名编码正确
        if file_name:
            try:
                # 如果是bytes，先解码为字符串
                if isinstance(file_name, bytes):
                    file_name = file_name.decode('utf-8')
                # 确保是UTF-8编码的字符串
                file_name = str(file_name)
                print(f"海报文件名处理: {file_name}")
            except Exception as name_error:
                print(f"海报文件名编码处理失败: {name_error}")
                file_name = f"poster_{file_id}.jpg"  # 使用默认文件名
                print(f"使用默认文件名: {file_name}")
        
        content = await poster.read()
        if not content:
            return {"success": False, "error": "文件内容为空"}

        # 验证文件类型
        if not poster.content_type or not poster.content_type.startswith('image/'):
            return {"success": False, "error": "只支持图片文件"}

        # 如果没有提供task_id，生成一个
        if not task_id:
            task_id = file_id

        print(f"创建海报上传任务: {task_id}")
        print(f"海报统一团队协作模式")

                # 统一使用OSS存储
        use_oss = USE_OSS
        print(f"海报使用OSS: {'是' if use_oss else '否'} (统一团队协作模式)")
        
        if use_oss:
            print(f'开始上传海报到阿里云oss, task_id: {task_id}')
            start_time = datetime.now()

            # 使用带进度和去重检查的上传方法
            file_url = await oss_client.upload_to_oss_with_progress(
                file_buffer=content,
                original_filename=file_name,
                folder=OSS_POSTER_DIR,
                progress_callback=None  # 海报文件通常较小，不需要进度回调
            )
            end_time = datetime.now()
            t = end_time - start_time
            print(f'上传海报到阿里云oss成功，文件url为：{file_url}, 上传耗时： {t}')
        else:
            # 团队协作模式必须使用OSS，不允许本地存储
            error_msg = "OSS未配置或上传失败，团队协作模式不支持本地存储"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}

        # 简单的图片尺寸检测 (可以使用PIL库获取更精确的信息)
        width, height = None, None
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(content))
            width, height = img.size
        except:
            pass

        poster_file = {
            "id": file_id,
            "name": file_name,
            "url": file_url,
            "size": len(content),
            "width": width,
            "height": height,
            "uploadedAt": datetime.now().isoformat()
        }
        
        # 从file_url中提取实际的OSS路径
        oss_file_path = None
        if USE_OSS and file_url:
            # 从URL中提取OSS对象key: https://bucket.endpoint/path -> path
            try:
                oss_file_path = file_url.split('.com/')[-1] if '.com/' in file_url else None
            except:
                oss_file_path = None
        
        # 记录文件信息到uploaded_files字典中，供materials接口使用
        uploaded_files[file_id] = {
            "type": "poster",
            "name": file_name,
            "url": file_url,
            "size": len(content),
            "width": width,
            "height": height,
            "uploadedAt": datetime.now().isoformat(),
            "task_id": task_id,
            "oss_path": oss_file_path if USE_OSS else None
        }
        
        return {
            "success": True,
            "data": poster_file
        }
    except Exception as e:
        return {"success": False, "error": f"上传失败: {str(e)}"}

async def handle_delete_file(file_id: str, file_type: str, file_url: str = None):
    """删除文件（视频/音频）"""
    try:
        print(f"尝试删除文件: file_id={file_id}, file_type={file_type}")
        print(f"当前记录的文件: {list(uploaded_files.keys())}")
        
        if file_id not in uploaded_files:
            print(f"文件记录不存在，file_id: {file_id}")
            
            # 如果提供了file_url，尝试从URL中提取路径并删除
            if file_url and USE_OSS:
                try:
                    # 从URL中提取OSS对象key
                    oss_path = file_url.split('.com/')[-1] if '.com/' in file_url else None
                    if oss_path:
                        print(f"从URL提取OSS路径: {oss_path}")
                        success = await oss_client.delete_from_oss(oss_path)
                        if success:
                            print(f"成功删除OSS文件: {oss_path}")
                            return {"success": True, "message": f"{file_type}删除成功"}
                        else:
                            print("OSS删除失败")
                except Exception as e:
                    print(f"使用URL删除文件时出错: {str(e)}")
            
            # 如果没有URL或URL删除失败，尝试搜索删除
            print("尝试搜索并删除文件...")
            
            if USE_OSS:
                # 尝试从OSS列出并删除相关文件
                try:
                    # 获取目录前缀
                    if file_type == "video":
                        prefix = f"{UPLOAD_VIDEO_DIR}/"
                    elif file_type == "audio":
                        prefix = f"{UPLOAD_AUDIO_DIR}/"
                    elif file_type == "poster":
                        prefix = f"{UPLOAD_POSTER_DIR}/"
                    else:
                        prefix = ""
                    
                    # 列出OSS中的文件，查找匹配的文件
                    from oss2 import ObjectIterator
                    
                    for obj in ObjectIterator(oss_client.bucket, prefix=prefix):
                        # 检查文件名是否包含file_id（这种情况很少，因为OSS使用随机UUID）
                        if file_id in obj.key:
                            print(f"找到匹配的OSS文件: {obj.key}")
                            success = await oss_client.delete_from_oss(obj.key)
                            if success:
                                print(f"成功删除OSS文件: {obj.key}")
                                return {"success": True, "message": f"{file_type}删除成功"}
                    
                    print(f"未找到包含ID {file_id} 的OSS文件")
                except Exception as e:
                    print(f"搜索OSS文件时出错: {str(e)}")
            
            # 对于记录不存在的情况，我们仍然返回成功，因为目标是确保文件被删除
            print("文件记录不存在，但返回删除成功")
            return {"success": True, "message": f"{file_type}删除成功（文件记录不存在）"}
        
        file_info = uploaded_files[file_id]
        print(f"文件信息: {file_info}")
        
        # 验证文件类型
        if file_info["type"] != file_type:
            print(f"文件类型不匹配，期望: {file_type}, 实际: {file_info['type']}")
            return {"success": False, "error": f"文件类型不匹配，期望: {file_type}, 实际: {file_info['type']}"}
        
        if USE_OSS:
            # 从OSS删除文件
            oss_path = file_info["oss_path"]
            print(f"删除OSS文件: {oss_path}")
            success = await oss_client.delete_from_oss(oss_path)
            if not success:
                print("OSS删除失败")
                return {"success": False, "error": "从OSS删除文件失败"}
        else:
            # 从本地删除文件
            local_path = file_info["oss_path"]  # 这里存储的是本地路径
            print(f"删除本地文件: {local_path}")
            if local_path and os.path.exists(local_path):
                os.remove(local_path)
                print("本地文件删除成功")
            else:
                print("本地文件不存在或路径为空")
        
        # 从记录中移除
        del uploaded_files[file_id]
        print(f"文件记录删除成功")
        
        return {"success": True, "message": f"{file_type}删除成功"}
        
    except Exception as e:
        print(f"删除过程中发生异常: {str(e)}")
        return {"success": False, "error": f"删除失败: {str(e)}"}

async def handle_delete_video(file_id: str, file_url: str = None):
    """删除视频文件"""
    return await handle_delete_file(file_id, "video", file_url)

async def handle_delete_audio(file_id: str, file_url: str = None):
    """删除音频文件"""
    return await handle_delete_file(file_id, "audio", file_url)

async def handle_delete_poster(file_id: str, file_url: str = None):
    """删除海报文件"""
    return await handle_delete_file(file_id, "poster", file_url)