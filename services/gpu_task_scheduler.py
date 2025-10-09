"""
GPU任务调度器 - 优化GPU和CPU资源分配，提升并发处理能力
专为RTX 3090优化，实现GPU使用率最大化
"""

import asyncio
import time
import psutil
import subprocess
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class TaskType(Enum):
    """任务类型枚举"""
    VIDEO_ENCODE = "video_encode"      # 视频编码
    VIDEO_DECODE = "video_decode"      # 视频解码
    VIDEO_FILTER = "video_filter"      # 视频滤镜
    VIDEO_CONCAT = "video_concat"      # 视频拼接
    AUDIO_PROCESS = "audio_process"    # 音频处理
    IMAGE_PROCESS = "image_process"    # 图像处理

class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class GPUTask:
    """GPU任务数据类"""
    task_id: str
    task_type: TaskType
    priority: TaskPriority
    command: List[str]
    input_files: List[str]
    output_file: str
    estimated_duration: float = 0.0
    gpu_memory_required: int = 1024  # MB
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    status: str = "pending"  # pending, running, completed, failed

class GPUResourceMonitor:
    """GPU资源监控器"""
    
    def __init__(self):
        self.gpu_available = self._check_gpu_availability()
        self.gpu_memory_total = self._get_gpu_memory_total()
        self.gpu_utilization_history = []
        self.cpu_utilization_history = []
    
    def _check_gpu_availability(self) -> bool:
        """检查GPU可用性"""
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def _get_gpu_memory_total(self) -> int:
        """获取GPU总内存（MB）"""
        try:
            result = subprocess.run([
                'nvidia-smi', '--query-gpu=memory.total', 
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                return int(result.stdout.strip())
            return 24576  # RTX 3090默认值
        except:
            return 24576
    
    def get_gpu_status(self) -> Dict:
        """获取GPU状态"""
        try:
            result = subprocess.run([
                'nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                values = result.stdout.strip().split(', ')
                return {
                    'utilization': int(values[0]),
                    'memory_used': int(values[1]),
                    'memory_total': int(values[2]),
                    'temperature': int(values[3]),
                    'memory_free': int(values[2]) - int(values[1])
                }
        except:
            pass
        
        return {
            'utilization': 0,
            'memory_used': 0,
            'memory_total': self.gpu_memory_total,
            'temperature': 0,
            'memory_free': self.gpu_memory_total
        }
    
    def get_cpu_status(self) -> Dict:
        """获取CPU状态"""
        return {
            'utilization': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'core_count': psutil.cpu_count(),
            'load_avg': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
        }
    
    def update_history(self):
        """更新历史记录"""
        gpu_status = self.get_gpu_status()
        cpu_status = self.get_cpu_status()
        
        self.gpu_utilization_history.append({
            'timestamp': time.time(),
            'utilization': gpu_status['utilization'],
            'memory_used': gpu_status['memory_used']
        })
        
        self.cpu_utilization_history.append({
            'timestamp': time.time(),
            'utilization': cpu_status['utilization'],
            'memory_percent': cpu_status['memory_percent']
        })
        
        # 保持历史记录在合理范围内
        if len(self.gpu_utilization_history) > 100:
            self.gpu_utilization_history = self.gpu_utilization_history[-50:]
        if len(self.cpu_utilization_history) > 100:
            self.cpu_utilization_history = self.cpu_utilization_history[-50:]

class GPUTaskScheduler:
    """GPU任务调度器 - 优化资源分配"""
    
    def __init__(self, max_concurrent_gpu_tasks: int = 3, max_concurrent_cpu_tasks: int = 8):
        self.max_concurrent_gpu_tasks = max_concurrent_gpu_tasks
        self.max_concurrent_cpu_tasks = max_concurrent_cpu_tasks
        
        self.resource_monitor = GPUResourceMonitor()
        self.task_queues = {
            TaskPriority.URGENT: asyncio.PriorityQueue(),
            TaskPriority.HIGH: asyncio.PriorityQueue(),
            TaskPriority.NORMAL: asyncio.PriorityQueue(),
            TaskPriority.LOW: asyncio.PriorityQueue()
        }
        
        self.running_gpu_tasks: Dict[str, GPUTask] = {}
        self.running_cpu_tasks: Dict[str, GPUTask] = {}
        self.completed_tasks: Dict[str, GPUTask] = {}
        
        self.running = False
        self.scheduler_task = None
        self.monitor_task = None
        
        # 性能统计
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'gpu_utilization_avg': 0.0,
            'cpu_utilization_avg': 0.0,
            'throughput': 0.0  # 任务/秒
        }
    
    async def start(self):
        """启动调度器"""
        if self.running:
            return
        
        self.running = True
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("🚀 GPU任务调度器已启动")
        logger.info(f"   最大GPU并发任务: {self.max_concurrent_gpu_tasks}")
        logger.info(f"   最大CPU并发任务: {self.max_concurrent_cpu_tasks}")
    
    async def stop(self):
        """停止调度器"""
        self.running = False
        
        if self.scheduler_task:
            self.scheduler_task.cancel()
        if self.monitor_task:
            self.monitor_task.cancel()
        
        # 等待所有运行中的任务完成
        all_tasks = list(self.running_gpu_tasks.values()) + list(self.running_cpu_tasks.values())
        if all_tasks:
            logger.info(f"等待 {len(all_tasks)} 个任务完成...")
            # 这里可以添加任务取消逻辑
        
        logger.info("🛑 GPU任务调度器已停止")
    
    async def submit_task(self, task: GPUTask) -> str:
        """提交任务到调度器"""
        task.created_at = time.time()
        task.task_id = f"{task.task_type.value}_{int(time.time() * 1000)}_{len(self.completed_tasks)}"
        
        # 根据优先级添加到对应队列
        await self.task_queues[task.priority].put((task.priority.value, task.created_at, task))
        
        self.stats['total_tasks'] += 1
        
        logger.info(f"📝 任务已提交: {task.task_id} ({task.task_type.value}, 优先级: {task.priority.name})")
        
        # 确保调度器运行
        if not self.running:
            await self.start()
        
        return task.task_id
    
    async def _scheduler_loop(self):
        """调度器主循环"""
        while self.running:
            try:
                # 检查是否有可用资源
                if not await self._has_available_resources():
                    await asyncio.sleep(0.1)
                    continue
                
                # 按优先级获取任务
                task = await self._get_next_task()
                if task:
                    await self._execute_task(task)
                else:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"调度器循环错误: {e}")
                await asyncio.sleep(1)
    
    async def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                self.resource_monitor.update_history()
                await self._update_performance_stats()
                await self._optimize_resource_allocation()
                await asyncio.sleep(5)  # 每5秒监控一次
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(5)
    
    async def _has_available_resources(self) -> bool:
        """检查是否有可用资源"""
        gpu_status = self.resource_monitor.get_gpu_status()
        cpu_status = self.resource_monitor.get_cpu_status()
        
        # GPU资源检查
        gpu_available = (
            len(self.running_gpu_tasks) < self.max_concurrent_gpu_tasks and
            gpu_status['memory_free'] > 2048 and  # 至少2GB空闲内存
            gpu_status['utilization'] < 90
        )
        
        # CPU资源检查
        cpu_available = (
            len(self.running_cpu_tasks) < self.max_concurrent_cpu_tasks and
            cpu_status['utilization'] < 80 and
            cpu_status['memory_percent'] < 85
        )
        
        return gpu_available or cpu_available
    
    async def _get_next_task(self) -> Optional[GPUTask]:
        """获取下一个要执行的任务"""
        # 按优先级顺序检查队列
        for priority in [TaskPriority.URGENT, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]:
            queue = self.task_queues[priority]
            if not queue.empty():
                try:
                    _, _, task = await asyncio.wait_for(queue.get(), timeout=0.1)
                    return task
                except asyncio.TimeoutError:
                    continue
        
        return None
    
    async def _execute_task(self, task: GPUTask):
        """执行任务"""
        task.started_at = time.time()
        task.status = "running"
        
        # 决定使用GPU还是CPU
        gpu_status = self.resource_monitor.get_gpu_status()
        use_gpu = (
            self.resource_monitor.gpu_available and
            len(self.running_gpu_tasks) < self.max_concurrent_gpu_tasks and
            gpu_status['memory_free'] >= task.gpu_memory_required and
            task.task_type in [TaskType.VIDEO_ENCODE, TaskType.VIDEO_FILTER, TaskType.VIDEO_CONCAT]
        )
        
        if use_gpu:
            self.running_gpu_tasks[task.task_id] = task
            logger.info(f"🚀 GPU执行任务: {task.task_id}")
        else:
            self.running_cpu_tasks[task.task_id] = task
            logger.info(f"🖥️ CPU执行任务: {task.task_id}")
        
        # 异步执行任务
        asyncio.create_task(self._run_task_command(task, use_gpu))
    
    async def _run_task_command(self, task: GPUTask, use_gpu: bool):
        """运行任务命令"""
        try:
            # 执行FFmpeg命令
            process = await asyncio.create_subprocess_exec(
                *task.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            task.completed_at = time.time()
            
            if process.returncode == 0:
                task.status = "completed"
                self.stats['completed_tasks'] += 1
                logger.info(f"✅ 任务完成: {task.task_id} (耗时: {task.completed_at - task.started_at:.1f}s)")
            else:
                task.status = "failed"
                self.stats['failed_tasks'] += 1
                logger.error(f"❌ 任务失败: {task.task_id} - {stderr.decode()}")
            
        except Exception as e:
            task.status = "failed"
            task.completed_at = time.time()
            self.stats['failed_tasks'] += 1
            logger.error(f"❌ 任务异常: {task.task_id} - {e}")
        
        finally:
            # 从运行队列中移除
            if use_gpu and task.task_id in self.running_gpu_tasks:
                del self.running_gpu_tasks[task.task_id]
            elif task.task_id in self.running_cpu_tasks:
                del self.running_cpu_tasks[task.task_id]
            
            # 添加到完成队列
            self.completed_tasks[task.task_id] = task
    
    async def _update_performance_stats(self):
        """更新性能统计"""
        if len(self.resource_monitor.gpu_utilization_history) > 0:
            recent_gpu = self.resource_monitor.gpu_utilization_history[-10:]
            self.stats['gpu_utilization_avg'] = sum(h['utilization'] for h in recent_gpu) / len(recent_gpu)
        
        if len(self.resource_monitor.cpu_utilization_history) > 0:
            recent_cpu = self.resource_monitor.cpu_utilization_history[-10:]
            self.stats['cpu_utilization_avg'] = sum(h['utilization'] for h in recent_cpu) / len(recent_cpu)
        
        # 计算吞吐量
        if self.stats['total_tasks'] > 0:
            total_time = time.time() - (min(task.created_at for task in self.completed_tasks.values()) if self.completed_tasks else time.time())
            if total_time > 0:
                self.stats['throughput'] = self.stats['completed_tasks'] / total_time
    
    async def _optimize_resource_allocation(self):
        """优化资源分配"""
        gpu_status = self.resource_monitor.get_gpu_status()
        cpu_status = self.resource_monitor.get_cpu_status()
        
        # 动态调整并发数
        if gpu_status['utilization'] < 50 and gpu_status['memory_free'] > 8192:
            # GPU利用率低，可以增加并发
            self.max_concurrent_gpu_tasks = min(5, self.max_concurrent_gpu_tasks + 1)
        elif gpu_status['utilization'] > 90 or gpu_status['memory_free'] < 2048:
            # GPU负载高，减少并发
            self.max_concurrent_gpu_tasks = max(1, self.max_concurrent_gpu_tasks - 1)
        
        if cpu_status['utilization'] < 60:
            self.max_concurrent_cpu_tasks = min(12, self.max_concurrent_cpu_tasks + 1)
        elif cpu_status['utilization'] > 85:
            self.max_concurrent_cpu_tasks = max(2, self.max_concurrent_cpu_tasks - 1)
    
    def get_status(self) -> Dict:
        """获取调度器状态"""
        return {
            'running': self.running,
            'gpu_tasks_running': len(self.running_gpu_tasks),
            'cpu_tasks_running': len(self.running_cpu_tasks),
            'max_concurrent_gpu': self.max_concurrent_gpu_tasks,
            'max_concurrent_cpu': self.max_concurrent_cpu_tasks,
            'stats': self.stats,
            'gpu_status': self.resource_monitor.get_gpu_status(),
            'cpu_status': self.resource_monitor.get_cpu_status()
        }

# 全局调度器实例
gpu_scheduler = GPUTaskScheduler()
