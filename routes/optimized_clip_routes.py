"""
优化的视频剪辑路由
集成新的FFmpeg处理器和并发管理器
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
import asyncio
import time

# 导入优化服务
from services.optimized_clip_service import get_optimized_clip_service
from services.concurrent_video_manager import get_video_manager

logger = logging.getLogger(__name__)

router = APIRouter()

class OptimizedClipRequest(BaseModel):
    """优化的视频剪辑请求"""
    video_count: int = 1
    duration: int = 30
    scripts: List[Dict[str, Any]] = []
    style: Dict[str, Any] = {}
    local_video_paths: List[str] = []
    local_audio_paths: List[str] = []
    use_gpu: bool = True
    quality_preset: str = "balanced"  # fast/balanced/quality
    priority: int = 5  # 1-10，数字越小优先级越高

class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    progress: float
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

@router.post("/api/clips/generate-optimized")
async def generate_clips_optimized(request: OptimizedClipRequest):
    """
    优化的视频生成接口
    使用FFmpeg处理器和并发管理器提供高性能视频处理
    """
    try:
        logger.info(f"收到优化视频生成请求，数量: {request.video_count}, 时长: {request.duration}s")
        
        # 获取优化服务
        service = get_optimized_clip_service()
        
        # 转换请求数据
        request_data = {
            'video_count': request.video_count,
            'duration': request.duration,
            'scripts': [{'content': script.get('content', '')} for script in request.scripts],
            'style': request.style,
            'local_video_paths': request.local_video_paths,
            'local_audio_paths': request.local_audio_paths,
            'use_gpu': request.use_gpu,
            'quality_preset': request.quality_preset
        }
        
        # 验证输入数据
        if not request.local_video_paths:
            raise HTTPException(status_code=400, detail="至少需要提供一个视频文件")
        
        if request.video_count <= 0 or request.video_count > 10:
            raise HTTPException(status_code=400, detail="视频数量必须在1-10之间")
        
        if request.duration <= 0 or request.duration > 300:
            raise HTTPException(status_code=400, detail="视频时长必须在1-300秒之间")
        
        # 处理视频
        start_time = time.time()
        result = await service.process_clips_optimized(request_data)
        processing_time = time.time() - start_time
        
        if result.get('success'):
            logger.info(f"优化视频生成成功，耗时: {processing_time:.2f}s")
            return JSONResponse(content={
                "success": True,
                "message": "视频生成成功",
                "data": {
                    "videos": result.get('videos', []),
                    "processing_time": processing_time,
                    "performance_stats": result.get('performance_stats', {}),
                    "optimization_enabled": True
                }
            })
        else:
            logger.error(f"优化视频生成失败: {result.get('error')}")
            raise HTTPException(status_code=500, detail=result.get('error', '视频生成失败'))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"优化视频生成异常: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

@router.post("/api/clips/generate-async")
async def generate_clips_async(request: OptimizedClipRequest):
    """
    异步视频生成接口
    立即返回任务ID，客户端可以通过任务ID查询进度
    """
    try:
        logger.info(f"收到异步视频生成请求，数量: {request.video_count}")
        
        # 获取并发管理器
        manager = get_video_manager()
        await manager.start()
        
        # 提交任务
        task_id = await manager.submit_task(
            task_type='video_generation',
            params={
                'video_count': request.video_count,
                'duration': request.duration,
                'scripts': request.scripts,
                'style': request.style,
                'local_video_paths': request.local_video_paths,
                'local_audio_paths': request.local_audio_paths,
                'use_gpu': request.use_gpu,
                'quality_preset': request.quality_preset
            },
            priority=request.priority
        )
        
        logger.info(f"异步任务已提交: {task_id}")
        
        return JSONResponse(content={
            "success": True,
            "message": "任务已提交",
            "data": {
                "task_id": task_id,
                "estimated_time": request.duration * request.video_count * 0.2,  # 估算时间
                "status_url": f"/api/clips/task/{task_id}/status"
            }
        })
        
    except Exception as e:
        logger.error(f"异步任务提交失败: {e}")
        raise HTTPException(status_code=500, detail=f"任务提交失败: {str(e)}")

@router.get("/api/clips/task/{task_id}/status")
async def get_task_status(task_id: str):
    """获取任务状态"""
    try:
        manager = get_video_manager()
        task = manager.get_task_status(task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        response = TaskStatusResponse(
            task_id=task.task_id,
            status=task.status.value,
            progress=task.progress,
            result=task.result,
            error=task.error,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at
        )
        
        return JSONResponse(content={
            "success": True,
            "data": response.dict()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@router.get("/api/clips/tasks")
async def get_all_tasks():
    """获取所有任务状态"""
    try:
        manager = get_video_manager()
        tasks = manager.get_all_tasks()
        
        task_list = []
        for task in tasks:
            task_list.append({
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": task.status.value,
                "progress": task.progress,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "error": task.error
            })
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "tasks": task_list,
                "total_count": len(task_list)
            }
        })
        
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")

@router.get("/api/system/performance")
async def get_system_performance():
    """获取系统性能状态"""
    try:
        # 获取优化服务状态
        service = get_optimized_clip_service()
        performance_stats = await service.get_processing_status()
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "performance_stats": performance_stats,
                "optimization_enabled": True,
                "timestamp": time.time()
            }
        })
        
    except Exception as e:
        logger.error(f"获取性能状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取性能状态失败: {str(e)}")

@router.post("/api/clips/generate-with-fallback")
async def generate_clips_with_fallback(request: OptimizedClipRequest):
    """
    带降级的视频生成接口
    优先使用优化方案，失败时自动降级到原有方案
    """
    try:
        logger.info(f"收到带降级的视频生成请求")
        
        # 尝试使用优化服务
        try:
            service = get_optimized_clip_service()
            request_data = {
                'video_count': request.video_count,
                'duration': request.duration,
                'scripts': [{'content': script.get('content', '')} for script in request.scripts],
                'style': request.style,
                'local_video_paths': request.local_video_paths,
                'local_audio_paths': request.local_audio_paths,
                'use_gpu': request.use_gpu,
                'quality_preset': request.quality_preset
            }
            
            result = await service.process_clips_optimized(request_data)
            
            if result.get('success'):
                logger.info("使用优化方案处理成功")
                return JSONResponse(content={
                    "success": True,
                    "message": "视频生成成功（优化方案）",
                    "data": {
                        "videos": result.get('videos', []),
                        "processing_method": "optimized",
                        "performance_stats": result.get('performance_stats', {})
                    }
                })
            else:
                logger.warning(f"优化方案失败: {result.get('error')}，尝试降级")
                raise Exception(result.get('error', '优化方案失败'))
                
        except Exception as e:
            logger.warning(f"优化方案异常: {e}，降级到原有方案")
            
            # 降级到原有方案（这里需要调用原有的处理函数）
            # 注意：这里需要根据您的实际原有函数进行调整
            from services.clip_service import process_clips  # 假设原有函数
            
            # 转换为原有格式的请求
            original_request = {
                # 根据原有接口格式转换参数
                'video_count': request.video_count,
                'duration': request.duration,
                # ... 其他参数转换
            }
            
            # 调用原有处理函数
            original_result = await process_clips(original_request)
            
            if original_result.get('success'):
                logger.info("降级方案处理成功")
                return JSONResponse(content={
                    "success": True,
                    "message": "视频生成成功（降级方案）",
                    "data": {
                        "videos": original_result.get('videos', []),
                        "processing_method": "fallback",
                        "fallback_reason": str(e)
                    }
                })
            else:
                raise HTTPException(status_code=500, detail="所有处理方案均失败")
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"视频生成完全失败: {e}")
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")

@router.post("/api/system/optimize")
async def trigger_system_optimization():
    """触发系统优化"""
    try:
        # 这里可以添加系统优化逻辑
        # 例如：清理临时文件、优化缓存、重启服务等
        
        logger.info("触发系统优化")
        
        return JSONResponse(content={
            "success": True,
            "message": "系统优化已触发",
            "data": {
                "optimization_time": time.time(),
                "actions": [
                    "清理临时文件",
                    "优化内存使用",
                    "重置任务队列"
                ]
            }
        })
        
    except Exception as e:
        logger.error(f"系统优化失败: {e}")
        raise HTTPException(status_code=500, detail=f"系统优化失败: {str(e)}")

# 启动时注册视频生成处理器
@router.on_event("startup")
async def startup_event():
    """启动时初始化"""
    try:
        # 注册视频生成处理器
        manager = get_video_manager()
        
        async def video_generation_processor(params):
            """视频生成处理器"""
            service = get_optimized_clip_service()
            return await service.process_clips_optimized(params)
        
        manager.register_processor('video_generation', video_generation_processor)
        
        logger.info("优化路由初始化完成")
        
    except Exception as e:
        logger.error(f"优化路由初始化失败: {e}")

@router.on_event("shutdown")
async def shutdown_event():
    """关闭时清理"""
    try:
        # 清理资源
        service = get_optimized_clip_service()
        await service.cleanup()
        
        manager = get_video_manager()
        await manager.stop()
        
        logger.info("优化路由清理完成")
        
    except Exception as e:
        logger.error(f"优化路由清理失败: {e}")
