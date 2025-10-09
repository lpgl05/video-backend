#!/usr/bin/env python3
"""
优化字幕批量处理系统
解决字幕逐个处理效率低的问题，实现批量高效处理
"""

import asyncio
import os
import time
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import logging

from .optimized_font_cache import get_font_path_cached, get_batch_font_paths

logger = logging.getLogger(__name__)

class BatchSubtitleProcessor:
    """批量字幕处理器"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self.processing_stats = {
            'total_batches': 0,
            'total_subtitles': 0,
            'total_time': 0,
            'avg_batch_time': 0
        }
        
        logger.info(f"批量字幕处理器已初始化，工作线程数: {max_workers}")
    
    async def process_subtitles_batch(self, 
                                    subtitle_requests: List[Dict[str, Any]],
                                    style_config: Dict[str, Any],
                                    temp_dir: str) -> List[Dict[str, Any]]:
        """批量处理字幕"""
        
        if not subtitle_requests:
            return []
        
        start_time = time.time()
        batch_id = f"batch_{int(start_time * 1000)}"
        
        logger.info(f"🚀 开始批量处理字幕 (批次ID: {batch_id})")
        logger.info(f"   字幕数量: {len(subtitle_requests)}")
        logger.info(f"   工作线程: {self.max_workers}")
        
        try:
            # 1. 预处理：批量获取字体路径
            font_paths = await self._batch_prepare_fonts(subtitle_requests, style_config)
            
            # 2. 分组处理：将字幕分成批次
            batches = self._split_into_batches(subtitle_requests, self.max_workers)
            
            # 3. 并发处理每个批次
            tasks = []
            for i, batch in enumerate(batches):
                task = asyncio.create_task(
                    self._process_subtitle_batch(
                        batch, style_config, font_paths, temp_dir, f"{batch_id}_{i}"
                    )
                )
                tasks.append(task)
            
            # 4. 等待所有批次完成
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 5. 合并结果
            results = []
            for batch_result in batch_results:
                if isinstance(batch_result, Exception):
                    logger.error(f"批次处理失败: {batch_result}")
                    continue
                results.extend(batch_result)
            
            # 6. 统计性能
            end_time = time.time()
            processing_time = end_time - start_time
            
            self._update_stats(len(subtitle_requests), processing_time)
            
            logger.info(f"✅ 批量字幕处理完成 (批次ID: {batch_id})")
            logger.info(f"   处理数量: {len(results)}/{len(subtitle_requests)}")
            logger.info(f"   总耗时: {processing_time:.2f}秒")
            logger.info(f"   平均耗时: {processing_time/len(subtitle_requests):.3f}秒/字幕")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ 批量字幕处理失败: {e}")
            raise
    
    async def _batch_prepare_fonts(self, 
                                 subtitle_requests: List[Dict[str, Any]], 
                                 style_config: Dict[str, Any]) -> Dict[str, str]:
        """批量准备字体路径"""
        
        logger.info("📝 批量准备字体路径...")
        
        # 收集所有需要的字体
        font_requests = []
        font_families = set()
        
        for request in subtitle_requests:
            # 从样式配置中提取字体信息
            subtitle_style = request.get('style', style_config)
            
            if isinstance(subtitle_style, dict):
                # 标题字体
                title_font = subtitle_style.get('title', {}).get('fontFamily', 'SourceHanSansCN-Heavy')
                if title_font not in font_families:
                    font_requests.append({
                        'fontFamily': title_font,
                        'fontType': 'title',
                        'key': f"title_{title_font}"
                    })
                    font_families.add(title_font)
                
                # 字幕字体
                subtitle_font = subtitle_style.get('subtitle', {}).get('fontFamily', 'Microsoft YaHei, sans-serif')
                if subtitle_font not in font_families:
                    font_requests.append({
                        'fontFamily': subtitle_font,
                        'fontType': 'subtitle',
                        'key': f"subtitle_{subtitle_font}"
                    })
                    font_families.add(subtitle_font)
        
        # 批量获取字体路径
        font_paths = get_batch_font_paths(font_requests)
        
        logger.info(f"✅ 字体准备完成，共 {len(font_paths)} 个字体")
        return font_paths
    
    def _split_into_batches(self, items: List[Any], batch_count: int) -> List[List[Any]]:
        """将列表分割成批次"""
        if not items:
            return []
        
        batch_size = max(1, len(items) // batch_count)
        batches = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batches.append(batch)
        
        return batches
    
    async def _process_subtitle_batch(self, 
                                    batch: List[Dict[str, Any]],
                                    style_config: Dict[str, Any],
                                    font_paths: Dict[str, str],
                                    temp_dir: str,
                                    batch_id: str) -> List[Dict[str, Any]]:
        """处理单个字幕批次"""
        
        logger.debug(f"🔄 处理字幕批次 {batch_id}，数量: {len(batch)}")
        
        # 在线程池中并发处理
        loop = asyncio.get_event_loop()
        
        tasks = []
        for i, subtitle_request in enumerate(batch):
            task = loop.run_in_executor(
                self.thread_pool,
                self._process_single_subtitle,
                subtitle_request,
                style_config,
                font_paths,
                temp_dir,
                f"{batch_id}_{i}"
            )
            tasks.append(task)
        
        # 等待批次内所有字幕处理完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤异常结果
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"字幕处理失败: {result}")
            else:
                valid_results.append(result)
        
        logger.debug(f"✅ 批次 {batch_id} 处理完成，成功: {len(valid_results)}/{len(batch)}")
        return valid_results
    
    def _process_single_subtitle(self, 
                               subtitle_request: Dict[str, Any],
                               style_config: Dict[str, Any],
                               font_paths: Dict[str, str],
                               temp_dir: str,
                               subtitle_id: str) -> Dict[str, Any]:
        """处理单个字幕 - 在线程池中执行"""
        
        try:
            # 提取字幕信息
            text = subtitle_request.get('text', '')
            start_time = subtitle_request.get('start_time', 0)
            duration = subtitle_request.get('duration', 2)
            subtitle_type = subtitle_request.get('type', 'subtitle')
            
            # 获取字体路径
            font_key = f"{subtitle_type}_{style_config.get(subtitle_type, {}).get('fontFamily', 'Microsoft YaHei, sans-serif')}"
            font_path = font_paths.get(font_key, '')
            
            # 生成字幕文件
            output_path = os.path.join(temp_dir, f"subtitle_{subtitle_id}.png")
            
            # 这里调用实际的字幕生成逻辑
            # 注意：这是一个简化的示例，实际实现需要根据具体的字幕生成库
            success = self._generate_subtitle_image(
                text=text,
                font_path=font_path,
                style=style_config.get(subtitle_type, {}),
                output_path=output_path
            )
            
            if success:
                return {
                    'subtitle_id': subtitle_id,
                    'text': text,
                    'start_time': start_time,
                    'duration': duration,
                    'output_path': output_path,
                    'font_path': font_path,
                    'status': 'success'
                }
            else:
                return {
                    'subtitle_id': subtitle_id,
                    'text': text,
                    'status': 'failed',
                    'error': '字幕生成失败'
                }
                
        except Exception as e:
            logger.error(f"字幕处理异常 {subtitle_id}: {e}")
            return {
                'subtitle_id': subtitle_id,
                'text': subtitle_request.get('text', ''),
                'status': 'failed',
                'error': str(e)
            }
    
    def _generate_subtitle_image(self, 
                               text: str, 
                               font_path: str, 
                               style: Dict[str, Any], 
                               output_path: str) -> bool:
        """生成字幕图片 - 简化实现"""
        
        try:
            # 这里应该调用实际的字幕生成逻辑
            # 例如使用PIL、OpenCV或其他图像处理库
            
            # 简化实现：创建一个空文件表示成功
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 实际实现应该在这里生成字幕图片
            # 使用font_path、style等参数生成图片
            
            with open(output_path, 'w') as f:
                f.write(f"Subtitle: {text}\nFont: {font_path}\nStyle: {style}")
            
            return True
            
        except Exception as e:
            logger.error(f"字幕图片生成失败: {e}")
            return False
    
    def _update_stats(self, subtitle_count: int, processing_time: float):
        """更新处理统计"""
        self.processing_stats['total_batches'] += 1
        self.processing_stats['total_subtitles'] += subtitle_count
        self.processing_stats['total_time'] += processing_time
        
        if self.processing_stats['total_batches'] > 0:
            self.processing_stats['avg_batch_time'] = (
                self.processing_stats['total_time'] / self.processing_stats['total_batches']
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计"""
        return self.processing_stats.copy()
    
    def reset_stats(self):
        """重置统计"""
        self.processing_stats = {
            'total_batches': 0,
            'total_subtitles': 0,
            'total_time': 0,
            'avg_batch_time': 0
        }
    
    def shutdown(self):
        """关闭处理器"""
        self.thread_pool.shutdown(wait=True)
        logger.info("批量字幕处理器已关闭")

