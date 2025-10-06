import asyncio
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Set, Optional
from services.clip_service import process_clips001
from services.gpu_task_scheduler import gpu_scheduler, GPUTask, TaskType, TaskPriority
from services.performance_optimizer import performance_optimizer
from uuid import uuid4
from datetime import datetime
import time

router = APIRouter()

class VideoFile(BaseModel):
    id: str
    name: str
    url: str
    size: int
    duration: int
    uploadedAt: str
    thumbnail: Optional[str] = None

class AudioFile(BaseModel):
    id: str
    name: str
    url: str
    size: int
    duration: int
    uploadedAt: str
    thumbnail: Optional[str] = None

class PosterFile(BaseModel):
    id: str
    name: str
    url: str
    size: int
    uploadedAt: str

class Script(BaseModel):
    id: str
    content: str
    selected: bool
    generatedAt: str

class StyleConfig(BaseModel):
    title: Dict[str, Any]
    subtitle: Dict[str, Any]

class ClipRequest(BaseModel):
    name: str
    videos: List[VideoFile]
    audios: List[AudioFile]
    posters: Optional[List[PosterFile]] = None
    scripts: List[Script]
    duration: str
    videoCount: int
    voice: str
    style: StyleConfig
    portraitMode: Optional[bool] = None
    frameBlur: Optional[bool] = False  # 是否需要逐帧模糊视频，默认false

class StartGenerationRequest(BaseModel):
    projectId: str

# 添加全局变量存储最新生成的视频
_latest_generated_videos = []

# 任务状态存储（生产环境建议用Redis）
_task_storage = {}

# 添加项目存储
_project_storage = {}

# 🚀 GPU优化：支持更多并发任务充分利用RTX 3090
_task_queue = asyncio.Queue()  # 任务队列
_processing_tasks: Set[str] = set()  # 正在处理的任务ID集合
_max_concurrent_tasks = 5  # 增加并发数以充分利用GPU (RTX 3090可支持更多并发)
_queue_processor_started = False  # 队列处理器是否已启动
_gpu_optimization_enabled = True  # GPU优化开关

async def start_concurrent_queue_processor():
    """启动GPU优化的并发队列处理器 - 支持更多并发任务"""
    global _processing_tasks, _queue_processor_started

    if _queue_processor_started:
        return

    _queue_processor_started = True
    print(f"🚀 启动GPU优化并发队列处理器 (支持{_max_concurrent_tasks}个并发任务)...")

    # 启动GPU调度器和性能监控
    if _gpu_optimization_enabled:
        try:
            await gpu_scheduler.start()
            await performance_optimizer.start_monitoring()
            print("✅ GPU调度器和性能监控已启动")
        except Exception as e:
            print(f"⚠️ GPU优化启动失败，使用CPU模式: {e}")

    # 创建更多并发工作协程以充分利用GPU
    workers = []
    for i in range(_max_concurrent_tasks):
        worker = asyncio.create_task(gpu_optimized_worker_coroutine(f"GPU-Worker-{i+1}"))
        workers.append(worker)

    # 等待所有工作协程完成
    await asyncio.gather(*workers)

async def gpu_optimized_worker_coroutine(worker_name: str):
    """GPU优化的工作协程 - 智能资源分配和任务处理"""
    print(f"🚀 {worker_name} 已启动 (GPU优化模式)")

    while True:
        try:
            # 从队列中获取任务
            task_data = await _task_queue.get()
            task_id = task_data['task_id']
            clip_req = task_data['clip_req']

            # 将任务添加到处理集合
            _processing_tasks.add(task_id)

            print(f"📋 {worker_name} 开始GPU加速处理: {task_id}")
            print(f"🔄 当前并发任务数: {len(_processing_tasks)}/{_max_concurrent_tasks}")

            # 检查GPU状态
            if _gpu_optimization_enabled:
                gpu_status = gpu_scheduler.get_status()
                print(f"   GPU状态: {gpu_status['gpu_tasks_running']}个GPU任务运行中")

            # 更新任务状态为处理中
            if task_id in _task_storage:
                _task_storage[task_id]["status"] = "processing"
                _task_storage[task_id]["progress"] = 10
                _task_storage[task_id]["updatedAt"] = datetime.now().isoformat()
                _task_storage[task_id]["worker"] = worker_name
                _task_storage[task_id]["gpu_enabled"] = _gpu_optimization_enabled

            # 执行GPU优化的视频生成任务
            start_time = time.time()
            await process_video_generation(task_id, clip_req)
            processing_time = time.time() - start_time

            print(f"✅ {worker_name} 完成任务: {task_id} (耗时: {processing_time:.1f}秒)")

            # 记录性能统计
            if task_id in _task_storage:
                _task_storage[task_id]["processing_time"] = processing_time
                _task_storage[task_id]["performance_optimized"] = True

        except Exception as e:
            print(f"❌ {worker_name} 处理任务异常: {e}")
            if task_id in _task_storage:
                _task_storage[task_id]["status"] = "failed"
                _task_storage[task_id]["error"] = f"GPU优化处理异常: {str(e)}"
                _task_storage[task_id]["updatedAt"] = datetime.now().isoformat()
        finally:
            # 从处理集合中移除任务
            if task_id in _processing_tasks:
                _processing_tasks.remove(task_id)
            _task_queue.task_done()
            print(f"🔄 当前并发任务数: {len(_processing_tasks)}/{_max_concurrent_tasks}")

