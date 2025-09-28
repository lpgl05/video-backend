#!/usr/bin/env python3
"""
视频生成性能监控工具
用于检测和诊断视频生成过程中的性能瓶颈
"""
import time
import psutil
import os
import json
from datetime import datetime

class PerformanceMonitor:
    def __init__(self):
        self.start_time = None
        self.checkpoints = []
        self.system_stats = []
        
    def start_monitoring(self, process_name="视频生成"):
        """开始性能监控"""
        self.start_time = time.time()
        self.process_name = process_name
        print(f"🚀 开始监控 {process_name}...")
        self._record_checkpoint("开始", 0)
        
    def checkpoint(self, name, additional_info=None):
        """记录检查点"""
        if self.start_time is None:
            return
            
        current_time = time.time()
        elapsed = current_time - self.start_time
        
        # 系统资源监控
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk_io = psutil.disk_io_counters()
        
        checkpoint_data = {
            'name': name,
            'elapsed_time': elapsed,
            'timestamp': datetime.now().isoformat(),
            'cpu_percent': cpu_percent,
            'memory_used_gb': memory.used / (1024**3),
            'memory_percent': memory.percent,
            'disk_read_mb': disk_io.read_bytes / (1024**2) if disk_io else 0,
            'disk_write_mb': disk_io.write_bytes / (1024**2) if disk_io else 0,
            'additional_info': additional_info
        }
        
        self.checkpoints.append(checkpoint_data)
        
        print(f"⏱️  [{elapsed:.1f}s] {name}")
        print(f"   💻 CPU: {cpu_percent:.1f}% | 内存: {memory.percent:.1f}% ({memory.used/(1024**3):.1f}GB)")
        if additional_info:
            print(f"   📝 {additional_info}")
        print()
        
    def _record_checkpoint(self, name, elapsed):
        """内部记录检查点方法"""
        self.checkpoints.append({
            'name': name,
            'elapsed_time': elapsed,
            'timestamp': datetime.now().isoformat()
        })
        
    def finish_monitoring(self):
        """结束监控并生成报告"""
        if self.start_time is None:
            return
            
        total_time = time.time() - self.start_time
        self._record_checkpoint("完成", total_time)
        
        print(f"✅ {self.process_name} 完成，总耗时: {total_time:.1f}秒")
        print()
        
        # 分析性能瓶颈
        self._analyze_performance()
        
        # 保存详细报告
        self._save_report()
        
    def _analyze_performance(self):
        """分析性能瓶颈"""
        print("📊 性能分析报告:")
        print("=" * 50)
        
        if len(self.checkpoints) < 2:
            print("❌ 数据不足，无法分析")
            return
            
        # 找出耗时最长的步骤
        max_duration = 0
        slowest_step = None
        
        for i in range(1, len(self.checkpoints)):
            duration = self.checkpoints[i]['elapsed_time'] - self.checkpoints[i-1]['elapsed_time']
            if duration > max_duration:
                max_duration = duration
                slowest_step = (self.checkpoints[i-1]['name'], self.checkpoints[i]['name'], duration)
        
        if slowest_step:
            print(f"🐌 最慢步骤: {slowest_step[0]} → {slowest_step[1]}")
            print(f"   耗时: {slowest_step[2]:.1f}秒 ({slowest_step[2]/self.checkpoints[-1]['elapsed_time']*100:.1f}%)")
            print()
        
        # 资源使用分析
        if any('cpu_percent' in cp for cp in self.checkpoints):
            cpu_values = [cp.get('cpu_percent', 0) for cp in self.checkpoints if 'cpu_percent' in cp]
            memory_values = [cp.get('memory_percent', 0) for cp in self.checkpoints if 'memory_percent' in cp]
            
            if cpu_values:
                avg_cpu = sum(cpu_values) / len(cpu_values)
                max_cpu = max(cpu_values)
                print(f"🖥️  CPU使用: 平均 {avg_cpu:.1f}%, 峰值 {max_cpu:.1f}%")
                
            if memory_values:
                avg_memory = sum(memory_values) / len(memory_values)
                max_memory = max(memory_values)
                print(f"💾 内存使用: 平均 {avg_memory:.1f}%, 峰值 {max_memory:.1f}%")
                print()
        
        # 性能建议
        self._generate_recommendations()
        
    def _generate_recommendations(self):
        """生成性能优化建议"""
        print("💡 优化建议:")
        
        total_time = self.checkpoints[-1]['elapsed_time']
        
        if total_time > 600:  # 10分钟
            print("🔴 生成时间过长 (>10分钟):")
            print("   1. 检查网络连接状态")
            print("   2. 考虑减少视频数量或时长")
            print("   3. 检查FFmpeg配置")
            print("   4. 考虑使用更简单的处理模式")
        elif total_time > 300:  # 5分钟
            print("🟡 生成时间较长 (>5分钟):")
            print("   1. 检查上传速度")
            print("   2. 优化视频编码参数")
            print("   3. 检查是否使用了动态字幕功能")
        else:
            print("🟢 生成时间正常")
            
        # 检查CPU和内存使用
        if any('cpu_percent' in cp for cp in self.checkpoints):
            cpu_values = [cp.get('cpu_percent', 0) for cp in self.checkpoints if 'cpu_percent' in cp]
            if cpu_values and max(cpu_values) > 90:
                print("   ⚠️  CPU使用率过高，考虑降低并发数")
                
            memory_values = [cp.get('memory_percent', 0) for cp in self.checkpoints if 'memory_percent' in cp]
            if memory_values and max(memory_values) > 85:
                print("   ⚠️  内存使用率过高，考虑减少分片大小")
        
    def _save_report(self):
        """保存详细报告"""
        report_data = {
            'process_name': self.process_name,
            'total_time': self.checkpoints[-1]['elapsed_time'],
            'checkpoints': self.checkpoints,
            'generated_at': datetime.now().isoformat()
        }
        
        # 确保输出目录存在
        os.makedirs('logs', exist_ok=True)
        
        # 保存JSON报告
        filename = f"logs/performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
            
        print(f"📄 详细报告已保存: {filename}")

# 创建全局监控实例
monitor = PerformanceMonitor()

def start_video_generation_monitoring():
    """开始视频生成监控"""
    monitor.start_monitoring("视频生成")

def checkpoint(name, info=None):
    """记录检查点"""
    monitor.checkpoint(name, info)

def finish_video_generation_monitoring():
    """结束视频生成监控"""
    monitor.finish_monitoring()

if __name__ == "__main__":
    # 测试监控功能
    monitor.start_monitoring("测试进程")
    
    import time
    time.sleep(1)
    monitor.checkpoint("步骤1完成")
    
    time.sleep(2)
    monitor.checkpoint("步骤2完成", "这是额外信息")
    
    time.sleep(1)
    monitor.checkpoint("步骤3完成")
    
    monitor.finish_monitoring()