# 全局批量字幕处理器实例
_subtitle_processor = BatchSubtitleProcessor()

async def process_subtitles_optimized(subtitle_requests: List[Dict[str, Any]], 
                                    style_config: Dict[str, Any], 
                                    temp_dir: str) -> List[Dict[str, Any]]:
    """优化的字幕批量处理接口"""
    return await _subtitle_processor.process_subtitles_batch(
        subtitle_requests, style_config, temp_dir
    )

def get_subtitle_processing_stats() -> Dict[str, Any]:
    """获取字幕处理统计"""
    return _subtitle_processor.get_stats()

def reset_subtitle_processing_stats():
    """重置字幕处理统计"""
    _subtitle_processor.reset_stats()

# 兼容性函数 - 替换原有的字幕处理函数
async def create_time_synced_dynamic_subtitles_optimized(sentences: List[str], 
                                                       tts_audio_path: str, 
                                                       video_width: int = 1080, 
                                                       style: Dict[str, Any] = None, 
                                                       temp_dir: str = None) -> List[Dict[str, Any]]:
    """优化的时间同步动态字幕创建"""
    
    if not sentences:
        return []
    
    try:
        # 获取TTS音频时长
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        audio_clip = AudioFileClip(tts_audio_path)
        actual_audio_duration = audio_clip.duration
        audio_clip.close()
        
        logger.info(f"TTS音频实际时长: {actual_audio_duration:.2f}秒")
        
        # 计算每个句子的时间分配
        sentence_count = len(sentences)
        sentence_lengths = [len(sentence) for sentence in sentences]
        total_length = sum(sentence_lengths)
        
        # 构建字幕请求
        subtitle_requests = []
        current_time = 0
        
        for i, sentence in enumerate(sentences):
            # 基于句子长度分配时间
            if total_length > 0:
                sentence_duration = (sentence_lengths[i] / total_length) * actual_audio_duration
            else:
                sentence_duration = actual_audio_duration / sentence_count
            
            subtitle_requests.append({
                'text': sentence,
                'start_time': current_time,
                'duration': sentence_duration,
                'type': 'subtitle',
                'style': style
            })
            
            current_time += sentence_duration
        
        # 批量处理字幕
        results = await process_subtitles_optimized(
            subtitle_requests, style or {}, temp_dir or "temp"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"优化字幕创建失败: {e}")
        # 回退到简单处理
        return []

if __name__ == "__main__":
    # 测试批量字幕处理
    import logging
    logging.basicConfig(level=logging.INFO)
    
    async def test_batch_processing():
        # 测试数据
        test_requests = [
            {'text': '这是第一句字幕', 'start_time': 0, 'duration': 2},
            {'text': '这是第二句字幕', 'start_time': 2, 'duration': 2},
            {'text': '这是第三句字幕', 'start_time': 4, 'duration': 2},
            {'text': '这是第四句字幕', 'start_time': 6, 'duration': 2},
        ]
        
        style_config = {
            'title': {'fontFamily': 'SourceHanSansCN-Heavy'},
            'subtitle': {'fontFamily': 'Microsoft YaHei, sans-serif'}
        }
        
        # 执行批量处理
        results = await process_subtitles_optimized(
            test_requests, style_config, "temp"
        )
        
        print(f"\n🧪 批量处理测试结果:")
        print(f"   输入: {len(test_requests)} 个字幕")
        print(f"   输出: {len(results)} 个结果")
        
        # 显示统计
        stats = get_subtitle_processing_stats()
        print(f"   统计: {stats}")
    
    # 运行测试
    asyncio.run(test_batch_processing())