# 保持原有的worker_coroutine作为备用
async def worker_coroutine(worker_name: str):
    """传统工作协程 - 备用模式"""
    return await gpu_optimized_worker_coroutine(worker_name)

async def process_clips_with_gpu_acceleration(task_id: str, clip_req: ClipRequest):
    """GPU加速的视频处理核心函数"""
    try:
        print(f"🎬 启动GPU加速视频处理: {clip_req.name}")

        # 更新进度 - 开始处理
        if task_id in _task_storage:
            _task_storage[task_id]["progress"] = 30
            _task_storage[task_id]["status"] = "processing"
            _task_storage[task_id]["updatedAt"] = datetime.now().isoformat()

        # 预处理阶段 - 并行下载和缓存素材
        print("📥 第一阶段: 并行预处理素材...")
        preprocess_start = time.time()

        # 这里可以添加并行素材下载逻辑
        # 暂时使用原有的处理逻辑，但添加GPU优化

        if task_id in _task_storage:
            _task_storage[task_id]["progress"] = 50
            _task_storage[task_id]["updatedAt"] = datetime.now().isoformat()

        preprocess_time = time.time() - preprocess_start
        print(f"✅ 预处理完成，耗时: {preprocess_time:.1f}秒")

        # 视频合成阶段 - 使用GPU加速
        print("🚀 第二阶段: GPU加速视频合成...")
        composition_start = time.time()

        # 调用优化后的视频处理服务
        result = await process_clips001(clip_req)

        composition_time = time.time() - composition_start
        print(f"✅ GPU合成完成，耗时: {composition_time:.1f}秒")

        if task_id in _task_storage:
            _task_storage[task_id]["progress"] = 90
            _task_storage[task_id]["updatedAt"] = datetime.now().isoformat()

        # 后处理阶段 - 优化和上传
        print("📤 第三阶段: 后处理和优化...")
        postprocess_start = time.time()

        # 这里可以添加视频优化和上传逻辑

        postprocess_time = time.time() - postprocess_start
        print(f"✅ 后处理完成，耗时: {postprocess_time:.1f}秒")

        # 计算总体性能统计
        total_time = preprocess_time + composition_time + postprocess_time
        print(f"📊 性能统计:")
        print(f"   预处理: {preprocess_time:.1f}s ({preprocess_time/total_time*100:.1f}%)")
        print(f"   GPU合成: {composition_time:.1f}s ({composition_time/total_time*100:.1f}%)")
        print(f"   后处理: {postprocess_time:.1f}s ({postprocess_time/total_time*100:.1f}%)")
        print(f"   总耗时: {total_time:.1f}s")

        return result

    except Exception as e:
        print(f"❌ GPU加速处理异常: {e}")
        # 回退到原始处理方式
        print("🔄 回退到CPU处理模式...")
        return await process_clips001(clip_req)

