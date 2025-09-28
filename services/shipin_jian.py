import os
import numpy as np
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont

# --- 1. 参数配置 ---
# --- 1. 参数配置 ---
# ==== 配置路径 ====
data_dir = "d:\\code\\vscode\\vllm-demo\\data"
# 支持多个视频素材
video_paths = [
    os.path.join(data_dir, "21f8f8bb5b4c2663a60c440d7d7db83a.mp4"),
    # 可继续添加更多视频素材路径
    # os.path.join(data_dir, "another_video.mp4"),
]
bgm_path = os.path.join(data_dir, "111111111.mp3")
output_dir = os.path.join(data_dir, "outputs")
os.makedirs(output_dir, exist_ok=True)

# 注意：确保这个字体文件存在于你的系统中，或者和脚本在同一个文件夹下
# 否则中文会显示为乱码
font_path = r"C:\Windows\Fonts\msyh.ttc"  # Windows下微软雅黑，或换成你有的中文字体

# 三段文案内容
texts = [
    "AAAAAAAAAAAAAAAAAA，\nThis is a VEDIO。",
    "BBBBBBBBBBBBBBBBBBBBBBBBBBBB\n It's very funny.",
    "CCCCCCCCCCCCCCCCCCCCCCCCCCCC\n This is the end. 你好你好"
]

# 每个短视频的持续时间（秒）
# 这里我们假设每个短视频剪辑3秒，你可以根据需要修改
clip_duration = 10


# --- 2. 使用 Pillow 创建文字图片的核心函数 ---

def create_text_image(text, font_path, fontsize, size, font_color, bg_color):
    """
    使用 Pillow 在内存中创建一张包含文字的图片。
    :param text: 文案字符串
    :param font_path: 字体文件路径
    :param fontsize: 字体大小
    :param size: 图片尺寸 (width, height)
    :param font_color: 字体颜色 (R, G, B, A)
    :param bg_color: 背景颜色 (R, G, B, A)
    :return: PIL Image 对象
    """
    # 创建一个带透明通道的图片
    image = Image.new("RGBA", size, bg_color)
    draw = ImageDraw.Draw(image)

    # 加载字体
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except IOError:
        print(f"无法加载字体: {font_path}，将使用默认字体。")
        font = ImageFont.load_default()

    # 计算文字位置使其居中
    # draw.textbbox 在新版 Pillow 中用于精确获取边界
    try:
        text_bbox = draw.textbbox((0, 0), text, font=font, align="center")
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    except AttributeError: # 兼容旧版 Pillow
        text_width, text_height = draw.textsize(text, font=font)
        
    position = ((size[0] - text_width) / 2, (size[1] - text_height) / 2)

    # 在图片上绘制文字
    draw.text(position, text, font=font, fill=font_color, align="center")

    return image


# --- 3. 核心剪辑功能 ---

def create_short_video_without_imagemagick(video_clip, bgm_clip, text, output_filename):
    print(f"开始创建: {output_filename}...")

    final_clip = video_clip.set_audio(bgm_clip)
    w, h = final_clip.size

    # 1. 调用函数，使用 Pillow 生成文字图片
    # 背景设为完全透明 (0, 0, 0, 0)
    # 计算自适应字体大小，使文字宽度接近视频宽度的 80%
    max_width = int(w * 0.8)
    test_fontsize = 10
    font = None
    text_width = 0
    # 递增字体大小，直到宽度接近 max_width 或达到上限
    while True:
        try:
            font = ImageFont.truetype(font_path, test_fontsize)
        except IOError:
            font = ImageFont.load_default()
        dummy_img = Image.new("RGBA", (max_width, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy_img)
        try:
            bbox = draw.textbbox((0, 0), text, font=font, align="center")
            text_width = bbox[2] - bbox[0]
        except AttributeError:
            text_width, _ = draw.textsize(text, font=font)
        if text_width >= max_width or test_fontsize > 200:
            break
        test_fontsize += 2
    # 回退到合适的字体大小
    adaptive_fontsize = max(test_fontsize - 2, 10)

    text_img = create_text_image(
        text,
        font_path=font_path,
        fontsize=adaptive_fontsize,
        size=(max_width, h),  # 文字区域为视频宽度的 80%
        # 蓝色 (不透明)
        font_color=(0, 102, 255, 255),
        bg_color=(0, 0, 0, 0)  # 背景，完全透明
    )

    # 2. 将 Pillow 图片转换为 MoviePy 的 ImageClip
    # 注意：需要先将 PIL Image 转为 numpy 数组
    text_clip = ImageClip(np.array(text_img))
    
    # 3. 设置文字剪辑的持续时间和位置
    text_clip = text_clip.set_duration(final_clip.duration).set_pos(('center', 'center'))

    # 4. 叠加剪辑
    result_video = CompositeVideoClip([final_clip, text_clip])

    # 5. 写入文件
    result_video.write_videofile(
        output_filename, 
        codec="libx264", 
        audio_codec="aac",
        threads=4,
        ffmpeg_params=["-crf", "23"]
    )
    print(f"完成: {output_filename}")


# --- 4. 主逻辑 (与之前相同) ---

if __name__ == "__main__":
    # 检查所有视频素材
    missing = [p for p in video_paths if not os.path.exists(p)]
    if missing:
        print(f"错误：找不到视频文件: {missing}")
    elif not os.path.exists(bgm_path):
        print(f"错误：找不到背景音乐文件 '{bgm_path}'")
    else:
        # 合并所有视频素材
        video_clips = [VideoFileClip(p) for p in video_paths]
        if len(video_clips) == 1:
            merged_video = video_clips[0]
        else:
            merged_video = concatenate_videoclips(video_clips, method="compose")
        main_bgm = AudioFileClip(bgm_path)
        merged_duration = merged_video.duration
        n_clips = len(texts)

        for i, text in enumerate(texts):
            # --- 随机起点，保证能剪出足够数量 ---
            if merged_duration > clip_duration:
                max_start = merged_duration - clip_duration
                start_time = np.random.uniform(0, max_start)
            else:
                # 素材不够长，允许循环采样
                start_time = np.random.uniform(0, merged_duration)
            end_time = start_time + clip_duration

            # --- 处理跨越结尾的情况 ---
            if end_time <= merged_duration:
                video_subclip = merged_video.subclip(start_time, end_time)
            else:
                # 片段跨越结尾，拼接两段
                first = merged_video.subclip(start_time, merged_duration)
                second = merged_video.subclip(0, end_time - merged_duration)
                video_subclip = concatenate_videoclips([first, second])

            bgm_subclip = main_bgm.subclip(0, clip_duration)
            if bgm_subclip.duration < clip_duration:
                bgm_subclip = bgm_subclip.fx(vfx.loop, duration=clip_duration)

            output_filename = os.path.join(output_dir, f"short_video_{i+1}.mp4")
            create_short_video_without_imagemagick(video_subclip, bgm_subclip, text, output_filename)

        # 关闭所有视频资源
        for vc in video_clips:
            try:
                vc.close()
            except Exception:
                pass
        main_bgm.close()
        print("\n所有视频处理完成！")