"""
异步视频处理器
基于现有的并发管理器，提供简化的异步处理接口
"""

import asyncio
import time
import uuid
import subprocess
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

class TaskPriority(Enum):
    """任务优先级"""
    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class ProcessingTask:
    """处理任务"""
    task_id: str
    command: List[str]
    priority: TaskPriority
    use_gpu: bool
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: float = 0.0
    output_path: Optional[str] = None

class AsyncVideoProcessor:
    """异步视频处理器"""
    
    def __init__(self, max_gpu_tasks: int = 3, max_cpu_tasks: int = 2):
        self.max_gpu_tasks = max_gpu_tasks
        self.max_cpu_tasks = max_cpu_tasks
        self.tasks: Dict[str, ProcessingTask] = {}
        self.gpu_tasks: List[str] = []  # 当前GPU任务ID列表
        self.cpu_tasks: List[str] = []  # 当前CPU任务ID列表
        self.task_queue = asyncio.PriorityQueue()
        self.running = False
        self.worker_task = None
        
    async def start(self):
        """启动处理器"""
        if not self.running:
            self.running = True
            self.worker_task = asyncio.create_task(self._worker())
            logger.info("异步视频处理器已启动")
    
    async def stop(self):
        """停止处理器"""
        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("异步视频处理器已停止")
    
    async def submit_task(self, 
                         command: List[str], 
                         priority: TaskPriority = TaskPriority.NORMAL,
                         use_gpu: bool = True,
                         output_path: Optional[str] = None) -> str:
        """提交处理任务"""
        
        task_id = str(uuid.uuid4())
        
        task = ProcessingTask(
            task_id=task_id,
            command=command,
            priority=priority,
            use_gpu=use_gpu,
            created_at=time.time(),
            output_path=output_path
        )
        
        self.tasks[task_id] = task
        
        # 添加到优先级队列
        await self.task_queue.put((priority.value, time.time(), task_id))
        
        logger.info(f"任务已提交: {task_id}, 优先级: {priority.name}, GPU: {use_gpu}")
        
        # 确保处理器运行
        if not self.running:
            await self.start()
        
        return task_id
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        if task_id not in self.tasks:
            return {"error": "任务不存在"}
        
        task = self.tasks[task_id]
        
        return {
            "task_id": task_id,
            "status": task.status.value,
            "progress": task.progress,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error": task.error,
            "output_path": task.output_path
        }
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        if task.status in [TaskStatus.PENDING]:
            task.status = TaskStatus.CANCELLED
            logger.info(f"任务已取消: {task_id}")
            return True
        
        return False
    
    async def _worker(self):
        """工作线程"""
        logger.info("异步处理工作线程已启动")
        
        while self.running:
            try:
                # 检查是否有可用资源
                if not self._has_available_resources():
                    await asyncio.sleep(1)
                    continue
                
                # 获取下一个任务
                try:
                    priority, timestamp, task_id = await asyncio.wait_for(
                        self.task_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                if task_id not in self.tasks:
                    continue
                
                task = self.tasks[task_id]
                
                if task.status != TaskStatus.PENDING:
                    continue
                
                # 执行任务
                await self._execute_task(task)
                
            except Exception as e:
                logger.error(f"工作线程异常: {e}")
                await asyncio.sleep(1)
        
        logger.info("异步处理工作线程已停止")
    
    def _has_available_resources(self) -> bool:
        """检查是否有可用资源"""
        gpu_available = len(self.gpu_tasks) < self.max_gpu_tasks
        cpu_available = len(self.cpu_tasks) < self.max_cpu_tasks
        return gpu_available or cpu_available
    
    async def _execute_task(self, task: ProcessingTask):
        """执行单个任务"""
        task_id = task.task_id
        
        try:
            # 分配资源
            if task.use_gpu and len(self.gpu_tasks) < self.max_gpu_tasks:
                self.gpu_tasks.append(task_id)
                resource_type = "GPU"
            elif len(self.cpu_tasks) < self.max_cpu_tasks:
                self.cpu_tasks.append(task_id)
                resource_type = "CPU"
            else:
                # 资源不足，重新排队
                await self.task_queue.put((task.priority.value, time.time(), task_id))
                return
            
            # 更新任务状态
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            
            logger.info(f"开始执行任务: {task_id} ({resource_type})")
            
            # 执行FFmpeg命令
            process = await asyncio.create_subprocess_exec(
                *task.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 等待完成
            stdout, stderr = await process.communicate()
            
            # 更新任务状态
            task.completed_at = time.time()
            
            if process.returncode == 0:
                task.status = TaskStatus.COMPLETED
                task.progress = 100.0
                task.result = {
                    "stdout": stdout.decode() if stdout else "",
                    "returncode": process.returncode
                }
                logger.info(f"任务完成: {task_id}")
            else:
                task.status = TaskStatus.FAILED
                task.error = stderr.decode() if stderr else "未知错误"
                logger.error(f"任务失败: {task_id}, 错误: {task.error}")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            logger.error(f"任务执行异常: {task_id}, 错误: {e}")
        
        finally:
            # 释放资源
            if task_id in self.gpu_tasks:
                self.gpu_tasks.remove(task_id)
            if task_id in self.cpu_tasks:
                self.cpu_tasks.remove(task_id)
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        pending_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.PENDING)
        running_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.RUNNING)
        completed_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.FAILED)
        
        return {
            "running": self.running,
            "gpu_tasks": {
                "active": len(self.gpu_tasks),
                "max": self.max_gpu_tasks,
                "utilization": len(self.gpu_tasks) / self.max_gpu_tasks * 100
            },
            "cpu_tasks": {
                "active": len(self.cpu_tasks),
                "max": self.max_cpu_tasks,
                "utilization": len(self.cpu_tasks) / self.max_cpu_tasks * 100
            },
            "task_counts": {
                "pending": pending_tasks,
                "running": running_tasks,
                "completed": completed_tasks,
                "failed": failed_tasks,
                "total": len(self.tasks)
            },
            "queue_size": self.task_queue.qsize()
        }

# 全局实例
_processor_instance = None

def get_async_processor() -> AsyncVideoProcessor:
    """获取异步处理器实例"""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = AsyncVideoProcessor()
    return _processor_instance