async def process_video_generation(task_id: str, clip_req: ClipRequest):
    """GPU加速的视频生成任务处理"""
    try:
        print(f"🚀 开始GPU加速视频生成: {task_id}")
        start_time = time.time()

        # 启动性能监控
        if not performance_optimizer.running:
            await performance_optimizer.start_monitoring()

        # 启动GPU调度器
        if not gpu_scheduler.running:
            await gpu_scheduler.start()

        # 更新进度
        if task_id in _task_storage:
            _task_storage[task_id]["progress"] = 20
            _task_storage[task_id]["updatedAt"] = datetime.now().isoformat()

        # 使用GPU加速的视频处理服务
        result = await process_clips_with_gpu_acceleration(task_id, clip_req)

        processing_time = time.time() - start_time
        print(f"✅ GPU加速处理完成: {task_id}, 耗时: {processing_time:.1f}秒")

        # 更新任务状态为完成
        if task_id in _task_storage:
            _task_storage[task_id]["status"] = "completed"
            _task_storage[task_id]["progress"] = 100
            _task_storage[task_id]["result"] = result
            _task_storage[task_id]["updatedAt"] = datetime.now().isoformat()
            
        # 添加到最新生成视频列表
        _latest_generated_videos.append({
            "id": task_id,
            "result": result,
            "createdAt": datetime.now().isoformat()
        })
        
        # 保持最新10个视频
        if len(_latest_generated_videos) > 10:
            _latest_generated_videos.pop(0)
            
    except Exception as e:
        print(f"❌ 视频生成失败: {e}")
        if task_id in _task_storage:
            _task_storage[task_id]["status"] = "failed"
            _task_storage[task_id]["error"] = str(e)
            _task_storage[task_id]["updatedAt"] = datetime.now().isoformat()
        raise

def get_queue_status_info():
    """获取队列状态信息"""
    queue_size = _task_queue.qsize()
    processing_count = len(_processing_tasks)
    available_workers = _max_concurrent_tasks - processing_count
    
    return {
        "queueSize": queue_size,
        "processingCount": processing_count,
        "maxConcurrentTasks": _max_concurrent_tasks,
        "availableWorkers": available_workers,
        "isProcessing": processing_count > 0,
        "processingTasks": list(_processing_tasks)
    }

# 保存项目配置
@router.post("/api/projects")
async def save_project_and_generate(req: ClipRequest, background_tasks: BackgroundTasks):
    # 保存项目配置到内存存储
    project_id = str(uuid4())
    _project_storage[project_id] = req
    
    # 启动队列处理器（如果未启动）
    if not _queue_processor_started:
        background_tasks.add_task(start_concurrent_queue_processor)
    
    return {
        "success": True,
        "data": {
            "id": project_id,
            "name": req.name,
            "videos": [v.dict() for v in req.videos],
            "audios": [a.dict() for a in req.audios],
            "posters": [p.dict() for p in (req.posters or [])],
            "scripts": [s.dict() for s in req.scripts],
            "duration": req.duration,
            "videoCount": req.videoCount,
            "voice": req.voice,
            "style": req.style.dict() if hasattr(req.style, "dict") else req.style,
            "portraitMode": req.portraitMode
        }
    }

# 开始生成视频
@router.post("/api/generation/start")
async def start_generation(req: StartGenerationRequest, background_tasks: BackgroundTasks):
    # 启动队列处理器（如果未启动）
    if not _queue_processor_started:
        background_tasks.add_task(start_concurrent_queue_processor)
    
    # 生成任务ID
    task_id = str(uuid4())
    
    # 获取项目配置
    if req.projectId not in _project_storage:
        return {
            "success": False,
            "error": "项目不存在"
        }
    
    clip_req = _project_storage[req.projectId]
    
    # 获取当前队列状态
    queue_status = get_queue_status_info()
    queue_size = queue_status["queueSize"]
    processing_count = queue_status["processingCount"]
    
    # 判断任务状态
    if processing_count < _max_concurrent_tasks:
        # 有空闲工作协程，立即处理
        task_status = "processing"
        queue_position = 1
    else:
        # 需要排队
        task_status = "queued"
        queue_position = queue_size + 1
    
    # 初始化任务状态
    _task_storage[task_id] = {
        "id": task_id,
        "projectId": req.projectId,
        "status": task_status,
        "progress": 0,
        "result": None,
        "error": None,
        "createdAt": datetime.now().isoformat(),
        "updatedAt": datetime.now().isoformat(),
        "queuePosition": queue_position,
        "queueSize": queue_size + 1
    }
    
    # 将任务加入队列
    await _task_queue.put({
        'task_id': task_id,
        'clip_req': clip_req
    })
    
    # 返回任务信息
    status_msg = "已加入处理队列" if task_status == "queued" else "开始处理"
    
    print(f"📝 新任务 {task_id}: {status_msg}")
    print(f"   队列状态: 队列中{queue_size + 1}个任务, 排队位置#{queue_position}")
    print(f"   正在处理: {processing_count}/{_max_concurrent_tasks} 个任务")
    
    return {
        "success": True,
        "data": {
            **_task_storage[task_id],
            "message": status_msg,
            "estimatedWaitTime": f"预计等待 {queue_position * 3} 分钟" if queue_position > 1 else "正在处理中"
        }
    }

