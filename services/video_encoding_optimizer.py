"""
视频编码优化服务 - 集成到现有clip_service中
解决HEVC/HDR兼容性问题，优化编码参数选择
"""

import os
import subprocess
import json
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

class VideoEncodingOptimizer:
    """视频编码优化器 - 专门解决兼容性问题"""
    
    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        self.supported_codecs = self._detect_supported_codecs()
    
    def _find_ffmpeg(self) -> str:
        """查找FFmpeg可执行文件"""
        import shutil
        for cmd in ['ffmpeg', 'ffmpeg.exe']:
            if shutil.which(cmd):
                return cmd
        return 'ffmpeg'  # 默认值
    
    def _detect_supported_codecs(self) -> Dict[str, List[str]]:
        """检测支持的编码器"""
        try:
            result = subprocess.run([self.ffmpeg_path, '-encoders'], 
                                  capture_output=True, text=True, timeout=10)
            output = result.stdout.lower()
            
            return {
                'nvenc': 'h264_nvenc' in output,
                'amf': 'h264_amf' in output,
                'qsv': 'h264_qsv' in output,
                'libx264': 'libx264' in output,
                'libx265': 'libx265' in output
            }
        except:
            return {'nvenc': False, 'amf': False, 'qsv': False, 'libx264': True, 'libx265': False}
    
    def get_safe_encoding_params(self, use_gpu: bool = True, quality: str = 'balanced') -> List[str]:
        """获取安全的编码参数 - 强制使用Tesla T4 GPU"""
        
        # 强制使用Tesla T4优化器，不使用其他编码器
        if use_gpu:
            try:
                from services.tesla_t4_gpu_optimizer import tesla_t4_optimizer
                ready, message = tesla_t4_optimizer.is_ready()
                if ready:
                    print("🚀 VideoEncodingOptimizer: 使用Tesla T4 GPU")
                    return tesla_t4_optimizer.get_optimal_encoding_params(quality)
                else:
                    print(f"⚠️ VideoEncodingOptimizer: Tesla T4不可用: {message}，强制回退")
            except Exception as e:
                print(f"❌ VideoEncodingOptimizer: Tesla T4初始化失败: {e}")
        
        # 只有在明确指定不使用GPU或Tesla T4完全不可用时才回退
        return self._get_safe_cpu_params(quality)
    
    def _get_safe_nvenc_params(self, quality: str) -> List[str]:
        """获取安全的NVENC参数 - 解决驱动兼容性问题"""
        base_params = [
            '-c:v', 'h264_nvenc',
            '-preset', 'fast',           # 使用fast预设提高兼容性
            '-profile:v', 'main',        # 强制Main Profile，避免High Profile问题
            '-level:v', '4.1',           # 设置兼容性级别
            '-pix_fmt', 'yuv420p',       # 强制8-bit 4:2:0，避免10-bit问题
            '-rc', 'vbr',                # 可变比特率
            '-tune', 'hq',               # 高质量调优
            '-spatial-aq', '1',          # 空间自适应量化
            '-temporal-aq', '1',         # 时间自适应量化
            '-rc-lookahead', '20',       # 前瞻帧数
            '-surfaces', '64',           # 增加表面缓冲区
            '-delay', '0',               # 减少延迟
            '-no-scenecut', '0'          # 启用场景切换检测
        ]
        
        # 根据质量调整参数
        if quality == 'fast':
            base_params.extend(['-cq', '28', '-b:v', '2M', '-maxrate', '3M', '-bufsize', '4M'])
        elif quality == 'balanced':
            base_params.extend(['-cq', '23', '-b:v', '5M', '-maxrate', '8M', '-bufsize', '10M'])
        elif quality == 'quality':
            base_params.extend(['-cq', '18', '-b:v', '8M', '-maxrate', '12M', '-bufsize', '16M'])
        
        # 添加GOP设置
        base_params.extend(['-g', '60', '-keyint_min', '30'])  # 2秒GOP，最小1秒
        
        return base_params
    
    def _get_safe_amf_params(self, quality: str) -> List[str]:
        """获取安全的AMF参数"""
        base_params = [
            '-c:v', 'h264_amf',
            '-quality', 'balanced',
            '-profile:v', 'main',
            '-level:v', '4.1',
            '-pix_fmt', 'yuv420p',
            '-usage', 'transcoding',
            '-rc', 'vbr_peak'
        ]
        
        if quality == 'fast':
            base_params.extend(['-qp_i', '28', '-qp_p', '30', '-qp_b', '32'])
        elif quality == 'balanced':
            base_params.extend(['-qp_i', '23', '-qp_p', '25', '-qp_b', '27'])
        elif quality == 'quality':
            base_params.extend(['-qp_i', '18', '-qp_p', '20', '-qp_b', '22'])
        
        return base_params
    
    def _get_safe_qsv_params(self, quality: str) -> List[str]:
        """获取安全的QSV参数"""
        base_params = [
            '-c:v', 'h264_qsv',
            '-preset', 'medium',
            '-profile:v', 'main',
            '-level:v', '4.1',
            '-pix_fmt', 'yuv420p',
            '-look_ahead', '1',
            '-look_ahead_depth', '40'
        ]
        
        if quality == 'fast':
            base_params.extend(['-q', '28'])
        elif quality == 'balanced':
            base_params.extend(['-q', '23'])
        elif quality == 'quality':
            base_params.extend(['-q', '18'])
        
        return base_params
    
    def _get_safe_cpu_params(self, quality: str) -> List[str]:
        """获取安全的CPU编码参数"""
        base_params = [
            '-c:v', 'libx264',
            '-profile:v', 'main',        # 强制Main Profile
            '-level:v', '4.1',           # 兼容性级别
            '-pix_fmt', 'yuv420p',       # 8-bit 4:2:0
            '-x264-params', 'nal-hrd=cbr'  # 恒定比特率HRD
        ]
        
        if quality == 'fast':
            base_params.extend(['-preset', 'fast', '-crf', '28'])
        elif quality == 'balanced':
            base_params.extend(['-preset', 'medium', '-crf', '23'])
        elif quality == 'quality':
            base_params.extend(['-preset', 'slow', '-crf', '18'])
        
        # 添加线程和GOP设置
        base_params.extend([
            '-threads', str(os.cpu_count()),
            '-g', '60',                  # 2秒GOP
            '-keyint_min', '30',         # 最小GOP
            '-sc_threshold', '40'        # 场景切换阈值
        ])
        
        return base_params
    
    def check_video_compatibility(self, video_path: str) -> Dict[str, Any]:
        """检查视频兼容性 - 专门检测HEVC/HDR问题"""
        try:
            ffprobe_path = self.ffmpeg_path.replace('ffmpeg', 'ffprobe')
            cmd = [
                ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {'compatible': False, 'error': 'FFprobe执行失败'}
            
            data = json.loads(result.stdout)
            issues = []
            
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    codec = stream.get('codec_name', '').lower()
                    profile = stream.get('profile', '').lower()
                    color_transfer = stream.get('color_transfer', '').lower()
                    
                    # 检查HEVC问题
                    if codec == 'hevc':
                        issues.append('HEVC编码可能导致兼容性问题，建议转换为H.264')
                    
                    # 检查Main 10 Profile问题
                    if 'main 10' in profile:
                        issues.append('Main 10 Profile (10-bit)可能导致解码问题')
                    
                    # 检查HDR问题
                    if any(hdr in color_transfer for hdr in ['smpte2084', 'arib-std-b67', 'bt2020']):
                        issues.append('HDR内容可能导致色彩处理问题')
            
            return {
                'compatible': len(issues) == 0,
                'issues': issues,
                'needs_conversion': len(issues) > 0
            }
            
        except Exception as e:
            return {'compatible': False, 'error': f'检查失败: {e}'}
    
    def get_conversion_recommendation(self, video_path: str) -> Dict[str, Any]:
        """获取转换建议"""
        compatibility = self.check_video_compatibility(video_path)
        
        if compatibility['compatible']:
            return {
                'needs_conversion': False,
                'message': '视频格式兼容，无需转换'
            }
        
        recommendations = []
        
        if compatibility.get('issues'):
            for issue in compatibility['issues']:
                if 'hevc' in issue.lower():
                    recommendations.append('转换为H.264编码')
                elif 'main 10' in issue.lower():
                    recommendations.append('使用8-bit Main Profile编码')
                elif 'hdr' in issue.lower():
                    recommendations.append('移除HDR元数据，转换为SDR')
        
        return {
            'needs_conversion': True,
            'issues': compatibility.get('issues', []),
            'recommendations': recommendations,
            'suggested_params': self.get_safe_encoding_params(use_gpu=True, quality='balanced')
        }
    
    def test_gpu_encoder_compatibility(self) -> Dict[str, Any]:
        """测试GPU编码器兼容性"""
        test_results = {
            'nvenc_available': False,
            'nvenc_working': False,
            'driver_compatible': False,
            'error_message': ''
        }
        
        if not self.supported_codecs.get('nvenc', False):
            test_results['error_message'] = 'NVENC编码器不可用'
            return test_results
        
        test_results['nvenc_available'] = True
        
        # 测试NVENC是否真正工作
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                test_output = tmp.name
            
            cmd = [
                self.ffmpeg_path, '-y',
                '-f', 'lavfi',
                '-i', 'testsrc=duration=2:size=640x480:rate=30',
                '-c:v', 'h264_nvenc',
                '-preset', 'fast',
                '-t', '2',
                test_output
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(test_output):
                test_results['nvenc_working'] = True
                test_results['driver_compatible'] = True
                # 清理测试文件
                try:
                    os.remove(test_output)
                except:
                    pass
            else:
                error_output = result.stderr.lower()
                if 'driver does not support' in error_output:
                    test_results['error_message'] = '驱动版本过低，需要570.0或更高版本'
                elif 'nvenc api version' in error_output:
                    test_results['error_message'] = 'NVENC API版本不兼容'
                else:
                    test_results['error_message'] = f'NVENC测试失败: {result.stderr[:100]}'
                    
        except Exception as e:
            test_results['error_message'] = f'测试异常: {e}'
        
        return test_results


# 全局实例
_video_encoding_optimizer = None

def get_video_encoding_optimizer() -> VideoEncodingOptimizer:
    """获取视频编码优化器实例"""
    global _video_encoding_optimizer
    if _video_encoding_optimizer is None:
        _video_encoding_optimizer = VideoEncodingOptimizer()
    return _video_encoding_optimizer

def get_optimized_encoding_params(use_gpu: bool = True, quality: str = 'balanced') -> List[str]:
    """获取优化的编码参数 - 供现有代码调用"""
    optimizer = get_video_encoding_optimizer()
    return optimizer.get_safe_encoding_params(use_gpu, quality)

def check_video_needs_conversion(video_path: str) -> bool:
    """检查视频是否需要转换 - 供现有代码调用"""
    optimizer = get_video_encoding_optimizer()
    compatibility = optimizer.check_video_compatibility(video_path)
    return not compatibility.get('compatible', False)
