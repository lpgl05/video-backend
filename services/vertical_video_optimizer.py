#!/usr/bin/env python3
"""
竖屏视频处理优化器
专门优化template2模式的视频处理，确保竖屏视频不变形，无背景模糊
"""

import os
import json
import asyncio
import subprocess
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class VideoProperties:
    """视频属性"""
    width: int
    height: int
    duration: float
    orientation: str  # 'vertical', 'horizontal', 'square'
    aspect_ratio: str
    codec: str
    bitrate: Optional[str] = None
    fps: Optional[str] = None

class VerticalVideoOptimizer:
    """竖屏视频优化器"""
    
    def __init__(self):
        self.ffmpeg_path = "ffmpeg"
        self.ffprobe_path = "ffprobe"
        
    async def analyze_video(self, video_path: str) -> Optional[VideoProperties]:
        """分析视频属性"""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                info = json.loads(stdout.decode())
                
                # 提取视频流信息
                video_stream = None
                for stream in info.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        video_stream = stream
                        break
                
                if video_stream:
                    width = int(video_stream.get('width', 0))
                    height = int(video_stream.get('height', 0))
                    duration = float(info.get('format', {}).get('duration', 0))
                    
                    # 判断视频方向
                    if height > width:
                        orientation = 'vertical'
                        aspect_ratio = f"{width}:{height}"
                    elif width > height:
                        orientation = 'horizontal'
                        aspect_ratio = f"{width}:{height}"
                    else:
                        orientation = 'square'
                        aspect_ratio = '1:1'
                    
                    return VideoProperties(
                        width=width,
                        height=height,
                        duration=duration,
                        orientation=orientation,
                        aspect_ratio=aspect_ratio,
                        codec=video_stream.get('codec_name', ''),
                        bitrate=video_stream.get('bit_rate'),
                        fps=video_stream.get('r_frame_rate')
                    )
            
            return None
            
        except Exception as e:
            print(f"❌ 视频分析失败: {e}")
            return None
    
    def get_optimal_template2_params(self, video_props: VideoProperties) -> Dict:
        """获取template2模式的最优处理参数"""
        
        # 判断是否已经是竖屏
        is_already_portrait = video_props.height > video_props.width
        
        if is_already_portrait:
            # 竖屏视频：保持原始比例，不强制缩放
            strategy = "preserve_aspect_ratio"
            target_width = video_props.width
            target_height = video_props.height
            
            # 如果原始视频太小，适当放大但保持比例
            if video_props.width < 720:
                scale_factor = 720 / video_props.width
                target_width = int(video_props.width * scale_factor)
                target_height = int(video_props.height * scale_factor)
                strategy = "upscale_preserve_ratio"
            
            # 如果原始视频太大，适当缩小但保持比例
            elif video_props.width > 1440:
                scale_factor = 1440 / video_props.width
                target_width = int(video_props.width * scale_factor)
                target_height = int(video_props.height * scale_factor)
                strategy = "downscale_preserve_ratio"
            
            filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black"
            
        else:
            # 横屏或正方形视频：转换为竖屏，但保持内容完整
            strategy = "convert_to_portrait"
            
            # 计算最佳的竖屏尺寸
            if video_props.orientation == 'square':
                # 正方形视频：转为9:16，上下留黑边
                target_width = 1080
                target_height = 1920
            else:
                # 横屏视频：根据原始比例计算最佳竖屏尺寸
                original_ratio = video_props.width / video_props.height
                
                if original_ratio >= 16/9:
                    # 超宽屏：转为9:16，左右可能有黑边
                    target_width = 1080
                    target_height = 1920
                else:
                    # 普通横屏：保持内容完整，上下留黑边
                    target_width = 1080
                    target_height = int(1080 / original_ratio)
                    
                    # 确保高度不超过合理范围
                    if target_height > 1920:
                        target_height = 1920
                        target_width = int(1920 * original_ratio)
            
            filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black"
        
        return {
            'strategy': strategy,
            'target_width': target_width,
            'target_height': target_height,
            'filter_complex': filter_complex,
            'use_blur_background': False,  # template2模式不使用背景模糊
            'preserve_aspect_ratio': True,
            'description': self._get_strategy_description(strategy, video_props, target_width, target_height)
        }
    
    def _get_strategy_description(self, strategy: str, video_props: VideoProperties, target_width: int, target_height: int) -> str:
        """获取处理策略描述"""
        descriptions = {
            'preserve_aspect_ratio': f"保持原始竖屏比例 ({video_props.width}x{video_props.height})",
            'upscale_preserve_ratio': f"放大竖屏视频并保持比例 ({video_props.width}x{video_props.height} → {target_width}x{target_height})",
            'downscale_preserve_ratio': f"缩小竖屏视频并保持比例 ({video_props.width}x{video_props.height} → {target_width}x{target_height})",
            'convert_to_portrait': f"转换为竖屏格式 ({video_props.width}x{video_props.height} → {target_width}x{target_height})"
        }
        return descriptions.get(strategy, "未知处理策略")
    
    def get_optimized_ffmpeg_filter(self, video_props: VideoProperties, title_overlay_y: int = 100) -> str:
        """获取优化的FFmpeg滤镜链"""
        
        params = self.get_optimal_template2_params(video_props)
        
        # 构建完整的滤镜链
        filter_parts = [
            f"[0:v]{params['filter_complex']}[base];",
            f"[base][1:v]overlay=0:{title_overlay_y}[with_title];"
        ]
        
        return "".join(filter_parts)
    
    def validate_template2_processing(self, original_props: VideoProperties, processed_props: VideoProperties) -> Dict:
        """验证template2处理结果"""
        
        validation_result = {
            'is_valid': True,
            'issues': [],
            'recommendations': []
        }
        
        # 检查1：确保输出是竖屏或正方形
        if processed_props.height <= processed_props.width:
            validation_result['is_valid'] = False
            validation_result['issues'].append("输出视频不是竖屏格式")
        
        # 检查2：确保没有过度变形
        original_ratio = original_props.width / original_props.height
        processed_ratio = processed_props.width / processed_props.height
        
        # 对于原本就是竖屏的视频，比例变化应该很小
        if original_props.height > original_props.width:
            ratio_change = abs(original_ratio - processed_ratio) / original_ratio
            if ratio_change > 0.1:  # 允许10%的比例变化
                validation_result['issues'].append(f"竖屏视频比例变化过大: {ratio_change:.2%}")
        
        # 检查3：分辨率合理性
        if processed_props.width < 720:
            validation_result['recommendations'].append("输出分辨率较低，建议提高到720p以上")
        
        if processed_props.width > 1440:
            validation_result['recommendations'].append("输出分辨率过高，可能影响性能")
        
        # 检查4：时长一致性
        duration_diff = abs(original_props.duration - processed_props.duration)
        if duration_diff > 1.0:  # 允许1秒误差
            validation_result['issues'].append(f"视频时长变化过大: {duration_diff:.1f}秒")
        
        return validation_result
    
    async def test_template2_optimization(self, input_video: str, output_video: str) -> Dict:
        """测试template2优化效果"""
        
        print(f"🧪 测试template2优化: {os.path.basename(input_video)}")
        
        # 分析原始视频
        original_props = await self.analyze_video(input_video)
        if not original_props:
            return {'success': False, 'error': '无法分析原始视频'}
        
        print(f"   原始视频: {original_props.width}x{original_props.height} ({original_props.orientation})")
        
        # 获取优化参数
        params = self.get_optimal_template2_params(original_props)
        print(f"   处理策略: {params['description']}")
        
        # 创建简单的标题图片用于测试
        title_image = "temp_title.png"
        await self._create_test_title_image(title_image, params['target_width'])
        
        try:
            # 构建FFmpeg命令
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', input_video,
                '-i', title_image,
                '-filter_complex', self.get_optimized_ffmpeg_filter(original_props),
                '-map', '[with_title]',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-t', '10',  # 只处理10秒用于测试
                output_video
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # 分析处理后的视频
                processed_props = await self.analyze_video(output_video)
                
                if processed_props:
                    print(f"   ✅ 处理成功: {processed_props.width}x{processed_props.height}")
                    
                    # 验证处理结果
                    validation = self.validate_template2_processing(original_props, processed_props)
                    
                    return {
                        'success': True,
                        'original_props': original_props,
                        'processed_props': processed_props,
                        'optimization_params': params,
                        'validation': validation
                    }
                else:
                    return {'success': False, 'error': '无法分析处理后的视频'}
            else:
                error_msg = stderr.decode()
                print(f"   ❌ FFmpeg处理失败: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            print(f"   ❌ 测试异常: {e}")
            return {'success': False, 'error': str(e)}
            
        finally:
            # 清理临时文件
            if os.path.exists(title_image):
                os.remove(title_image)
    
    async def _create_test_title_image(self, output_path: str, width: int):
        """创建测试用的标题图片"""
        try:
            cmd = [
                self.ffmpeg_path, '-y',
                '-f', 'lavfi',
                '-i', f'color=c=blue@0.5:size={width}x100:duration=1',
                '-frames:v', '1',
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
        except Exception as e:
            print(f"❌ 创建测试标题图片失败: {e}")

# 全局实例
vertical_optimizer = VerticalVideoOptimizer()

def get_vertical_video_optimizer() -> VerticalVideoOptimizer:
    """获取竖屏视频优化器实例"""
    return vertical_optimizer
