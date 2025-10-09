"""
优化的视频剪辑服务 - 集成FFmpeg处理器和并发管理器
替代原有的MoviePy密集型操作，提供高性能视频处理
"""

import os
import asyncio
import time
from typing import List, Dict, Any, Optional
from uuid import uuid4
import logging

# 导入新的优化模块
from .ffmpeg_video_processor import get_video_processor
from .concurrent_video_manager import get_video_manager
from .ass_subtitle_service import ass_generator
from .smart_material_cache import smart_cache

# 导入原有模块（保持兼容性）
from models.oss_client import OSSClient

logger = logging.getLogger(__name__)

class OptimizedClipService:
    """优化的视频剪辑服务"""
    
    def __init__(self):
        self.video_processor = get_video_processor(gpu_enabled=True)
        self.video_manager = get_video_manager()
        self.oss_client = OSSClient()
        
        # 注册任务处理器
        self._register_processors()
        
        # 启动管理器
        self._manager_started = False
    
    async def _ensure_manager_started(self):
        """确保管理器已启动"""
        if not self._manager_started:
            await self.video_manager.start()
            self._manager_started = True
    
    def _register_processors(self):
        """注册任务处理器"""
        self.video_manager.register_processor('montage', self._process_montage_task)
        self.video_manager.register_processor('subtitle', self._process_subtitle_task)
        self.video_manager.register_processor('encode', self._process_encode_task)
        self.video_manager.register_processor('upload', self._process_upload_task)
    
    async def process_clips_optimized(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """优化的视频处理主函数"""
        await self._ensure_manager_started()
        
        start_time = time.time()
        
        try:
            # 解析请求参数
            video_count = request_data.get('video_count', 1)
            duration_sec = request_data.get('duration', 30)
            scripts = request_data.get('scripts', [])
            style = request_data.get('style', {})
            local_video_paths = request_data.get('local_video_paths', [])
            local_audio_paths = request_data.get('local_audio_paths', [])
            
            logger.info(f"开始优化视频处理，数量: {video_count}, 时长: {duration_sec}s")
            
            # 第一阶段：并发创建视频蒙太奇
            montage_task_ids = []
            for i in range(video_count):
                task_id = await self.video_manager.submit_task(
                    task_type='montage',
                    params={
                        'source_paths': local_video_paths,
                        'target_duration': duration_sec,
                        'index': i,
                        'use_gpu': True
                    },
                    priority=1  # 高优先级
                )
                montage_task_ids.append(task_id)
            
            # 等待蒙太奇任务完成
            montage_results = await self._wait_for_tasks(montage_task_ids)
            
            if not montage_results:
                return {"success": False, "error": "蒙太奇创建失败"}
            
            # 第二阶段：并发处理字幕和音频
            final_task_ids = []
            for i, montage_path in enumerate(montage_results):
                if not montage_path or not os.path.exists(montage_path):
                    continue
                
                # 准备字幕和音频
                script = scripts[i % len(scripts)] if scripts else None
                bgm_path = local_audio_paths[i % len(local_audio_paths)] if local_audio_paths else None
                
                task_id = await self.video_manager.submit_task(
                    task_type='subtitle',
                    params={
                        'montage_path': montage_path,
                        'script': script.content if script else "",
                        'style': style,
                        'bgm_path': bgm_path,
                        'duration': duration_sec,
                        'index': i,
                        'use_gpu': True
                    },
                    priority=2
                )
                final_task_ids.append(task_id)
            
            # 等待最终处理完成
            final_results = await self._wait_for_tasks(final_task_ids)
            
            if not final_results:
                return {"success": False, "error": "视频最终处理失败"}
            
            # 第三阶段：并发上传到OSS
            upload_task_ids = []
            for video_path in final_results:
                if video_path and os.path.exists(video_path):
                    task_id = await self.video_manager.submit_task(
                        task_type='upload',
                        params={
                            'video_path': video_path,
                            'folder': 'final_videos'
                        },
                        priority=3
                    )
                    upload_task_ids.append(task_id)
            
            # 等待上传完成
            upload_results = await self._wait_for_tasks(upload_task_ids)
            
            # 构建返回结果
            result_videos = []
            for i, oss_url in enumerate(upload_results):
                if oss_url:
                    result_videos.append({
                        "video_url": oss_url,
                        "video_size": self._get_file_size(final_results[i]) if i < len(final_results) else 0,
                        "duration": duration_sec
                    })
            
            total_time = time.time() - start_time
            
            logger.info(f"优化视频处理完成，耗时: {total_time:.1f}s，成功: {len(result_videos)}")
            
            return {
                "success": True,
                "videos": result_videos,
                "processing_time": total_time,
                "performance_stats": self._get_performance_stats()
            }
            
        except Exception as e:
            logger.error(f"优化视频处理失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _wait_for_tasks(self, task_ids: List[str], timeout: int = 600) -> List[Any]:
        """等待任务完成"""
        results = []
        start_time = time.time()
        
        while task_ids and (time.time() - start_time) < timeout:
            completed_tasks = []
            
            for task_id in task_ids:
                task = self.video_manager.get_task_status(task_id)
                if task and task.status.value in ['completed', 'failed']:
                    completed_tasks.append(task_id)
                    if task.status.value == 'completed':
                        results.append(task.result)
                    else:
                        logger.error(f"任务失败: {task_id}, 错误: {task.error}")
                        results.append(None)
            
            # 移除已完成的任务
            for task_id in completed_tasks:
                task_ids.remove(task_id)
            
            if task_ids:
                await asyncio.sleep(1)
        
        # 处理超时的任务
        if task_ids:
            logger.warning(f"任务超时: {task_ids}")
            for _ in task_ids:
                results.append(None)
        
        return results
    
    async def _process_montage_task(self, params: Dict[str, Any]) -> Optional[str]:
        """处理蒙太奇任务"""
        try:
            source_paths = params['source_paths']
            target_duration = params['target_duration']
            index = params['index']
            
            # 使用FFmpeg处理器创建蒙太奇
            montage_results = await self.video_processor.create_montage_async(
                source_paths=source_paths,
                target_duration=target_duration,
                count=1
            )
            
            if montage_results:
                return montage_results[0]
            else:
                raise RuntimeError("蒙太奇创建失败")
                
        except Exception as e:
            logger.error(f"蒙太奇任务处理失败: {e}")
            raise
    
    async def _process_subtitle_task(self, params: Dict[str, Any]) -> Optional[str]:
        """处理字幕任务"""
        try:
            montage_path = params['montage_path']
            script = params['script']
            style = params['style']
            bgm_path = params['bgm_path']
            duration = params['duration']
            index = params['index']
            
            # 生成输出路径
            output_path = os.path.join(
                self.video_processor.work_dir,
                f"final_video_{index}_{int(time.time())}.mp4"
            )
            
            # 这里可以集成原有的字幕处理逻辑
            # 或者实现新的FFmpeg字幕处理
            success = await self._create_video_with_subtitles_ffmpeg(
                video_path=montage_path,
                script=script,
                style=style,
                bgm_path=bgm_path,
                output_path=output_path,
                duration=duration
            )
            
            if success and os.path.exists(output_path):
                return output_path
            else:
                raise RuntimeError("字幕处理失败")
                
        except Exception as e:
            logger.error(f"字幕任务处理失败: {e}")
            raise
    
    async def _process_encode_task(self, params: Dict[str, Any]) -> Optional[str]:
        """处理编码任务"""
        # 预留给未来的编码优化
        pass
    
    async def _process_upload_task(self, params: Dict[str, Any]) -> Optional[str]:
        """处理上传任务"""
        try:
            video_path = params['video_path']
            folder = params['folder']
            
            # 读取视频文件
            with open(video_path, 'rb') as f:
                video_content = f.read()
            
            # 上传到OSS
            filename = os.path.basename(video_path)
            oss_url = await self.oss_client.upload_to_oss(
                file_buffer=video_content,
                original_filename=filename,
                folder=folder
            )
            
            # 删除本地临时文件
            try:
                os.remove(video_path)
            except:
                pass
            
            return oss_url
            
        except Exception as e:
            logger.error(f"上传任务处理失败: {e}")
            raise
    
    async def _create_video_with_subtitles_ffmpeg(self, video_path: str, script: str,
                                                style: Dict, bgm_path: Optional[str],
                                                output_path: str, duration: int) -> bool:
        """使用FFmpeg创建带字幕的视频"""
        try:
            # 这里可以调用原有的FFmpeg字幕处理函数
            # 或者实现新的优化版本
            
            # 简化版实现：直接复制视频（后续可以扩展）
            import shutil
            shutil.copy2(video_path, output_path)
            return True
            
        except Exception as e:
            logger.error(f"FFmpeg字幕处理失败: {e}")
            return False
    
    def _get_file_size(self, file_path: str) -> int:
        """获取文件大小"""
        try:
            return os.path.getsize(file_path)
        except:
            return 0
    
    def _get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return self.video_manager.get_system_status()
    
    async def get_processing_status(self) -> Dict[str, Any]:
        """获取处理状态"""
        await self._ensure_manager_started()
        return self.video_manager.get_system_status()
    
    async def cleanup(self):
        """清理资源"""
        if self._manager_started:
            await self.video_manager.stop()
        self.video_processor.cleanup()

# 全局服务实例
_service_instance = None

def get_optimized_clip_service() -> OptimizedClipService:
    """获取优化的剪辑服务实例（单例模式）"""
    global _service_instance
    if _service_instance is None:
        _service_instance = OptimizedClipService()
    return _service_instance
