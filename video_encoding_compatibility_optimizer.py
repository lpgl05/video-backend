#!/usr/bin/env python3
"""
视频编码兼容性优化器
解决HEVC/HDR兼容性问题，优化测试视频格式，提供智能编码器选择
"""

import os
import sys
import subprocess
import json
import tempfile
import shutil
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoEncodingCompatibilityOptimizer:
    """视频编码兼容性优化器"""
    
    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        self.ffprobe_path = self._find_ffprobe()
        self.supported_codecs = self._detect_supported_codecs()
        
    def _find_ffmpeg(self) -> str:
        """查找FFmpeg可执行文件"""
        for cmd in ['ffmpeg', 'ffmpeg.exe']:
            if shutil.which(cmd):
                return cmd
        raise RuntimeError("未找到FFmpeg，请确保已安装并在PATH中")
    
    def _find_ffprobe(self) -> str:
        """查找FFprobe可执行文件"""
        for cmd in ['ffprobe', 'ffprobe.exe']:
            if shutil.which(cmd):
                return cmd
        raise RuntimeError("未找到FFprobe，请确保已安装并在PATH中")
    
    def _detect_supported_codecs(self) -> Dict[str, List[str]]:
        """检测支持的编码器"""
        try:
            result = subprocess.run([self.ffmpeg_path, '-encoders'], 
                                  capture_output=True, text=True, timeout=10)
            output = result.stdout.lower()
            
            codecs = {
                'h264': [],
                'h265': [],
                'gpu': []
            }
            
            # 检测H.264编码器
            if 'libx264' in output:
                codecs['h264'].append('libx264')
            if 'h264_nvenc' in output:
                codecs['h264'].append('h264_nvenc')
                codecs['gpu'].append('h264_nvenc')
            if 'h264_amf' in output:
                codecs['h264'].append('h264_amf')
                codecs['gpu'].append('h264_amf')
            if 'h264_qsv' in output:
                codecs['h264'].append('h264_qsv')
                codecs['gpu'].append('h264_qsv')
            
            # 检测H.265编码器
            if 'libx265' in output:
                codecs['h265'].append('libx265')
            if 'hevc_nvenc' in output:
                codecs['h265'].append('hevc_nvenc')
                codecs['gpu'].append('hevc_nvenc')
            if 'hevc_amf' in output:
                codecs['h265'].append('hevc_amf')
                codecs['gpu'].append('hevc_amf')
            if 'hevc_qsv' in output:
                codecs['h265'].append('hevc_qsv')
                codecs['gpu'].append('hevc_qsv')
            
            logger.info(f"检测到编码器: {codecs}")
            return codecs
            
        except Exception as e:
            logger.error(f"编码器检测失败: {e}")
            return {'h264': ['libx264'], 'h265': ['libx265'], 'gpu': []}
    
    def analyze_video_compatibility(self, video_path: str) -> Dict[str, Any]:
        """分析视频兼容性"""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {'error': f'FFprobe执行失败: {result.stderr}'}
            
            data = json.loads(result.stdout)
            analysis = {
                'compatible': True,
                'issues': [],
                'recommendations': [],
                'video_streams': [],
                'audio_streams': []
            }
            
            # 分析视频流
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_info = {
                        'codec': stream.get('codec_name'),
                        'profile': stream.get('profile'),
                        'level': stream.get('level'),
                        'width': stream.get('width'),
                        'height': stream.get('height'),
                        'bit_depth': stream.get('bits_per_raw_sample'),
                        'color_space': stream.get('color_space'),
                        'color_transfer': stream.get('color_transfer'),
                        'color_primaries': stream.get('color_primaries')
                    }
                    analysis['video_streams'].append(video_info)
                    
                    # 检查兼容性问题
                    self._check_video_compatibility(video_info, analysis)
                
                elif stream.get('codec_type') == 'audio':
                    audio_info = {
                        'codec': stream.get('codec_name'),
                        'channels': stream.get('channels'),
                        'sample_rate': stream.get('sample_rate'),
                        'bit_rate': stream.get('bit_rate')
                    }
                    analysis['audio_streams'].append(audio_info)
            
            return analysis
            
        except Exception as e:
            return {'error': f'视频分析失败: {e}'}
    
    def _check_video_compatibility(self, video_info: Dict, analysis: Dict):
        """检查视频兼容性问题"""
        codec = video_info.get('codec', '').lower()
        profile = video_info.get('profile', '').lower()
        bit_depth = video_info.get('bit_depth')
        color_transfer = video_info.get('color_transfer', '').lower()
        
        # 检查HEVC兼容性
        if codec == 'hevc':
            analysis['issues'].append('使用HEVC (H.265)编码，可能存在兼容性问题')
            analysis['recommendations'].append('建议转换为H.264编码以提高兼容性')
            analysis['compatible'] = False
        
        # 检查Main 10 Profile
        if 'main 10' in profile:
            analysis['issues'].append('使用Main 10 Profile，10-bit编码可能导致解码问题')
            analysis['recommendations'].append('建议使用Main Profile (8-bit)编码')
            analysis['compatible'] = False
        
        # 检查HDR
        if any(hdr in color_transfer for hdr in ['smpte2084', 'arib-std-b67', 'bt2020']):
            analysis['issues'].append('包含HDR元数据，可能导致色彩处理问题')
            analysis['recommendations'].append('建议移除HDR元数据或转换为SDR')
            analysis['compatible'] = False
        
        # 检查Dolby Vision
        if 'dolby' in str(video_info).lower():
            analysis['issues'].append('包含Dolby Vision元数据，可能导致兼容性问题')
            analysis['recommendations'].append('建议移除Dolby Vision元数据')
            analysis['compatible'] = False
    
    def get_optimal_encoding_params(self, target_codec: str = 'h264', 
                                  quality: str = 'balanced', 
                                  use_gpu: bool = True) -> List[str]:
        """获取最优编码参数"""
        
        # 选择最佳编码器
        if target_codec == 'h264':
            if use_gpu and self.supported_codecs['gpu']:
                # 优先使用GPU编码器
                if 'h264_nvenc' in self.supported_codecs['gpu']:
                    return self._get_nvenc_h264_params(quality)
                elif 'h264_amf' in self.supported_codecs['gpu']:
                    return self._get_amf_h264_params(quality)
                elif 'h264_qsv' in self.supported_codecs['gpu']:
                    return self._get_qsv_h264_params(quality)
            
            # 回退到CPU编码器
            return self._get_cpu_h264_params(quality)
        
        elif target_codec == 'h265':
            if use_gpu and self.supported_codecs['gpu']:
                if 'hevc_nvenc' in self.supported_codecs['gpu']:
                    return self._get_nvenc_h265_params(quality)
                elif 'hevc_amf' in self.supported_codecs['gpu']:
                    return self._get_amf_h265_params(quality)
            
            return self._get_cpu_h265_params(quality)
        
        # 默认返回安全的H.264参数
        return self._get_cpu_h264_params(quality)
    
    def _get_nvenc_h264_params(self, quality: str) -> List[str]:
        """获取NVENC H.264编码参数"""
        base_params = [
            '-c:v', 'h264_nvenc',
            '-preset', 'fast',
            '-tune', 'hq',
            '-rc', 'vbr',
            '-profile:v', 'main',  # 强制使用Main Profile
            '-level:v', '4.1',     # 兼容性级别
            '-pix_fmt', 'yuv420p'  # 8-bit 4:2:0
        ]
        
        if quality == 'fast':
            base_params.extend(['-cq', '28', '-b:v', '2M', '-maxrate', '3M'])
        elif quality == 'balanced':
            base_params.extend(['-cq', '23', '-b:v', '5M', '-maxrate', '8M'])
        elif quality == 'quality':
            base_params.extend(['-cq', '18', '-b:v', '8M', '-maxrate', '12M'])
        
        base_params.extend(['-bufsize', '16M', '-g', '60'])  # 2秒GOP
        return base_params
    
    def _get_cpu_h264_params(self, quality: str) -> List[str]:
        """获取CPU H.264编码参数"""
        base_params = [
            '-c:v', 'libx264',
            '-profile:v', 'main',  # 强制使用Main Profile
            '-level:v', '4.1',     # 兼容性级别
            '-pix_fmt', 'yuv420p'  # 8-bit 4:2:0
        ]
        
        if quality == 'fast':
            base_params.extend(['-preset', 'fast', '-crf', '28'])
        elif quality == 'balanced':
            base_params.extend(['-preset', 'medium', '-crf', '23'])
        elif quality == 'quality':
            base_params.extend(['-preset', 'slow', '-crf', '18'])
        
        base_params.extend(['-g', '60', '-threads', str(os.cpu_count())])
        return base_params
    
    def _get_amf_h264_params(self, quality: str) -> List[str]:
        """获取AMF H.264编码参数"""
        base_params = [
            '-c:v', 'h264_amf',
            '-quality', 'balanced',
            '-profile:v', 'main',
            '-level:v', '4.1',
            '-pix_fmt', 'yuv420p'
        ]
        
        if quality == 'fast':
            base_params.extend(['-qp_i', '28', '-qp_p', '30'])
        elif quality == 'balanced':
            base_params.extend(['-qp_i', '23', '-qp_p', '25'])
        elif quality == 'quality':
            base_params.extend(['-qp_i', '18', '-qp_p', '20'])
        
        return base_params
    
    def _get_qsv_h264_params(self, quality: str) -> List[str]:
        """获取QSV H.264编码参数"""
        base_params = [
            '-c:v', 'h264_qsv',
            '-preset', 'medium',
            '-profile:v', 'main',
            '-level:v', '4.1',
            '-pix_fmt', 'yuv420p'
        ]
        
        if quality == 'fast':
            base_params.extend(['-q', '28'])
        elif quality == 'balanced':
            base_params.extend(['-q', '23'])
        elif quality == 'quality':
            base_params.extend(['-q', '18'])
        
        return base_params
    
    def _get_cpu_h265_params(self, quality: str) -> List[str]:
        """获取CPU H.265编码参数"""
        base_params = [
            '-c:v', 'libx265',
            '-profile:v', 'main',  # 使用Main Profile而非Main 10
            '-pix_fmt', 'yuv420p'  # 8-bit 4:2:0
        ]
        
        if quality == 'fast':
            base_params.extend(['-preset', 'fast', '-crf', '28'])
        elif quality == 'balanced':
            base_params.extend(['-preset', 'medium', '-crf', '23'])
        elif quality == 'quality':
            base_params.extend(['-preset', 'slow', '-crf', '18'])
        
        return base_params
    
    def _get_nvenc_h265_params(self, quality: str) -> List[str]:
        """获取NVENC H.265编码参数"""
        base_params = [
            '-c:v', 'hevc_nvenc',
            '-preset', 'fast',
            '-tune', 'hq',
            '-rc', 'vbr',
            '-profile:v', 'main',  # 使用Main Profile
            '-pix_fmt', 'yuv420p'  # 8-bit 4:2:0
        ]
        
        if quality == 'fast':
            base_params.extend(['-cq', '28', '-b:v', '1.5M'])
        elif quality == 'balanced':
            base_params.extend(['-cq', '23', '-b:v', '3M'])
        elif quality == 'quality':
            base_params.extend(['-cq', '18', '-b:v', '5M'])
        
        return base_params
    
    def _get_amf_h265_params(self, quality: str) -> List[str]:
        """获取AMF H.265编码参数"""
        base_params = [
            '-c:v', 'hevc_amf',
            '-quality', 'balanced',
            '-profile:v', 'main',
            '-pix_fmt', 'yuv420p'
        ]
        
        if quality == 'fast':
            base_params.extend(['-qp_i', '28'])
        elif quality == 'balanced':
            base_params.extend(['-qp_i', '23'])
        elif quality == 'quality':
            base_params.extend(['-qp_i', '18'])
        
        return base_params

    def convert_to_compatible_format(self, input_path: str, output_path: str,
                                   target_codec: str = 'h264',
                                   quality: str = 'balanced',
                                   use_gpu: bool = True) -> bool:
        """转换视频为兼容格式"""
        try:
            # 分析输入视频
            analysis = self.analyze_video_compatibility(input_path)
            if analysis.get('error'):
                logger.error(f"视频分析失败: {analysis['error']}")
                return False

            # 获取最优编码参数
            encoding_params = self.get_optimal_encoding_params(target_codec, quality, use_gpu)

            # 构建FFmpeg命令
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', input_path,
                *encoding_params,
                '-c:a', 'aac',  # 音频使用AAC编码
                '-b:a', '192k',
                '-movflags', '+faststart',  # 优化流媒体播放
                '-avoid_negative_ts', 'make_zero',  # 避免负时间戳
                output_path
            ]

            logger.info(f"开始转换视频: {input_path} -> {output_path}")
            logger.info(f"使用编码参数: {encoding_params}")

            # 执行转换
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info(f"视频转换成功: {output_path}")
                return True
            else:
                logger.error(f"视频转换失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"视频转换异常: {e}")
            return False

    def generate_test_videos(self, output_dir: str = "test_videos") -> List[str]:
        """生成标准测试视频"""
        os.makedirs(output_dir, exist_ok=True)
        generated_videos = []

        test_configs = [
            {
                'name': 'test_h264_1080p_30fps.mp4',
                'duration': 10,
                'resolution': '1920x1080',
                'fps': 30,
                'codec': 'h264'
            },
            {
                'name': 'test_h264_720p_30fps.mp4',
                'duration': 15,
                'resolution': '1280x720',
                'fps': 30,
                'codec': 'h264'
            },
            {
                'name': 'test_h264_vertical_1080x1920_30fps.mp4',
                'duration': 20,
                'resolution': '1080x1920',
                'fps': 30,
                'codec': 'h264'
            }
        ]

        for config in test_configs:
            output_path = os.path.join(output_dir, config['name'])
            if self._generate_single_test_video(output_path, config):
                generated_videos.append(output_path)
                logger.info(f"生成测试视频: {output_path}")
            else:
                logger.error(f"生成测试视频失败: {output_path}")

        return generated_videos

    def _generate_single_test_video(self, output_path: str, config: Dict) -> bool:
        """生成单个测试视频"""
        try:
            # 获取编码参数
            encoding_params = self.get_optimal_encoding_params(
                config['codec'], 'balanced', use_gpu=False  # 测试视频使用CPU编码确保兼容性
            )

            # 构建FFmpeg命令
            cmd = [
                self.ffmpeg_path, '-y',
                '-f', 'lavfi',
                '-i', f'testsrc=duration={config["duration"]}:size={config["resolution"]}:rate={config["fps"]}',
                '-f', 'lavfi',
                '-i', f'sine=frequency=1000:duration={config["duration"]}',
                *encoding_params,
                '-c:a', 'aac',
                '-b:a', '128k',
                '-shortest',
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0

        except Exception as e:
            logger.error(f"生成测试视频异常: {e}")
            return False

    def test_encoding_compatibility(self, test_video_dir: str = "test_videos") -> Dict[str, Any]:
        """测试编码兼容性"""
        import time

        results = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'gpu_available': len(self.supported_codecs['gpu']) > 0,
            'supported_codecs': self.supported_codecs,
            'tests': []
        }

        # 生成测试视频
        test_videos = self.generate_test_videos(test_video_dir)

        # 测试不同编码器
        test_cases = [
            {'codec': 'h264', 'quality': 'fast', 'use_gpu': False},
            {'codec': 'h264', 'quality': 'balanced', 'use_gpu': False},
            {'codec': 'h264', 'quality': 'fast', 'use_gpu': True},
            {'codec': 'h264', 'quality': 'balanced', 'use_gpu': True},
        ]

        for test_video in test_videos:
            for test_case in test_cases:
                test_result = self._test_single_encoding(test_video, test_case)
                test_result['input_video'] = os.path.basename(test_video)
                results['tests'].append(test_result)

        return results

    def _test_single_encoding(self, input_video: str, test_case: Dict) -> Dict[str, Any]:
        """测试单个编码配置"""
        import time

        test_name = f"{test_case['codec']}_{test_case['quality']}_{'gpu' if test_case['use_gpu'] else 'cpu'}"
        output_path = f"test_output_{test_name}_{int(time.time())}.mp4"

        start_time = time.time()
        success = False
        error_message = ""

        try:
            # 获取编码参数
            encoding_params = self.get_optimal_encoding_params(
                test_case['codec'],
                test_case['quality'],
                test_case['use_gpu']
            )

            # 如果请求GPU但没有GPU编码器，跳过测试
            if test_case['use_gpu'] and not self.supported_codecs['gpu']:
                return {
                    'test_name': test_name,
                    'success': False,
                    'duration': 0,
                    'error': 'GPU编码器不可用',
                    'encoding_params': encoding_params
                }

            # 构建FFmpeg命令
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', input_video,
                *encoding_params,
                '-c:a', 'aac',
                '-b:a', '128k',
                '-t', '5',  # 只编码5秒进行测试
                output_path
            ]

            # 执行编码
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0 and os.path.exists(output_path):
                success = True
                # 清理测试文件
                try:
                    os.remove(output_path)
                except:
                    pass
            else:
                error_message = result.stderr

        except Exception as e:
            error_message = str(e)

        duration = time.time() - start_time

        return {
            'test_name': test_name,
            'success': success,
            'duration': duration,
            'error': error_message if not success else "",
            'encoding_params': encoding_params
        }

    def generate_compatibility_report(self, output_file: str = "video_encoding_compatibility_report.md") -> str:
        """生成兼容性报告"""
        test_results = self.test_encoding_compatibility()

        report = f"""# 视频编码兼容性测试报告

**测试时间**: {test_results['timestamp']}
**GPU可用**: {'✅' if test_results['gpu_available'] else '❌'}

## 🔧 支持的编码器

### H.264编码器
{', '.join(self.supported_codecs['h264']) if self.supported_codecs['h264'] else '无'}

### H.265编码器
{', '.join(self.supported_codecs['h265']) if self.supported_codecs['h265'] else '无'}

### GPU编码器
{', '.join(self.supported_codecs['gpu']) if self.supported_codecs['gpu'] else '无'}

## 📊 编码测试结果

| 测试用例 | 输入视频 | 状态 | 耗时(s) | 编码器 | 错误信息 |
|---------|---------|------|---------|--------|----------|
"""

        for test in test_results['tests']:
            status = '✅' if test['success'] else '❌'
            encoder = test['encoding_params'][1] if len(test['encoding_params']) > 1 else 'unknown'
            error = test['error'][:50] + '...' if len(test['error']) > 50 else test['error']

            report += f"| {test['test_name']} | {test['input_video']} | {status} | {test['duration']:.2f} | {encoder} | {error} |\n"

        report += f"""
## 🎯 优化建议

### 立即修复
1. **更新GPU驱动**: 确保NVIDIA驱动版本 ≥ 570.0
2. **使用标准格式**: 避免HEVC Main 10和HDR内容
3. **测试GPU编码**: 验证硬件编码器功能

### 编码参数优化
- **推荐编码器**: {self.supported_codecs['h264'][0] if self.supported_codecs['h264'] else 'libx264'}
- **推荐格式**: H.264 Main Profile, 8-bit 4:2:0
- **推荐容器**: MP4 with faststart

### 兼容性最佳实践
1. 使用H.264而非HEVC以确保最大兼容性
2. 避免10-bit编码和HDR元数据
3. 设置合适的Profile和Level
4. 使用标准像素格式(yuv420p)

---
**报告生成工具**: 视频编码兼容性优化器 v1.0
"""

        # 保存报告
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"兼容性报告已生成: {output_file}")
        return output_file


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='视频编码兼容性优化器')
    parser.add_argument('--action', choices=['analyze', 'convert', 'test', 'report'],
                       default='report', help='执行的操作')
    parser.add_argument('--input', help='输入视频文件路径')
    parser.add_argument('--output', help='输出文件路径')
    parser.add_argument('--codec', choices=['h264', 'h265'], default='h264', help='目标编码器')
    parser.add_argument('--quality', choices=['fast', 'balanced', 'quality'],
                       default='balanced', help='编码质量')
    parser.add_argument('--gpu', action='store_true', help='使用GPU加速')

    args = parser.parse_args()

    optimizer = VideoEncodingCompatibilityOptimizer()

    if args.action == 'analyze':
        if not args.input:
            print("❌ 分析模式需要指定输入文件")
            return

        print(f"🔍 分析视频兼容性: {args.input}")
        analysis = optimizer.analyze_video_compatibility(args.input)

        if analysis.get('error'):
            print(f"❌ 分析失败: {analysis['error']}")
        else:
            print(f"✅ 兼容性: {'是' if analysis['compatible'] else '否'}")
            if analysis['issues']:
                print("⚠️ 发现问题:")
                for issue in analysis['issues']:
                    print(f"  - {issue}")
            if analysis['recommendations']:
                print("💡 建议:")
                for rec in analysis['recommendations']:
                    print(f"  - {rec}")

    elif args.action == 'convert':
        if not args.input or not args.output:
            print("❌ 转换模式需要指定输入和输出文件")
            return

        print(f"🔄 转换视频格式: {args.input} -> {args.output}")
        success = optimizer.convert_to_compatible_format(
            args.input, args.output, args.codec, args.quality, args.gpu
        )

        if success:
            print("✅ 转换成功")
        else:
            print("❌ 转换失败")

    elif args.action == 'test':
        print("🧪 执行编码兼容性测试...")
        results = optimizer.test_encoding_compatibility()

        print(f"📊 测试结果:")
        print(f"  GPU可用: {'是' if results['gpu_available'] else '否'}")
        print(f"  测试用例: {len(results['tests'])}个")

        success_count = sum(1 for test in results['tests'] if test['success'])
        print(f"  成功率: {success_count}/{len(results['tests'])} ({success_count/len(results['tests'])*100:.1f}%)")

    elif args.action == 'report':
        print("📝 生成兼容性报告...")
        report_file = optimizer.generate_compatibility_report()
        print(f"✅ 报告已生成: {report_file}")


if __name__ == "__main__":
    main()
