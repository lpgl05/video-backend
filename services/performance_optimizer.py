"""
性能监控和自动调优系统
实时监控GPU/CPU使用率，自动调整参数以最大化性能
"""

import asyncio
import time
import json
import os
import subprocess
import psutil
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: float
    gpu_utilization: int
    gpu_memory_used: int
    gpu_memory_total: int
    gpu_temperature: int
    cpu_utilization: float
    cpu_memory_percent: float
    active_gpu_tasks: int
    active_cpu_tasks: int
    video_processing_fps: float = 0.0
    encoding_speed: float = 0.0

@dataclass
class OptimizationRecommendation:
    """优化建议数据类"""
    category: str  # gpu, cpu, memory, encoding
    priority: str  # low, medium, high, critical
    title: str
    description: str
    action: str
    expected_improvement: str

class PerformanceOptimizer:
    """性能优化器 - 自动监控和调优"""
    
    def __init__(self):
        self.running = False
        self.metrics_history: List[PerformanceMetrics] = []
        self.optimization_history: List[OptimizationRecommendation] = []
        
        # 性能阈值配置
        self.thresholds = {
            'gpu_utilization_low': 30,      # GPU利用率过低阈值
            'gpu_utilization_high': 95,     # GPU利用率过高阈值
            'gpu_memory_high': 90,          # GPU内存使用过高阈值
            'cpu_utilization_high': 85,     # CPU利用率过高阈值
            'cpu_memory_high': 90,          # CPU内存使用过高阈值
            'gpu_temperature_high': 83,     # GPU温度过高阈值
            'encoding_fps_low': 50,         # 编码FPS过低阈值
        }
        
        # 当前优化配置
        self.current_config = {
            'gpu_encoding_quality': 'balanced',
            'max_concurrent_gpu_tasks': 3,
            'max_concurrent_cpu_tasks': 8,
            'ffmpeg_threads': psutil.cpu_count() // 2,
            'gpu_memory_buffer': 2048,  # MB
        }
        
        # 性能统计
        self.stats = {
            'monitoring_duration': 0.0,
            'total_optimizations': 0,
            'performance_improvements': [],
            'avg_gpu_utilization': 0.0,
            'avg_cpu_utilization': 0.0,
            'peak_encoding_fps': 0.0,
        }
    
    async def start_monitoring(self):
        """开始性能监控"""
        if self.running:
            return
        
        self.running = True
        self.start_time = time.time()
        
        logger.info("🔍 性能监控系统启动")
        logger.info("   监控GPU/CPU使用率")
        logger.info("   自动优化编码参数")
        logger.info("   实时调整并发数")
        
        # 启动监控任务
        asyncio.create_task(self._monitoring_loop())
        asyncio.create_task(self._optimization_loop())
    
    async def stop_monitoring(self):
        """停止性能监控"""
        self.running = False
        self.stats['monitoring_duration'] = time.time() - self.start_time
        
        logger.info("🛑 性能监控系统停止")
        await self._generate_performance_report()
    
    async def _monitoring_loop(self):
        """监控循环 - 每秒收集性能数据"""
        while self.running:
            try:
                metrics = await self._collect_performance_metrics()
                self.metrics_history.append(metrics)
                
                # 保持历史记录在合理范围内
                if len(self.metrics_history) > 300:  # 保留5分钟数据
                    self.metrics_history = self.metrics_history[-200:]
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"性能监控错误: {e}")
                await asyncio.sleep(5)
    
    async def _optimization_loop(self):
        """优化循环 - 每10秒分析并优化"""
        while self.running:
            try:
                if len(self.metrics_history) >= 10:
                    await self._analyze_and_optimize()
                
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"性能优化错误: {e}")
                await asyncio.sleep(10)
    
    async def _collect_performance_metrics(self) -> PerformanceMetrics:
        """收集性能指标"""
        # GPU指标
        gpu_metrics = await self._get_gpu_metrics()
        
        # CPU指标
        cpu_metrics = await self._get_cpu_metrics()
        
        # 任务数量（需要从调度器获取）
        task_counts = await self._get_task_counts()
        
        return PerformanceMetrics(
            timestamp=time.time(),
            gpu_utilization=gpu_metrics['utilization'],
            gpu_memory_used=gpu_metrics['memory_used'],
            gpu_memory_total=gpu_metrics['memory_total'],
            gpu_temperature=gpu_metrics['temperature'],
            cpu_utilization=cpu_metrics['utilization'],
            cpu_memory_percent=cpu_metrics['memory_percent'],
            active_gpu_tasks=task_counts['gpu_tasks'],
            active_cpu_tasks=task_counts['cpu_tasks']
        )
    
    async def _get_gpu_metrics(self) -> Dict:
        """获取GPU指标"""
        try:
            result = await asyncio.create_subprocess_exec(
                'nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                '--format=csv,noheader,nounits',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                values = stdout.decode().strip().split(', ')
                return {
                    'utilization': int(values[0]),
                    'memory_used': int(values[1]),
                    'memory_total': int(values[2]),
                    'temperature': int(values[3])
                }
        except:
            pass
        
        return {
            'utilization': 0,
            'memory_used': 0,
            'memory_total': 24576,
            'temperature': 0
        }
    
    async def _get_cpu_metrics(self) -> Dict:
        """获取CPU指标"""
        return {
            'utilization': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'core_count': psutil.cpu_count()
        }
    
    async def _get_task_counts(self) -> Dict:
        """获取任务数量（需要与调度器集成）"""
        # 这里应该从GPU调度器获取实际数据
        return {
            'gpu_tasks': 0,
            'cpu_tasks': 0
        }
    
    async def _analyze_and_optimize(self):
        """分析性能数据并执行优化"""
        recent_metrics = self.metrics_history[-10:]  # 最近10秒数据
        
        # 计算平均值
        avg_gpu_util = sum(m.gpu_utilization for m in recent_metrics) / len(recent_metrics)
        avg_cpu_util = sum(m.cpu_utilization for m in recent_metrics) / len(recent_metrics)
        avg_gpu_memory = sum(m.gpu_memory_used for m in recent_metrics) / len(recent_metrics)
        avg_gpu_temp = sum(m.gpu_temperature for m in recent_metrics) / len(recent_metrics)
        
        # 更新统计
        self.stats['avg_gpu_utilization'] = avg_gpu_util
        self.stats['avg_cpu_utilization'] = avg_cpu_util
        
        recommendations = []
        
        # GPU利用率分析
        if avg_gpu_util < self.thresholds['gpu_utilization_low']:
            recommendations.append(OptimizationRecommendation(
                category='gpu',
                priority='high',
                title='GPU利用率过低',
                description=f'GPU平均利用率仅{avg_gpu_util:.1f}%，远低于预期',
                action='increase_gpu_tasks',
                expected_improvement='提升GPU利用率至60-80%'
            ))
        
        elif avg_gpu_util > self.thresholds['gpu_utilization_high']:
            recommendations.append(OptimizationRecommendation(
                category='gpu',
                priority='medium',
                title='GPU利用率过高',
                description=f'GPU平均利用率{avg_gpu_util:.1f}%，可能影响稳定性',
                action='decrease_gpu_tasks',
                expected_improvement='降低GPU利用率至80-90%'
            ))
        
        # GPU内存分析
        gpu_memory_percent = (avg_gpu_memory / recent_metrics[0].gpu_memory_total) * 100
        if gpu_memory_percent > self.thresholds['gpu_memory_high']:
            recommendations.append(OptimizationRecommendation(
                category='memory',
                priority='high',
                title='GPU内存使用过高',
                description=f'GPU内存使用{gpu_memory_percent:.1f}%，可能导致编码失败',
                action='reduce_gpu_memory_usage',
                expected_improvement='降低GPU内存使用至80%以下'
            ))
        
        # CPU利用率分析
        if avg_cpu_util > self.thresholds['cpu_utilization_high']:
            recommendations.append(OptimizationRecommendation(
                category='cpu',
                priority='medium',
                title='CPU利用率过高',
                description=f'CPU平均利用率{avg_cpu_util:.1f}%，可能影响系统响应',
                action='reduce_cpu_tasks',
                expected_improvement='降低CPU利用率至70%以下'
            ))
        
        # GPU温度分析
        if avg_gpu_temp > self.thresholds['gpu_temperature_high']:
            recommendations.append(OptimizationRecommendation(
                category='gpu',
                priority='critical',
                title='GPU温度过高',
                description=f'GPU平均温度{avg_gpu_temp:.1f}°C，存在过热风险',
                action='reduce_gpu_load',
                expected_improvement='降低GPU温度至80°C以下'
            ))
        
        # 执行优化建议
        for rec in recommendations:
            await self._execute_optimization(rec)
            self.optimization_history.append(rec)
    
    async def _execute_optimization(self, recommendation: OptimizationRecommendation):
        """执行优化建议"""
        logger.info(f"🔧 执行优化: {recommendation.title}")
        
        if recommendation.action == 'increase_gpu_tasks':
            # 增加GPU并发任务数
            self.current_config['max_concurrent_gpu_tasks'] = min(
                5, self.current_config['max_concurrent_gpu_tasks'] + 1
            )
            logger.info(f"   增加GPU并发数至: {self.current_config['max_concurrent_gpu_tasks']}")
        
        elif recommendation.action == 'decrease_gpu_tasks':
            # 减少GPU并发任务数
            self.current_config['max_concurrent_gpu_tasks'] = max(
                1, self.current_config['max_concurrent_gpu_tasks'] - 1
            )
            logger.info(f"   减少GPU并发数至: {self.current_config['max_concurrent_gpu_tasks']}")
        
        elif recommendation.action == 'reduce_gpu_memory_usage':
            # 降低GPU编码质量以减少内存使用
            if self.current_config['gpu_encoding_quality'] == 'quality':
                self.current_config['gpu_encoding_quality'] = 'balanced'
            elif self.current_config['gpu_encoding_quality'] == 'balanced':
                self.current_config['gpu_encoding_quality'] = 'fast'
            logger.info(f"   调整编码质量至: {self.current_config['gpu_encoding_quality']}")
        
        elif recommendation.action == 'reduce_cpu_tasks':
            # 减少CPU并发任务数
            self.current_config['max_concurrent_cpu_tasks'] = max(
                2, self.current_config['max_concurrent_cpu_tasks'] - 1
            )
            logger.info(f"   减少CPU并发数至: {self.current_config['max_concurrent_cpu_tasks']}")
        
        elif recommendation.action == 'reduce_gpu_load':
            # 降低GPU负载
            self.current_config['max_concurrent_gpu_tasks'] = max(
                1, self.current_config['max_concurrent_gpu_tasks'] - 1
            )
            self.current_config['gpu_encoding_quality'] = 'fast'
            logger.info("   降低GPU负载: 减少并发数并使用快速编码")
        
        self.stats['total_optimizations'] += 1
    
    async def _generate_performance_report(self):
        """生成性能报告"""
        if not self.metrics_history:
            return
        
        report = {
            'summary': {
                'monitoring_duration': self.stats['monitoring_duration'],
                'total_optimizations': self.stats['total_optimizations'],
                'avg_gpu_utilization': self.stats['avg_gpu_utilization'],
                'avg_cpu_utilization': self.stats['avg_cpu_utilization'],
            },
            'final_config': self.current_config,
            'optimization_history': [asdict(opt) for opt in self.optimization_history],
            'performance_trends': self._calculate_performance_trends(),
            'recommendations': self._generate_final_recommendations()
        }
        
        # 保存报告
        report_path = f"logs/performance_optimization_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs('logs', exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📊 性能优化报告已保存: {report_path}")
        
        # 打印摘要
        print("\n" + "="*60)
        print("🎯 性能优化摘要")
        print("="*60)
        print(f"监控时长: {self.stats['monitoring_duration']:.1f}秒")
        print(f"执行优化: {self.stats['total_optimizations']}次")
        print(f"平均GPU利用率: {self.stats['avg_gpu_utilization']:.1f}%")
        print(f"平均CPU利用率: {self.stats['avg_cpu_utilization']:.1f}%")
        print(f"最终GPU并发数: {self.current_config['max_concurrent_gpu_tasks']}")
        print(f"最终编码质量: {self.current_config['gpu_encoding_quality']}")
        print("="*60)
    
    def _calculate_performance_trends(self) -> Dict:
        """计算性能趋势"""
        if len(self.metrics_history) < 20:
            return {}
        
        # 计算前后对比
        early_metrics = self.metrics_history[:10]
        late_metrics = self.metrics_history[-10:]
        
        early_gpu_util = sum(m.gpu_utilization for m in early_metrics) / len(early_metrics)
        late_gpu_util = sum(m.gpu_utilization for m in late_metrics) / len(late_metrics)
        
        early_cpu_util = sum(m.cpu_utilization for m in early_metrics) / len(early_metrics)
        late_cpu_util = sum(m.cpu_utilization for m in late_metrics) / len(late_metrics)
        
        return {
            'gpu_utilization_change': late_gpu_util - early_gpu_util,
            'cpu_utilization_change': late_cpu_util - early_cpu_util,
            'optimization_effectiveness': 'improved' if late_gpu_util > early_gpu_util else 'stable'
        }
    
    def _generate_final_recommendations(self) -> List[str]:
        """生成最终建议"""
        recommendations = []
        
        if self.stats['avg_gpu_utilization'] < 50:
            recommendations.append("考虑增加视频处理任务的并发数以提高GPU利用率")
        
        if self.stats['avg_cpu_utilization'] > 80:
            recommendations.append("CPU使用率较高，建议将更多任务转移到GPU处理")
        
        if self.stats['total_optimizations'] > 10:
            recommendations.append("系统进行了多次自动优化，建议检查硬件配置")
        
        return recommendations
    
    def get_current_status(self) -> Dict:
        """获取当前状态"""
        return {
            'running': self.running,
            'current_config': self.current_config,
            'stats': self.stats,
            'recent_metrics': self.metrics_history[-5:] if self.metrics_history else [],
            'recent_optimizations': self.optimization_history[-3:] if self.optimization_history else []
        }

# 全局性能优化器实例
performance_optimizer = PerformanceOptimizer()
