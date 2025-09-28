#!/usr/bin/env python3
"""
Tesla T4 GPU优化模块
专门针对NVIDIA Tesla T4数据中心GPU的视频处理优化
"""

import os
import subprocess
import json
from typing import Dict, List, Optional, Tuple

class TeslaT4Optimizer:
    """Tesla T4 GPU优化器"""
    
    def __init__(self):
        self.gpu_info = self._detect_tesla_t4()
        self.driver_version = self._get_driver_version()
        self.nvenc_support = self._check_nvenc_support()
        
    def _detect_tesla_t4(self) -> Dict:
        """检测Tesla T4 GPU"""
        try:
            result = subprocess.run([
                'nvidia-smi', '--query-gpu=name,memory.total,driver_version,compute_cap',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 4:
                        gpu_name = parts[0]
                        if 'Tesla T4' in gpu_name or 'T4' in gpu_name:
                            return {
                                'available': True,
                                'name': gpu_name,
                                'memory_mb': int(parts[1]),
                                'driver_version': parts[2],
                                'compute_capability': parts[3],
                                'is_tesla_t4': True
                            }
                
                # 如果没有找到Tesla T4，检查是否有其他NVIDIA GPU
                if lines and lines[0]:
                    parts = [p.strip() for p in lines[0].split(',')]
                    return {
                        'available': True,
                        'name': parts[0],
                        'memory_mb': int(parts[1]),
                        'driver_version': parts[2],
                        'compute_capability': parts[3] if len(parts) >= 4 else 'unknown',
                        'is_tesla_t4': False
                    }
            
            return {'available': False, 'reason': 'No NVIDIA GPU detected'}
            
        except Exception as e:
            return {'available': False, 'reason': f'Detection failed: {str(e)}'}
    
    def _get_driver_version(self) -> Optional[float]:
        """获取驱动版本号"""
        if self.gpu_info.get('available') and 'driver_version' in self.gpu_info:
            try:
                version_str = self.gpu_info['driver_version']
                return float(version_str.split('.')[0])
            except:
                return None
        return None
    
    def _check_nvenc_support(self) -> bool:
        """检查NVENC编码器支持"""
        try:
            # 查找FFmpeg
            ffmpeg_paths = ['ffmpeg', 'ffmpeg.exe']
            for ffmpeg_path in ffmpeg_paths:
                try:
                    result = subprocess.run([ffmpeg_path, '-encoders'], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        return 'h264_nvenc' in result.stdout.lower()
                except:
                    continue
            return False
        except:
            return False
    
    def is_ready(self) -> Tuple[bool, str]:
        """检查Tesla T4是否准备就绪"""
        if not self.gpu_info.get('available'):
            return False, self.gpu_info.get('reason', 'GPU不可用')
        
        if not self.nvenc_support:
            return False, 'FFmpeg不支持NVENC编码器'
        
        if not self.driver_version:
            return False, '无法获取驱动版本'
        
        if self.driver_version < 450:
            return False, f'驱动版本过旧 ({self.driver_version})，建议升级到450+版本'
        
        return True, 'Tesla T4 GPU准备就绪'
    
    def get_optimal_encoding_params(self, quality: str = 'balanced') -> List[str]:
        """
        获取Tesla T4优化的编码参数 - 兼容性优先版本
        
        Tesla T4特点：
        - 数据中心GPU，专为推理和编码优化
        - 支持最新的NVENC编码器
        - 16GB GDDR6内存，适合大型视频处理
        """
        ready, message = self.is_ready()
        if not ready:
            print(f"⚠️ Tesla T4不可用: {message}")
            return self._get_cpu_fallback_params()
        
        print(f"🚀 使用Tesla T4 GPU加速编码 (驱动版本: {self.driver_version}) - 兼容模式")
        
        # Tesla T4兼容性优先参数 - 简化版
        base_params = [
            '-c:v', 'h264_nvenc',
            '-pix_fmt', 'yuv420p',         # 标准像素格式
        ]
        
        # 使用更兼容的参数，避免新API可能的问题
        if quality == 'fast':
            quality_params = [
                '-preset', 'fast',         # 使用传统预设名
                '-rc', 'cbr',              # 恒定比特率
                '-b:v', '8M',
                '-maxrate', '12M',
                '-bufsize', '16M',
                '-profile:v', 'main',      # 兼容性profile
                '-level', '4.1',           # 兼容level
            ]
        elif quality == 'quality':
            quality_params = [
                '-preset', 'slow',         # 高质量传统预设
                '-rc', 'vbr_hq',           # 高质量VBR
                '-cq', '19',
                '-b:v', '15M',
                '-maxrate', '20M',
                '-bufsize', '30M',
                '-profile:v', 'high',      # 高质量profile
                '-level', '4.1',
            ]
        else:  # balanced
            quality_params = [
                '-preset', 'medium',       # 平衡传统预设
                '-rc', 'vbr',              # 标准VBR
                '-cq', '23',
                '-b:v', '10M',
                '-maxrate', '15M',
                '-bufsize', '20M',
                '-profile:v', 'main',      # 平衡profile
                '-level', '4.1',
            ]
        
        return base_params + quality_params
    
    def _get_new_api_params(self, quality: str) -> List[str]:
        """新版驱动API参数 (470+) - 修复格式兼容性问题"""
        if quality == 'fast':
            return [
                '-preset', 'p1',           # 最快预设
                '-tune', 'ull',            # 超低延迟
                '-rc', 'cbr',              # 恒定比特率
                '-b:v', '8M',
                '-maxrate', '12M',
                '-bufsize', '16M',
                '-bf', '0',                # 无B帧，降低延迟
                '-profile:v', 'main',      # 强制使用main profile
                '-level', '4.1',           # 设置兼容level
            ]
        elif quality == 'quality':
            return [
                '-preset', 'p7',           # 最高质量预设
                '-tune', 'hq',             # 高质量调优
                '-rc', 'vbr',              # 可变比特率
                '-cq', '19',               # 高质量CQ值
                '-b:v', '15M',
                '-maxrate', '20M',
                '-bufsize', '30M',
                '-bf', '3',                # 使用B帧提高压缩率
                '-profile:v', 'high',      # 高质量profile
                '-level', '4.1',           # 设置兼容level
            ]
        else:  # balanced
            return [
                '-preset', 'p4',           # 平衡预设
                '-tune', 'hq',             # 高质量调优
                '-rc', 'vbr',              # 可变比特率
                '-cq', '23',               # 平衡的CQ值
                '-b:v', '10M',
                '-maxrate', '15M',
                '-bufsize', '20M',
                '-bf', '2',                # 适度使用B帧
                '-profile:v', 'main',      # 平衡profile
                '-level', '4.1',           # 设置兼容level
            ]
    
    def _get_legacy_api_params(self, quality: str) -> List[str]:
        """旧版驱动兼容参数 (450-469)"""
        if quality == 'fast':
            return [
                '-preset', 'fast',         # 快速预设
                '-rc', 'cbr',              # 恒定比特率
                '-b:v', '8M',
                '-maxrate', '12M',
                '-bufsize', '16M',
                '-2pass', '0',             # 单次编码
            ]
        elif quality == 'quality':
            return [
                '-preset', 'slow',         # 高质量预设
                '-rc', 'vbr_hq',           # 高质量VBR
                '-cq', '19',
                '-b:v', '15M',
                '-maxrate', '20M',
                '-bufsize', '30M',
                '-2pass', '1',             # 双次编码
            ]
        else:  # balanced
            return [
                '-preset', 'medium',       # 平衡预设
                '-rc', 'vbr',              # 可变比特率
                '-cq', '23',
                '-b:v', '10M',
                '-maxrate', '15M',
                '-bufsize', '20M',
            ]
    
    def _get_cpu_fallback_params(self) -> List[str]:
        """CPU回退参数"""
        return [
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-threads', str(os.cpu_count())
        ]
    
    def get_hardware_decode_params(self) -> List[str]:
        """获取硬件解码参数 - 修复格式兼容性"""
        ready, _ = self.is_ready()
        if not ready:
            return []
        
        # 不使用 cuda 输出格式，避免格式转换问题
        return [
            '-hwaccel', 'cuda'
        ]
    
    def get_gpu_filter_params(self) -> Dict[str, str]:
        """获取GPU滤镜参数"""
        ready, _ = self.is_ready()
        if not ready:
            return {
                'scale': 'scale',
                'overlay': 'overlay',
                'format': '',
                'download': '',
            }
        
        return {
            'scale': 'scale_cuda',           # GPU缩放
            'overlay': 'overlay_cuda',       # GPU叠加
            'format': 'hwupload_cuda',       # 上传到GPU
            'download': 'hwdownload',        # 从GPU下载
        }
    
    def optimize_ffmpeg_command(self, base_cmd: List[str], enable_gpu_filters: bool = True) -> List[str]:
        """优化FFmpeg命令以使用Tesla T4"""
        ready, message = self.is_ready()
        if not ready:
            print(f"⚠️ Tesla T4优化跳过: {message}")
            return base_cmd
        
        optimized_cmd = base_cmd.copy()
        
        # 添加硬件解码
        if '-i ' in ' '.join(optimized_cmd):
            # 在第一个输入前添加硬件解码参数
            for i, arg in enumerate(optimized_cmd):
                if arg == '-i':
                    decode_params = self.get_hardware_decode_params()
                    optimized_cmd = optimized_cmd[:i] + decode_params + optimized_cmd[i:]
                    break
        
        # 替换CPU编码器为GPU编码器
        for i, arg in enumerate(optimized_cmd):
            if arg == 'libx264':
                optimized_cmd[i] = 'h264_nvenc'
                # 添加GPU编码参数
                gpu_params = self.get_optimal_encoding_params('balanced')
                # 移除重复的编码器参数
                gpu_params = [p for p in gpu_params if p not in ['-c:v', 'h264_nvenc']]
                optimized_cmd = optimized_cmd[:i+1] + gpu_params + optimized_cmd[i+1:]
                break
        
        return optimized_cmd
    
    def get_performance_stats(self) -> Dict:
        """获取性能统计信息"""
        return {
            'gpu_available': self.gpu_info.get('available', False),
            'gpu_name': self.gpu_info.get('name', 'Unknown'),
            'is_tesla_t4': self.gpu_info.get('is_tesla_t4', False),
            'memory_mb': self.gpu_info.get('memory_mb', 0),
            'driver_version': self.driver_version,
            'nvenc_support': self.nvenc_support,
            'compute_capability': self.gpu_info.get('compute_capability', 'unknown')
        }
    
    def print_status(self):
        """打印Tesla T4状态"""
        print("🎮 Tesla T4 GPU状态:")
        print("=" * 50)
        
        if self.gpu_info.get('available'):
            print(f"✅ GPU: {self.gpu_info['name']}")
            print(f"📊 内存: {self.gpu_info['memory_mb']}MB")
            print(f"🔧 驱动版本: {self.driver_version}")
            print(f"⚡ NVENC支持: {'✅' if self.nvenc_support else '❌'}")
            print(f"🎯 Tesla T4: {'✅' if self.gpu_info.get('is_tesla_t4') else '❌'}")
            
            ready, message = self.is_ready()
            print(f"🚀 状态: {'就绪' if ready else message}")
            
            if ready:
                print("\n💡 优化建议:")
                print("• 视频编码将使用GPU硬件加速")
                print("• 预期性能提升: 3-8倍编码速度")
                print("• GPU内存使用: 2-4GB (视频复杂度决定)")
                print("• CPU使用率: 大幅降低")
        else:
            print(f"❌ GPU不可用: {self.gpu_info.get('reason', '未知错误')}")

# 全局Tesla T4优化器实例
tesla_t4_optimizer = TeslaT4Optimizer()

def check_tesla_t4_support() -> Dict:
    """检查Tesla T4支持状态"""
    return tesla_t4_optimizer.gpu_info

def get_tesla_t4_encoding_params(quality: str = 'balanced') -> List[str]:
    """获取Tesla T4编码参数"""
    return tesla_t4_optimizer.get_optimal_encoding_params(quality)

def optimize_command_for_tesla_t4(cmd: List[str]) -> List[str]:
    """为Tesla T4优化FFmpeg命令"""
    return tesla_t4_optimizer.optimize_ffmpeg_command(cmd)

if __name__ == "__main__":
    # 测试Tesla T4优化器
    optimizer = TeslaT4Optimizer()
    optimizer.print_status()
    
    # 测试编码参数
    print("\n🔧 编码参数测试:")
    for quality in ['fast', 'balanced', 'quality']:
        params = optimizer.get_optimal_encoding_params(quality)
        print(f"  {quality}: {' '.join(params)}")
