"""
并发视频处理管理器
支持多任务并发处理、资源管理、负载均衡
"""

import asyncio
import time
import psutil
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
import logging
from concurrent.futures import ThreadPoolExecutor
import queue

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class VideoProcessingTask:
    """视频处理任务"""
    task_id: str
    task_type: str  # montage, subtitle, encode等
    params: Dict[str, Any]
    priority: int = 5  # 1-10，数字越小优先级越高
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: float = 0.0

@dataclass
class SystemResources:
    """系统资源状态"""
    cpu_percent: float
    memory_percent: float
    gpu_memory_used: float
    gpu_utilization: float
    active_tasks: int
    max_concurrent_tasks: int

class ResourceMonitor:
    """资源监控器"""
    
    def __init__(self):
        self.gpu_available = self._check_gpu_available()
        
    def _check_gpu_available(self) -> bool:
        """检查GPU是否可用"""
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi'], capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def get_system_resources(self) -> SystemResources:
        """获取系统资源状态"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        gpu_memory_used = 0.0
        gpu_utilization = 0.0
        
        if self.gpu_available:
            try:
                import subprocess
                result = subprocess.run([
                    'nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu',
                    '--format=csv,noheader,nounits'
                ], capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if lines and lines[0]:
                        parts = lines[0].split(', ')
                        memory_used = float(parts[0])
                        memory_total = float(parts[1])
                        gpu_memory_used = (memory_used / memory_total) * 100
                        gpu_utilization = float(parts[2])
            except:
                pass
        
        return SystemResources(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            gpu_memory_used=gpu_memory_used,
            gpu_utilization=gpu_utilization,
            active_tasks=0,  # 将由管理器设置
            max_concurrent_tasks=0  # 将由管理器设置
        )

class ConcurrentVideoManager:
    """并发视频处理管理器"""
    
    def __init__(self, max_concurrent_tasks: int = 3, max_gpu_tasks: int = 2):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.max_gpu_tasks = max_gpu_tasks
        
        # 任务管理
        self.tasks: Dict[str, VideoProcessingTask] = {}
        self.task_queue = asyncio.PriorityQueue()
        self.running_tasks: Dict[str, asyncio.Task] = {}
        
        # 资源管理
        self.resource_monitor = ResourceMonitor()
        self.gpu_task_count = 0
        self.cpu_task_count = 0
        
        # 线程池用于CPU密集型任务
        self.cpu_executor = ThreadPoolExecutor(max_workers=max_concurrent_tasks)
        
        # 任务处理器映射
        self.task_processors: Dict[str, Callable] = {}
        
        # 启动后台任务
        self._background_tasks = []
        self._running = False
        
        logger.info(f"并发管理器初始化完成，最大并发任务: {max_concurrent_tasks}")
    
    def register_processor(self, task_type: str, processor: Callable):
        """注册任务处理器"""
        self.task_processors[task_type] = processor
        logger.info(f"注册任务处理器: {task_type}")
    
    async def start(self):
        """启动管理器"""
        if self._running:
            return
            
        self._running = True
        
        # 启动任务调度器
        scheduler_task = asyncio.create_task(self._task_scheduler())
        self._background_tasks.append(scheduler_task)
        
        # 启动资源监控器
        monitor_task = asyncio.create_task(self._resource_monitor_loop())
        self._background_tasks.append(monitor_task)
        
        logger.info("并发管理器已启动")
    
    async def stop(self):
        """停止管理器"""
        if not self._running:
            return
            
        self._running = False
        
        # 取消所有后台任务
        for task in self._background_tasks:
            task.cancel()
        
        # 等待所有运行中的任务完成
        if self.running_tasks:
            await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)
        
        # 关闭线程池
        self.cpu_executor.shutdown(wait=True)
        
        logger.info("并发管理器已停止")
    
    async def submit_task(self, task_type: str, params: Dict[str, Any], 
                         priority: int = 5) -> str:
        """提交任务"""
        task_id = str(uuid4())
        
        task = VideoProcessingTask(
            task_id=task_id,
            task_type=task_type,
            params=params,
            priority=priority
        )
        
        self.tasks[task_id] = task
        
        # 添加到优先级队列（优先级越小越先执行）
        await self.task_queue.put((priority, time.time(), task))
        
        logger.info(f"任务已提交: {task_id} ({task_type})")
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[VideoProcessingTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[VideoProcessingTask]:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        resources = self.resource_monitor.get_system_resources()
        resources.active_tasks = len(self.running_tasks)
        resources.max_concurrent_tasks = self.max_concurrent_tasks
        
        return {
            "resources": resources,
            "task_queue_size": self.task_queue.qsize(),
            "running_tasks": len(self.running_tasks),
            "total_tasks": len(self.tasks),
            "gpu_tasks": self.gpu_task_count,
            "cpu_tasks": self.cpu_task_count
        }
    
    async def _task_scheduler(self):
        """任务调度器"""
        while self._running:
            try:
                # 检查是否可以启动新任务
                if len(self.running_tasks) >= self.max_concurrent_tasks:
                    await asyncio.sleep(1)
                    continue
                
                # 检查系统资源
                resources = self.resource_monitor.get_system_resources()
                if resources.cpu_percent > 90 or resources.memory_percent > 85:
                    logger.warning("系统资源不足，暂停任务调度")
                    await asyncio.sleep(5)
                    continue
                
                # 从队列获取任务
                try:
                    priority, timestamp, task = await asyncio.wait_for(
                        self.task_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # 检查任务是否已被取消
                if task.status == TaskStatus.CANCELLED:
                    continue
                
                # 启动任务
                await self._start_task(task)
                
            except Exception as e:
                logger.error(f"任务调度器错误: {e}")
                await asyncio.sleep(1)
    
    async def _start_task(self, task: VideoProcessingTask):
        """启动任务"""
        if task.task_type not in self.task_processors:
            task.status = TaskStatus.FAILED
            task.error = f"未找到任务处理器: {task.task_type}"
            logger.error(task.error)
            return
        
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        
        # 创建任务协程
        processor = self.task_processors[task.task_type]
        task_coroutine = self._execute_task(task, processor)
        
        # 启动任务
        async_task = asyncio.create_task(task_coroutine)
        self.running_tasks[task.task_id] = async_task
        
        logger.info(f"任务已启动: {task.task_id}")
    
    async def _execute_task(self, task: VideoProcessingTask, processor: Callable):
        """执行任务"""
        try:
            # 判断是否为GPU任务
            is_gpu_task = task.params.get('use_gpu', True) and self.resource_monitor.gpu_available
            
            if is_gpu_task:
                self.gpu_task_count += 1
            else:
                self.cpu_task_count += 1
            
            # 执行任务
            if asyncio.iscoroutinefunction(processor):
                result = await processor(task.params)
            else:
                # CPU密集型任务使用线程池
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(self.cpu_executor, processor, task.params)
            
            # 任务完成
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()
            task.progress = 100.0
            
            logger.info(f"任务完成: {task.task_id}")
            
        except Exception as e:
            # 任务失败
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            
            logger.error(f"任务失败: {task.task_id}, 错误: {e}")
            
        finally:
            # 清理
            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]
            
            if task.params.get('use_gpu', True):
                self.gpu_task_count = max(0, self.gpu_task_count - 1)
            else:
                self.cpu_task_count = max(0, self.cpu_task_count - 1)
    
    async def _resource_monitor_loop(self):
        """资源监控循环"""
        while self._running:
            try:
                resources = self.resource_monitor.get_system_resources()
                
                # 记录资源使用情况
                if resources.cpu_percent > 80:
                    logger.warning(f"CPU使用率过高: {resources.cpu_percent}%")
                
                if resources.memory_percent > 80:
                    logger.warning(f"内存使用率过高: {resources.memory_percent}%")
                
                if resources.gpu_memory_used > 80:
                    logger.warning(f"GPU内存使用率过高: {resources.gpu_memory_used}%")
                
                await asyncio.sleep(10)  # 每10秒检查一次
                
            except Exception as e:
                logger.error(f"资源监控错误: {e}")
                await asyncio.sleep(10)

# 全局管理器实例
_manager_instance = None

def get_video_manager() -> ConcurrentVideoManager:
    """获取视频管理器实例（单例模式）"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ConcurrentVideoManager()
    return _manager_instance
