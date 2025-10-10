#!/usr/bin/env python3
"""
SRT字幕处理器 - 支持GPU加速
使用SRT格式替代复杂的图片字幕，提高性能和兼容性
"""

import os
import subprocess
from typing import List, Dict, Tuple
import tempfile
import random
import string

def get_subtitle_font_path(style_config: dict = None) -> str:
    """
    根据样式配置获取字幕字体路径
    
    Args:
        style_config: 样式配置字典
        
    Returns:
        str: 字体文件的绝对路径
    """
    # 如果有样式配置，优先使用样式中指定的字体
    if style_config:
        # 导入字体映射函数
        try:
            from services.clip_service import get_font_path_from_style
            font_path = get_font_path_from_style(style_config, 'subtitle')
            if font_path and os.path.exists(font_path):
                print(f"🎨 使用样式配置字体: {os.path.basename(font_path)} -> {font_path}")
                # 确保字体可用
                try:
                    ensure_font_available(font_path)
                except Exception as e:
                    print(f"⚠️ 字体可用性检查失败: {e}")
                return font_path
        except ImportError as e:
            print(f"⚠️ 无法导入字体映射函数: {e}")
    
    # 回退到默认字体查找逻辑
    print("🔄 回退到默认字体查找")
    
    # 项目字体目录
    font_dir = os.path.join(os.path.dirname(__file__), '..', 'fonts')
    
    # 优先级顺序的字体列表
    font_candidates = [
        'SourceHanSansCN-Heavy.otf',  # 思源黑体
        'msyh.ttc',                   # 微软雅黑
    ]
    
    for font_name in font_candidates:
        font_path = os.path.join(font_dir, font_name)
        if os.path.exists(font_path):
            abs_font_path = os.path.abspath(font_path)
            print(f"🎨 找到中文字体: {font_name} -> {abs_font_path}")
            
            # 尝试确保字体被系统识别
            try:
                ensure_font_available(abs_font_path)
            except Exception as e:
                print(f"⚠️ 字体可用性检查失败: {e}")
            
            return abs_font_path
    
    # 如果项目字体不存在，尝试系统字体
    system_fonts = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/System/Library/Fonts/Arial.ttf',  # macOS
        'C:\\Windows\\Fonts\\msyh.ttc',     # Windows
        'C:\\Windows\\Fonts\\simsun.ttc',   # Windows
    ]
    
    for font_path in system_fonts:
        if os.path.exists(font_path):
            print(f"🎨 使用系统字体: {font_path}")
            return font_path
    
    print("⚠️ 未找到合适的中文字体，将使用默认字体")
    return ""

def get_chinese_font_path() -> str:
    """
    向后兼容的函数，调用新的get_subtitle_font_path函数
    """
    return get_subtitle_font_path()

def ensure_font_available(font_path: str) -> bool:
    """
    确保字体对libass可用
    
    Args:
        font_path: 字体文件路径
    
    Returns:
        bool: 是否成功
    """
    try:
        # 创建用户字体目录（如果不存在）
        user_fonts_dir = os.path.expanduser("~/.fonts")
        if not os.path.exists(user_fonts_dir):
            os.makedirs(user_fonts_dir, exist_ok=True)
            print(f"📁 创建用户字体目录: {user_fonts_dir}")
        
        # 检查字体是否已经在用户字体目录中
        font_name = os.path.basename(font_path)
        user_font_path = os.path.join(user_fonts_dir, font_name)
        
        if not os.path.exists(user_font_path):
            # 复制字体到用户字体目录
            import shutil
            shutil.copy2(font_path, user_font_path)
            print(f"📋 复制字体到用户目录: {user_font_path}")
            
            # 刷新字体缓存
            try:
                subprocess.run(['fc-cache', '-fv'], capture_output=True, timeout=30)
                print("🔄 刷新字体缓存成功")
            except:
                print("⚠️ 无法刷新字体缓存，但字体已复制")
        
        return True
        
    except Exception as e:
        print(f"⚠️ 字体可用性设置失败: {e}")
        return False

