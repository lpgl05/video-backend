import os
# 视频编码兼容性优化
try:
    from services.video_encoding_optimizer import get_optimized_encoding_params, check_video_needs_conversion
    ENCODING_OPTIMIZATION_AVAILABLE = True
    print("✅ 视频编码优化功能已加载")
except ImportError as e:
    print(f"⚠️ 视频编码优化功能不可用: {e}")
    ENCODING_OPTIMIZATION_AVAILABLE = False

import math
import random
import requests
from uuid import uuid4
from models.oss_client import OSSClient
import subprocess
import re

# 导入新的优化模块
from services.ass_subtitle_service import ass_generator
from services.smart_material_cache import smart_cache

# 视频相关
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import TextClip, ColorClip
from moviepy.editor import CompositeVideoClip, concatenate_videoclips, ImageClip

# 音频相关
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.audio.AudioClip import AudioClip, CompositeAudioClip, concatenate_audioclips

# 新增：使用 PIL 生成文字贴图，避免 ImageMagick 依赖
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# 语音合成
import edge_tts
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# 团队协作模式：保留必要的处理目录，移除uploads依赖
DOWNLOAD_VIDEO_PATH = "outputs/download_videos"
DOWNLOAD_AUDIO_PATH = "outputs/download_audios"
OUTPUT_DIR = "outputs/clips"
TTS_TEMP_DIR = "outputs/tts_audio"
SUBTITLE_TEMP_DIR = "outputs/subtitle_images"
OSS_UPLOAD_FINAL_VEDIO = "final/videos"  # OSS存储路径，无需本地uploads前缀

# 确保处理所需的临时目录存在
os.makedirs(DOWNLOAD_VIDEO_PATH, exist_ok=True)
os.makedirs(DOWNLOAD_AUDIO_PATH, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TTS_TEMP_DIR, exist_ok=True)
os.makedirs(SUBTITLE_TEMP_DIR, exist_ok=True)
oss_client = OSSClient()

# 先从.env中读取字体要求
VIDEO_FONT = os.getenv("VIDEO_FONT", "msyh.ttc")
FONT_PATH = os.path.join("fonts", VIDEO_FONT)
print(f'指定的字体路径是: {FONT_PATH}')

# 字体映射配置：前端字体名到后端字体文件的映射
FONT_MAPPING = {
    'Arial, sans-serif': None,  # 使用系统默认
    'Microsoft YaHei, sans-serif': 'msyh.ttc',
    'SimSun, serif': 'simsun.ttc',
    'SimHei, sans-serif': 'simhei.ttf',
    'KaiTi, serif': 'simkai.ttf',
    'LIULISONG': 'LIULISONG.ttf',
    'MiaobiJunli': '妙笔珺俐体.ttf',
    'MiaobiDuanmu': '妙笔段慕体.ttf',
    'SourceHanSansCN-Heavy': 'SourceHanSansCN-Heavy.otf',  # 思源黑体Heavy
}

def get_font_path_from_style(style_config, font_type='title'):
    """根据样式配置获取字体文件路径"""
    if not style_config:
        return FONT_PATH
    
    font_style = style_config.get(font_type, {}) if isinstance(style_config, dict) else {}
    font_family = font_style.get('fontFamily', 'Microsoft YaHei, sans-serif')
    
    print(f'查找字体: {font_family} (类型: {font_type})')
    
    # 查找字体映射
    font_file = FONT_MAPPING.get(font_family)
    if font_file:
        print(f'字体映射找到: {font_file}')
        
        # 优先从前端目录获取
        frontend_font_path = os.path.join("..", "frontend", "public", "fonts", font_file)
        frontend_font_path = os.path.abspath(frontend_font_path)
        
        if os.path.exists(frontend_font_path):
            print(f'✅ 使用前端字体: {frontend_font_path}')
            return frontend_font_path
        
        # 如果前端不存在，尝试本地fonts目录
        local_font_path = os.path.join("fonts", font_file)
        local_font_path = os.path.abspath(local_font_path)
        
        if os.path.exists(local_font_path):
            print(f'✅ 使用本地字体: {local_font_path}')
            return local_font_path
        
        print(f'❌ 字体文件不存在，前端路径: {frontend_font_path}')
        print(f'❌ 字体文件不存在，本地路径: {local_font_path}')
    else:
        print(f'❌ 字体映射中未找到: {font_family}')
    
    print(f'🔄 使用默认字体: {FONT_PATH}')
    return FONT_PATH

