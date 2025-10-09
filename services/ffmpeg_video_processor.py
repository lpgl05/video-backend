"""
FFmpeg视频处理器 - 替代MoviePy的高性能视频处理模块
支持GPU硬件加速、并发处理、内存优化
"""

import os
import subprocess
import json
import asyncio
import tempfile
import shutil
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VideoSegment:
    """视频片段信息"""
    path: str
    start: float
    duration: float
    volume: float = 1.0

@dataclass
class GPUInfo:
    """GPU信息"""
    vendor: str  # NVIDIA, AMD, Intel
    model: str
    memory: int
    driver_version: str
    nvenc_support: bool = False
    amf_support: bool = False
    qsv_support: bool = False

class FFmpegVideoProcessor:
    """高性能FFmpeg视频处理器"""
    
    def __init__(self, gpu_enabled: bool = True, temp_dir: Optional[str] = None):
        self.gpu_enabled = gpu_enabled
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.ffmpeg_path = self._find_ffmpeg()
        self.gpu_info = self._detect_gpu() if gpu_enabled else None
        
        # 创建临时目录
        self.work_dir = os.path.join(self.temp_dir, "ffmpeg_processor")
        os.makedirs(self.work_dir, exist_ok=True)
        
        logger.info(f"FFmpeg处理器初始化完成，GPU支持: {self.gpu_enabled}")
        if self.gpu_info:
            logger.info(f"检测到GPU: {self.gpu_info.vendor} {self.gpu_info.model}")
    
    def _find_ffmpeg(self) -> str:
        """查找ffmpeg可执行文件"""
        for path in ["ffmpeg", "ffmpeg.exe", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
            if shutil.which(path):
                return path
        raise RuntimeError("未找到ffmpeg可执行文件")
    
    def _detect_gpu(self) -> Optional[GPUInfo]:
        """检测GPU信息"""
        try:
            # 检测NVIDIA GPU
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', 
                                   '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines and lines[0]:
                    parts = lines[0].split(', ')
                    return GPUInfo(
                        vendor="NVIDIA",
                        model=parts[0],
                        memory=int(parts[1]),
                        driver_version=parts[2],
                        nvenc_support=True
                    )
        except:
            pass
        
        # 如果没有NVIDIA GPU，返回None（后续可扩展AMD/Intel检测）
        return None
    
    def _get_gpu_encoding_params(self, quality: str = "balanced") -> List[str]:
        """获取GPU编码参数 - 强制使用Tesla T4"""
        # 强制使用Tesla T4优化器
        try:
            from services.tesla_t4_gpu_optimizer import tesla_t4_optimizer
            ready, message = tesla_t4_optimizer.is_ready()
            if ready:
                print("🚀 FFmpegVideoProcessor: 使用Tesla T4 GPU")
                return tesla_t4_optimizer.get_optimal_encoding_params(quality)
            else:
                print(f"⚠️ FFmpegVideoProcessor: Tesla T4不可用: {message}")
        except Exception as e:
            print(f"❌ FFmpegVideoProcessor: Tesla T4初始化失败: {e}")
        
        # 回退到CPU编码
        return ['-c:v', 'libx264', '-preset', 'medium', '-crf', '23']
    
    def _get_nvenc_params(self, quality: str) -> List[str]:
        """获取NVENC编码参数"""
        base_params = [
            '-c:v', 'h264_nvenc',
            '-preset', 'fast',
            '-tune', 'hq',
            '-rc', 'vbr',
            '-cq', '23',
            '-b:v', '5M',
            '-maxrate', '10M',
            '-bufsize', '20M'
        ]
        
        if quality == "fast":
            base_params[3] = 'fast'  # preset
            base_params[9] = '28'    # cq
        elif quality == "quality":
            base_params[3] = 'slow'  # preset
            base_params[9] = '18'    # cq
            
        return base_params
    
    async def create_montage_async(self, source_paths: List[str], target_duration: int, 
                                 count: int = 1) -> List[str]:
        """异步创建视频蒙太奇"""
        tasks = []
        for i in range(count):
            task = self._create_single_montage(source_paths, target_duration, i)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤成功的结果
        successful_results = []
        for result in results:
            if isinstance(result, str) and os.path.exists(result):
                successful_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"蒙太奇创建失败: {result}")
        
        return successful_results
    
    async def _create_single_montage(self, source_paths: List[str], 
                                   target_duration: int, index: int) -> str:
        """创建单个蒙太奇视频"""
        output_path = os.path.join(self.work_dir, f"montage_{index}_{os.getpid()}.mp4")
        
        # 生成随机片段
        segments = self._generate_random_segments(source_paths, target_duration)
        
        if not segments:
            raise ValueError("无法生成有效的视频片段")
        
        # 构建ffmpeg命令
        success = await self._execute_montage_command(segments, output_path)
        
        if success and os.path.exists(output_path):
            return output_path
        else:
            raise RuntimeError(f"蒙太奇创建失败: {output_path}")
    
    def _generate_random_segments(self, source_paths: List[str], 
                                target_duration: int) -> List[VideoSegment]:
        """生成随机视频片段"""
        import random
        
        segments = []
        remaining_duration = target_duration
        
        # 获取视频信息
        video_info = {}
        for path in source_paths:
            info = self._get_video_info(path)
            if info and info.get('duration', 0) > 1:
                video_info[path] = info
        
        if not video_info:
            return []
        
        # 分配时长给每个视频
        available_videos = list(video_info.keys())
        base_duration = max(1, target_duration // len(available_videos))
        
        for i, video_path in enumerate(available_videos):
            if remaining_duration <= 0:
                break
                
            video_duration = video_info[video_path]['duration']
            max_segment_duration = min(video_duration - 1, remaining_duration)
            
            if max_segment_duration <= 0:
                continue
            
            # 最后一个视频用完剩余时长
            if i == len(available_videos) - 1:
                segment_duration = min(max_segment_duration, remaining_duration)
            else:
                segment_duration = min(base_duration, max_segment_duration)
            
            # 随机选择开始时间
            max_start = max(0, video_duration - segment_duration - 0.5)
            start_time = random.uniform(0, max_start) if max_start > 0 else 0
            
            segments.append(VideoSegment(
                path=video_path,
                start=start_time,
                duration=segment_duration
            ))
            
            remaining_duration -= segment_duration
        
        return segments
    
    def _get_video_info(self, video_path: str) -> Optional[Dict]:
        """获取视频信息"""
        try:
            cmd = [
                self.ffmpeg_path.replace('ffmpeg', 'ffprobe'),
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                # 查找视频流
                for stream in data.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        return {
                            'duration': float(stream.get('duration', 0)),
                            'width': int(stream.get('width', 0)),
                            'height': int(stream.get('height', 0)),
                            'fps': eval(stream.get('r_frame_rate', '0/1'))
                        }
        except Exception as e:
            logger.warning(f"获取视频信息失败 {video_path}: {e}")
        
        return None
    
    async def _execute_montage_command(self, segments: List[VideoSegment], 
                                     output_path: str) -> bool:
        """执行蒙太奇命令"""
        try:
            # 构建输入参数
            inputs = []
            filter_parts = []
            
            for i, segment in enumerate(segments):
                inputs.extend(['-i', segment.path])
                
                # 构建滤镜：提取片段并缩放
                filter_parts.append(
                    f"[{i}:v]trim=start={segment.start}:duration={segment.duration},"
                    f"setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,"
                    f"crop=1080:1920[v{i}];"
                )
            
            # 拼接所有片段
            concat_inputs = "".join([f"[v{i}]" for i in range(len(segments))])
            filter_parts.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[outv]")
            
            filter_complex = "".join(filter_parts)
            
            # 构建完整命令
            cmd = [
                self.ffmpeg_path, '-y',
                *inputs,
                '-filter_complex', filter_complex,
                '-map', '[outv]',
                '-t', str(sum(s.duration for s in segments)),
                *self._get_gpu_encoding_params(),
                '-movflags', '+faststart',
                output_path
            ]
            
            # 异步执行
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"蒙太奇创建成功: {output_path}")
                return True
            else:
                logger.error(f"FFmpeg执行失败: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"执行蒙太奇命令失败: {e}")
            return False
    
    def cleanup(self):
        """清理临时文件"""
        try:
            if os.path.exists(self.work_dir):
                shutil.rmtree(self.work_dir)
                logger.info("临时文件清理完成")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")
    
    def __del__(self):
        """析构函数"""
        self.cleanup()

# 全局处理器实例
_processor_instance = None

def get_video_processor(gpu_enabled: bool = True) -> FFmpegVideoProcessor:
    """获取视频处理器实例（单例模式）"""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = FFmpegVideoProcessor(gpu_enabled=gpu_enabled)
    return _processor_instance
