#!/usr/bin/env python3
"""
ASS字幕服务模块
高性能动态字幕实现，替代PNG图片方案
"""
import os
import re
from datetime import timedelta
from typing import List, Dict, Any, Optional
from uuid import uuid4

class ASSSubtitleGenerator:
    """ASS字幕生成器"""
    
    def __init__(self):
        self.temp_dir = "outputs/subtitle_ass"
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def create_ass_file(self, sentences: List[str], total_duration: float, style_config: Optional[Dict[str, Any]] = None, output_path: Optional[str] = None) -> str:
        """
        生成ASS字幕文件
        
        Args:
            sentences: 字幕句子列表
            total_duration: 总时长（秒）
            style_config: 样式配置
            output_path: 输出路径，如果为None则自动生成
        
        Returns:
            ASS文件路径
        """
        if not sentences:
            return self._create_empty_ass_file(output_path)
        
        if output_path is None:
            output_path = os.path.join(self.temp_dir, f"subtitle_{uuid4().hex[:8]}.ass")
        
        # 解析样式配置
        style = self._parse_style_config(style_config)
        
        # 生成ASS内容
        ass_content = self._generate_ass_content(sentences, total_duration, style)
        
        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        print(f"✅ ASS字幕文件生成: {output_path}")
        print(f"   字幕数量: {len(sentences)}")
        print(f"   总时长: {total_duration:.1f}秒")
        
        return output_path
    
    def _parse_style_config(self, style_config: Dict[str, Any]) -> Dict[str, Any]:
        """解析样式配置"""
        if not style_config:
            return self._get_default_style()
        
        subtitle_style = style_config.get("subtitle", {})
        
        # 解析字体大小
        font_size = int(subtitle_style.get("fontSize", 48))
        
        # 解析颜色（转换为ASS格式）
        color = subtitle_style.get("color", "#FFFFFF")
        primary_color = self._hex_to_ass_color(color)
        
        # 解析字体
        font_family = subtitle_style.get("fontFamily", "Microsoft YaHei")
        font_name = self._get_font_name(font_family)
        
        # 解析位置
        position = subtitle_style.get("position", "bottom")
        alignment, margin_v = self._get_position_settings(position)
        
        return {
            "font_name": font_name,
            "font_size": font_size,
            "primary_color": primary_color,
            "outline_color": "&H00000000",  # 黑色描边
            "back_color": "&H80000000",     # 半透明背景
            "alignment": alignment,
            "margin_v": margin_v,
            "outline": 2,                   # 描边宽度
            "shadow": 2                     # 阴影
        }
    
    def _get_default_style(self) -> Dict[str, Any]:
        """获取默认样式"""
        return {
            "font_name": "Microsoft YaHei",
            "font_size": 20,                # 默认20号字体
            "primary_color": "&H00FFFFFF",  # 白色
            "outline_color": "&H00000000",  # 黑色描边
            "back_color": "&H80000000",     # 半透明背景
            "alignment": 8,                 # 顶部居中（适合横屏）
            "margin_v": 173,               # 距上边框1372.4像素（按1920x1080比例约为173）
            "outline": 2,
            "shadow": 0                    # 无阴影
        }
    
    def _hex_to_ass_color(self, hex_color: str) -> str:
        """将十六进制颜色转换为ASS格式"""
        # 移除#号
        hex_color = hex_color.lstrip('#')
        
        # 确保是6位十六进制
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])
        elif len(hex_color) != 6:
            hex_color = "FFFFFF"  # 默认白色
        
        # 转换为BGR格式（ASS使用BGR而不是RGB）
        r = hex_color[0:2]
        g = hex_color[2:4]
        b = hex_color[4:6]
        
        # ASS格式：&H00BBGGRR
        return f"&H00{b}{g}{r}".upper()
    
    def _get_font_name(self, font_family: str) -> str:
        """获取字体名称，处理字体映射"""
        font_mapping = {
            'Arial, sans-serif': 'Arial',
            'Microsoft YaHei, sans-serif': 'Microsoft YaHei',
            'SimSun, serif': 'SimSun',
            'SimHei, sans-serif': 'SimHei',
            'KaiTi, serif': 'KaiTi',
            'LIULISONG': 'LIULISONG',
            'MiaobiJunli': '妙笔珺俐体',
            'MiaobiDuanmu': '妙笔段慕体',
            'SourceHanSansCN-Heavy': 'Arial'  # 修复字体映射，使用系统默认字体
        }
        
        # 优先使用系统常见字体，避免字体选择错误
        mapped_font = font_mapping.get(font_family, 'Arial')
        
        # 如果是中文字体，优先使用微软雅黑
        if any(char in mapped_font for char in ['妙笔', '思源', 'Source Han']):
            return 'Microsoft YaHei'
        
        return mapped_font
    
    def _get_position_settings(self, position: str) -> tuple:
        """获取位置设置"""
        position_mapping = {
            "top": (8, 80),        # 顶部居中，上边距80（为主标题留空间）
            "center": (5, 0),      # 中部居中
            "bottom": (2, 120),    # 底部居中，下边距120（防止被底部UI遮挡）
            "template1": (8, 173)  # 模板位置1（横屏视频），顶部居中，距上边框173像素
        }
        
        return position_mapping.get(position, (8, 173))
    
    def _generate_ass_content(self, sentences: List[str], total_duration: float, style: Dict[str, Any]) -> str:
        """生成ASS文件内容"""
        
        # ASS文件头部 - 添加PlayResX和PlayResY设置
        header = f"""[Script Info]
Title: AI Generated Dynamic Subtitles
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['font_name']},{style['font_size']},{style['primary_color']},&H000000FF,{style['outline_color']},{style['back_color']},0,0,0,0,100,100,0,0,1,{style['outline']},{style['shadow']},{style['alignment']},80,80,{style['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # 计算每句字幕的时间分配
        sentence_timings = self._calculate_sentence_timings(sentences, total_duration)
        
        # 生成字幕事件
        events = []
        for i, (sentence, start_time, end_time) in enumerate(sentence_timings):
            start_ass = self._seconds_to_ass_time(start_time)
            end_ass = self._seconds_to_ass_time(end_time)
            
            # 清理文本（移除可能影响ASS的特殊字符）
            clean_text = self._clean_text_for_ass(sentence)
            
            event = f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{clean_text}"
            events.append(event)
            
            print(f"   字幕{i+1}: {start_time:.1f}s-{end_time:.1f}s '{sentence[:30]}...'")
        
        return header + "\n".join(events) + "\n"
    
    def _calculate_sentence_timings(self, sentences: List[str], total_duration: float) -> List[tuple]:
        """计算每句字幕的显示时间"""
        if not sentences:
            return []
        
        timings = []
        
        # 根据句子长度分配时间权重
        sentence_lengths = [len(sentence) for sentence in sentences]
        total_length = sum(sentence_lengths)
        
        current_time = 0.0
        
        for i, sentence in enumerate(sentences):
            # 按长度比例分配时间
            if total_length > 0:
                weight = sentence_lengths[i] / total_length
                duration = total_duration * weight
            else:
                duration = total_duration / len(sentences)
            
            # 设置最小和最大显示时间
            min_duration = 1.5  # 最少显示1.5秒
            max_duration = 5.0   # 最多显示5秒
            
            duration = max(min_duration, min(duration, max_duration))
            
            # 如果是最后一句，确保不超过总时长
            if i == len(sentences) - 1:
                duration = min(duration, total_duration - current_time)
            
            start_time = current_time
            end_time = start_time + duration
            
            timings.append((sentence, start_time, end_time))
            current_time = end_time
            
            # 如果时间用完了，停止
            if current_time >= total_duration:
                break
        
        return timings
    
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """将秒数转换为ASS时间格式 (H:MM:SS.DD)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        
        return f"{hours:01d}:{minutes:02d}:{secs:05.2f}"
    
    def _clean_text_for_ass(self, text: str) -> str:
        """清理并处理文本用于ASS格式，包含自动换行"""
        # 自动换行处理
        text = self._auto_wrap_text(text)
        
        # 移除或转义ASS特殊字符
        text = text.replace('{', '\\{').replace('}', '\\}')
        text = text.replace('\n', '\\N')  # ASS换行符
        
        # 移除多余的空格
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _auto_wrap_text(self, text: str, max_chars_per_line: int = 20) -> str:
        """自动换行处理，确保字幕不会超出屏幕边界"""
        if len(text) <= max_chars_per_line:
            return text
        
        # 按标点符号优先断句
        punctuation = ['，', '。', '！', '？', ',', '.', '!', '?', '；', ';']
        words = []
        current_word = ""
        
        for char in text:
            current_word += char
            if char in punctuation or len(current_word) >= max_chars_per_line:
                words.append(current_word.strip())
                current_word = ""
        
        if current_word.strip():
            words.append(current_word.strip())
        
        # 重新组合，确保每行不超过最大字符数
        lines = []
        current_line = ""
        
        for word in words:
            if len(current_line + word) <= max_chars_per_line:
                current_line += word
            else:
                if current_line:
                    lines.append(current_line.strip())
                current_line = word
        
        if current_line:
            lines.append(current_line.strip())
        
        return '\n'.join(lines)
    
    def _create_empty_ass_file(self, output_path: str = None) -> str:
        """创建空的ASS文件"""
        if output_path is None:
            output_path = os.path.join(self.temp_dir, f"empty_{uuid4().hex[:8]}.ass")
        
        # 空ASS文件内容 - 添加PlayResX和PlayResY设置
        empty_content = """[Script Info]
Title: Empty Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,2,2,30,30,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(empty_content)
        
        return output_path
    
    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            import glob
            temp_files = glob.glob(os.path.join(self.temp_dir, "*.ass"))
            for file_path in temp_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
            print(f"🧹 清理了 {len(temp_files)} 个临时ASS文件")
        except Exception as e:
            print(f"清理临时文件失败: {e}")

# 全局实例
ass_generator = ASSSubtitleGenerator()