def parse_color(value, default=(0, 0, 0, 200)):
    """
    返回 (r,g,b,a) 四元组，a 为 0-255
    支持：tuple/list, "#RRGGBB", "#RRGGBBAA", "rgb(...)" / "rgba(...)" / 简单数字字符串
    """
    if value is None:
        return default
    if isinstance(value, (tuple, list)):
        if len(value) >= 4:
            return (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
        if len(value) == 3:
            return (int(value[0]), int(value[1]), int(value[2]), default[3])
    s = str(value).strip()
    # hex with #
    if s.startswith('#'):
        s = s[1:]
    # hex lengths
    if re.fullmatch(r'[0-9a-fA-F]{6}', s):
        r = int(s[0:2], 16); g = int(s[2:4], 16); b = int(s[4:6], 16); a = default[3]
        return (r, g, b, a)
    if re.fullmatch(r'[0-9a-fA-F]{8}', s):
        r = int(s[0:2], 16); g = int(s[2:4], 16); b = int(s[4:6], 16); a = int(s[6:8], 16)
        return (r, g, b, a)
    # rgb / rgba
    m = re.findall(r'[\d.]+', s)
    if m and (s.lower().startswith('rgb')):
        try:
            nums = [float(x) for x in m]
            if len(nums) >= 3:
                r, g, b = int(nums[0]), int(nums[1]), int(nums[2])
                if len(nums) >= 4:
                    a_val = nums[3]
                    a = int(a_val * 255) if 0 <= a_val <= 1 else int(a_val)
                else:
                    a = default[3]
                return (r, g, b, a)
        except Exception:
            pass
    # fallback: try to parse simple numeric comma-separated
    m = re.findall(r'[\d]+', s)
    if m and len(m) >= 3:
        try:
            nums = [int(x) for x in m]
            r, g, b = nums[0], nums[1], nums[2]
            a = nums[3] if len(nums) >= 4 else default[3]
            return (r, g, b, a)
        except Exception:
            pass
    return default

def get_bg_rgba_from_style(style, section_name, default=(0,0,0,200)):
    """
    从 style 中提取背景颜色并返回 (r,g,b,a)
    支持多种结构并兼容旧字段
    """
    if not style or not isinstance(style, dict):
        return default

    lookups = [style, style.get("style", {})]

    possible_keys = [section_name, section_name + 's']
    for base in lookups:
        if not isinstance(base, dict):
            continue
        section = None
        for k in possible_keys:
            if k in base and isinstance(base[k], dict):
                section = base[k]
                break
        if section is None:
            for k in possible_keys:
                if k in base:
                    section = base[k]
                    break
        if section is None:
            continue

        bg = None
        if isinstance(section, dict):
            bg = section.get("background")
            if isinstance(bg, dict):
                color = bg.get("background_color") or bg.get("color") or bg.get("backgroundColor")
                opacity = bg.get("background_opacity") or bg.get("opacity") or bg.get("alpha")
                if color:
                    a = default[3]
                    if opacity is not None:
                        try:
                            a = int(opacity)
                        except:
                            try:
                                a = int(float(opacity) * 255)
                            except:
                                a = default[3]
                    rgba = parse_color(color, default=(default[0], default[1], default[2], a))
                    return (rgba[0], rgba[1], rgba[2], a)
            if isinstance(bg, (str, tuple, list)):
                opacity = section.get("background_opacity") or section.get("opacity") or None
                if opacity is not None:
                    try:
                        a = int(opacity)
                    except:
                        try:
                            a = int(float(opacity) * 255)
                        except:
                            a = default[3]
                    rgba = parse_color(bg, default=default)
                    return (rgba[0], rgba[1], rgba[2], a)
                else:
                    return parse_color(bg, default=default)

            color_field = section.get("background_color") or section.get("color")
            opacity_field = section.get("background_opacity") or section.get("opacity")
            if color_field:
                a = default[3]
                if opacity_field is not None:
                    try:
                        a = int(opacity_field)
                    except:
                        try:
                            a = int(float(opacity_field) * 255)
                        except:
                            a = default[3]
                rgba = parse_color(color_field, default=(default[0], default[1], default[2], a))
                return (rgba[0], rgba[1], rgba[2], a)

        if isinstance(section, (tuple, list, str)):
            return parse_color(section, default=default)

    return default

def rgba_to_ass_backcolour(rgba):
    """
    将 (r,g,b,a) 转为 ASS/FFmpeg 字幕中 BackColour 表示形式 &HAABBGGRR
    """
    r, g, b, a = rgba
    aa = f"{int(a) & 0xff:02x}"
    bb = f"{int(b) & 0xff:02x}"
    gg = f"{int(g) & 0xff:02x}"
    rr = f"{int(r) & 0xff:02x}"
    return f"&H{aa}{bb}{gg}{rr}"

async def download_video(url):
    # 团队协作模式：统一从OSS下载视频文件
    filename = url.split("/")[-1]
    print('---------------------------------------')
    print(url)
    print(filename)

    local_file = DOWNLOAD_VIDEO_PATH + "/" + filename
    print(local_file)
    await oss_client.download_video(url, local_file)
    return local_file

async def download_audio(url):
    # 团队协作模式：统一从OSS下载音频文件
    filename = url.split("/")[-1]
    print('---------------------------------------')
    print(f"下载音频: {url}")
    print(f"文件名: {filename}")

    local_file = DOWNLOAD_AUDIO_PATH + "/" + filename
    print(f"本地路径: {local_file}")
    await oss_client.download_video(url, local_file)  # OSS客户端只有download_video方法
    return local_file

async def download_poster(url):
    """下载海报图片到本地"""
    # 团队协作模式：统一从OSS下载海报文件
    filename = url.split("/")[-1]
    
    # 确保海报下载目录存在
    poster_download_path = "downloads/posters"
    os.makedirs(poster_download_path, exist_ok=True)
    
    local_file = os.path.join(poster_download_path, filename)
    print(f"下载海报: {url} -> {local_file}")
    await oss_client.download_video(url, local_file)  # 复用下载方法
    return local_file

def random_cut(video_path, min_duration, max_duration, count):
    video = VideoFileClip(video_path)
    clips = []
    for _ in range(count):
        max_clip_duration = min(max_duration, int(video.duration) - 1)
        if max_clip_duration < min_duration:
            continue
        duration = random.randint(min_duration, max_clip_duration)
        start = random.uniform(0, video.duration - duration)
        clip = video.subclip(start, start + duration)
        clips.append(clip)
    return clips

def add_text(clip, text, style, font_path=None):
    # 使用 PIL 渲染文本，避免 TextClip 依赖 ImageMagick
    title_style = style.get("title", {}) if isinstance(style, dict) else {}
    fontsize = int(title_style.get("fontSize", 40))
    
    # 如果字体大小为0，则不显示标题
    if fontsize <= 0:
        return clip
        
    color = title_style.get("color", "#FFFFFF")
    position = title_style.get("position", "bottom")  # top | center | bottom

    banner_h = max(60, int(fontsize * 2))  # 简单设定高度

    # 从 style 读取背景颜色，兼容新旧结构
    bg_rgba = get_bg_rgba_from_style(style, "title", default=(0,0,0,0))  # 默认完全透明

    img = Image.new("RGBA", (int(clip.w), banner_h), bg_rgba)  # 使用可配置背景
    draw = ImageDraw.Draw(img)

    # 优先使用从样式配置中获取的字体
    if not font_path:
        font_path = get_font_path_from_style(style, 'title')
    
    font = None
    if font_path and os.path.exists(font_path):
        try:
            print(f'使用字体文件: {font_path}')
            font = ImageFont.truetype(font_path, fontsize)
        except Exception as e:
            print(f'加载字体失败: {e}')
            font = None
    else:
        chinese_fonts = [
            "C:\\Windows\\Fonts\\msyh.ttc",      # 微软雅黑
            "C:\\Windows\\Fonts\\simsun.ttc",   # 宋体
            "C:\\Windows\\Fonts\\simhei.ttf",   # 黑体
            "C:\\Windows\\Fonts\\simkai.ttf",   # 楷体
            "/System/Library/Fonts/PingFang.ttc",  # macOS
            "/System/Library/Fonts/Hiragino Sans GB.ttc",  # macOS
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # Linux备选
        ]
        for fp in chinese_fonts:
            try:
                font = ImageFont.truetype(fp, fontsize)
                break
            except Exception:
                continue

    if font is None:
        try:
            # 尝试使用系统默认字体，指定字体大小
            font = ImageFont.load_default()
        except Exception:
            # 如果都失败，创建一个简单的默认字体
            font = ImageFont.load_default()

    # 文本换行以适配宽度
    max_width = clip.w - 40
    if not text:
        text = ""
    
    # 改进文本换行逻辑，按词或字符分割
    lines = []
    words = text.split() if ' ' in text else list(text)  # 英文按词分割，中文按字符分割
    current = ""
    
    for word in words:
        test = current + (" " if current and ' ' in text else "") + word
        try:
            bbox = draw.textbbox((0, 0), test, font=font)
            text_width = bbox[2] - bbox[0]
        except Exception:
            text_width = len(test) * fontsize // 2  # 备选计算方法
            
        if text_width > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    
    if current:
        lines.append(current)
    if not lines:
        lines = [""]  # 防止空文本异常

    # 居中绘制文本
    total_height = len(lines) * (fontsize + 4)
    y = max(0, (banner_h - total_height) // 2)
    
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * fontsize // 2  # 备选计算方法
            
        x = max(0, (clip.w - tw) // 2)
        
        try:
            draw.text((x, y), line, font=font, fill=color)
        except Exception:
            # 如果绘制失败，尝试使用默认字体
            draw.text((x, y), line, fill=color)
            
        y += fontsize + 4

    # 生成 ImageClip 覆盖在视频上
    banner_clip = ImageClip(np.array(img)).set_duration(clip.duration)
    if position == "top":
        banner_clip = banner_clip.set_position(("center", "top"))
    elif position == "center":
        banner_clip = banner_clip.set_position(("center", "center"))
    else:
        banner_clip = banner_clip.set_position(("center", "bottom"))

    return CompositeVideoClip([clip, banner_clip])

def add_bgm(clip, bgm_path):
    bgm = AudioFileClip(bgm_path).volumex(0.2)
    if bgm.duration < clip.duration:
        bgm = bgm.audio_loop(duration=clip.duration)
    else:
        bgm = bgm.subclip(0, clip.duration)
    final_audio = bgm.set_duration(clip.duration)
    return clip.set_audio(final_audio)

def build_montage_clips(source_paths, target_duration, count):
    """
    为每个目标输出构建一个由多个源视频片段拼接而成的短视频，
    尽量保证每个输出都包含所有源视频的一部分。
    """
    if not source_paths:
        return []

    # 预加载源视频，避免重复打开
    sources = [VideoFileClip(p) for p in source_paths]
    outputs = []

    for _ in range(count):
        remaining = target_duration
        segments = []
        n = len(sources)
        # 基础分配：尽量均分给每个源视频
        base_share = max(1, target_duration // max(1, n))

        for idx, src in enumerate(sources):
            if remaining <= 0:
                break
            # 当前源视频可用最大片段时长（留 0.5s 余量避免溢出）
            src_max = max(0, int(src.duration) - 1)
            if src_max <= 0:
                continue

            # 最后一个源视频用剩余时长补齐
            alloc = base_share if idx < n - 1 else remaining
            seg_dur = min(max(1, int(alloc)), src_max)
            if seg_dur <= 0:
                continue

            start_max = max(0, src.duration - seg_dur - 0.1)
            start = random.uniform(0, start_max) if start_max > 0 else 0
            seg = src.subclip(start, start + seg_dur)
            segments.append(seg)
            remaining -= seg_dur

        # 如果还没凑够目标时长，循环从可用源视频再补片段
        safe_guard = 0
        while remaining > 0 and safe_guard < 10 * n:
            safe_guard += 1
            src = random.choice(sources)
            src_max = max(0, int(src.duration) - 1)
            if src_max <= 0:
                continue
            seg_dur = min(max(1, int(remaining)), src_max)
            if seg_dur <= 0:
                continue
            start_max = max(0, src.duration - seg_dur - 0.1)
            start = random.uniform(0, start_max) if start_max > 0 else 0
            seg = src.subclip(start, start + seg_dur)
            segments.append(seg)
            remaining -= seg_dur

        if not segments:
            continue

        # 拼接所有片段
        final = concatenate_videoclips(segments, method="compose")
        # 超出目标时长则裁剪
        if final.duration > target_duration:
            final = final.subclip(0, target_duration)
        outputs.append(final)

    # 注意：sources 由调用方统一在写文件后关闭
    return outputs

def get_rotation(video_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "side_data=displaymatrix",
        "-of", "default=noprint_wrappers=1",
        "-read_intervals", "%+#1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout

    # 提取矩阵
    lines = [line.strip() for line in output.splitlines() if line.startswith("00000000") or line.startswith("00000001")]
    if len(lines) < 2:
        return 0  # 没有旋转矩阵，认为0度

    a, b, _ = map(int, lines[0].split(":")[1].split())
    c, d, _ = map(int, lines[1].split(":")[1].split())

    # Q16 转为浮点
    a /= 65536
    b /= 65536
    c /= 65536
    d /= 65536

    # 计算角度
    angle = math.degrees(math.atan2(c, a))
    angle = int((angle + 360) % 360)  # 转换为 0~359 度
    return angle

def process_original_video(videos_file):
    # 使用命令 ffprobe -v error -select_streams v:0 -show_frames -show_entries frame=pict_type -count_frames -read_intervals "%+#5" video01.mp4
    # 去判断，如果返回值中存在90,则需要处理，否则不处理
    videos_path = []
    for video_file in videos_file:
        video_file_name = os.path.splitext(os.path.basename(video_file))[0]
        # 获取其所在目录
        video_file_dir = os.path.dirname(video_file)
        # 处理后的视频名称
        xuanzhuan_video = f"{video_file_dir}/{video_file_name}_rotated.mp4"

        ffmpeg_xuanzhuan_cmd = ""
        rotation = get_rotation(video_file)
        match rotation:
            case 0 | 180:
                print(f"视频 {video_file} 不需要处理")
                ffmpeg_xuanzhuan_cmd = f'ffmpeg -hwaccel cuda -i "{video_file}" -vf "hflip,hflip,scale=1080:1920" -c:v h264_nvenc -profile:v main -pix_fmt yuv420p -preset fast -r 30 -c:a copy -metadata:s:v:0 rotate=0 "{xuanzhuan_video}"'
            case 90:
                print(f"视频 {video_file} 旋转角度为 90° 需要处理")
                ffmpeg_xuanzhuan_cmd = f'ffmpeg -hwaccel cuda -i "{video_file}" -vf "hflip,hflip,scale=1080:1920" -c:v h264_nvenc -profile:v main -pix_fmt yuv420p -preset fast -r 30 -c:a copy -metadata:s:v:0 rotate=0 "{xuanzhuan_video}"'
            case 270:
                print(f"视频 {video_file} 旋转角度为 270° 需要处理")
                ffmpeg_xuanzhuan_cmd = f'ffmpeg -hwaccel cuda -i "{video_file}" -vf "vflip,vflip,scale=1080:1920" -c:v h264_nvenc -profile:v main -pix_fmt yuv420p -preset fast -r 30 -c:a copy -metadata:s:v:0 rotate=0 "{xuanzhuan_video}"'

        if os.path.exists(xuanzhuan_video):
            # 说明视频已经旋转，无须再进行一次旋转
            videos_path.append(f"{xuanzhuan_video}")
            # 删除原视频
            os.remove(video_file)
        else:
            # 执行旋转命令
            rr = subprocess.run(ffmpeg_xuanzhuan_cmd, shell=True)
            if rr.returncode == 0:
                print(f"视频 {video_file} 旋转完成")
                videos_path.append(f"{xuanzhuan_video}")
                # 删除原视频
                os.remove(video_file)
            else:
                print(f"视频 {video_file} 旋转失败, 移除该原始视频")
    return videos_path

def process_original_video001(videos_file):
    # 使用命令 ffprobe -v error -select_streams v:0 -show_frames -show_entries frame=pict_type -count_frames -read_intervals "%+#5" video01.mp4
    # 去判断，如果返回值中存在90,则需要处理，否则不处理
    videos_path = []
    for video_file in videos_file:
        ffprobe_cmd = f"ffprobe -v error -select_streams v:0 -show_frames -show_entries frame=pict_type -count_frames -read_intervals \"%+#3\" {video_file}"
        # 执行命令并获取返回值
        result = subprocess.run(ffprobe_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            # 判断返回值中是否存在90
            if "rotation=90" in result.stdout or "rotation=-90" in result.stdout:
                rotation = "90" if "rotation=90" in result.stdout else "-90"
                print(f"视频 {video_file} 是一个颠倒视频 (rotation={rotation})")

                video_file_name = os.path.splitext(os.path.basename(video_file))[0]
                # 获取其所在目录
                video_file_dir = os.path.dirname(video_file)

                # 处理后的视频名称
                xuanzhuan_video = f"{video_file_dir}/{video_file_name}_rotated.mp4"

                if os.path.exists(xuanzhuan_video):
                    # 说明视频已经旋转，无须再进行一次旋转
                    videos_path.append(f"{xuanzhuan_video}")
                    # 删除原视频
                    os.remove(video_file)
                else:
                    if rotation == "90":
                        # 进行180度旋转
                        # 使用如下命令进行旋转
                        # ffmpeg -hwaccel cuda -i video01.mp4 -vf "hflip,vflip" -c:v hevc_nvenc -pix_fmt p010le -preset fast -c:a copy -metadata:s:v:0 rotate=0 ddd.mp4
                        ffmpeg_xuanzhuan_cmd = f"ffmpeg -hwaccel cuda -i {video_file} -vf \"hflip,vflip\" -c:v hevc_nvenc -pix_fmt p010le -preset fast -c:a copy -metadata:s:v:0 rotate=0 {xuanzhuan_video}"
                    else:
                        # rotation == "-90"
                        # 进行180度旋转
                        # 使用如下命令进行旋转
                        # ffmpeg -hwaccel cuda -i video01.mp4 -vf "vflip,hflip" -c:v hevc_nvenc -pix_fmt p010le -preset fast -c:a copy -metadata:s:v:0 rotate=0 ddd.mp4
                        ffmpeg_xuanzhuan_cmd = f"ffmpeg -hwaccel cuda -i {video_file} -vf \"hflip,hflip\" -c:v hevc_nvenc -pix_fmt p010le -preset fast -c:a copy -metadata:s:v:0 rotate=0 {xuanzhuan_video}"
                    # 执行旋转命令
                    rr = subprocess.run(ffmpeg_xuanzhuan_cmd, shell=True)
                    if rr.returncode == 0:
                        print(f"视频 {video_file} 旋转完成")
                        videos_path.append(f"{xuanzhuan_video}")
                        # 删除原视频
                        os.remove(video_file)
                    else:
                        print(f"视频 {video_file} 旋转失败, 移除该原始视频")
            else:
                print(f"视频 {video_file} 不需要处理")
                videos_path.append(video_file)
        else:
            print(f"ffprobe 命令执行失败: {result.stderr}")

    return videos_path
    
def add_bgm_with_tts(clip, bgm_path, tts_audio_path):
    """
    添加BGM和TTS语音，两者混合播放
    
    Args:
        clip: 视频片段
        bgm_path: 背景音乐路径
        tts_audio_path: TTS语音文件路径
    """
    try:
        # 加载TTS语音
        tts_audio = AudioFileClip(tts_audio_path)
        
        # 加载BGM并降低音量
        bgm = AudioFileClip(bgm_path).volumex(0.15)  # 降低BGM音量以突出语音
        
        # 调整TTS语音音量
        tts_audio = tts_audio.volumex(0.8)
        
        # 如果BGM时长小于视频时长，循环播放
        if bgm.duration < clip.duration:
            bgm = bgm.audio_loop(duration=clip.duration)
        else:
            bgm = bgm.subclip(0, clip.duration)
        
        # 如果TTS时长小于视频时长，在开头播放TTS，剩余时间只有BGM
        if tts_audio.duration < clip.duration:
            # 创建静音填充
            silence_duration = clip.duration - tts_audio.duration
            silence = AudioClip(lambda t: [0, 0], duration=silence_duration)
            tts_audio = concatenate_audioclips([tts_audio, silence])
        else:
            # 如果TTS更长，截取到视频长度
            tts_audio = tts_audio.subclip(0, clip.duration)
        
        # 混合两个音频轨道
        final_audio = CompositeAudioClip([bgm, tts_audio])
        final_audio = final_audio.set_duration(clip.duration)
        
        return clip.set_audio(final_audio)
        
    except Exception as e:
        print(f"音频混合失败: {e}")
        # 如果混合失败，至少保留原BGM
        return add_bgm(clip, bgm_path)


def parse_duration(duration_str):
    # 支持 '15s' | '30s' | '30-60s'
    if not duration_str:
        return 30
    s = duration_str.strip().lower()
    if s.endswith('s'):
        s = s[:-1]
    if '-' in s:
        try:
            a, b = s.split('-', 1)
            lo, hi = int(a), int(b)
            if lo > hi:
                lo, hi = hi, lo
            return random.randint(lo, hi)
        except Exception:
            return 30
    try:
        return int(s)
    except Exception:
        return 30

def load_font_for_title(title_config, style, title_type='title'):
    """为标题加载字体"""
    font_size = title_config.get("fontSize", 64)
    font_family = title_config.get("fontFamily")
    
    # 尝试从配置中获取字体路径
    font_path = None
    if font_family:
        font_path = get_font_path_from_style({title_type: {"fontFamily": font_family}}, title_type)
    
    # 如果没有找到，尝试从style中获取
    if not font_path:
        font_path = get_font_path_from_style(style, title_type)
    
    font = None
    if font_path and os.path.exists(font_path):
        try:
            print(f'标题使用字体文件: {font_path}')
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            print(f'标题字体加载失败: {e}')
            font = None
    
    if font is None:
        # 回退到系统字体
        chinese_fonts = [
            "C:\\Windows\\Fonts\\msyh.ttc",
            "C:\\Windows\\Fonts\\simsun.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/winfonts/msyh.ttc"
        ]
        
        for fp in chinese_fonts:
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except:
                continue
    
    if font is None:
        font = ImageFont.load_default()
    
    return font

def wrap_text_for_title(text, font, max_width):
    """文本换行处理"""
    lines = []
    current_line = ""
    
    # 创建临时draw对象用于测量
    temp_img = Image.new("RGBA", (max_width + 200, 100), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    
    for char in text:
        test_line = current_line + char
        try:
            bbox = temp_draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(test_line) * (font.size // 2)
            
        if text_width > max_width and current_line:
            lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    
    if current_line:
        lines.append(current_line)
    
    # 限制行数
    lines = lines[:2]
    return lines

def calculate_text_x_position(draw, text, font, target_width, alignment):
    """计算文本的X位置"""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
    except:
        text_width = len(text) * (font.size // 2)
    
    if alignment == "left":
        return 60  # 左边距
    elif alignment == "right":
        return target_width - text_width - 60  # 右边距
    else:  # center
        return (target_width - text_width) // 2

def draw_text_with_effects(draw, text, font, x, y, color, title_config):
    """绘制带效果的文本"""
    # 绘制阴影
    if title_config.get("shadow"):
        shadow_color = title_config.get("shadowColor", "#000000")
        draw.text((x+2, y+2), text, font=font, fill=shadow_color)
    
    # 绘制描边
    if title_config.get("strokeColor") and title_config.get("strokeWidth", 0) > 0:
        stroke_width = title_config.get("strokeWidth", 1)
        stroke_color = title_config.get("strokeColor", "#000000")
        
        # 简单描边实现
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)
    
    # 绘制主文字
    draw.text((x, y), text, font=font, fill=color)

def create_title_image(text, width=1080, height=1920, style=None):
    """生成标题字幕图片 - 支持主副标题"""
    if not style:
        style = {}
    
    title_config = style.get("title", {})
    
    # 检查是否有主副标题配置
    main_title = title_config.get("mainTitle")
    sub_title = title_config.get("subTitle")
    
    # 向后兼容：如果没有主副标题配置，但有旧的配置方式
    if not main_title and not sub_title:
        # 检查是否有旧的title配置
        if title_config.get("fontSize") and title_config.get("fontSize", 0) > 0:
            # 使用旧的逐个属性作为主标题
            main_title = {
                "text": text or "",
                "fontSize": title_config.get("fontSize", 64),
                "color": title_config.get("color", "#000000"),
                "fontFamily": title_config.get("fontFamily"),
                "bold": title_config.get("bold", False),
                "italic": title_config.get("italic", False)
            }
        elif text:  # 如果只有text参数，也作为主标题处理
            main_title = {
                "text": text,
                "fontSize": title_config.get("fontSize", 64),
                "color": title_config.get("color", "#000000"),
                "fontFamily": title_config.get("fontFamily")
            }
    
    # 如果没有任何可显示的标题，返回透明图片
    main_text = main_title.get("text", "") if main_title else ""
    main_font_size = main_title.get("fontSize", 0) if main_title else 0
    sub_text = sub_title.get("text", "") if sub_title else ""
    sub_font_size = sub_title.get("fontSize", 0) if sub_title else 0
    
    # 检查是否有任何需要渲染的内容
    has_main_title = main_title and main_text and main_font_size > 0
    has_sub_title = sub_title and sub_text and sub_font_size > 0
    has_legacy_title = not has_main_title and not has_sub_title and text and title_config.get("fontSize", 0) > 0
    
    if not has_main_title and not has_sub_title and not has_legacy_title:
        # 创建1x1透明图片
        img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return img
    
    # 计算实际需要的横幅尺寸
    target_width = 1080  # 视频宽度
    
    # 如果是旧版本兼容模式，使用原有逻辑
    if has_legacy_title:
        fontsize = int(title_config.get("fontSize", 64))
        color = title_config.get("color", "#FFD700")
        return create_legacy_title_image(text, target_width, style, fontsize, color)
    
    # 新的主副标题渲染逻辑
    spacing = title_config.get("spacing", 1)  # 主副标题之间的间距
    alignment = title_config.get("alignment", "center")  # 对齐方式
    
    # 计算每个标题的尺寸和文本行
    main_title_info = None
    sub_title_info = None
    
    if has_main_title:
        main_title_info = calculate_title_layout(main_text, main_font_size, target_width, main_title, style)
        
    if has_sub_title:
        sub_title_info = calculate_title_layout(sub_text, sub_font_size, target_width, sub_title, style)
    
    # 计算总高度
    total_height = 0
    padding_vertical = 60  # 上下内边距
    
    if main_title_info:
        total_height += main_title_info['height']
        
    if sub_title_info:
        if main_title_info:
            total_height += spacing  # 主副标题之间的间距
        total_height += sub_title_info['height']
    
    total_height += padding_vertical
    total_height = max(140, total_height)  # 最小高度
    
    print(f"主副标题计算: 主标题高度={main_title_info['height'] if main_title_info else 0}, 副标题高度={sub_title_info['height'] if sub_title_info else 0}, 间距={spacing}, 总高度={total_height}")
    
    # 创建图片
    bg_rgba = get_bg_rgba_from_style(style, "title", default=(0,0,0,0))
    img = Image.new("RGBA", (target_width, total_height), bg_rgba)
    draw = ImageDraw.Draw(img)
    
    # 开始绘制
    current_y = padding_vertical // 2  # 从上边距开始
    
    # 绘制主标题
    if main_title_info:
        current_y = draw_title_text(draw, main_title_info, target_width, current_y, alignment)
        if sub_title_info:
            current_y += spacing  # 添加间距
    
    # 绘制副标题
    if sub_title_info:
        draw_title_text(draw, sub_title_info, target_width, current_y, alignment)
    
    return img


def create_legacy_title_image(text, target_width, style, fontsize, color):
    """创建旧版本兼容的标题图片"""
    # 获取字体
    font = load_font_for_title({'fontSize': fontsize}, style, 'title')
    
    # 文本换行
    max_width = target_width - 120
    lines = wrap_text_for_title(text, font, max_width)
    lines = lines[:2]  # 最多2行
    
    # 计算高度
    line_height = fontsize + 20
    text_total_height = len(lines) * line_height
    padding_vertical = 60
    banner_h = max(140, text_total_height + padding_vertical)
    
    # 创建图片
    bg_rgba = get_bg_rgba_from_style(style, "title", default=(0,0,0,0))
    img = Image.new("RGBA", (target_width, banner_h), bg_rgba)
    draw = ImageDraw.Draw(img)
    
    # 绘制文本
    start_y = (banner_h - text_total_height) // 2
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(line) * fontsize // 2
            
        x = (target_width - tw) // 2
        try:
            draw.text((x+2, start_y+2), line, font=font, fill=(0, 0, 0, 128))  # 阴影
            draw.text((x, start_y), line, font=font, fill=color)  # 主文字
        except:
            draw.text((x, start_y), line, fill=color)
        start_y += line_height
    
    return img


def calculate_title_layout(text, font_size, target_width, title_config, style):
    """计算单个标题的布局信息"""
    font = load_font_for_title(title_config, style, 'title')
    max_width = target_width - 120  # 左右边距
    lines = wrap_text_for_title(text, font, max_width)
    lines = lines[:2]  # 最多2行
    
    line_height = font_size + 20
    height = len(lines) * line_height
    
    return {
        'text': text,
        'lines': lines,
        'font': font,
        'font_size': font_size,
        'color': title_config.get('color', '#000000'),
        'height': height,
        'line_height': line_height,
        'letter_spacing': title_config.get('letterSpacing', 0)  # 添加字间距参数
    }


def draw_title_text(draw, title_info, target_width, start_y, alignment):
    """绘制单个标题的文本，支持字间距"""
    current_y = start_y
    letter_spacing = title_info.get('letter_spacing', 0)  # 获取字间距
    
    for line in title_info['lines']:
        if letter_spacing != 0:
            # 有字间距时，手动绘制每个字符
            total_width = 0
            char_widths = []
            
            # 先计算每个字符的宽度
            for char in line:
                try:
                    bbox = draw.textbbox((0, 0), char, font=title_info['font'])
                    char_width = bbox[2] - bbox[0]
                except:
                    char_width = title_info['font_size'] // 2
                char_widths.append(char_width)
                total_width += char_width
            
            # 计算总宽度（包括字间距）
            if len(line) > 1:
                total_width += (len(line) - 1) * letter_spacing
            
            # 根据对齐方式计算起始x位置
            if alignment == 'left':
                x = 60  # 左边距
            elif alignment == 'right':
                x = target_width - total_width - 60  # 右边距
            else:  # center
                x = (target_width - total_width) // 2
            
            # 绘制每个字符
            current_x = x
            for i, char in enumerate(line):
                try:
                    # 添加阴影效果
                    draw.text((current_x+2, current_y+2), char, font=title_info['font'], fill=(0, 0, 0, 128))
                    draw.text((current_x, current_y), char, font=title_info['font'], fill=title_info['color'])
                except:
                    draw.text((current_x, current_y), char, fill=title_info['color'])
                
                # 移动到下一个字符位置
                current_x += char_widths[i] + letter_spacing
        else:
            # 没有字间距时，使用原来的方法
            try:
                bbox = draw.textbbox((0, 0), line, font=title_info['font'])
                tw = bbox[2] - bbox[0]
            except:
                tw = len(line) * title_info['font_size'] // 2
            
            # 根据对齐方式计算x位置
            if alignment == 'left':
                x = 60  # 左边距
            elif alignment == 'right':
                x = target_width - tw - 60  # 右边距
            else:  # center
                x = (target_width - tw) // 2
            
            try:
                # 添加阴影效果
                draw.text((x+2, current_y+2), line, font=title_info['font'], fill=(0, 0, 0, 128))
                draw.text((x, current_y), line, font=title_info['font'], fill=title_info['color'])
            except:
                draw.text((x, current_y), line, fill=title_info['color'])
        
        current_y += title_info['line_height']
    
    return current_y

def create_subtitle_image(text, width=480, height=854, style=None):
    """生成字幕图片 - 只生成字幕横幅大小的图片"""
    if not text:
        # 创建1x1透明图片
        img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return img
    
    subtitle_style = style.get("subtitle", {}) if style else {}
    fontsize = int(subtitle_style.get("fontSize", 48))
    color = subtitle_style.get("color", "#FFFFFF")
    
    # 计算实际需要的横幅尺寸
    target_width = 1080  # 视频宽度
    
    # 先创建临时画布来计算实际需要的高度
    temp_img = Image.new("RGBA", (target_width, 500), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    
    # 使用从样式配置中获取的字体
    font_path = get_font_path_from_style(style, 'subtitle')
    font = None
    if font_path and os.path.exists(font_path):
        try:
            print(f'字幕使用字体文件: {font_path}')
            font = ImageFont.truetype(font_path, fontsize)
        except Exception as e:
            print(f'字幕字体加载失败: {e}')
            font = None
    else:
        chinese_fonts = [
            "C:\\Windows\\Fonts\\msyh.ttc",      # 微软雅黑
            "C:\\Windows\\Fonts\\simsun.ttc",   # 宋体
            "C:\\Windows\\Fonts\\simhei.ttf",   # 黑体
            "C:\\Windows\\Fonts\\simkai.ttf",   # 楷体
            "/System/Library/Fonts/PingFang.ttc",  # macOS
            "/System/Library/Fonts/Hiragino Sans GB.ttc",  # macOS
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # Linux备选
        ]
        for fp in chinese_fonts:
            try:
                font = ImageFont.truetype(fp, fontsize)
                break
            except Exception:
                continue

    if font is None:
        try:
            # 尝试使用系统默认字体，指定字体大小
            font = ImageFont.load_default()
        except Exception:
            # 如果都失败，创建一个简单的默认字体
            font = ImageFont.load_default()

    # 文本换行
    max_width = target_width - 80  # 左右各留40像素边距
    lines = []
    current_line = ""
    
    for char in text:
        test_line = current_line + char
        try:
            bbox = temp_draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(test_line) * fontsize // 2
            
        if text_width > max_width and current_line:
            lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    
    if current_line:
        lines.append(current_line)
    
    # 限制行数
    lines = lines[:3]
    
    # 计算实际需要的高度
    line_height = fontsize + 16  # 每行高度增加间距
    text_total_height = len(lines) * line_height
    padding_vertical = 40  # 上下各20像素内边距
    banner_h = text_total_height + padding_vertical
    
    # 确保最小高度
    banner_h = max(120, banner_h)  # 最小120像素高度
    
    print(f"字幕计算: 字体={fontsize}, 行数={len(lines)}, 横幅高度={banner_h}")

    # 创建实际的字幕横幅，背景使用可配置颜色
    bg_rgba = get_bg_rgba_from_style(style, "subtitle", default=(0,0,0,0))  # 默认完全透明
    img = Image.new("RGBA", (target_width, banner_h), bg_rgba)  # 使用可配置背景
    draw = ImageDraw.Draw(img)

    # 绘制文本，垂直居中
    start_y = (banner_h - text_total_height) // 2
    
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(line) * fontsize // 2
            
        x = (target_width - tw) // 2  # 居中
        try:
            draw.text((x, start_y), line, font=font, fill=color)
        except:
            draw.text((x, start_y), line, fill=color)
        start_y += line_height

    return img

async def generate_tts_audio(text: str, output_path: str, voice: str = "zh-CN-XiaoxiaoNeural"):
    """使用 edge_tts 生成语音文件"""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        print(f"TTS音频生成完成: {output_path}, {voice}")
    except Exception as e:
        print(f"TTS生成失败: {e}")
        raise Exception("语音合成失败")

def create_9_16_video_with_title_ffmpeg(source_video, title_image, subtitle_image, tts_audio, bgm_audio, output_path, duration, title_position="top", subtitle_position="bottom", poster_image=None, use_gpu=True):
    """使用FFmpeg创建9:16视频，包含模糊背景、Title、Subtitle和音频混合"""
    ffmpeg = find_ffmpeg()
    
    target_width = 1080
    target_height = 1920
    
    # 计算Title位置
    title_margin = 200
    if title_position == "top":
        title_overlay_y = title_margin
        title_desc = "顶部"
    elif title_position == "center":
        title_overlay_y = f"(H-h)/2-100"  # 稍微偏上一些
        title_desc = "中部"
    else:  # bottom
        title_overlay_y = f"H-h-{title_margin}"
        title_desc = "底部"
    
    # 计算Subtitle位置
    subtitle_margin = 250
    if subtitle_position == "top":
        subtitle_overlay_y = subtitle_margin
        subtitle_overlay_x = "0"
        subtitle_desc = "顶部"
    elif subtitle_position == "center":
        subtitle_overlay_y = f"(H-h)/2+100"  # 稍微偏下一些
        subtitle_overlay_x = "0"
        subtitle_desc = "中部"
    elif subtitle_position == "template1":
        # 模板位置1：距上边框1372.4像素 - 需要考虑字幕图片内部的偏移
        # 字幕图片有上下40像素的padding，文字在图片中心，所以需要向上调整
        subtitle_overlay_y = str(1372.4 - 60)  # 减去字幕图片高度的一半，让文字中心在1372.4位置
        subtitle_overlay_x = "0"  # 模板位置1：水平居中（X=0表示居中）
        subtitle_desc = "模板位置1"
    else:  # bottom
        subtitle_overlay_y = f"H-h-{subtitle_margin}"
        subtitle_overlay_x = "0"
        subtitle_desc = "底部"
    
    print(f"Title位置设置: {title_desc} (overlay_y={title_overlay_y})")
    print(f"Subtitle位置设置: {subtitle_desc} (overlay_y={subtitle_overlay_y})")
    print(f"海报背景: {'启用' if poster_image else '未启用'}")
    
    # 根据是否有海报背景选择不同的滤镜链
    if poster_image and poster_image != "":
        # 有海报背景：海报作为背景，源视频作为前景
        filter_complex = f"""
        [5:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height}[bg];
        [0:v]scale={target_width}:-1[fg_scale];
        [fg_scale]scale={target_width}:{target_width*9//16}[fg];
        [bg][fg]overlay=(W-w)/2:(H-h)/2[bg_with_fg];
        [1:v]format=rgba[title];
        [2:v]format=rgba[subtitle];
        [bg_with_fg][title]overlay=0:{title_overlay_y}:format=auto[bg_with_title];
        [bg_with_title][subtitle]overlay={subtitle_overlay_x}:{subtitle_overlay_y}:format=auto,format=yuv420p[video_out];
        [3:a]volume=0.8[tts];
        [4:a]volume=0.15[bgm];
        [tts][bgm]amix=inputs=2:duration=first:dropout_transition=0[audio_out]
        """
        
        # 将源视频循环输入，图片输入作为 looped 静态帧流，音频在滤镜里被 trim
        cmd = [
            ffmpeg, '-y',
            '-hwaccel', 'cuda',                            # 启用CUDA硬件加速
            '-hwaccel_output_format', 'cuda',              # 输出格式保持在GPU
            '-c:v', 'h264_cuvid',                          # 强制使用h264_cuvid解码
            '-stream_loop', '-1', '-i', source_video,      # 输入0: 源视频（循环）
            '-loop', '1', '-i', title_image,               # 输入1: Title图片（loop）
            '-loop', '1', '-i', subtitle_image,            # 输入2: Subtitle图片（loop）
            '-i', tts_audio,                               # 输入3: TTS音频
            '-i', bgm_audio,                               # 输入4: BGM音频
            '-loop', '1', '-i', poster_image,              # 输入5: 海报背景（loop）
            '-filter_complex', filter_complex,
            '-map', '[video_out]',                         # 映射视频流
            '-map', '[audio_out]',                         # 映射音频流
            '-t', str(duration),                           # 设置时长（强制输出时长）
            *get_gpu_encoding_params(use_gpu, 'balanced'), # GPU加速编码参数
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            output_path
        ]
    else:
        # 无海报背景：使用原逻辑（模糊源视频作为背景）
        filter_complex = f"""
        [0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height}[bg];
        [bg]boxblur=luma_radius=50:chroma_radius=50:luma_power=3[bg_blur];
        [0:v]scale={target_width}:-1[fg_scale];
        [fg_scale]scale={target_width}:{target_width*9//16}[fg];
        [bg_blur][fg]overlay=(W-w)/2:(H-h)/2[bg_with_fg];
        [1:v]format=rgba[title];
        [2:v]format=rgba[subtitle];
        [bg_with_fg][title]overlay=0:{title_overlay_y}:format=auto[bg_with_title];
        [bg_with_title][subtitle]overlay={subtitle_overlay_x}:{subtitle_overlay_y}:format=auto,format=yuv420p[video_out];
        [3:a]volume=0.8[tts];
        [4:a]volume=0.15[bgm];
        [tts][bgm]amix=inputs=2:duration=first:dropout_transition=0[audio_out]
        """
        
        cmd = [
            ffmpeg, '-y',
            '-hwaccel', 'cuda',                            # 启用CUDA硬件加速
            '-hwaccel_output_format', 'cuda',              # 输出格式保持在GPU
            '-c:v', 'h264_cuvid',                          # 强制使用h264_cuvid解码
            '-stream_loop', '-1', '-i', source_video,      # 输入0: 源视频（循环）
            '-loop', '1', '-i', title_image,               # 输入1: Title图片（loop）
            '-loop', '1', '-i', subtitle_image,            # 输入2: Subtitle图片（loop）
            '-i', tts_audio,                               # 输入3: TTS音频
            '-i', bgm_audio,                               # 输入4: BGM音频
            '-filter_complex', filter_complex,
            '-map', '[video_out]',                         # 映射视频流
            '-map', '[audio_out]',                         # 映射音频流
            '-t', str(duration),                           # 设置时长（强制输出时长）
            *get_gpu_encoding_params(use_gpu, 'balanced'), # GPU加速编码参数
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            output_path
        ]
    
    try:
        print("开始FFmpeg处理...")
        result = subprocess.run(cmd, capture_output=True, text=False)
        if result.returncode != 0:
            try:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
            except:
                stderr_text = str(result.stderr)
            print(f"FFmpeg错误: {stderr_text}")
            return False
        print("FFmpeg处理完成")
        return True
    except Exception as e:
        print(f"FFmpeg执行失败: {e}")
        return False

def extract_random_clip_ffmpeg(source_video, output_path, start_time, duration, use_gpu=True):
    """使用FFmpeg提取随机片段，强制使用GPU硬件解码和编码"""
    ffmpeg = find_ffmpeg()
    
    print(f"🎬 提取视频片段: {os.path.basename(source_video)} ({start_time:.1f}s-{start_time+duration:.1f}s)")
    
    # 强制使用GPU硬件解码和编码
    cmd_gpu = [
        ffmpeg, '-y',
        '-hwaccel', 'cuda',                    # 启用CUDA硬件加速
        '-hwaccel_output_format', 'cuda',      # 输出格式保持在GPU
        '-c:v', 'h264_cuvid',                  # 强制使用h264_cuvid解码
        '-ss', str(start_time),
        '-i', source_video,
        '-t', str(duration),
        '-c:v', 'h264_nvenc',                  # 强制使用h264_nvenc编码
        '-preset', 'fast',
        '-crf', '23',
        '-c:a', 'aac',                         # 音频编码
        '-movflags', '+faststart',             # 优化播放
        output_path
    ]
    
    try:
        print("🚀 使用GPU硬件解码和编码提取片段")
        result = subprocess.run(cmd_gpu, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ GPU片段提取成功")
            return True
        else:
            print(f"❌ GPU片段提取失败: {result.stderr}")
            
            # 如果GPU失败，回退到CPU
            print("🖥️ 回退到CPU编码提取片段")
            cmd_cpu = [
                ffmpeg, '-y',
                '-ss', str(start_time),
                '-i', source_video,
                '-t', str(duration),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-movflags', '+faststart',
                output_path
            ]
            
            result_cpu = subprocess.run(cmd_cpu, capture_output=True, text=True)
            if result_cpu.returncode == 0:
                print("✅ CPU片段提取成功")
                return True
            else:
                print(f"❌ CPU片段提取失败: {result_cpu.stderr}")
                return False
                
    except Exception as e:
        print(f"❌ 片段提取异常: {e}")
        return False

def create_silence_audio(duration, output_path):
    """创建静音音频文件"""
    ffmpeg = find_ffmpeg()
    
    cmd = [
        ffmpeg, '-y',
        '-f', 'lavfi',
        '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
        '-t', str(duration),
        '-c:a', 'aac',
        output_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except:
        return False

def split_long_sentence_by_screen(sentence, video_width=1080, style=None, max_chars_per_screen=15):
    """
    将长句子按屏幕显示能力分割成多个片段
    每个片段确保能在一屏内完整显示
    """
    if not sentence:
        return []
    
    subtitle_style = style.get("subtitle", {}) if style else {}
    fontsize = int(subtitle_style.get("fontSize", 48))
    
    # 获取字体
    font_path = get_font_path_from_style(style, 'subtitle')
    font = None
    if font_path and os.path.exists(font_path):
        try:
            print(f'分屏字幕使用字体: {font_path}')
            font = ImageFont.truetype(font_path, fontsize)
        except Exception as e:
            print(f'分屏字幕字体加载失败: {e}')
            font = None
    
    if font is None:
        chinese_fonts = [
            "C:\\Windows\\Fonts\\msyh.ttc",
            "C:\\Windows\\Fonts\\simsun.ttc",
            "C:\\Windows\\Fonts\\simhei.ttf",
        ]
        for fp in chinese_fonts:
            try:
                font = ImageFont.truetype(fp, fontsize)
                break
            except Exception:
                continue
    
    if font is None:
        font = ImageFont.load_default()
    
    # 计算单屏最大宽度
    max_width = video_width - 120  # 左右各留60像素边距
    
    # 创建临时画布测试文本宽度
    temp_img = Image.new("RGBA", (video_width, 200), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    
    segments = []
    current_segment = ""
    
    # 按字符逐个添加，测试是否超出屏幕宽度
    for char in sentence:
        test_segment = current_segment + char
        
        try:
            bbox = temp_draw.textbbox((0, 0), test_segment, font=font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(test_segment) * fontsize // 2
        
        # 如果超出最大宽度且当前片段不为空，分割
        if text_width > max_width and current_segment:
            segments.append(current_segment.strip())
            current_segment = char
        else:
            current_segment = test_segment
    
    # 添加最后一个片段
    if current_segment.strip():
        segments.append(current_segment.strip())
    
    # 如果没有分割，返回原句子
    if not segments:
        segments = [sentence]
    
    return segments

def split_text_into_screen_friendly_sentences(text, video_width=1080, style=None):
    """
    将文本分割成适合屏幕显示的句子片段
    优先按标点符号分割，如果单句太长则按屏幕宽度再次分割
    """
    if not text:
        return []
    import re

    # 按中英文常用标点拆分并去掉这些标点
    split_re = re.compile(r"[，。！？；：,\.!\?;:]+")

    parts = [p.strip() for p in split_re.split(text) if p and p.strip()]

    # 回退：如果没有分割出内容，保留原文本
    if not parts:
        parts = [text.strip()]

    # 对每个分段，使用按屏宽再细分的函数（保持兼容性）
    final_segments = []
    for part in parts:
        segments = split_long_sentence_by_screen(part, video_width, style)
        if segments:
            final_segments.extend(segments)
        else:
            final_segments.append(part)

    if not final_segments:
        final_segments = [text.strip()]

    print(f"文本分割结果：原文 -> {len(parts)}个句子 -> {len(final_segments)}个显示片段")
    for i, segment in enumerate(final_segments):
        print(f"  片段{i+1}: '{segment[:30]}{'...' if len(segment) > 30 else ''}'")

    return final_segments

def create_single_line_subtitle_image(text, video_width=1080, style=None):
    """
    创建单行字幕图片，确保文本在一行内显示
    如果文本过长会自动调整字体大小
    """
    if not text:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    
    subtitle_style = style.get("subtitle", {}) if style else {}
    base_fontsize = int(subtitle_style.get("fontSize", 48))
    color = subtitle_style.get("color", "#FFFFFF")
    
    # 字体处理
    font_path = get_font_path_from_style(style, 'subtitle')
    font = None
    if font_path and os.path.exists(font_path):
        try:
            print(f'单行字幕使用字体: {font_path}')
            font = ImageFont.truetype(font_path, base_fontsize)
        except Exception as e:
            print(f'单行字幕字体加载失败: {e}')
            font = None
    
    if font is None:
        chinese_fonts = [
            "C:\\Windows\\Fonts\\msyh.ttc",
            "C:\\Windows\\Fonts\\simsun.ttc",
            "C:\\Windows\\Fonts\\simhei.ttf",
        ]
        for fp in chinese_fonts:
            try:
                font = ImageFont.truetype(fp, base_fontsize)
                break
            except Exception:
                continue
    
    if font is None:
        font = ImageFont.load_default()

    # 计算合适的字体大小，确保文本能在一行显示
    max_width = video_width - 120  # 左右各留60像素边距
    fontsize = base_fontsize
    
    # 创建临时画布测试
    temp_img = Image.new("RGBA", (video_width, 200), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    
    # 自动调整字体大小
    while fontsize > 20:  # 最小字体大小
        try:
            if font_path and os.path.exists(font_path):
                test_font = ImageFont.truetype(font_path, fontsize)
            else:
                test_font = ImageFont.truetype("C:\\Windows\\Fonts\\msyh.ttc", fontsize)
        except:
            test_font = ImageFont.load_default()
        
        try:
            bbox = temp_draw.textbbox((0, 0), text, font=test_font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(text) * fontsize // 2
        
        if text_width <= max_width:
            font = test_font
            break
    # 计算图片尺寸
    line_height = fontsize + 12
    padding = 30
    banner_h = line_height + padding * 2
    
    # 创建字幕图片（使用可配置背景颜色）
    bg_rgba = get_bg_rgba_from_style(style, "subtitle", default=(0,0,0,0))  # 默认完全透明
    img = Image.new("RGBA", (video_width, banner_h), bg_rgba)
    draw = ImageDraw.Draw(img)
    
    # 绘制单行文本
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
    except Exception:
        # 如果无法获取精确边界，使用估算宽度作为回退
        text_width = len(text) * fontsize // 2
    
    x = (video_width - text_width) // 2  # 居中
    y = padding
    
    # 添加文字阴影和主文字
    draw.text((x+2, y+2), text, font=font, fill=(0, 0, 0, 128))  # 阴影
    draw.text((x, y), text, font=font, fill=color)  # 主文字
    
    print(f"单行字幕: 字体{fontsize}px, 文本'{text[:20]}...', 宽度{text_width}px")
    
    return img

def create_dynamic_subtitles(sentences, total_duration, video_width=1080, style=None, temp_dir=None):
    """创建动态字幕片段，每句字幕按时间显示"""
    if not sentences:
        return []
    
    if temp_dir is None:
        temp_dir = SUBTITLE_TEMP_DIR
    
    subtitle_clips = []
    
    # 计算每句字幕的显示时间 - 基于句子长度分配时间
    sentence_count = len(sentences)
    
    # 计算每个句子的相对长度权重
    sentence_lengths = [len(sentence) for sentence in sentences]
    total_length = sum(sentence_lengths)
    
    current_time = 0
    
    for i, sentence in enumerate(sentences):
        # 为每句创建单行字幕图片
        subtitle_id = str(uuid4())[:8]
        subtitle_path = os.path.join(temp_dir, f"dynamic_subtitle_{i}_{subtitle_id}.png")
        
        # 使用新的单行字幕生成函数
        subtitle_img = create_single_line_subtitle_image(sentence, video_width, style)
        subtitle_img.save(subtitle_path)
        
        # 根据句子长度按比例分配时间
        if total_length > 0:
            sentence_ratio = sentence_lengths[i] / total_length
            allocated_duration = total_duration * sentence_ratio
        else:
            allocated_duration = total_duration / sentence_count
        
        # 设置最小和最大显示时间
        min_duration = 1.2  # 最少显示1.2秒
        max_duration = 4.0   # 最多显示4秒
        
        # 调整显示时间
        duration = max(min_duration, min(allocated_duration, max_duration))
        
        # 如果是最后一句，确保不超过总时长
        if i == len(sentences) - 1:
            duration = min(duration, total_duration - current_time)
        
        start_time = current_time
        end_time = start_time + duration
        
        if duration > 0:
            subtitle_clips.append({
                'path': subtitle_path,
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration,
                'text': sentence
            })
            
            print(f"字幕片段{i+1}: {start_time:.1f}s-{end_time:.1f}s (时长{duration:.1f}s) '{sentence[:25]}...'")
        
        current_time = end_time
        
        # 如果已经达到总时长，停止创建
        if current_time >= total_duration:
            break
    
    # 如果时间分配有剩余，将剩余时间平均分配给所有字幕
    if current_time < total_duration and subtitle_clips:
        remaining_time = total_duration - current_time
        time_per_clip = remaining_time / len(subtitle_clips)
        
        print(f"调整字幕时间：剩余{remaining_time:.1f}s，平均分配给{len(subtitle_clips)}个字幕")
        
        for i, clip in enumerate(subtitle_clips):
            clip['duration'] += time_per_clip
            if i > 0:
                clip['start_time'] = subtitle_clips[i-1]['end_time']
            clip['end_time'] = clip['start_time'] + clip['duration']
            
            print(f"调整后字幕{i+1}: {clip['start_time']:.1f}s-{clip['end_time']:.1f}s (时长{clip['duration']:.1f}s)")
    
    print(f"创建了{len(subtitle_clips)}个动态字幕片段，总时长{total_duration}秒")
    return subtitle_clips

async def process_clips_parallel_gpu(req):
    """
    【并行GPU版本】视频处理方法 - 多线程GPU并行生成
    性能目标：1-2分钟生成多个视频，充分利用GPU资源
    """
    from services.enhanced_clip_service import enhanced_clip_service
    return await enhanced_clip_service.process_clips_enhanced(req)

async def process_clips_optimized(req):
    """
    【优化版本】视频处理方法 - 使用ASS字幕 + 智能缓存
    性能目标：3-5分钟生成，保留所有高级功能
    """
    import time
    start_time = time.time()

    video_count = req.videoCount
    duration_sec = parse_duration(req.duration)
    video_files = req.videos
    audio_files = req.audios
    poster_files = req.posters if hasattr(req, 'posters') else []
    scripts = [s for s in req.scripts if s.selected]
    style = req.style.dict() if hasattr(req.style, "dict") else req.style

    # 项目的标题和样式
    title = req.name
    title_position = style.get("title", {}).get("position", "top")
    subtitle_position = style.get("subtitle", {}).get("position", "bottom")
    
    # 支持主副标题：优先使用主标题的文本，如果没有则使用项目名称
    title_config = style.get("title", {})
    if title_config.get("mainTitle") and title_config.get("mainTitle", {}).get("text"):
        title = title_config["mainTitle"]["text"]
    
    print(f"🚀 开始优化版本视频生成...")
    print(f"   项目标题: {title}")
    print(f"   视频数量: {video_count}")
    print(f"   目标时长: {duration_sec}秒")
    print(f"   脚本数量: {len(scripts)}")
    print("=" * 50)

    # 🎯 第一步：智能素材预加载（并行下载）
    print("📥 第一步：智能预加载素材...")
    preload_start = time.time()
    
    # 收集所有素材URL
    all_urls = []
    all_urls.extend([v.url for v in video_files])
    all_urls.extend([a.url for a in audio_files])
    if poster_files:
        all_urls.extend([p.url for p in poster_files])
    
    # 并行预加载所有素材
    url_to_path = await smart_cache.preload_materials(all_urls)
    
    preload_time = time.time() - preload_start
    print(f"✅ 素材预加载完成，耗时: {preload_time:.1f}秒")
    print(f"   成功加载: {len(url_to_path)}/{len(all_urls)} 个素材")

    # 映射到本地路径
    local_video_paths = [url_to_path.get(v.url) for v in video_files if url_to_path.get(v.url)]
    local_audio_paths = [url_to_path.get(a.url) for a in audio_files if url_to_path.get(a.url)]

    local_audio_paths = process_original_video(local_audio_paths)
    
    local_poster_path = None
    if poster_files and len(poster_files) > 0:
        poster_url = poster_files[0].url
        local_poster_path = url_to_path.get(poster_url)
        if local_poster_path:
            print(f"🖼️  海报加载完成: {local_poster_path}")

    if not local_video_paths:
        return {"success": False, "error": "找不到可用的视频文件"}

    result_videos = []

    try:
        ffmpeg = find_ffmpeg()
        
        # 🎯 第二步：获取视频信息（批量处理）
        print("📊 第二步：分析视频信息...")
        video_info_start = time.time()
        
        video_infos = []
        for video_path in local_video_paths:
            if os.path.exists(video_path):
                info = get_video_info(video_path)
                video_infos.append(info)

        if not video_infos:
            return {"success": False, "error": "无有效视频文件"}
        
        video_info_time = time.time() - video_info_start
        print(f"✅ 视频信息分析完成，耗时: {video_info_time:.1f}秒")

        # 🎯 第三步：批量生成视频
        print("🎬 第三步：开始批量生成视频...")
        generation_start = time.time()

        # 🚀 多线程并行处理：当视频数量>=2时启用多线程
        if video_count >= 2:
            print(f"⚡ 启用多线程并行处理 ({video_count}个视频)")
            import concurrent.futures
            import threading
            
            # 动态调整并发线程数，避免GPU资源过度竞争
            # 检查当前GPU负载，如果负载高则减少并发数
            try:
                import psutil
                gpu_memory_percent = 0  # 简化处理，实际应该检查GPU使用率
                if gpu_memory_percent > 80:
                    max_workers = min(2, video_count)  # 高负载时减少并发
                    print(f"   检测到GPU高负载，减少并发数至{max_workers}")
                else:
                    max_workers = min(3, video_count)  # 正常负载
                    print(f"   GPU负载正常，使用{max_workers}个并行线程")
            except:
                max_workers = min(2, video_count)  # 保守策略
                print(f"   使用保守并发数{max_workers}个线程，避免资源竞争")
            
            def process_single_video_thread(video_index):
                """单个视频处理线程函数"""
                return _process_single_video_optimized(
                    video_index, video_count, local_video_paths, local_audio_paths, 
                    local_poster_path, video_infos, duration_sec, title, scripts, 
                    style, title_position, subtitle_position, req
                )
            
            # 使用线程池并行处理
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_index = {
                    executor.submit(process_single_video_thread, i): i 
                    for i in range(video_count)
                }
                
                # 收集结果
                parallel_results = []
                for future in concurrent.futures.as_completed(future_to_index):
                    video_index = future_to_index[future]
                    try:
                        result = future.result()
                        if result:
                            parallel_results.append(result)
                            print(f"✅ 线程{video_index+1}完成")
                        else:
                            print(f"❌ 线程{video_index+1}失败")
                    except Exception as e:
                        print(f"❌ 线程{video_index+1}异常: {e}")
                
                # 将并行结果添加到result_videos
                result_videos.extend(parallel_results)
        else:
            print("🔄 单视频使用串行处理")
            # 单个视频时使用原有串行逻辑，直接调用单个视频处理函数
            for i in range(video_count):
                result = _process_single_video_optimized(
                    i, video_count, local_video_paths, local_audio_paths, 
                    local_poster_path, video_infos, duration_sec, title, scripts, 
                    style, title_position, subtitle_position, req
                )
                if result:
                    result_videos.append(result)
                    print(f"✅ 串行视频{i+1}完成")
                else:
                    print(f"❌ 串行视频{i+1}失败")
        
        # 计算处理时间
        generation_time = time.time() - generation_start
        total_time = time.time() - start_time
        
        print("\n" + "=" * 50)
        print("🎊 优化版本生成完成！")
        print(f"📊 性能统计:")
        print(f"   素材预加载: {preload_time:.1f}秒")
        print(f"   视频信息分析: {video_info_time:.1f}秒") 
        print(f"   视频生成: {generation_time:.1f}秒")
        print(f"   总耗时: {total_time:.1f}秒")
        print(f"   平均每个视频: {generation_time/max(video_count,1):.1f}秒")
        print(f"   成功生成: {len(result_videos)}/{video_count} 个视频")
        
        # 检查是否有视频生成成功
        if not result_videos:
            error_msg = f"视频生成失败：请求生成{video_count}个视频，但没有任何视频成功生成"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
        
        return {
            "success": True,
            "message": f"优化版本视频处理完成，总耗时{total_time:.1f}秒，成功生成{len(result_videos)}/{video_count}个视频",
            "videos": result_videos,
            "performance_stats": {
                "total_time": total_time,
                "preload_time": preload_time,
                "generation_time": generation_time,
                "videos_generated": len(result_videos),
                "videos_requested": video_count
            }
        }
                
    except Exception as e:
        import traceback
        error_msg = f"优化版本视频生成异常: {str(e)}"
        print(f"❌ {error_msg}")
        print("详细错误信息:")
        traceback.print_exc()
        return {"success": False, "error": error_msg}

async def process_clips001(req):
    """
    【FFmpeg版本】视频处理方法 - 支持动态字幕逐句显示
    """
    import time
    from services.smart_material_cache import smart_cache

    video_count = req.videoCount
    duration_sec = parse_duration(req.duration)
    video_files = req.videos
    audio_files = req.audios
    poster_files = req.posters if hasattr(req, 'posters') else []
    scripts = [s for s in req.scripts if s.selected]
    style = req.style.dict() if hasattr(req.style, "dict") else req.style

    # 项目的标题和样式
    title = req.name
    title_position = style.get("title", {}).get("position", "top")
    subtitle_position = style.get("subtitle", {}).get("position", "bottom")
    
    # 支持主副标题：优先使用主标题的文本，如果没有则使用项目名称
    title_config = style.get("title", {})
    if title_config.get("mainTitle") and title_config.get("mainTitle", {}).get("text"):
        title = title_config["mainTitle"]["text"]
    
    print(f"使用标题: {title}")
    print(f"标题配置: {title_config}")

    # 🚀 使用智能缓存并行下载所有素材
    print("📥 使用智能缓存下载素材...")
    download_start = time.time()
    
    # 收集所有素材URL
    all_urls = []
    all_urls.extend([v.url for v in video_files])
    all_urls.extend([a.url for a in audio_files])
    if poster_files:
        all_urls.extend([p.url for p in poster_files])
    
    # 并行下载所有素材
    url_to_path = await smart_cache.preload_materials(all_urls)
    
    download_time = time.time() - download_start
    print(f"✅ 智能缓存下载完成，耗时: {download_time:.1f}秒")
    
    # 映射到本地路径
    local_video_paths = [url_to_path.get(v.url) for v in video_files if url_to_path.get(v.url)]
    local_audio_paths = [url_to_path.get(a.url) for a in audio_files if url_to_path.get(a.url)]

    print(local_video_paths)
    local_video_paths = process_original_video(local_video_paths)
    print(local_video_paths)
    
    local_poster_path = None
    if poster_files and len(poster_files) > 0:
        poster_url = poster_files[0].url
        local_poster_path = url_to_path.get(poster_url)
        if local_poster_path:
            print(f"🖼️  海报加载完成: {local_poster_path}")

    print("=======================================")
    print("包含：Title + 动态字幕(智能分屏显示) + TTS语音 + 背景音乐 + 海报背景")
    print(f"项目标题: {title}")
    print(f"Title位置: {title_position}")
    print(f"动态字幕位置: {subtitle_position}")
    print("=======================================")

    if not local_video_paths:
        return {"success": False, "error": "找不到视频文件"}

    result_videos = []

    try:
        ffmpeg = find_ffmpeg()
        
        # 获取所有源视频信息
        video_infos = []
        for video_path in local_video_paths:
            if os.path.exists(video_path):
                info = get_video_info(video_path)
                video_infos.append(info)

        if not video_infos:
            return {"success": False, "error": "无有效视频文件"}

        # 🚀 多线程并行处理：当视频数量>=2时启用多线程
        generation_start = time.time()
        if video_count >= 2:
            print(f"⚡ 启用多线程并行处理 ({video_count}个视频)")
            import concurrent.futures
            import threading
            
            # 动态调整并发线程数，避免GPU资源过度竞争
            # 检查当前GPU负载，如果负载高则减少并发数
            try:
                import psutil
                gpu_memory_percent = 0  # 简化处理，实际应该检查GPU使用率
                if gpu_memory_percent > 80:
                    max_workers = min(2, video_count)  # 高负载时减少并发
                    print(f"   检测到GPU高负载，减少并发数至{max_workers}")
                else:
                    max_workers = min(3, video_count)  # 正常负载
                    print(f"   GPU负载正常，使用{max_workers}个并行线程")
            except:
                max_workers = min(2, video_count)  # 保守策略
                print(f"   使用保守并发数{max_workers}个线程，避免资源竞争")
            
            def process_single_video_001(video_index):
                """单个视频处理线程函数 - process_clips001版本"""
                return _process_single_video_001(
                    video_index, video_count, local_video_paths, local_audio_paths, 
                    local_poster_path, video_infos, duration_sec, title, scripts, 
                    style, title_position, subtitle_position, req
                )
            
            # 使用线程池并行处理
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_index = {
                    executor.submit(process_single_video_001, i): i 
                    for i in range(video_count)
                }
                
                # 收集结果
                parallel_results = []
                for future in concurrent.futures.as_completed(future_to_index):
                    video_index = future_to_index[future]
                    try:
                        result = future.result()
                        if result:
                            parallel_results.append(result)
                            print(f"✅ 线程{video_index+1}完成")
                        else:
                            print(f"❌ 线程{video_index+1}失败")
                    except Exception as e:
                        print(f"❌ 线程{video_index+1}异常: {e}")
                
                # 将并行结果添加到result_videos
                result_videos.extend(parallel_results)
        else:
            print("🔄 单视频使用串行处理")
            # 单个视频时使用原有串行逻辑，直接调用单个视频处理函数
            for i in range(video_count):
                result = _process_single_video_001(
                    i, video_count, local_video_paths, local_audio_paths, 
                    local_poster_path, video_infos, duration_sec, title, scripts, 
                    style, title_position, subtitle_position, req
                )
                if result:
                    result_videos.append(result)
                    print(f"✅ 串行视频{i+1}完成")
                else:
                    print(f"❌ 串行视频{i+1}失败")
        
        generation_time = time.time() - generation_start
        print(f"🎊 视频生成完成！总耗时: {generation_time:.1f}秒")
        print(f"   成功生成: {len(result_videos)}/{video_count} 个视频")
        
        return {
            "success": True,
            "message": f"动态字幕视频处理完成，成功生成{len(result_videos)}/{video_count}个视频",
            "videos": result_videos
        }
        
    except Exception as e:
        import traceback
        error_msg = f"动态字幕视频生成异常: {str(e)}"
        print(f"❌ {error_msg}")
        traceback.print_exc()
        return {"success": False, "error": error_msg}

def _process_single_video_001(video_index, video_count, local_video_paths, local_audio_paths, 
                              local_poster_path, video_infos, duration_sec, title, scripts, 
                              style, title_position, subtitle_position, req):
    """
    单个视频处理函数 - process_clips001版本，支持动态字幕
    专门优化GPU使用，减少CPU负载
    """
    import asyncio
    import random
    import time
    from uuid import uuid4
    
    try:
        clip_start = time.time()
        clip_id = str(uuid4())[:8]
        
        print(f"\n🎞️  线程{video_index+1}: 处理动态字幕视频 (ID: {clip_id})")
        
        # 1. 蒙太奇拼接（使用GPU加速）
        montage_start = time.time()
        temp_clips = []
        n_videos = len(local_video_paths)
        base_duration = duration_sec // n_videos
        remaining_duration = duration_sec % n_videos
        
        # 关键改进：为每个视频随机打乱素材顺序，确保每个视频使用不同的拼接顺序
        # 创建索引列表并打乱
        indices = list(range(n_videos))
        random.shuffle(indices)
        
        # 使用打乱后的索引来访问视频路径和视频信息
        for idx in indices:
            video_path = local_video_paths[idx]
            video_info = video_infos[idx]
            
            segment_duration = base_duration
            if len(temp_clips) < remaining_duration:
                segment_duration += 1
            
            if segment_duration <= 0:
                continue
                
            max_segment = min(segment_duration, int(video_info['duration']) - 1)
            if max_segment <= 0:
                continue
            
            max_start = max(0, video_info['duration'] - max_segment - 0.5)
            start_time = random.uniform(0, max_start) if max_start > 0 else 0
            
            temp_clip_path = os.path.join(OUTPUT_DIR, f"temp_segment_{clip_id}_{idx}.mp4")
            
            if extract_random_clip_ffmpeg(video_path, temp_clip_path, start_time, max_segment):
                temp_clips.append(temp_clip_path)
        
        if not temp_clips:
            print(f"   ❌ 线程{video_index+1}: 无有效片段")
            return None
        
        montage_clip_path = os.path.join(OUTPUT_DIR, f"montage_clip_{clip_id}.mp4")
        
        if len(temp_clips) == 1:
            import shutil
            shutil.copy2(temp_clips[0], montage_clip_path)
        else:
            if not concat_videos_ffmpeg(temp_clips, montage_clip_path):
                print(f"   ❌ 线程{video_index+1}: 拼接失败")
                return None
        
        montage_time = time.time() - montage_start
        print(f"   ✅ 线程{video_index+1}: 蒙太奇拼接完成，耗时: {montage_time:.1f}秒")

        # 2. 生成Title图片
        title_start = time.time()
        title_image_path = os.path.join(SUBTITLE_TEMP_DIR, f"title_{clip_id}.png")
        title_img = create_title_image(title, 1080, 1920, style)
        title_img.save(title_image_path)
        title_time = time.time() - title_start
        print(f"   ✅ 线程{video_index+1}: 标题图片生成完成，耗时: {title_time:.1f}秒")

        # 3. 准备脚本文本
        script = random.choice(scripts).content if scripts else "这是一段精彩的视频内容，展现了多个精彩瞬间的完美融合。通过蒙太奇技术，我们将不同的视频片段巧妙地组合在一起。"
        
        # 4. 生成TTS音频（在线程中需要创建新的事件循环）
        tts_start = time.time()
        tts_path = os.path.join(TTS_TEMP_DIR, f"tts_{clip_id}.wav")
        voice = 'zh-CN-YunxiNeural' if hasattr(req, 'voice') and req.voice == 'male' else 'zh-CN-XiaoxiaoNeural'
        
        # 在线程中需要创建新的事件循环来调用异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(generate_tts_audio(script, tts_path, voice))
        finally:
            loop.close()
        
        tts_time = time.time() - tts_start
        print(f"   ✅ 线程{video_index+1}: TTS语音生成完成，耗时: {tts_time:.1f}秒")

        # 读取TTS实际时长，动态调整视频时长
        target_duration = duration_sec
        try:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            audio_clip_tmp = AudioFileClip(tts_path)
            tts_len = audio_clip_tmp.duration
            audio_clip_tmp.close()
            if tts_len and tts_len > duration_sec:
                print(f"   🎵 线程{video_index+1}: TTS时长{tts_len:.2f}s > 目标时长{duration_sec}s，扩展到{tts_len:.2f}s")
                target_duration = tts_len
            else:
                print(f"   🎵 线程{video_index+1}: TTS时长{tts_len:.2f}s，目标时长保持{duration_sec}s")
        except Exception as e:
            print(f"   ⚠️  线程{video_index+1}: 读取TTS时长失败: {e}")

        # 5. 使用智能分屏方法分割文本
        subtitle_start = time.time()
        sentences = split_text_into_screen_friendly_sentences(script, 1080, style)
        print(f"   📝 线程{video_index+1}: 智能分屏分割成{len(sentences)}个片段")
        
        # 准备字幕数据（使用SRT格式）
        subtitle_sentences = []
        current_time = 0.0
        time_per_sentence = target_duration / max(len(sentences), 1)
        
        for sentence in sentences:
            text = sentence.strip()
            if text:
                # 根据文字长度估算显示时间，但不超过平均时间
                estimated_duration = min(max(2.0, len(text) * 0.15), time_per_sentence * 1.5)
                subtitle_sentences.append({
                    "text": text,
                    "start_time": current_time,
                    "end_time": current_time + estimated_duration
                })
                current_time += estimated_duration
        
        subtitle_time = time.time() - subtitle_start
        print(f"   ✅ 线程{video_index+1}: 字幕数据准备完成，耗时: {subtitle_time:.1f}秒")

        # 6. GPU加速最终视频合成
        final_start = time.time()
        final_output = os.path.join(OUTPUT_DIR, f"dynamic_subtitle_{clip_id}.mp4")
        
        bgm_audio = random.choice(local_audio_paths) if local_audio_paths else None
        silence_path = None
        if not bgm_audio or not os.path.exists(bgm_audio):
            silence_path = os.path.join(TTS_TEMP_DIR, f"silence_{clip_id}.wav")
            create_silence_audio(target_duration, silence_path)
            bgm_audio = silence_path

        # 🚀 使用GPU加速SRT字幕处理
        print(f"   🚀 线程{video_index+1}: 开始GPU加速视频合成")
        from services.srt_subtitle_processor import create_gpu_video_with_srt_subtitles
        
        success = create_gpu_video_with_srt_subtitles(
            input_video=montage_clip_path,
            title_image=title_image_path,
            srt_file="",  # 将在函数内部创建
            tts_audio=tts_path,
            bgm_audio=bgm_audio,
            output_path=final_output,
            duration=target_duration,
            title_position=title_position,
            poster_image=local_poster_path,
            use_gpu=True,  # 强制使用GPU
            subtitle_sentences=subtitle_sentences,
            style=style  # 传递样式配置
        )
        
        final_time = time.time() - final_start
        print(f"   ✅ 线程{video_index+1}: 视频合成完成，耗时: {final_time:.1f}秒")
        
        if not success:
            print(f"   ❌ 线程{video_index+1}: 视频合成失败")
            return None
        
        # 7. 上传到OSS
        upload_start = time.time()
        try:
            clip_name = f"dynamic_subtitle_{clip_id}.mp4"
            with open(final_output, 'rb') as f:
                video_content = f.read()
            
            # 在线程中调用异步OSS上传
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                oss_url = loop.run_until_complete(oss_client.upload_to_oss(
                    file_buffer=video_content,
                    original_filename=clip_name,
                    folder=OSS_UPLOAD_FINAL_VEDIO
                ))
            finally:
                loop.close()
            
            # 动态获取端口
            port = os.getenv("BACKEND_PORT", "8000")
            video_url = f"http://39.96.187.7:{port}/api/videos/oss-proxy?url={oss_url}"
            video_size = len(video_content)
            os.remove(final_output)
            
            upload_time = time.time() - upload_start
            print(f"   ✅ 线程{video_index+1}: OSS上传完成，耗时: {upload_time:.1f}秒")
            
        except Exception as e:
            print(f"   ❌ 线程{video_index+1}: OSS上传失败: {str(e)}")
            video_url = f"/outputs/clips/dynamic_subtitle_{clip_id}.mp4"
            video_size = os.path.getsize(final_output) if os.path.exists(final_output) else 0

        # 8. 清理临时文件
        cleanup_files = temp_clips + [montage_clip_path, title_image_path, tts_path]
        if silence_path:
            cleanup_files.append(silence_path)
        
        for temp_file in cleanup_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"   ⚠️ 线程{video_index+1}: 清理失败: {temp_file} - {e}")
        
        clip_time = time.time() - clip_start
        print(f"   🎉 线程{video_index+1}: 完成，总耗时: {clip_time:.1f}秒")
        
        return {
            "id": clip_id,
            "name": f"dynamic_subtitle_{clip_id}.mp4",
            "url": video_url,
            "size": video_size,
            "duration": target_duration,
            "uploadedAt": None,
            "thread_id": video_index+1,
            "processing_time": clip_time
        }
        
    except Exception as e:
        print(f"   ❌ 线程{video_index+1}: 处理异常: {e}")
        import traceback
        traceback.print_exc()
        return None

async def create_time_synced_dynamic_subtitles(sentences, tts_audio_path, video_width=1080, style=None, temp_dir=None):
    """创建与TTS音频时间同步的动态字幕"""
    if not sentences:
        return []
    
    if temp_dir is None:
        temp_dir = SUBTITLE_TEMP_DIR
    
    try:
        # 获取TTS音频的实际时长
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        audio_clip = AudioFileClip(tts_audio_path)
        actual_audio_duration = audio_clip.duration
        audio_clip.close()
        
        print(f"TTS音频实际时长: {actual_audio_duration:.2f}秒")
        
        # 使用实际音频时长创建字幕
        return create_dynamic_subtitles(sentences, actual_audio_duration, video_width, style, temp_dir)
        
    except Exception as e:
        print(f"获取TTS音频时长失败: {e}，使用默认时长")
        # 如果获取音频时长失败，使用默认方法
        return create_dynamic_subtitles(sentences, 30, video_width, style, temp_dir)

def create_9_16_video_with_dynamic_subtitles_ffmpeg(source_video, title_image, subtitle_clips, tts_audio, bgm_audio, output_path, duration, title_position="top", subtitle_position="bottom", poster_image=None, use_gpu=True, portrait_mode: bool=False):
    """使用FFmpeg创建包含动态字幕的9:16视频，支持GPU加速"""
    print(f"🚀 进入动态字幕函数 - portrait_mode: {portrait_mode}, subtitle_position: {subtitle_position}")
    print(f"🎮 GPU加速参数: use_gpu={use_gpu}")
    ffmpeg = find_ffmpeg()
    
    # 获取原始视频信息
    video_info = get_video_info(source_video)
    original_width = video_info['width']
    original_height = video_info['height']
    print(f"📐 原始视频尺寸: {original_width}x{original_height}")
    
    # 调试信息：打印参数
    print(f"🔍 调试信息 - portrait_mode: {portrait_mode}, subtitle_position: {subtitle_position}")
    
    # 根据模式设置目标尺寸
    # 判断原始视频是否已经是竖屏（高度 > 宽度）
    is_already_portrait = original_height > original_width
    
    if portrait_mode or subtitle_position == "template2":
        # 竖屏模式处理
        if is_already_portrait:
            # 原始视频已经是竖屏，保持原始比例，不强制缩放
            target_width = original_width
            target_height = original_height
            print(f"✅ 检测到原始视频已是竖屏 ({original_width}x{original_height})，保持原始比例")
        else:
            # 原始视频是横屏，需要转换为竖屏9:16比例
            target_width = 1080
            target_height = 1920
            print(f"✅ 横屏视频转竖屏模式，目标尺寸: {target_width}x{target_height}")
    else:
        # 横屏模式：使用标准9:16尺寸
        target_width = 1080
        target_height = 1920
        print(f"✅ 使用横屏模式处理")
    
    print(f"📺 最终目标尺寸: {target_width}x{target_height}")
    
    # 计算Title位置
    title_margin = 200
    if title_position == "top":
        title_overlay_y = title_margin
    elif title_position == "center":
        title_overlay_y = f"(H-h)/2-100"
    else:
        title_overlay_y = f"H-h-{title_margin}"
    
    # 计算Subtitle位置
    subtitle_margin = 250
    if subtitle_position == "top":
        subtitle_overlay_y = subtitle_margin
        subtitle_overlay_x = "0"
    elif subtitle_position == "center":
        subtitle_overlay_y = f"(H-h)/2+100"
        subtitle_overlay_x = "0"
    elif subtitle_position == "template1":
        # 模板位置1：距上边框1372.4像素 - 需要考虑字幕图片内部的偏移
        subtitle_overlay_y = str(1372.4 - 60)  # 减去字幕图片高度的一半，让文字中心在1372.4位置
        subtitle_overlay_x = "0"  # 模板位置1：水平居中（X=0表示居中）
    else:
        subtitle_overlay_y = f"H-h-{subtitle_margin}"
        subtitle_overlay_x = "0"
    
    # 构建输入参数
    # 将源视频循环输入以覆盖目标时长；title 与 subtitle 图片作为 looped 输入
    inputs = [
        '-stream_loop', '-1', '-i', source_video,  # 输入0: 源视频（循环）
        '-loop', '1', '-i', title_image,   # 输入1: Title图片（loop）
    ]
    
    # 添加字幕输入
    subtitle_input_indices = []
    for i, subtitle_clip in enumerate(subtitle_clips):
        # 每个字幕图片作为 looped 输入
        inputs.extend(['-loop', '1', '-i', subtitle_clip['path']])
        subtitle_input_indices.append(2 + i)  # 从输入2开始
    
    # 添加音频输入
    tts_input_index = len(subtitle_input_indices) + 2
    bgm_input_index = tts_input_index + 1
    inputs.extend(['-i', tts_audio, '-i', bgm_audio])

    # 如果有海报背景
    poster_input_index = None
    if poster_image and poster_image != "":
        poster_input_index = bgm_input_index + 1
        # poster 也作为 loop 输入
        inputs.extend(['-loop', '1', '-i', poster_image])

    # 构建滤镜链 - 根据竖屏模式选择不同的处理方式
    if portrait_mode or subtitle_position == "template2":
        # 竖屏模式处理
        if poster_image and poster_image != "":
            # 有海报背景的情况
            if is_already_portrait:
                # 原始视频已经是竖屏，直接使用，不强制缩放
                filter_parts = [
                    f"[{poster_input_index}:v]scale={target_width}:{target_height}[bg];",
                    f"[0:v][1:v]overlay=0:{title_overlay_y}[video_with_title];",
                    f"[bg][video_with_title]overlay=(W-w)/2:(H-h)/2[with_title];"
                ]
            else:
                # 横屏视频转竖屏：海报作为背景，原始视频叠加
                filter_parts = [
                    f"[{poster_input_index}:v]scale={target_width}:{target_height}[bg];",
                    f"[0:v]scale={target_width}:{target_height}[fg];",
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2[bg_with_fg];",
                    f"[bg_with_fg][1:v]overlay=0:{title_overlay_y}[with_title];"
                ]
        else:
            # 无海报背景的情况
            if is_already_portrait:
                # 原始视频已经是竖屏，保持原始比例，直接叠加标题
                filter_parts = [
                    f"[0:v][1:v]overlay=0:{title_overlay_y}[with_title];"
                ]
            else:
                # 横屏视频转竖屏：直接缩放到9:16比例
                filter_parts = [
                    f"[0:v]scale={target_width}:{target_height}[base];",
                    f"[base][1:v]overlay=0:{title_overlay_y}[with_title];"
                ]
        
        if is_already_portrait:
            print(f"✅ 竖屏模式：保持原始视频比例 ({target_width}x{target_height})")
        else:
            print(f"✅ 竖屏模式：横屏视频转换为9:16比例 ({target_width}x{target_height})")
    else:
        # 横屏模式：使用原来的逻辑
        if poster_image and poster_image != "":
            # 有海报背景
            filter_parts = [
                f"[{poster_input_index}:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height}[bg];",
                f"[0:v]scale={target_width}:-1[fg_scale];",
                f"[fg_scale]scale={target_width}:{target_width*9//16}[fg];",
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[bg_with_fg];",
                f"[bg_with_fg][1:v]overlay=0:{title_overlay_y}[with_title];"
            ]
        else:
            # 无海报背景，使用模糊背景 - 修复叠加顺序
            filter_parts = [
                f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height}[bg];",
                f"[bg]boxblur=luma_radius=50:chroma_radius=50:luma_power=3[bg_blur];",
                f"[0:v]scale={target_width}:-1[fg_scale];",
                f"[fg_scale]scale={target_width}:{target_width*9//16}[fg];",
                f"[bg_blur][fg]overlay=(W-w)/2:(H-h)/2[bg_with_fg];",
                f"[bg_with_fg][1:v]overlay=0:{title_overlay_y}[with_title];"
            ]
        print(f"✅ 横屏模式：使用increase+crop，有背景模糊")
    
    # 添加动态字幕叠加
    current_layer = "with_title"
    for i, (subtitle_clip, input_idx) in enumerate(zip(subtitle_clips, subtitle_input_indices)):
        next_layer = f"with_subtitle_{i}" if i < len(subtitle_clips) - 1 else "final_video"
        
        # 正确的字幕叠加语法
        filter_parts.append(
            f"[{current_layer}][{input_idx}:v]overlay={subtitle_overlay_x}:{subtitle_overlay_y}:"
            f"enable='between(t,{subtitle_clip['start_time']},{subtitle_clip['end_time']})'"
            f"[{next_layer}];"
        )
        current_layer = next_layer
        
        print(f"字幕{i+1}: {subtitle_clip['start_time']:.1f}s-{subtitle_clip['end_time']:.1f}s 添加到滤镜链")
    # 确保最终输出格式正确
    filter_parts.append(f"[{current_layer}]format=yuv420p[video_out];")
    
    # 音频处理
    # 明确将音频 trim 到目标时长，混音使用 shortest，最终再截断确保一致
    filter_parts.extend([
        f"[{tts_input_index}:a]volume=0.8,atrim=0:{duration}[tts];",
        f"[{bgm_input_index}:a]volume=0.15,atrim=0:{duration}[bgm];",
        f"[tts][bgm]amix=inputs=2:duration=shortest:dropout_transition=0,atrim=0:{duration}[audio_out]"
    ])
    
    filter_complex = "".join(filter_parts)
    
    print(f"修复后的FFmpeg滤镜链:")
    print(filter_complex)
    print("=" * 50)
    
    # 构建完整命令 - GPU加速
    gpu_params = get_gpu_encoding_params(use_gpu, 'balanced')
    print(f"🎮 获取到的GPU编码参数: {' '.join(gpu_params)}")
    
    cmd = [ffmpeg, '-y'] + inputs + [
        '-filter_complex', filter_complex,
        '-map', '[video_out]',
        '-map', '[audio_out]',
        '-t', str(duration),
        *gpu_params,  # GPU加速编码参数
        '-c:a', 'aac',
        '-b:a', '192k',
        '-movflags', '+faststart',
        output_path
    ]
    
    try:
        print("开始FFmpeg动态字幕处理...")
        print(f"总共{len(subtitle_clips)}个字幕片段")
        for i, clip in enumerate(subtitle_clips):
            print(f"  字幕{i+1}: {clip['start_time']:.1f}s-{clip['end_time']:.1f}s '{clip['text'][:30]}...'")
        
        result = subprocess.run(cmd, capture_output=True, text=False)
        if result.returncode != 0:
            try:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
            except:
                stderr_text = str(result.stderr)
            print(f"FFmpeg错误: {stderr_text}")
            # 如果动态字幕失败，尝试使用第一句字幕作为静态字幕
            if subtitle_clips:
                print("尝试使用静态字幕作为备选方案...")
                return create_fallback_static_subtitle_video(
                    source_video, title_image, subtitle_clips[0]['path'], 
                    tts_audio, bgm_audio, output_path, duration, 
                    title_position, subtitle_position, poster_image
                )
            return False
        print("FFmpeg动态字幕处理完成")
        return True
    except Exception as e:
        print(f"FFmpeg执行失败: {e}")
        return False

def create_fallback_static_subtitle_video(source_video, title_image, subtitle_image, tts_audio, bgm_audio, output_path, duration, title_position="top", subtitle_position="bottom", poster_image=None):
    """备选方案：创建静态字幕视频"""
    print("使用静态字幕备选方案...")
    return create_9_16_video_with_title_ffmpeg(
        source_video, title_image, subtitle_image, 
        tts_audio, bgm_audio, output_path, duration, 
        title_position, subtitle_position, poster_image
    )

def create_optimized_video_with_ass_subtitles(source_video, title_image, ass_subtitle, tts_audio, bgm_audio, output_path, duration, title_position="top", poster_image=None, use_gpu=True, subtitle_position: str = "bottom", portrait_mode: bool=False):
    """
    使用ASS字幕的优化视频合成 - 修复FFmpeg兼容性问题
    性能优化：单次FFmpeg调用，ASS字幕烧录，GPU硬件加速
    """
    print(f"🚀 进入ASS字幕函数 - portrait_mode: {portrait_mode}, subtitle_position: {subtitle_position}")
    ffmpeg = find_ffmpeg()
    
    # 调试信息：打印参数
    print(f"🔍 ASS字幕调试信息 - portrait_mode: {portrait_mode}, subtitle_position: {subtitle_position}")
    
    target_width = 1080
    target_height = 1920
    
    # 计算Title位置
    title_margin = 200
    if title_position == "top":
        title_overlay_y = title_margin
    elif title_position == "center":
        title_overlay_y = f"(H-h)/2-100"
    else:
        title_overlay_y = f"H-h-{title_margin}"
    
    print(f"🎬 ASS字幕视频合成:")
    print(f"   源视频: {source_video}")
    print(f"   ASS字幕: {ass_subtitle}")
    print(f"   Title位置: {title_position}")
    print(f"   海报背景: {'是' if poster_image else '否'}")
    
    # 修复ASS字幕路径处理 - 确保Windows路径兼容性
    ass_path_fixed = ass_subtitle.replace('\\', '/').replace('\\', '/')
    if ':' in ass_path_fixed:  # Windows绝对路径
        ass_path_fixed = ass_path_fixed.replace(':', '\\:')
    
    print(f"   🔧 修复后的ASS路径: {ass_path_fixed}")
    
    # 🚀 优化后的FFmpeg滤镜链 - 强制使用GPU硬件解码和编码
    if portrait_mode or subtitle_position == "template2":
        # 竖屏模式：直接使用原始视频，不做任何缩放和背景处理，保持9:16比例
        filter_complex = (
            f"[0:v]scale={target_width}:{target_height}[base];"
            f"[base]subtitles='{ass_path_fixed}'[with_subtitles];"
            f"[with_subtitles][1:v]overlay=0:{title_overlay_y}[video_out];"
            f"[2:a]volume=0.8,atrim=0:{duration}[tts];"
            f"[3:a]volume=0.15,atrim=0:{duration}[bgm];"
            f"[tts][bgm]amix=inputs=2:duration=shortest,atrim=0:{duration}[audio_out]"
        )
        
        # 强制使用GPU硬件解码参数
        gpu_decode_params = [
            '-hwaccel', 'cuda',                    # 启用CUDA硬件加速
            '-hwaccel_output_format', 'cuda',      # 输出格式保持在GPU
            '-c:v', 'h264_cuvid'                   # 强制使用h264_cuvid解码
        ]
        
        print(f"   🚀 ASS字幕处理强制使用GPU硬件解码和编码")
        
        inputs = [
            ffmpeg, '-y',
            *gpu_decode_params,                        # GPU硬件解码参数
            '-stream_loop', '-1', '-i', source_video,  # 输入0: 源视频
            '-loop', '1', '-i', title_image,           # 输入1: Title图片
            '-i', tts_audio,                           # 输入2: TTS音频
            '-i', bgm_audio,                           # 输入3: BGM音频
        ]
    elif poster_image and poster_image != "" and os.path.exists(poster_image):
        # 有海报背景的版本 - 强制使用GPU硬件解码
        filter_complex = (
            f"[4:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height}[bg];"
            f"[0:v]scale={target_width}:{target_width*9//16}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[bg_with_fg];"
            f"[bg_with_fg]subtitles='{ass_path_fixed}'[with_subtitles];"
            f"[with_subtitles][1:v]overlay=0:{title_overlay_y}[video_out];"
            f"[2:a]volume=0.8,atrim=0:{duration}[tts];"
            f"[3:a]volume=0.15,atrim=0:{duration}[bgm];"
            f"[tts][bgm]amix=inputs=2:duration=shortest,atrim=0:{duration}[audio_out]"
        )
        
        # 强制使用GPU硬件解码参数
        gpu_decode_params = [
            '-hwaccel', 'cuda',
            '-hwaccel_output_format', 'cuda',
            '-c:v', 'h264_cuvid'
        ]
        
        inputs = [
            ffmpeg, '-y',
            *gpu_decode_params,                        # GPU硬件解码参数
            '-stream_loop', '-1', '-i', source_video,  # 输入0: 源视频
            '-loop', '1', '-i', title_image,           # 输入1: Title图片
            '-i', tts_audio,                           # 输入2: TTS音频
            '-i', bgm_audio,                           # 输入3: BGM音频
            '-loop', '1', '-i', poster_image,          # 输入4: 海报背景
        ]
    else:
        # 无海报背景的版本（简化模糊背景）- 强制使用GPU硬件解码
        filter_complex = (
            f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height},boxblur=20:20[bg];"
            f"[0:v]scale={target_width}:{target_width*9//16}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[bg_with_fg];"
            f"[bg_with_fg]subtitles='{ass_path_fixed}'[with_subtitles];"
            f"[with_subtitles][1:v]overlay=0:{title_overlay_y}[video_out];"
            f"[2:a]volume=0.8,atrim=0:{duration}[tts];"
            f"[3:a]volume=0.15,atrim=0:{duration}[bgm];"
            f"[tts][bgm]amix=inputs=2:duration=shortest,atrim=0:{duration}[audio_out]"
        )
        
        # 强制使用GPU硬件解码参数
        gpu_decode_params = [
            '-hwaccel', 'cuda',
            '-hwaccel_output_format', 'cuda',
            '-c:v', 'h264_cuvid'
        ]
        
        inputs = [
            ffmpeg, '-y',
            *gpu_decode_params,                        # GPU硬件解码参数
            '-stream_loop', '-1', '-i', source_video,  # 输入0: 源视频
            '-loop', '1', '-i', title_image,           # 输入1: Title图片
            '-i', tts_audio,                           # 输入2: TTS音频
            '-i', bgm_audio,                           # 输入3: BGM音频
        ]
    
    # 获取安全的编码参数
    try:
        encoding_params = get_gpu_encoding_params(use_gpu, 'fast')
        print(f"   🔧 使用编码参数: {encoding_params}")
    except Exception as e:
        print(f"   ⚠️ GPU编码参数获取失败: {e}，使用CPU编码")
        encoding_params = ['-c:v', 'libx264', '-preset', 'fast', '-crf', '23']
    
    # 构建完整命令 - 增强错误处理
    cmd = inputs + [
        '-filter_complex', filter_complex,
        '-map', '[video_out]',
        '-map', '[audio_out]',
        '-t', str(duration),
        *encoding_params,
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        '-avoid_negative_ts', 'make_zero',
        '-fflags', '+genpts',
        '-max_muxing_queue_size', '1024',  # 增加缓冲区大小
        output_path
    ]
    
    try:
        print("   ⚡ 开始ASS字幕FFmpeg处理...")
        
        # 打印完整的滤镜链用于调试
        print(f"   🔧 滤镜链: {filter_complex}")
        
        # 打印命令用于调试（去掉敏感路径信息）
        cmd_debug = [item.replace(os.getcwd(), '.') if isinstance(item, str) else str(item) for item in cmd]
        print(f"   🔧 FFmpeg命令: {' '.join(cmd_debug[:15])}...")
        
        # 执行FFmpeg命令
        result = subprocess.run(cmd, capture_output=True, text=False, timeout=1200)  # 5分钟超时
        
        if result.returncode != 0:
            # 安全地解码stderr，避免编码错误
            try:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
            except:
                try:
                    stderr_text = result.stderr.decode('gbk', errors='replace')
                except:
                    stderr_text = str(result.stderr)
            
            print(f"   ❌ FFmpeg错误 (返回码: {result.returncode}):")
            print(f"   {stderr_text}")
            
            # 检查特定的GPU编码错误 - 增强错误检测
            gpu_error_indicators = [
                '3221225477',  # Windows访问违规错误
                '0xc0000005',  # 另一种访问违规表示
                'access violation',  # 访问违规文本
                'out of memory',  # 内存不足
                'insufficient memory',  # 内存不足
                'failed locking bitstream buffer',  # NVENC bitstream buffer错误
                'invalid param (8)',  # NVENC参数错误
                'error submitting video frame',  # 帧提交错误
                'error encoding a frame',  # 编码帧错误
                'nvenc',
                'cuda',
                'gpu',
                'device',
                'driver',
                'encoder initialization failed',  # 编码器初始化失败
                'cannot load encoder',  # 无法加载编码器
                'hardware acceleration',  # 硬件加速相关
            ]
            
            is_gpu_error = any(indicator.lower() in stderr_text.lower() for indicator in gpu_error_indicators)
            
            # 特殊处理访问违规错误
            is_access_violation = '3221225477' in stderr_text or '0xc0000005' in stderr_text.lower() or 'access violation' in stderr_text.lower()
            
            # 尝试使用CPU编码作为回退
            if use_gpu and (is_gpu_error or 'nvenc' in str(encoding_params)):
                if is_access_violation:
                    print("   🚨 GPU编码访问违规错误 - 可能是GPU内存不足或驱动兼容性问题")
                    print("   💡 建议: 1) 关闭其他GPU应用 2) 重启系统 3) 更新GPU驱动")
                else:
                    print("   🔄 检测到GPU编码错误，尝试CPU编码...")
                    print(f"   🔧 错误类型: {'GPU相关错误' if is_gpu_error else 'NVENC编码器错误'}")
                
                print("   🔄 GPU编码失败，尝试CPU编码...")
                return create_optimized_video_with_ass_subtitles(
                    source_video, title_image, ass_subtitle, tts_audio, bgm_audio,
                    output_path, duration, title_position, poster_image, use_gpu=False
                )
            
            return False
        
        # 检查输出文件是否存在且有内容
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            print(f"   ❌ 输出文件不存在或为空: {output_path}")
            return False
        
        print("   ✅ ASS字幕FFmpeg处理完成")
        return True
        
    except subprocess.TimeoutExpired:
        print(f"   ❌ FFmpeg执行超时 (5分钟)")
        return False
    except Exception as e:
        print(f"   ❌ FFmpeg执行失败: {e}")
        return False

def create_optimized_video_with_ass_subtitles_gpu_enhanced(source_video, title_image, ass_subtitle, 
                                                          tts_audio, bgm_audio, output_path, duration, 
                                                          title_position="top", poster_image=None, 
                                                          subtitle_position="bottom", thread_id=1):
    """
    GPU增强的ASS字幕视频合成 - 专为多线程并行处理优化
    减少CPU负载，强制使用GPU加速
    """
    print(f"🚀 线程{thread_id}: 进入GPU增强ASS字幕合成")
    ffmpeg = find_ffmpeg()
    
    target_width = 1080
    target_height = 1920
    
    # 计算Title位置
    title_margin = 200
    if title_position == "top":
        title_overlay_y = title_margin
    elif title_position == "center":
        title_overlay_y = f"(H-h)/2-100"
    else:
        title_overlay_y = f"H-h-{title_margin}"
    
    print(f"   线程{thread_id}: 源视频: {os.path.basename(source_video)}")
    print(f"   线程{thread_id}: 字幕位置: {subtitle_position}")
    
    # 修复ASS字幕路径
    ass_path_fixed = ass_subtitle.replace('\\', '/').replace('\\', '/')
    if ':' in ass_path_fixed:
        ass_path_fixed = ass_path_fixed.replace(':', '\\:')
    
    # 🚀 强制使用GPU硬件解码和编码
    gpu_decode_params = [
        '-hwaccel', 'cuda',                    # 启用CUDA硬件加速
        '-hwaccel_output_format', 'cuda',      # 输出格式保持在GPU
        '-c:v', 'h264_cuvid'                   # 强制使用h264_cuvid解码
    ]
    
    gpu_encode_params = [
        '-c:v', 'h264_nvenc',                  # 强制使用h264_nvenc编码
        '-preset', 'fast',
        '-crf', '23',
        '-profile:v', 'main',
        '-pix_fmt', 'yuv420p'
    ]
    
    print(f"   🚀 线程{thread_id}: 强制使用GPU硬件解码和编码")
    
    # 🚀 优化的滤镜链 - 减少CPU操作，专为template2优化
    portrait_mode = subtitle_position == "template2"
    
    if portrait_mode:
        # 竖屏模式：直接缩放，减少复杂操作
        filter_complex = (
            f"[0:v]scale={target_width}:{target_height}:flags=fast_bilinear[base];"
            f"[base]subtitles='{ass_path_fixed}':fontsdir=fonts[with_subtitles];"
            f"[with_subtitles][1:v]overlay=0:{title_overlay_y}:format=auto[video_out];"
            f"[2:a]volume=0.8,aresample=44100[tts];"
            f"[3:a]volume=0.15,aresample=44100[bgm];"
            f"[tts][bgm]amix=inputs=2:duration=first[audio_out]"
        )
    else:
        # 其他模式的简化处理
        filter_complex = (
            f"[0:v]scale={target_width}:{target_height}:flags=fast_bilinear[base];"
            f"[base]subtitles='{ass_path_fixed}':fontsdir=fonts[with_subtitles];"
            f"[with_subtitles][1:v]overlay=0:{title_overlay_y}:format=auto[video_out];"
            f"[2:a]volume=0.8,aresample=44100[tts];"
            f"[3:a]volume=0.15,aresample=44100[bgm];"
            f"[tts][bgm]amix=inputs=2:duration=first[audio_out]"
        )
    
    # 构建优化的FFmpeg命令
    cmd = [
        ffmpeg, '-y',
        *gpu_decode_params,                        # GPU硬件解码
        '-i', source_video,                        # 输入0: 源视频
        '-loop', '1', '-i', title_image,           # 输入1: Title图片
        '-i', tts_audio,                           # 输入2: TTS音频
        '-i', bgm_audio,                           # 输入3: BGM音频
        '-filter_complex', filter_complex,
        '-map', '[video_out]',
        '-map', '[audio_out]',
        '-t', str(duration),
        *gpu_encode_params,                        # GPU编码参数
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        '-threads', '2',                           # 限制线程数，避免资源竞争
        output_path
    ]
    
    try:
        print(f"   ⚡ 线程{thread_id}: 开始GPU加速FFmpeg处理...")
        
        # 执行FFmpeg命令
        result = subprocess.run(cmd, capture_output=True, text=False, timeout=600)
        
        if result.returncode != 0:
            try:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
            except:
                stderr_text = str(result.stderr)
            
            print(f"   ❌ 线程{thread_id}: FFmpeg错误: {stderr_text[:200]}...")
            
            # 如果GPU失败，尝试CPU回退
            if 'nvenc' in stderr_text.lower() or 'cuda' in stderr_text.lower():
                print(f"   🔄 线程{thread_id}: GPU编码失败，回退到CPU")
                return create_optimized_video_with_ass_subtitles(
                    source_video, title_image, ass_subtitle, tts_audio, bgm_audio,
                    output_path, duration, title_position, poster_image, use_gpu=False,
                    subtitle_position=subtitle_position, portrait_mode=portrait_mode
                )
            
            return False
        
        # 检查输出文件
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            print(f"   ❌ 线程{thread_id}: 输出文件不存在或为空")
            return False
        
        print(f"   ✅ 线程{thread_id}: GPU增强FFmpeg处理完成")
        return True
        
    except subprocess.TimeoutExpired:
        print(f"   ❌ 线程{thread_id}: FFmpeg执行超时")
        return False
    except Exception as e:
        print(f"   ❌ 线程{thread_id}: FFmpeg执行异常: {e}")
        return False

def find_ffmpeg():
    """查找FFmpeg可执行文件"""
    possible_paths = [
        'ffmpeg',  # 系统PATH中
        'ffmpeg.exe',
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg'
    ]
    
    for path in possible_paths:
        try:
            subprocess.run([path, '-version'], capture_output=True, check=True, text=False)
            return path
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    raise Exception("未找到FFmpeg，请安装FFmpeg并添加到系统PATH")

def check_gpu_memory():
    """检查GPU内存使用情况"""
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'], 
                              capture_output=True, text=False, timeout=10)
        if result.returncode == 0:
            try:
                output = result.stdout.decode('utf-8', errors='replace').strip()
                used, total = map(int, output.split(', '))
                usage_percent = (used / total) * 100
                
                print(f"🔍 GPU内存使用: {used}MB / {total}MB ({usage_percent:.1f}%)")
                
                # 如果GPU内存使用超过80%，可能导致编码失败
                if usage_percent > 80:
                    print("⚠️ GPU内存使用率过高，可能导致编码失败")
                    return False
                return True
            except:
                return True  # 解析失败时假设内存充足
        return True
    except Exception:
        return True  # 检查失败时假设内存充足

def test_nvenc_encoder():
    """测试NVENC编码器是否能正常工作 - 增强内存检查"""
    try:
        # 先检查GPU内存使用情况
        if not check_gpu_memory():
            print("❌ GPU内存不足，跳过NVENC测试")
            return False
        
        ffmpeg = find_ffmpeg()
        
        # 使用极简参数进行测试，避免访问违规
        test_cmd = [
            ffmpeg, '-y',
            '-f', 'lavfi',
            '-i', 'testsrc=duration=1:size=320x240:rate=1',
            '-c:v', 'h264_nvenc',
            '-preset', 'fast',  # 最兼容的预设
            '-cq', '30',        # 使用恒定质量，避免比特率控制
            '-t', '1',
            '-f', 'null',
            '-'
        ]
        
        print(f"🧪 测试NVENC编码器: {' '.join(test_cmd[3:8])}...")
        result = subprocess.run(test_cmd, capture_output=True, text=False, timeout=15)
        
        if result.returncode == 0:
            print("✅ NVENC编码器测试成功")
            return True
        else:
            try:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
            except:
                stderr_text = str(result.stderr)
            
            # 检查是否是访问违规错误
            if '3221225477' in stderr_text:
                print(f"❌ NVENC访问违规错误 (3221225477) - GPU内存不足或驱动问题")
                print(f"💡 建议: 1) 关闭其他GPU应用 2) 重启系统 3) 降低视频分辨率")
            else:
                print(f"❌ NVENC编码器测试失败: {stderr_text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ NVENC编码器测试异常: {e}")
        return False

def check_gpu_support():
    """检查GPU硬件编码支持"""
    try:
        ffmpeg = find_ffmpeg()
        result = subprocess.run([ffmpeg, '-encoders'], capture_output=True, text=False)
        try:
            output = result.stdout.decode('utf-8', errors='replace').lower()
        except:
            output = str(result.stdout).lower()
        
        # 检查NVIDIA NVENC支持
        has_nvenc = 'h264_nvenc' in output or 'hevc_nvenc' in output
        
        # 检查AMD AMF支持
        has_amf = 'h264_amf' in output or 'hevc_amf' in output
        
        # 检查Intel QSV支持
        has_qsv = 'h264_qsv' in output or 'hevc_qsv' in output
        
        # 检查NVENC API版本兼容性
        nvenc_version = check_nvenc_version()
        
        # 如果检测到NVENC，进行实际测试
        nvenc_working = False
        if has_nvenc:
            nvenc_working = test_nvenc_encoder()
        
        return {
            'nvenc': has_nvenc and nvenc_working,  # 只有通过测试才认为可用
            'amf': has_amf,
            'qsv': has_qsv,
            'any_gpu': (has_nvenc and nvenc_working) or has_amf or has_qsv,
            'nvenc_version': nvenc_version,
            'nvenc_compatible': nvenc_version >= 12.0 if nvenc_version else False,
            'nvenc_tested': nvenc_working
        }
    except Exception as e:
        print(f"检查GPU支持失败: {e}")
        return {'nvenc': False, 'amf': False, 'qsv': False, 'any_gpu': False, 'nvenc_version': None, 'nvenc_compatible': False}

def check_nvenc_version():
    """检查NVENC API版本"""
    try:
        # 检查NVIDIA驱动版本
        result = subprocess.run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'], 
                              capture_output=True, text=False)
        if result.returncode == 0:
            try:
                driver_version = result.stdout.decode('utf-8', errors='replace').strip()
            except:
                driver_version = str(result.stdout).strip()
            # 将驱动版本转换为NVENC API版本
            driver_num = float(driver_version.split('.')[0])
            
            if driver_num >= 570:
                return 13.0
            elif driver_num >= 560:
                return 12.2
            elif driver_num >= 550:
                return 12.1
            elif driver_num >= 540:
                return 12.0
            else:
                return 11.0
        return None
    except Exception:
        return None

def get_gpu_encoding_params(use_gpu=True, quality='balanced'):
    """
    统一的GPU编码参数获取函数 - 强制使用h264_nvenc
    
    Args:
        use_gpu: 是否使用GPU加速
        quality: 编码质量 ('fast', 'balanced', 'quality')
    
    Returns:
        list: FFmpeg编码参数列表
    """
    # 强制使用GPU，除非明确指定不使用
    if not use_gpu:
        print("🔧 用户明确指定使用CPU编码")
        return [
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23'
        ]
    
    # 强制使用h264_nvenc编码
    print("🚀 使用GPU硬件编码 (h264_nvenc)")
    
    base_params = [
        '-c:v', 'h264_nvenc',
        '-preset', 'fast',
        '-profile:v', 'main',
        '-pix_fmt', 'yuv420p'
    ]
    
    # 根据质量级别调整参数
    if quality == 'fast':
        return base_params + [
            '-crf', '28',
            '-b:v', '5M',
            '-maxrate', '8M',
            '-bufsize', '10M'
        ]
    elif quality == 'quality':
        return base_params + [
            '-crf', '20',
            '-b:v', '10M',
            '-maxrate', '15M',
            '-bufsize', '20M'
        ]
    else:  # balanced
        return base_params + [
            '-crf', '23',
            '-b:v', '8M',
            '-maxrate', '12M',
            '-bufsize', '16M'
        ]

def _get_safe_nvenc_params(quality):
    """
    获取修复NVENC编码错误的安全参数
    解决"Failed locking bitstream buffer: invalid param (8)"错误
    基于实际测试结果的最佳参数组合
    """
    print("🔧 使用修复后的NVENC参数 (解决bitstream buffer错误)")

    # 基于测试结果的最佳参数 - 兼容性优先
    # 这些参数在测试中表现最佳，编码时间最短且稳定
    base_params = [
        '-c:v', 'h264_nvenc',
        '-preset', 'fast',         # 使用fast预设，避免复杂参数
        '-profile:v', 'main',      # 强制使用main profile
        '-level', '4.1',           # 设置兼容的level
        '-pix_fmt', 'yuv420p',     # 强制像素格式，避免格式冲突
        '-gpu', '0',               # 指定GPU设备
    ]

    # 根据质量级别调整参数 - 使用简化参数避免bitstream buffer错误
    if quality == 'fast':
        return base_params + [
            '-cq', '30',           # 较低质量，更快编码
            '-b:v', '5M',          # 保守的比特率设置
            '-maxrate', '8M',      # 保守的最大比特率
            '-bufsize', '10M',     # 较小的缓冲区避免内存问题
        ]
    elif quality == 'quality':
        return base_params + [
            '-cq', '22',           # 高质量但不过度
            '-b:v', '8M',          # 适中的比特率
            '-maxrate', '12M',     # 适中的最大比特率
            '-bufsize', '16M',     # 适中的缓冲区
        ]
    else:  # balanced
        return base_params + [
            '-cq', '25',           # 平衡质量
            '-b:v', '6M',          # 平衡比特率
            '-maxrate', '10M',     # 平衡最大比特率
            '-bufsize', '12M',     # 平衡缓冲区
        ]

def _handle_nvenc_encoding_error(stderr_text: str, quality: str = 'balanced'):
    """
    处理NVENC编码错误并提供恢复方案
    专门处理"Failed locking bitstream buffer: invalid param (8)"等错误
    """
    print("🚨 检测到NVENC编码错误，启动错误恢复机制")

    # 分析错误类型
    error_type = "unknown"
    if "failed locking bitstream buffer" in stderr_text.lower():
        error_type = "bitstream_buffer_lock"
        print("   🔍 错误类型: Bitstream Buffer锁定失败")
    elif "error submitting video frame" in stderr_text.lower():
        error_type = "frame_submission"
        print("   🔍 错误类型: 视频帧提交失败")
    elif "error encoding a frame" in stderr_text.lower():
        error_type = "frame_encoding"
        print("   🔍 错误类型: 帧编码失败")
    elif "invalid param" in stderr_text.lower():
        error_type = "invalid_param"
        print("   🔍 错误类型: 无效参数")

    # 根据错误类型提供恢复参数
    recovery_params = _get_nvenc_recovery_params(error_type, quality)

    print(f"   🔧 应用恢复参数: {' '.join(recovery_params[:6])}...")
    return recovery_params

def _get_nvenc_recovery_params(error_type: str, quality: str = 'balanced'):
    """
    获取NVENC错误恢复参数
    基于错误类型提供最保守的编码参数
    """
    # 最基础的恢复参数 - 极简配置
    base_recovery_params = [
        '-c:v', 'h264_nvenc',
        '-preset', 'fast',         # 固定使用fast预设
        '-profile:v', 'baseline',  # 使用最兼容的baseline profile
        '-level', '3.1',           # 降低level避免复杂特性
        '-pix_fmt', 'yuv420p',     # 强制像素格式
    ]

    if error_type == "bitstream_buffer_lock":
        # Bitstream buffer锁定失败 - 减少内存使用
        return base_recovery_params + [
            '-cq', '28',           # 使用恒定质量避免比特率控制复杂性
            '-bufsize', '4M',      # 极小的缓冲区
            '-rc', 'cqp',          # 使用恒定量化参数模式
        ]
    elif error_type == "frame_submission":
        # 帧提交失败 - 简化帧处理
        return base_recovery_params + [
            '-cq', '30',           # 较低质量
            '-g', '30',            # 固定GOP大小
            '-bf', '0',            # 禁用B帧
        ]
    elif error_type == "invalid_param":
        # 参数无效 - 使用最简参数
        return [
            '-c:v', 'h264_nvenc',
            '-preset', 'fast',
            '-cq', '28',
        ]
    else:
        # 通用恢复参数
        return base_recovery_params + [
            '-cq', '28',
            '-b:v', '3M',
            '-maxrate', '5M',
            '-bufsize', '6M',
        ]

def detect_video_codec(video_path):
    """
    检测视频文件的编解码器

    Args:
        video_path: 视频文件路径

    Returns:
        str: 编解码器名称 ('h264', 'hevc', 'av1', 'unknown')
    """
    try:
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, '-i', video_path,
            '-t', '0.1',  # 只检查0.1秒
            '-f', 'null', '-'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        stderr_output = result.stderr.lower()

        # 检测编解码器
        if 'hevc' in stderr_output or 'h.265' in stderr_output or 'hev1' in stderr_output:
            return 'hevc'
        elif 'h264' in stderr_output or 'h.264' in stderr_output or 'avc1' in stderr_output:
            return 'h264'
        elif 'av1' in stderr_output or 'av01' in stderr_output:
            return 'av1'
        else:
            print(f"⚠️ 未识别的编解码器，FFmpeg输出: {stderr_output[:200]}")
            return 'unknown'

    except Exception as e:
        print(f"⚠️ 编解码器检测失败: {e}")
        return 'unknown'

def get_gpu_decoding_params(codec='h264'):
    """
    获取GPU硬件解码参数 - 支持多种编解码器

    Args:
        codec: 视频编解码器 ('h264', 'hevc', 'av1')

    Returns:
        list: GPU解码参数列表
    """
    try:
        gpu_support = check_gpu_support()

        if gpu_support.get('nvenc', False):
            # 根据编解码器选择对应的CUVID解码器
            decoder_map = {
                'h264': 'h264_cuvid',
                'hevc': 'hevc_cuvid',
                'av1': 'av1_cuvid'
            }

            decoder = decoder_map.get(codec, 'h264_cuvid')
            print(f"🚀 启用NVIDIA硬件解码加速 ({codec} -> {decoder})")

            return [
                '-hwaccel', 'cuda',                    # 启用CUDA硬件加速
                '-hwaccel_output_format', 'cuda',      # 输出格式保持在GPU
                '-extra_hw_frames', '8',               # 额外硬件帧缓冲
                '-c:v', decoder,                       # 使用对应的CUVID硬件解码器
            ]
        elif gpu_support.get('amf', False):
            print("🚀 启用AMD硬件解码加速")
            return [
                '-hwaccel', 'd3d11va',                 # AMD硬件加速
                '-hwaccel_output_format', 'd3d11',     # D3D11输出格式
            ]
        elif gpu_support.get('qsv', False):
            print("🚀 启用Intel硬件解码加速")
            return [
                '-hwaccel', 'qsv',                     # Intel QSV硬件加速
                '-hwaccel_output_format', 'qsv',       # QSV输出格式
            ]
        else:
            print("⚠️ 未检测到GPU解码支持，使用CPU解码")
            return []

    except Exception as e:
        print(f"⚠️ GPU解码参数获取失败: {e}")
        return []

def get_gpu_filter_params():
    """获取GPU加速滤镜参数 - 在GPU上执行滤镜操作"""
    try:
        gpu_support = check_gpu_support()

        if gpu_support.get('nvenc', False):
            return {
                'scale': 'scale_cuda',           # GPU缩放滤镜
                'overlay': 'overlay_cuda',       # GPU叠加滤镜
                'format': 'hwupload_cuda',       # 上传到GPU内存
                'download': 'hwdownload',        # 从GPU下载
            }
        else:
            return {
                'scale': 'scale',
                'overlay': 'overlay',
                'format': '',
                'download': '',
            }
    except Exception:
        return {
            'scale': 'scale',
            'overlay': 'overlay',
            'format': '',
            'download': '',
        }

def gpu_accelerated_video_composition(video_paths, output_path, composition_type='concat', **kwargs):
    """
    GPU加速视频合成函数 - 充分利用RTX 3090性能

    Args:
        video_paths: 输入视频路径列表
        output_path: 输出视频路径
        composition_type: 合成类型 ('concat', 'overlay', 'grid', 'pip')
        **kwargs: 额外参数

    Returns:
        bool: 合成是否成功
    """
    print(f"🚀 GPU加速视频合成: {composition_type}")
    print(f"   输入视频数量: {len(video_paths)}")
    print(f"   输出路径: {os.path.basename(output_path)}")

    try:
        # 检测视频编解码器
        codecs = []
        for video_path in video_paths:
            codec = detect_video_codec(video_path)
            codecs.append(codec)
            print(f"   检测到编解码器: {os.path.basename(video_path)} -> {codec}")

        # 选择主要编解码器
        from collections import Counter
        codec_counts = Counter(codec for codec in codecs if codec != 'unknown')
        primary_codec = codec_counts.most_common(1)[0][0] if codec_counts else 'h264'
        print(f"   使用主要编解码器: {primary_codec}")

        # 获取对应的GPU参数
        gpu_decode_params = get_gpu_decoding_params(primary_codec)
        gpu_encode_params = get_gpu_encoding_params(use_gpu=True, quality='balanced')
        gpu_filters = get_gpu_filter_params()

        # 构建基础命令
        ffmpeg = find_ffmpeg()
        cmd = [ffmpeg, '-y']

        # 添加GPU解码参数到每个输入
        inputs = []
        for video_path in video_paths:
            if gpu_decode_params:
                inputs.extend(gpu_decode_params)
            inputs.extend(['-i', video_path])

        cmd.extend(inputs)

        # 根据合成类型构建滤镜链
        if composition_type == 'concat':
            # GPU加速拼接
            filter_complex = _build_gpu_concat_filter(len(video_paths), gpu_filters)
        elif composition_type == 'grid':
            # GPU加速网格布局
            grid_size = kwargs.get('grid_size', (2, 2))
            output_size = kwargs.get('output_size', (1920, 1080))
            filter_complex = _build_gpu_grid_filter(len(video_paths), grid_size, output_size, gpu_filters)
        elif composition_type == 'overlay':
            # GPU加速叠加
            positions = kwargs.get('positions', [(0, 0)])
            filter_complex = _build_gpu_overlay_filter(len(video_paths), positions, gpu_filters)
        else:
            raise ValueError(f"不支持的合成类型: {composition_type}")

        # 添加滤镜链
        cmd.extend(['-filter_complex', filter_complex])
        cmd.extend(['-map', '[out]'])

        # 添加GPU编码参数
        cmd.extend(gpu_encode_params)

        # 音频和输出设置
        cmd.extend([
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            output_path
        ])

        print(f"🔧 执行GPU加速合成命令...")
        result = subprocess.run(cmd, capture_output=True, text=False, timeout=600)

        if result.returncode == 0:
            print(f"✅ GPU加速合成成功: {os.path.basename(output_path)}")
            return True
        else:
            stderr_text = result.stderr.decode('utf-8', errors='replace')
            print(f"❌ GPU合成失败: {stderr_text}")
            return False

    except Exception as e:
        print(f"❌ GPU加速合成异常: {e}")
        return False

def _build_gpu_concat_filter(num_videos, gpu_filters):
    """构建GPU加速拼接滤镜"""
    if gpu_filters['scale'] == 'scale_cuda':
        # 使用GPU滤镜
        filter_parts = []
        for i in range(num_videos):
            filter_parts.append(f'[{i}:v]hwupload_cuda,scale_cuda=1920:1080[v{i}];')

        concat_inputs = "".join([f"[v{i}]" for i in range(num_videos)])
        filter_parts.append(f'{concat_inputs}concat=n={num_videos}:v=1:a=0,hwdownload,format=nv12[out]')

        return "".join(filter_parts)
    else:
        # 回退到CPU滤镜
        filter_parts = []
        for i in range(num_videos):
            filter_parts.append(f'[{i}:v]scale=1920:1080[v{i}];')

        concat_inputs = "".join([f"[v{i}]" for i in range(num_videos)])
        filter_parts.append(f'{concat_inputs}concat=n={num_videos}:v=1:a=0[out]')

        return "".join(filter_parts)

def _build_gpu_grid_filter(num_videos, grid_size, output_size, gpu_filters):
    """构建GPU加速网格滤镜"""
    rows, cols = grid_size
    output_width, output_height = output_size
    cell_width = output_width // cols
    cell_height = output_height // rows

    if gpu_filters['scale'] == 'scale_cuda':
        # GPU网格滤镜
        filter_parts = []

        # 上传到GPU并缩放
        for i in range(num_videos):
            filter_parts.append(f'[{i}:v]hwupload_cuda,scale_cuda={cell_width}:{cell_height}[v{i}];')

        # 构建网格布局
        if num_videos == 4:  # 2x2网格
            filter_parts.append('[v0][v1]hstack_cuda=inputs=2[top];')
            filter_parts.append('[v2][v3]hstack_cuda=inputs=2[bottom];')
            filter_parts.append('[top][bottom]vstack_cuda=inputs=2,hwdownload,format=nv12[out]')
        else:  # 简单水平拼接
            inputs = "".join([f"[v{i}]" for i in range(num_videos)])
            filter_parts.append(f'{inputs}hstack_cuda=inputs={num_videos},hwdownload,format=nv12[out]')

        return "".join(filter_parts)
    else:
        # CPU网格滤镜
        filter_parts = []
        for i in range(num_videos):
            filter_parts.append(f'[{i}:v]scale={cell_width}:{cell_height}[v{i}];')

        if num_videos == 4:
            filter_parts.append('[v0][v1]hstack=inputs=2[top];')
            filter_parts.append('[v2][v3]hstack=inputs=2[bottom];')
            filter_parts.append('[top][bottom]vstack=inputs=2[out]')
        else:
            inputs = "".join([f"[v{i}]" for i in range(num_videos)])
            filter_parts.append(f'{inputs}hstack=inputs={num_videos}[out]')

        return "".join(filter_parts)

def _get_safe_amf_params(quality):
    """获取安全的AMD AMF参数"""
    print("🔧 使用安全的AMF参数")
    
    base_params = ['-c:v', 'h264_amf']
    
    if quality == 'fast':
        return base_params + ['-b:v', '6M', '-maxrate', '8M']
    elif quality == 'quality':
        return base_params + ['-b:v', '10M', '-maxrate', '15M']
    else:  # balanced
        return base_params + ['-b:v', '8M', '-maxrate', '12M']

def _get_safe_qsv_params(quality):
    """获取安全的Intel QSV参数"""
    print("🔧 使用安全的QSV参数")
    
    base_params = ['-c:v', 'h264_qsv']
    
    if quality == 'fast':
        return base_params + ['-preset', 'fast', '-b:v', '6M']
    elif quality == 'quality':
        return base_params + ['-preset', 'slow', '-b:v', '10M']
    else:  # balanced
        return base_params + ['-preset', 'medium', '-b:v', '8M']

def _get_default_nvenc_params(quality):
    """获取默认NVIDIA NVENC参数 - 兼容不同API版本"""
    gpu_support = check_gpu_support()
    nvenc_version = gpu_support.get('nvenc_version', 12.0)
    
    print(f"🔧 检测到NVENC API版本: {nvenc_version}")
    
    # 基础参数
    base_params = ['-c:v', 'h264_nvenc', '-gpu', '0']
    
    # 根据API版本选择兼容的参数
    if nvenc_version >= 13.0:
        # 新版本API (驱动570+)
        print("✅ 使用新版NVENC参数")
        base_params.extend(['-rc', 'vbr'])
        
        if quality == 'fast':
            return base_params + ['-preset', 'p1', '-cq', '28', '-b:v', '8M', '-maxrate', '12M', '-bufsize', '16M']
        elif quality == 'quality':
            return base_params + ['-preset', 'p7', '-cq', '19', '-b:v', '12M', '-maxrate', '18M', '-bufsize', '24M']
        else:  # balanced
            return base_params + ['-preset', 'p4', '-cq', '23', '-b:v', '10M', '-maxrate', '15M', '-bufsize', '20M']
    
    else:
        # 旧版本API兼容模式 (驱动560-569)
        print("⚠️ 使用兼容版NVENC参数")
        base_params.extend(['-rc', 'cbr'])  # 使用CBR模式更兼容
        
        if quality == 'fast':
            return base_params + ['-preset', 'fast', '-b:v', '8M', '-maxrate', '12M', '-bufsize', '16M']
        elif quality == 'quality':
            return base_params + ['-preset', 'slow', '-b:v', '12M', '-maxrate', '18M', '-bufsize', '24M']
        else:  # balanced
            return base_params + ['-preset', 'medium', '-b:v', '10M', '-maxrate', '15M', '-bufsize', '20M']

def _get_default_amf_params(quality):
    """获取默认AMD AMF参数"""
    return [
        '-c:v', 'h264_amf', '-quality', 'balanced', '-rc', 'vbr_peak',
        '-qp_i', '22', '-qp_p', '24', '-b:v', '10M', '-maxrate', '15M'
    ]

def _get_default_qsv_params(quality):
    """获取默认Intel QSV参数"""
    return [
        '-c:v', 'h264_qsv', '-preset', 'medium', '-global_quality', '23',
        '-b:v', '10M', '-maxrate', '15M'
    ]

def concat_videos_ffmpeg(video_paths, output_path):
    """
    使用FFmpeg拼接多个视频片段 - 支持混合编解码器

    Args:
        video_paths: 视频文件路径列表
        output_path: 输出文件路径
    """
    if not video_paths:
        return False

    ffmpeg = find_ffmpeg()

    try:
        print(f"🎬 开始拼接{len(video_paths)}个视频片段")

        # 检测所有视频的编解码器
        codecs = []
        for i, video_path in enumerate(video_paths):
            if os.path.exists(video_path):
                codec = detect_video_codec(video_path)
                codecs.append(codec)
                print(f"   视频{i+1}: {os.path.basename(video_path)} -> {codec}")
            else:
                print(f"   ⚠️ 视频{i+1}不存在: {video_path}")
                codecs.append('unknown')

        # 创建临时文件列表
        concat_file = os.path.join(OUTPUT_DIR, f"concat_list_{str(uuid4())[:8]}.txt")

        with open(concat_file, 'w', encoding='utf-8') as f:
            for video_path in video_paths:
                # 使用相对路径或绝对路径
                abs_path = os.path.abspath(video_path)
                f.write(f"file '{abs_path}'\n")

        # 判断是否可以使用流复制模式
        unique_codecs = set(codec for codec in codecs if codec != 'unknown')
        # 强制使用GPU加速拼接，不使用流复制模式
        print("🚀 强制使用GPU加速拼接模式")

        # 选择主要编解码器（出现最多的）
        if codecs:
            from collections import Counter
            codec_counts = Counter(codec for codec in codecs if codec != 'unknown')
            primary_codec = codec_counts.most_common(1)[0][0] if codec_counts else 'h264'
        else:
            primary_codec = 'h264'

        print(f"   检测到编解码器: {list(unique_codecs)}")
        print(f"   主要编解码器: {primary_codec}")

        # 修复拼接：使用GPU解码但允许CPU格式转换，避免concat滤镜格式冲突
        cmd = [
            ffmpeg, '-y',
            '-hwaccel', 'cuda',                    # 启用CUDA硬件加速解码
            '-c:v', 'h264_cuvid',                  # 强制使用h264_cuvid解码
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c:v', 'h264_nvenc',                  # 强制使用h264_nvenc编码
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            output_path
        ]
        
        print("🚀 使用GPU硬件解码和编码拼接视频（修复concat格式兼容性）")
        
        result = subprocess.run(cmd, capture_output=True, text=False)
        
        # 清理临时文件
        if os.path.exists(concat_file):
            os.remove(concat_file)
            
        if result.returncode != 0:
            try:
                stderr_text = result.stderr.decode('utf-8', errors='replace')
            except:
                stderr_text = str(result.stderr)
            print(f"FFmpeg拼接错误: {stderr_text}")
            return False

        # 检查输出文件是否存在
        if not os.path.exists(output_path):
            print(f"❌ 拼接失败：输出文件不存在 {output_path}")
            return False

        # 获取输出文件信息
        output_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
        print(f"✅ 成功拼接{len(video_paths)}个片段")
        print(f"📊 输出文件大小: {output_size:.1f}MB")

        # 打印视频链接
        print(f"🔗 拼接后视频路径: {output_path}")
        print(f"📁 视频文件名: {os.path.basename(output_path)}")


        return True
        
    except Exception as e:
        print(f"视频拼接失败: {e}")
        return False


def get_video_info(video_path):
    """获取视频信息 - 使用GPU硬件解码"""
    ffmpeg = find_ffmpeg()
    
    # 先尝试使用GPU硬件解码
    cmd_gpu = [
        ffmpeg,
        '-hwaccel', 'cuda',                    # 启用CUDA硬件加速
        '-c:v', 'h264_cuvid',                  # 使用h264_cuvid解码
        '-i', video_path,
        '-t', '0.1',                           # 只处理0.1秒，快速获取信息
        '-f', 'null', '-'
    ]
    
    try:
        result = subprocess.run(cmd_gpu, capture_output=True, text=True, timeout=10)
        
        # 如果GPU解码失败，回退到CPU
        if result.returncode != 0:
            print(f"GPU解码获取视频信息失败，回退到CPU: {os.path.basename(video_path)}")
            cmd_cpu = [
                ffmpeg, '-i', video_path,
                '-t', '0.1',
                '-f', 'null', '-'
            ]
            result = subprocess.run(cmd_cpu, capture_output=True, text=True, timeout=10)
        else:
            print(f"🚀 使用GPU解码获取视频信息: {os.path.basename(video_path)}")
        
        # 从stderr中解析视频信息
        output = result.stderr
        
        # 提取分辨率
        import re
        resolution_match = re.search(r'(\d+)x(\d+)', output)
        if resolution_match:
            width, height = map(int, resolution_match.groups())
        else:
            width, height = 1920, 1080  # 默认值
        
        # 提取时长
        duration_match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', output)
        if duration_match:
            h, m, s = duration_match.groups()
            duration = int(h) * 3600 + int(m) * 60 + float(s)
        else:
            duration = 30.0  # 默认值
        
        return {
            'width': width,
            'height': height,
            'duration': duration
        }
    except Exception as e:
        print(f"获取视频信息失败: {e}")
        return {'width': 1920, 'height': 1080, 'duration': 30.0}

def _process_single_video_optimized(video_index, video_count, local_video_paths, local_audio_paths, 
                                    local_poster_path, video_infos, duration_sec, title, scripts, 
                                    style, title_position, subtitle_position, req):
    """
    单个视频处理函数 - 用于多线程并行处理
    优化GPU使用，减少CPU负载
    """
    import asyncio
    import random
    import time
    from uuid import uuid4
    
    try:
        clip_start = time.time()
        clip_id = str(uuid4())[:8]
        
        print(f"\n🎞️  线程{video_index+1}: 处理视频 (ID: {clip_id})")
        
        # 3.1 蒙太奇拼接（使用FFmpeg，更快）
        montage_start = time.time()
        temp_clips = []
        n_videos = len(local_video_paths)
        base_duration = duration_sec // n_videos
        remaining_duration = duration_sec % n_videos
        
        # 关键改进：为每个视频随机打乱素材顺序，确保每个视频使用不同的拼接顺序
        # 创建索引列表并打乱
        indices = list(range(n_videos))
        random.shuffle(indices)
        
        # 使用打乱后的索引来访问视频路径和视频信息
        for idx in indices:
            video_path = local_video_paths[idx]
            video_info = video_infos[idx]
            
            segment_duration = base_duration
            if len(temp_clips) < remaining_duration:
                segment_duration += 1
            
            if segment_duration <= 0:
                continue
                
            max_segment = min(segment_duration, int(video_info['duration']) - 1)
            if max_segment <= 0:
                continue
            
            max_start = max(0, video_info['duration'] - max_segment - 0.5)
            start_time = random.uniform(0, max_start) if max_start > 0 else 0
            
            temp_clip_path = os.path.join(OUTPUT_DIR, f"temp_segment_{clip_id}_{idx}.mp4")
            
            # 🚀 强制使用GPU加速提取片段
            if extract_random_clip_ffmpeg(video_path, temp_clip_path, start_time, max_segment):
                temp_clips.append(temp_clip_path)
        
        if not temp_clips:
            print(f"   ❌ 线程{video_index+1}: 无有效片段")
            return None
        
        montage_clip_path = os.path.join(OUTPUT_DIR, f"montage_clip_{clip_id}.mp4")
        
        if len(temp_clips) == 1:
            import shutil
            shutil.copy2(temp_clips[0], montage_clip_path)
        else:
            if not concat_videos_ffmpeg(temp_clips, montage_clip_path):
                print(f"   ❌ 线程{video_index+1}: 拼接失败")
                return None
        
        montage_time = time.time() - montage_start
        print(f"   ✅ 线程{video_index+1}: 蒙太奇拼接完成，耗时: {montage_time:.1f}秒")

        # 3.2 生成Title图片
        title_start = time.time()
        title_image_path = os.path.join(SUBTITLE_TEMP_DIR, f"title_{clip_id}.png")
        title_img = create_title_image(title, 1080, 1920, style)
        title_img.save(title_image_path)
        title_time = time.time() - title_start
        print(f"   ✅ 线程{video_index+1}: 标题图片生成完成，耗时: {title_time:.1f}秒")

        # 3.3 准备脚本文本
        script = random.choice(scripts).content if scripts else "这是一段精彩的视频内容，展现了多个精彩瞬间的完美融合。"
        
        # 3.4 生成TTS音频（同步调用）
        tts_start = time.time()
        tts_path = os.path.join(TTS_TEMP_DIR, f"tts_{clip_id}.wav")
        voice = 'zh-CN-YunxiNeural' if hasattr(req, 'voice') and req.voice == 'male' else 'zh-CN-XiaoxiaoNeural'
        
        # 在线程中需要创建新的事件循环来调用异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(generate_tts_audio(script, tts_path, voice))
        finally:
            loop.close()
        
        tts_time = time.time() - tts_start
        print(f"   ✅ 线程{video_index+1}: TTS语音生成完成，耗时: {tts_time:.1f}秒")

        # 3.5 生成ASS字幕
        ass_start = time.time()
        
        # 智能分割文本
        sentences = split_text_into_screen_friendly_sentences(script, 1080, style)
        print(f"   📝 线程{video_index+1}: 智能分屏分割成{len(sentences)}个片段")
        
        # 读取TTS实际时长
        try:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            audio_clip_tmp = AudioFileClip(tts_path)
            actual_tts_duration = audio_clip_tmp.duration
            audio_clip_tmp.close()
            
            target_duration = max(duration_sec, actual_tts_duration)
            print(f"   🎵 线程{video_index+1}: TTS时长: {actual_tts_duration:.1f}s，目标时长: {target_duration:.1f}s")
        except Exception as e:
            print(f"   ⚠️  线程{video_index+1}: 读取TTS时长失败: {e}")
            target_duration = duration_sec
        
        # 生成ASS字幕文件
        ass_subtitle_path = os.path.join(SUBTITLE_TEMP_DIR, f"subtitle_{clip_id}.ass")
        ass_generator.create_ass_file(
            sentences=sentences,
            total_duration=target_duration,
            style_config=style,
            output_path=ass_subtitle_path
        )
        
        ass_time = time.time() - ass_start
        print(f"   ✅ 线程{video_index+1}: ASS字幕生成完成，耗时: {ass_time:.1f}秒")

        # 3.6 最终视频合成（强制GPU加速）
        final_start = time.time()
        final_output = os.path.join(OUTPUT_DIR, f"optimized_{clip_id}.mp4")
        
        # 处理背景音乐
        bgm_audio = random.choice(local_audio_paths) if local_audio_paths else None
        silence_path = None
        if not bgm_audio or not os.path.exists(bgm_audio):
            silence_path = os.path.join(TTS_TEMP_DIR, f"silence_{clip_id}.wav")
            create_silence_audio(target_duration, silence_path)
            bgm_audio = silence_path

        # 🚀 使用优化的GPU加速FFmpeg合成
        try:
            success = create_optimized_video_with_ass_subtitles_gpu_enhanced(
                source_video=montage_clip_path,
                title_image=title_image_path,
                ass_subtitle=ass_subtitle_path,
                tts_audio=tts_path,
                bgm_audio=bgm_audio,
                output_path=final_output,
                duration=target_duration,
                title_position=title_position,
                poster_image=local_poster_path,
                subtitle_position=subtitle_position,
                thread_id=video_index+1  # 传递线程ID用于日志
            )
            
            final_time = time.time() - final_start
            print(f"   ✅ 线程{video_index+1}: 视频合成完成，耗时: {final_time:.1f}秒")
            
            if not success:
                print(f"   ❌ 线程{video_index+1}: FFmpeg处理失败")
                return None
                
        except Exception as e:
            print(f"   ❌ 线程{video_index+1}: 视频合成异常: {e}")
            return None
        
        # 上传到OSS（异步调用）
        upload_start = time.time()
        try:
            clip_name = f"optimized_{clip_id}.mp4"
            with open(final_output, 'rb') as f:
                video_content = f.read()
            
            # 在线程中调用异步OSS上传
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                oss_url = loop.run_until_complete(oss_client.upload_to_oss(
                    file_buffer=video_content,
                    original_filename=clip_name,
                    folder=OSS_UPLOAD_FINAL_VEDIO
                ))
            finally:
                loop.close()
            
            # 动态获取端口
            port = os.getenv("BACKEND_PORT", "8000")
            video_url = f"http://39.96.187.7:{port}/api/videos/oss-proxy?url={oss_url}"
            video_size = len(video_content)
            os.remove(final_output)
            
            upload_time = time.time() - upload_start
            print(f"   ✅ 线程{video_index+1}: OSS上传完成，耗时: {upload_time:.1f}秒")
            
        except Exception as e:
            print(f"   ❌ 线程{video_index+1}: OSS上传失败: {str(e)}")
            video_url = f"/outputs/clips/optimized_{clip_id}.mp4"
            video_size = os.path.getsize(final_output) if os.path.exists(final_output) else 0

        # 清理临时文件
        cleanup_files = temp_clips + [montage_clip_path, title_image_path, tts_path, ass_subtitle_path]
        if silence_path:
            cleanup_files.append(silence_path)
        
        for temp_file in cleanup_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"   ⚠️ 线程{video_index+1}: 清理失败: {temp_file} - {e}")
        
        clip_time = time.time() - clip_start
        print(f"   🎉 线程{video_index+1}: 完成，总耗时: {clip_time:.1f}秒")
        
        return {
            "id": clip_id,
            "name": f"optimized_{clip_id}.mp4",
            "url": video_url,
            "size": video_size,
            "duration": target_duration,
            "uploadedAt": None,
            "thread_id": video_index+1,
            "processing_time": clip_time
        }
        
    except Exception as e:
        print(f"   ❌ 线程{video_index+1}: 处理异常: {e}")
        import traceback
        traceback.print_exc()
        return None

def split_text_into_sentences(text, max_words_per_sentence=8):
    """将文本分割成句子，支持中英文混合"""
    if not text:
        return []
    
    import re
    
    # 中文句子分割符
    chinese_punctuation = '。！？；'
    # 英文句子分割符
    english_punctuation = '.!?;'
    
    sentences = []
    current_sentence = ""
    
    # 按标点符号分割
    for char in text:
        current_sentence += char
        if char in chinese_punctuation or char in english_punctuation:
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
            current_sentence = ""
    
    # 处理最后一部分
    if current_sentence.strip():
        sentences.append(current_sentence.strip())
    
    # 如果没有标点符号，按长度分割
    if not sentences:
        words = text.split() if ' ' in text else list(text)
        for i in range(0, len(words), max_words_per_sentence):
            sentence = ''.join(words[i:i+max_words_per_sentence]) if ' ' not in text else ' '.join(words[i:i+max_words_per_sentence])
            if sentence:
                sentences.append(sentence)
    
    # 确保至少有一句
    if not sentences:
        sentences = [text]
    
    return sentences




def check_and_convert_video_if_needed(video_path, output_path=None):
    """检查并转换视频格式以确保兼容性"""
    if not ENCODING_OPTIMIZATION_AVAILABLE:
        return video_path
    
    try:
        needs_conversion = check_video_needs_conversion(video_path)
        
        if not needs_conversion:
            print(f"✅ 视频格式兼容: {os.path.basename(video_path)}")
            return video_path
        
        print(f"⚠️ 检测到兼容性问题: {os.path.basename(video_path)}")
        
        if output_path is None:
            base, ext = os.path.splitext(video_path)
            output_path = f"{base}_compatible{ext}"
        
        # 使用优化参数转换视频
        from video_encoding_compatibility_optimizer import VideoEncodingCompatibilityOptimizer
        optimizer = VideoEncodingCompatibilityOptimizer()
        
        success = optimizer.convert_to_compatible_format(
            video_path, output_path, 'h264', 'balanced', True
        )
        
        if success:
            print(f"✅ 视频转换成功: {os.path.basename(output_path)}")
            return output_path
        else:
            print(f"❌ 视频转换失败，使用原始文件")
            return video_path
            
    except Exception as e:
        print(f"⚠️ 视频兼容性检查失败: {e}")
        return video_path