def create_srt_subtitle_file(sentences: List[Dict], output_path: str) -> bool:
    """
    创建SRT字幕文件 - 确保UTF-8编码
    
    Args:
        sentences: 字幕句子列表，包含text, start_time, end_time
        output_path: 输出SRT文件路径
    
    Returns:
        bool: 创建是否成功
    """
    try:
        # 确保使用UTF-8编码并添加BOM以提高兼容性
        with open(output_path, 'w', encoding='utf-8-sig') as f:
            for i, sentence in enumerate(sentences, 1):
                start_time = sentence.get('start_time', 0)
                end_time = sentence.get('end_time', start_time + 3)
                text = sentence.get('text', '').strip()
                
                if not text:
                    continue
                
                # SRT时间格式：HH:MM:SS,mmm
                start_srt = seconds_to_srt_time(start_time)
                end_srt = seconds_to_srt_time(end_time)
                
                # SRT格式
                f.write(f"{i}\n")
                f.write(f"{start_srt} --> {end_srt}\n")
                f.write(f"{text}\n\n")
        
        print(f"✅ SRT字幕文件创建成功 (UTF-8编码): {output_path}")
        
        # 验证文件内容
        with open(output_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            print(f"📝 SRT内容预览: {content[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ SRT字幕文件创建失败: {e}")
        return False

def seconds_to_srt_time(seconds: float) -> str:
    """
    将秒数转换为SRT时间格式
    
    Args:
        seconds: 秒数
    
    Returns:
        str: SRT时间格式 HH:MM:SS,mmm
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def create_gpu_video_with_srt_subtitles(
    input_video: str,
    title_image: str,
    srt_file: str,
    tts_audio: str,
    bgm_audio: str,
    output_path: str,
    duration: float,
    title_position: str = "top",
    poster_image: str = None,
    use_gpu: bool = True,
    subtitle_sentences: List[Dict] = None,
    style: dict = None,
    portraitMode: bool = True,
    frameBlur: bool = False
) -> bool:
    """
    使用GPU和SRT字幕创建视频
    
    Args:
        input_video: 输入视频路径
        title_image: 标题图片路径
        srt_file: SRT字幕文件路径
        tts_audio: TTS音频路径
        bgm_audio: 背景音乐路径
        output_path: 输出视频路径
        duration: 视频时长
        title_position: 标题位置
        poster_image: 海报图片路径（可选）
        use_gpu: 是否使用GPU
        portraitMode: 是否为竖版视频
        frameBlur: 对于横版视频，是否需要逐帧模糊视频

    Returns:
        bool: 处理是否成功
    """
    print(f"🎬 开始GPU+SRT字幕视频合成")
    print(f"   输入视频: {os.path.basename(input_video)}")
    print(f"   使用GPU: {use_gpu}")
    print(f"   🔍 调试信息:")
    print(f"      portraitMode: {portraitMode}")
    print(f"      frameBlur: {frameBlur}")
    print(f"      poster_image: {poster_image is not None}")
    
    try:
        # ✅ 修复视频时长问题：预先延长视频到目标时长
        from .clip_service import get_video_info, find_ffmpeg
        
        video_info = get_video_info(input_video)
        source_duration = video_info.get('duration', 0)
        
        if source_duration > 0 and source_duration < duration:
            print(f"⚠️ 视频时长({source_duration:.1f}s)小于目标时长({duration:.1f}s)，预先延长视频...")
            extended_video = input_video.replace('.mp4', '_extended.mp4')
            
            # 计算需要循环的次数
            loop_times = int(duration / source_duration) + 1
            
            # 创建concat列表文件
            concat_list = input_video.replace('.mp4', '_concat_list.txt')
            with open(concat_list, 'w') as f:
                for _ in range(loop_times):
                    f.write(f"file '{os.path.abspath(input_video)}'\n")
            
            # 使用CPU concat（更稳定）延长视频
            ffmpeg = find_ffmpeg()
            cmd = [
                ffmpeg, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_list,
                '-t', str(duration),  # 截取到目标时长
                '-c:v', 'libx264',  # CPU编码
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '128k',
                extended_video
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=False, timeout=120)
            
            # 清理临时文件
            if os.path.exists(concat_list):
                os.remove(concat_list)
            
            if result.returncode == 0 and os.path.exists(extended_video):
                print(f"✅ 视频延长完成: {source_duration:.1f}s -> {duration:.1f}s")
                input_video = extended_video  # 使用延长后的视频
            else:
                print(f"⚠️ 视频延长失败，将使用原视频（可能导致画面卡顿）")
                print(f"   错误输出: {result.stderr.decode('utf-8', errors='ignore')[:200]}")
        else:
            print(f"✅ 视频时长({source_duration:.1f}s)足够，无需延长")
        
        # 如果没有提供SRT文件但有字幕数据，则创建临时SRT文件
        temp_srt_file = None
        if not srt_file and subtitle_sentences:
            temp_srt_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8')
            temp_srt_file.close()
            srt_file = temp_srt_file.name
            
            if not create_srt_subtitle_file(subtitle_sentences, srt_file):
                return False
            print(f"   临时SRT文件: {os.path.basename(srt_file)}")
        elif not srt_file:
            print("⚠️ 没有SRT文件或字幕数据，将跳过字幕处理")
            srt_file = None
        # 获取GPU编码参数 - 修复多线程竞争问题
        if use_gpu:
            # 使用更稳定的GPU编码参数，避免多线程冲突
            gpu_params = [
                '-c:v', 'h264_nvenc',
                '-preset', 'fast',
                '-crf', '23',
                '-profile:v', 'main',
                '-pix_fmt', 'yuv420p'
            ]
            print(f"🚀 使用稳定的GPU编码（多线程优化）: {' '.join(gpu_params[:4])}")
        else:
            gpu_params = ['-c:v', 'libx264', '-preset', 'fast', '-crf', '23']
            print("🖥️ 使用CPU编码")
        
        # 构建FFmpeg命令 - 简化版本，直接使用SRT字幕
        print(f"🔧 构建简化的GPU+SRT处理命令")
        
        # 获取硬件解码参数 - 修复多线程GPU竞争问题
        gpu_decode_params = []
        if use_gpu:
            try:
                # 使用更安全的GPU硬件解码参数，避免多线程冲突
                gpu_decode_params = [
                    '-hwaccel', 'cuda',
                    '-c:v', 'h264_cuvid'
                ]
                print(f"🚀 使用安全的GPU硬件解码（多线程优化）: {' '.join(gpu_decode_params)}")
            except Exception as e:
                print(f"⚠️ GPU解码设置失败: {e}")
                gpu_decode_params = []
        
        # 基础命令 - 添加硬件解码和视频循环
        if poster_image is not None:
            # 有海报图片：无论是横版还是竖版都需要添加海报作为输入4
            cmd = [
                'ffmpeg', '-y',
                *gpu_decode_params,                   # GPU硬件解码参数
                '-i', input_video,                    # 输入0: 源视频
                '-loop', '1', '-i', title_image,      # 输入1: 标题图片（循环）
                '-i', tts_audio,                      # 输入2: TTS音频
                '-i', bgm_audio,                      # 输入3: BGM音频
                '-i', poster_image                    # 输入4: 海报图片
            ]
        else:
            cmd = [
                'ffmpeg', '-y',
                *gpu_decode_params,                   # GPU硬件解码参数
                '-i', input_video,                    # 输入0: 源视频
                '-loop', '1', '-i', title_image,      # 输入1: 标题图片（循环）
                '-i', tts_audio,                      # 输入2: TTS音频
                '-i', bgm_audio,                      # 输入3: BGM音频
            ]
        
        # 构建复合滤镜 - 正确的语法
        filter_parts = []
        
        # 标题叠加
        title_margin = 200
        if title_position == "top":
            title_y = title_margin
        elif title_position == "center":
            title_y = "(H-h)/2-100"
        else:  # bottom
            title_y = f"H-h-{title_margin}"

        if not portraitMode:
            print("   🔍 横版视频处理逻辑:")
            print(f"      poster_image: {poster_image is not None}")
            print(f"      frameBlur: {frameBlur}")
            print(f"      ❌ 错误：portraitMode=False，应该输出9:16格式但使用了横版处理")
            # 横版视频，缩放标题宽度为1080，高度自适应
            if poster_image is not None:
                filter_parts.append("[4:v]crop='min(iw,ih*9/16)':'min(ih,iw*16/9)':'(iw-min(iw,ih*9/16))/2':'(ih-min(ih,iw*16/9))/2'[bg_cropped];")
                filter_parts.append("[bg_cropped]scale=1080:1920[bg];")
            else:
                if frameBlur:
                    # 用户要求逐帧虚化原始视频，作为背景
                    print("准备虚化原始视频，并将其作为背景")
                    filter_parts.append(
                        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,boxblur=40:20[bg];"
                    )
                else:
                    # 使用命令直接生成一张图片 ffmpeg -i input.mp4 -vf "select=eq(n\,100),boxblur=10:2" -vsync vfr -frames:v 1 bg_blur.png
                    # 获取 input_video所在的文件夹路径
                    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                    bg_blur_path = os.path.join(os.path.dirname(os.path.abspath(input_video)), f'bg_blur_{random_str}.png')
                    ffmpeg_bg_cmd = [
                        'ffmpeg', '-y',
                        '-i', input_video,
                        '-vf', 'select=eq(n\\,100),boxblur=10:2',
                        '-vsync', 'vfr',
                        '-frames:v', '1',
                        bg_blur_path
                    ]
                    print(f"🔧 生成背景虚化图片: {bg_blur_path}")
                    result = subprocess.run(ffmpeg_bg_cmd, capture_output=True, text=True, timeout=60)
                    if result.returncode == 0:
                        print("✅ 背景虚化图片生成成功")
                        # 将生成的图片作为新的输入添加到主 ffmpeg 命令（作为输入4）
                        cmd.extend(['-i', bg_blur_path])
                        # 使用生成的图片作为背景
                        filter_parts.append("[4:v]crop='min(iw,ih*9/16)':'min(ih,iw*16/9)':'(iw-min(iw,ih*9/16))/2':'(ih-min(ih,iw*16/9))/2'[bg_cropped];")
                        filter_parts.append("[bg_cropped]scale=1080:1920[bg];")
                    else:
                        print("❌ 背景虚化图片生成失败")
                        print(result.stderr)
                        print("准备虚化原始视频，并将其作为背景")
                        filter_parts.append(
                            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,boxblur=40:20[bg];"
                        )
            filter_parts.append(
                "[0:v]scale=1080:-1:force_original_aspect_ratio=decrease[fg];"
            )
            filter_parts.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[video_base];")
            # 避免重复添加标题 overlay，导致未连接的输出标签错误
            overlay_title = f"[video_base][1:v]overlay=0:{title_y}[video_with_title];"
            if overlay_title not in filter_parts:
                filter_parts.append(overlay_title)
        else:
            print("   🔍 竖版视频处理逻辑:")
            print(f"      portraitMode: {portraitMode}")
            print(f"      poster_image: {poster_image is not None}")
            print(f"      ✅ 正确：portraitMode=True，将输出9:16格式")
            
            # ✅ 修复：竖版视频也需要处理海报背景
            if poster_image is not None:
                # 有海报背景：海报作为背景，视频保持16:9比例居中叠加
                print("   🖼️ 竖版视频使用海报背景，视频保持16:9比例居中")
                filter_parts.append("[0:v]scale=1080:1920:flags=fast_bilinear[bg];")
                # ✅ 修复：保持视频16:9比例，不拉伸，居中显示
                # 16:9视频在9:16画布中居中：视频宽度1080，高度607，上下留白
                filter_parts.append("[4:v]scale=1080:1920:flags=fast_bilinear[fg];")
                filter_parts.append("[bg][fg]overlay=0:(H-h)/2[video_base];")
                filter_parts.append(f"[video_base][1:v]overlay=0:{title_y}[video_with_title];")
            else:
                # 无海报背景：直接缩放视频为9:16格式
                print("   📹 竖版视频直接缩放为9:16格式")
                filter_parts.append(f"[0:v]scale=1080:1920:flags=fast_bilinear[video_scaled];")
                filter_parts.append(f"[video_scaled][1:v]overlay=0:{title_y}[video_with_title];")
        
        # 如果有SRT字幕，添加字幕处理
        if srt_file and os.path.exists(srt_file):
            # 使用样式配置获取字体路径
            font_path = get_subtitle_font_path(style)
            
            # 路径转义处理 - 适用于Linux/Windows
            srt_path = srt_file.replace('\\', '/').replace(':', '\\:')
            
            # 从样式配置中提取字幕样式参数
            subtitle_config = style.get("subtitle", {}) if style else {}
            font_size = subtitle_config.get("fontSize", 48)  # 默认48px
            color = subtitle_config.get("color", "#ffffff")  # 默认白色
            stroke_color = subtitle_config.get("strokeColor", "#000000")  # 默认黑色描边
            stroke_width = subtitle_config.get("strokeWidth", 2)  # 默认描边宽度2
            shadow = subtitle_config.get("shadow", 0)  # 默认无阴影
            position = subtitle_config.get("position", "bottom")  # 默认底部
            
            # 颜色转换：从#ffffff格式转换为&Hffffff格式（BGR格式）
            def hex_to_ass_color(hex_color):
                if hex_color.startswith('#'):
                    hex_color = hex_color[1:]
                # 转换为BGR格式并添加&H前缀
                if len(hex_color) == 6:
                    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
                    return f"&H{b}{g}{r}"
                return "&Hffffff"  # 默认白色
            
            primary_color = hex_to_ass_color(color)
            outline_color = hex_to_ass_color(stroke_color)
            
            # 计算字幕的MarginV（垂直边距）和Alignment（对齐方式）
            margin_v = 60  # 默认底部边距60px
            alignment = 2  # 默认底部居中
            
            if position == "template2":
                # 竖屏模板：使用底部居中对齐
                # 先用非常小的MarginV（底边距100px），确保字幕一定显示
                margin_v = 60  # 距离底部60px，确保字幕显示
                alignment = 2  # 底部居中（水平居中，垂直从底部计算）
            elif position == "top":
                margin_v = 50
                alignment = 8  # 顶部居中
            elif position == "center":
                margin_v = 0  # 居中
                alignment = 5  # 垂直居中
            elif position == "bottom":
                margin_v = 50
                alignment = 2  # 底部居中
            
            # 设置左右边距为0，确保字幕居中
            margin_l = 0  # 左边距
            margin_r = 0  # 右边距
            
            print(f"🎨 字幕样式配置:")
            print(f"   字体大小: {font_size}px")
            print(f"   字体颜色: {color} -> {primary_color}")
            print(f"   描边颜色: {stroke_color} -> {outline_color}")
            print(f"   描边宽度: {stroke_width}")
            print(f"   阴影深度: {shadow}")
            print(f"   字幕位置: {position}, Alignment={alignment}, MarginV={margin_v}px, MarginL={margin_l}px, MarginR={margin_r}px")
            
            # 尝试多种字体配置方案
            subtitle_filter_attempts = []
            
            if font_path:
                print(f"🎨 使用字体: {os.path.basename(font_path)}")
                
                # 方案1: 使用fontsdir指定字体目录（推荐）
                font_dir = os.path.dirname(font_path)
                font_name = os.path.basename(font_path)
                font_name_without_ext = os.path.splitext(font_name)[0]
                
                subtitle_filter_attempts = [
                    # 方案1: 指定字体目录和字体名，使用样式配置
                    f"subtitles='{srt_path}':charenc=UTF-8:fontsdir='{font_dir}':force_style='FontName={font_name_without_ext},FontSize={font_size},PrimaryColour={primary_color},OutlineColour={outline_color},Outline={stroke_width},Shadow={shadow},Alignment={alignment},MarginV={margin_v},MarginL={margin_l},MarginR={margin_r}'",
                    
                    # 方案2: 直接使用字体文件名，使用样式配置
                    f"subtitles='{srt_path}':charenc=UTF-8:force_style='FontName={font_name_without_ext},FontSize={font_size},PrimaryColour={primary_color},OutlineColour={outline_color},Outline={stroke_width},Shadow={shadow},Alignment={alignment},MarginV={margin_v},MarginL={margin_l},MarginR={margin_r}'",
                    
                    # 方案3: 使用常见的中文字体名，使用样式配置
                    f"subtitles='{srt_path}':charenc=UTF-8:force_style='FontName=Source Han Sans CN,FontSize={font_size},PrimaryColour={primary_color},OutlineColour={outline_color},Outline={stroke_width},Shadow={shadow},Alignment={alignment},MarginV={margin_v},MarginL={margin_l},MarginR={margin_r}'",
                    
                    # 方案4: 回退到无字体指定，使用样式配置
                    f"subtitles='{srt_path}':charenc=UTF-8:force_style='FontSize={font_size},PrimaryColour={primary_color},OutlineColour={outline_color},Outline={stroke_width},Shadow={shadow},Alignment={alignment},MarginV={margin_v},MarginL={margin_l},MarginR={margin_r}'"
                ]
                
                print(f"🎨 字体目录: {font_dir}")
                print(f"🎨 字体名称: {font_name_without_ext}")
            else:
                # 无字体文件，使用基本配置和样式参数
                subtitle_filter_attempts = [
                    f"subtitles='{srt_path}':charenc=UTF-8:force_style='FontSize={font_size},PrimaryColour={primary_color},OutlineColour={outline_color},Outline={stroke_width},Shadow={shadow},Alignment={alignment},MarginV={margin_v},MarginL={margin_l},MarginR={margin_r}'"
                ]
            
            # 使用第一个字体配置方案
            subtitle_filter = subtitle_filter_attempts[0]
            filter_parts.append(f"[video_with_title]{subtitle_filter}[video_out];")
            
            print(f"📝 添加SRT字幕: {os.path.basename(srt_file)}")
            print(f"📝 编码: UTF-8")
            print(f"🔧 字幕滤镜: {subtitle_filter}")
        else:
            filter_parts.append("[video_with_title]format=yuv420p[video_out];")
        
        # 音频混合
        filter_parts.append("[2:a]volume=0.8[tts];")
        filter_parts.append("[3:a]volume=0.15[bgm];")
        filter_parts.append("[tts][bgm]amix=inputs=2:duration=first[audio_out]")
        
        # 组合完整的滤镜复合体
        filter_complex = "".join(filter_parts)
        
        # 完整命令 - 添加多线程优化参数
        cmd.extend([
            '-filter_complex', filter_complex,
            '-map', '[video_out]',
            '-map', '[audio_out]',
            '-t', str(duration),                    # 强制设置输出时长
            '-shortest',                           # 以最短输入为准，防止循环视频过长
            *gpu_params,
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',      # 避免时间戳问题
            '-threads', '2',                       # 限制线程数，避免多线程冲突
            output_path
        ])
        
        print(f"🔧 FFmpeg命令构建完成")
        # 从样式配置中获取实际参数来显示日志
        if style:
            subtitle_config = style.get("subtitle", {})
            font_size = subtitle_config.get("fontSize", 48)
            color = subtitle_config.get("color", "#ffffff")
            stroke_color = subtitle_config.get("strokeColor", "#000000")
            font_family = subtitle_config.get("fontFamily", "默认字体")
            print(f"📝 SRT字幕样式: {color}文字，{stroke_color}描边，{font_size}px {font_family}")
        else:
            print(f"📝 SRT字幕样式: 白色文字，黑色描边，48px默认字体")
        print(f"🔧 滤镜复合体: {filter_complex}")
        print(f"🔧 完整命令: {' '.join(cmd)}")
        
        # 执行FFmpeg命令
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ GPU+SRT字幕视频合成成功!")
            success = True
        else:
            print(f"❌ 视频合成失败:")
            print(f"   错误信息: {result.stderr}")
            success = False
        
        # 清理临时SRT文件
        if temp_srt_file:
            try:
                os.unlink(srt_file)
                print(f"🗑️ 清理临时SRT文件: {os.path.basename(srt_file)}")
            except:
                pass
        
        return success
            
    except Exception as e:
        print(f"❌ GPU+SRT字幕处理异常: {e}")
        # 清理临时文件
        if 'temp_srt_file' in locals() and temp_srt_file:
            try:
                os.unlink(srt_file)
            except:
                pass
        return False

def create_simple_gpu_srt_video(
    input_video: str,
    sentences: List[Dict],
    output_path: str,
    duration: float,
    use_gpu: bool = True
) -> bool:
    """
    简化版GPU+SRT字幕视频创建
    只处理视频和字幕，不添加标题和音频
    
    Args:
        input_video: 输入视频路径
        sentences: 字幕句子列表
        output_path: 输出视频路径
        duration: 视频时长
        use_gpu: 是否使用GPU
    
    Returns:
        bool: 处理是否成功
    """
    print(f"🎬 简化版GPU+SRT字幕处理")
    
    try:
        # 创建临时SRT文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
            srt_file = f.name
            
        if not create_srt_subtitle_file(sentences, srt_file):
            return False
        
        # 获取GPU编码参数
        if use_gpu:
            from services.tesla_t4_gpu_optimizer import tesla_t4_optimizer
            ready, _ = tesla_t4_optimizer.is_ready()
            if ready:
                gpu_params = tesla_t4_optimizer.get_optimal_encoding_params('balanced')
                print(f"🚀 使用Tesla T4 GPU编码")
            else:
                gpu_params = ['-c:v', 'libx264', '-preset', 'fast', '-crf', '23']
                print("⚠️ GPU不可用，使用CPU编码")
        else:
            gpu_params = ['-c:v', 'libx264', '-preset', 'fast', '-crf', '23']
        
        # 简化的FFmpeg命令
        cmd = [
            'ffmpeg', '-y',
            '-i', input_video,
            '-vf', f'subtitles={srt_file}:force_style=\'FontSize=48,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2\'',
            '-t', str(duration),
            *gpu_params,
            '-c:a', 'aac',
            '-movflags', '+faststart',
            output_path
        ]
        
        print(f"🔧 执行简化SRT字幕处理...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 清理临时文件
        try:
            os.unlink(srt_file)
        except:
            pass
        
        if result.returncode == 0:
            print(f"✅ 简化版GPU+SRT字幕处理成功!")
            return True
        else:
            print(f"❌ 处理失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 简化版SRT处理异常: {e}")
        return False

# 测试函数
def test_srt_subtitle_creation():
    """测试SRT字幕创建"""
    sentences = [
        {"text": "欢迎来到视频处理系统", "start_time": 0.0, "end_time": 3.0},
        {"text": "我们使用Tesla T4 GPU加速", "start_time": 3.0, "end_time": 6.0},
        {"text": "SRT字幕格式简单高效", "start_time": 6.0, "end_time": 9.0},
        {"text": "感谢您的使用！", "start_time": 9.0, "end_time": 12.0}
    ]
    
    srt_file = "test_subtitles.srt"
    success = create_srt_subtitle_file(sentences, srt_file)
    
    if success:
        print(f"✅ SRT测试成功，文件已创建: {srt_file}")
        # 显示文件内容
        with open(srt_file, 'r', encoding='utf-8') as f:
            print("文件内容:")
            print(f.read())
    else:
        print("❌ SRT测试失败")

if __name__ == "__main__":
    test_srt_subtitle_creation()