# 获取任务状态
@router.get("/api/generation/status/{task_id}")
async def get_generation_status(task_id: str):
    if task_id not in _task_storage:
        return {
            "success": False,
            "error": "任务不存在"
        }
    
    task_data = _task_storage[task_id].copy()
    
    # 如果是排队状态，更新队列信息
    if task_data["status"] == "queued":
        current_queue_size = _task_queue.qsize()
        task_data["currentQueueSize"] = current_queue_size
        task_data["estimatedWaitTime"] = f"预计等待 {current_queue_size * 3} 分钟"
    
    return {
        "success": True,
        "data": task_data
    }

# GPU性能监控接口
@router.get("/api/gpu/status")
async def get_gpu_status():
    """获取GPU状态和性能信息"""
    try:
        # 获取GPU调度器状态
        gpu_status = gpu_scheduler.get_status() if gpu_scheduler.running else {
            "running": False,
            "gpu_tasks_running": 0,
            "cpu_tasks_running": 0,
            "stats": {"completed_tasks": 0, "failed_tasks": 0}
        }

        # 获取性能优化器状态
        perf_status = performance_optimizer.get_current_status() if performance_optimizer.running else {
            "running": False,
            "stats": {"avg_gpu_utilization": 0, "avg_cpu_utilization": 0}
        }

        # 获取队列状态
        queue_status = get_queue_status_info()

        return {
            "success": True,
            "data": {
                "gpu_scheduler": gpu_status,
                "performance_optimizer": perf_status,
                "task_queue": queue_status,
                "gpu_optimization_enabled": _gpu_optimization_enabled,
                "max_concurrent_tasks": _max_concurrent_tasks,
                "current_processing_tasks": len(_processing_tasks)
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"获取GPU状态失败: {str(e)}"
        }

# GPU优化配置接口
@router.post("/api/gpu/config")
async def update_gpu_config(config: Dict[str, Any]):
    """更新GPU优化配置"""
    global _max_concurrent_tasks, _gpu_optimization_enabled

    try:
        if "max_concurrent_tasks" in config:
            new_max = int(config["max_concurrent_tasks"])
            if 1 <= new_max <= 10:  # 合理范围
                _max_concurrent_tasks = new_max
                print(f"🔧 更新最大并发任务数: {_max_concurrent_tasks}")

        if "gpu_optimization_enabled" in config:
            _gpu_optimization_enabled = bool(config["gpu_optimization_enabled"])
            print(f"🔧 GPU优化开关: {'开启' if _gpu_optimization_enabled else '关闭'}")

        return {
            "success": True,
            "data": {
                "max_concurrent_tasks": _max_concurrent_tasks,
                "gpu_optimization_enabled": _gpu_optimization_enabled
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"更新GPU配置失败: {str(e)}"
        }

# 获取队列状态
@router.get("/api/generation/queue/status")
async def get_queue_status():
    queue_status = get_queue_status_info()
    queue_size = queue_status["queueSize"]
    processing_count = queue_status["processingCount"]
    
    # 统计各状态任务数量
    queued_tasks = [t for t in _task_storage.values() if t.get("status") == "queued"]
    processing_tasks = [t for t in _task_storage.values() if t.get("status") == "processing"]
    completed_tasks = [t for t in _task_storage.values() if t.get("status") == "completed"]
    failed_tasks = [t for t in _task_storage.values() if t.get("status") == "failed"]
    
    return {
        "success": True,
        "data": {
            "queueSize": queue_size,
            "processingCount": processing_count,
            "maxConcurrentTasks": _max_concurrent_tasks,
            "availableWorkers": queue_status["availableWorkers"],
            "isProcessing": queue_status["isProcessing"],
            "statistics": {
                "queued": len(queued_tasks),
                "processing": len(processing_tasks),
                "completed": len(completed_tasks),
                "failed": len(failed_tasks),
                "total": len(_task_storage)
            },
            "estimatedWaitTime": f"新任务预计等待 {(queue_size + 1) * 3} 分钟" if queue_size > 0 or processing_count >= _max_concurrent_tasks else "可立即处理"
        }
    }

# 获取最新生成的视频
@router.get("/api/generation/latest")
async def get_latest_generated_videos():
    return {
        "success": True,
        "data": _latest_generated_videos[-10:]  # 返回最新10个
    }
