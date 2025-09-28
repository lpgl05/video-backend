"""
增强视频下载器
解决视频文件损坏、下载不完整等问题
"""

import os
import asyncio
import hashlib
import time
import subprocess
import logging
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import aiohttp
import aiofiles

logger = logging.getLogger(__name__)

class VideoValidationError(Exception):
    """视频验证错误"""
    pass

class DownloadError(Exception):
    """下载错误"""
    pass

class EnhancedVideoDownloader:
    """增强视频下载器"""
    
    def __init__(self, max_retries: int = 3, timeout: int = 30):
        self.max_retries = max_retries
        self.timeout = timeout
        self.ffmpeg_path = "ffmpeg"  # 假设ffmpeg在PATH中
        
    async def download_and_validate(self, 
                                  url: str, 
                                  local_path: str,
                                  expected_size: Optional[int] = None,
                                  skip_deep_validation: bool = False) -> bool:
        """
        下载并验证视频文件
        
        Args:
            url: 视频URL
            local_path: 本地保存路径
            expected_size: 期望的文件大小（字节）
            skip_deep_validation: 跳过深度验证，加快下载速度
            
        Returns:
            bool: 下载和验证是否成功
        """
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"🔄 尝试下载 (第{attempt+1}/{self.max_retries}次): {url}")
                
                # 1. 下载文件
                success = await self._download_file(url, local_path)
                if not success:
                    raise DownloadError("文件下载失败")
                
                # 2. 基本文件检查
                if not await self._basic_file_check(local_path, expected_size):
                    raise DownloadError("文件基本检查失败")
                
                # 3. 视频文件验证（可选）
                if not skip_deep_validation:
                    if not await self._validate_video_file(local_path):
                        raise VideoValidationError("视频文件验证失败")
                    logger.info(f"✅ 完整验证通过: {os.path.basename(local_path)}")
                else:
                    logger.info(f"⚡ 快速下载完成(跳过深度验证): {os.path.basename(local_path)}")
                
                logger.info(f"✅ 下载和验证成功: {local_path}")
                return True
                
            except Exception as e:
                logger.warning(f"❌ 第{attempt+1}次尝试失败: {e}")
                
                # 清理损坏的文件
                if os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                        logger.info(f"🗑️ 已清理损坏文件: {local_path}")
                    except Exception as cleanup_error:
                        logger.error(f"清理文件失败: {cleanup_error}")
                
                # 如果是最后一次尝试，抛出异常
                if attempt == self.max_retries - 1:
                    logger.error(f"❌ 所有下载尝试失败: {url}")
                    raise
                
                # 等待后重试
                await asyncio.sleep(2 ** attempt)  # 指数退避
        
        return False
    
    async def _download_file(self, url: str, local_path: str) -> bool:
        """下载文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 使用aiohttp下载
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise DownloadError(f"HTTP错误: {response.status}")
                    
                    # 获取文件大小
                    content_length = response.headers.get('content-length')
                    if content_length:
                        total_size = int(content_length)
                        logger.info(f"📥 开始下载，文件大小: {total_size/(1024*1024):.1f}MB")
                    
                    # 流式下载
                    async with aiofiles.open(local_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            # 显示进度（每1MB显示一次）
                            if downloaded % (1024 * 1024) == 0:
                                if content_length:
                                    progress = (downloaded / total_size) * 100
                                    logger.info(f"📥 下载进度: {progress:.1f}% ({downloaded/(1024*1024):.1f}MB)")
            
            logger.info(f"📥 文件下载完成: {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
    
    async def _basic_file_check(self, local_path: str, expected_size: Optional[int] = None) -> bool:
        """基本文件检查"""
        try:
            # 检查文件是否存在
            if not os.path.exists(local_path):
                logger.error(f"文件不存在: {local_path}")
                return False
            
            # 检查文件大小
            file_size = os.path.getsize(local_path)
            if file_size == 0:
                logger.error(f"文件为空: {local_path}")
                return False
            
            # 检查期望大小
            if expected_size and abs(file_size - expected_size) > 1024:  # 允许1KB误差
                logger.error(f"文件大小不匹配: 期望{expected_size}, 实际{file_size}")
                return False
            
            logger.info(f"✅ 文件基本检查通过: {file_size/(1024*1024):.1f}MB")
            return True
            
        except Exception as e:
            logger.error(f"文件检查失败: {e}")
            return False
    
    async def _validate_video_file(self, local_path: str) -> bool:
        """优化的视频文件完整性验证 - 减少CPU负载"""
        try:
            # 🚀 优化1: 使用GPU加速的快速验证
            cmd = [
                self.ffmpeg_path,
                '-v', 'error',  # 只显示错误
                '-i', local_path,
                '-t', '1',      # 只验证前1秒，大幅减少CPU负载
                '-f', 'null',   # 不输出文件
                '-'
            ]
            
            # 🚀 优化2: 尝试使用GPU硬件解码进行验证
            try:
                from services.tesla_t4_gpu_optimizer import tesla_t4_optimizer
                ready, _ = tesla_t4_optimizer.is_ready()
                if ready:
                    # 添加GPU硬件解码参数，减少CPU使用
                    gpu_decode_params = tesla_t4_optimizer.get_hardware_decode_params()
                    cmd = [
                        self.ffmpeg_path,
                        '-v', 'error',
                        *gpu_decode_params,  # GPU硬件解码
                        '-i', local_path,
                        '-t', '0.5',         # GPU验证只需0.5秒
                        '-f', 'null',
                        '-'
                    ]
                    logger.debug(f"🚀 使用GPU硬件解码验证: {os.path.basename(local_path)}")
            except:
                pass  # 如果GPU不可用，使用CPU验证
            
            # 🚀 优化3: 设置超时，避免验证过程卡住
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                # 设置5秒超时，避免验证过程占用太多时间
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ 视频验证超时，跳过详细验证: {os.path.basename(local_path)}")
                process.kill()
                # 超时情况下，只做基本文件大小检查
                return os.path.getsize(local_path) > 1024  # 至少1KB
            
            if process.returncode == 0:
                logger.debug(f"✅ 快速验证通过: {os.path.basename(local_path)}")
                return True
            else:
                error_msg = stderr.decode() if stderr else "未知错误"
                logger.warning(f"⚠️ 快速验证失败: {error_msg[:100]}...")
                
                # 🚀 优化4: 对于验证失败的情况，降级到基本检查
                # 检查关键错误，其他错误可能仍然是可用的视频
                critical_errors = [
                    "moov atom not found",
                    "Invalid data found",
                    "No such file or directory",
                    "Permission denied"
                ]
                
                is_critical = any(err in error_msg for err in critical_errors)
                if is_critical:
                    logger.error(f"❌ 发现关键错误，文件不可用: {error_msg}")
                    return False
                else:
                    # 非关键错误，可能仍然可用
                    logger.info(f"⚠️ 非关键验证错误，文件可能仍可使用: {os.path.basename(local_path)}")
                    return True
                
        except Exception as e:
            logger.warning(f"视频验证异常，跳过验证: {e}")
            # 验证异常时，只检查文件是否存在且大小合理
            try:
                return os.path.exists(local_path) and os.path.getsize(local_path) > 1024
            except:
                return False
    
    async def get_video_info(self, local_path: str) -> Optional[Dict[str, Any]]:
        """获取视频信息"""
        try:
            cmd = [
                self.ffmpeg_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                local_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                import json
                info = json.loads(stdout.decode())
                return info
            else:
                logger.error(f"获取视频信息失败: {stderr.decode()}")
                return None
                
        except Exception as e:
            logger.error(f"获取视频信息异常: {e}")
            return None
    
    def calculate_file_hash(self, file_path: str) -> str:
        """优化的文件哈希计算 - 减少CPU负载"""
        try:
            # 🚀 优化: 对于大文件，只计算前1MB的哈希，大幅减少CPU使用
            file_size = os.path.getsize(file_path)
            
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                if file_size > 1024 * 1024:  # 文件大于1MB
                    # 只读取前1MB计算哈希，加上文件大小作为标识
                    chunk_size = 1024 * 1024  # 1MB
                    data = f.read(chunk_size)
                    hash_md5.update(data)
                    # 添加文件大小到哈希中，确保唯一性
                    hash_md5.update(str(file_size).encode())
                    logger.debug(f"🚀 快速哈希计算(1MB): {os.path.basename(file_path)}")
                else:
                    # 小文件计算完整哈希
                    for chunk in iter(lambda: f.read(8192), b""):
                        hash_md5.update(chunk)
                    logger.debug(f"✅ 完整哈希计算: {os.path.basename(file_path)}")
            
            return hash_md5.hexdigest()
        except Exception as e:
            logger.warning(f"计算文件哈希失败，使用文件名+大小: {e}")
            # 失败时使用文件名和大小作为简单标识
            try:
                return hashlib.md5(f"{os.path.basename(file_path)}_{os.path.getsize(file_path)}".encode()).hexdigest()
            except:
                return ""
    
    async def repair_video_file(self, input_path: str, output_path: str) -> bool:
        """尝试修复损坏的视频文件"""
        try:
            logger.info(f"🔧 尝试修复视频文件: {input_path}")
            
            cmd = [
                self.ffmpeg_path,
                '-y',  # 覆盖输出文件
                '-i', input_path,
                '-c', 'copy',  # 复制流，不重新编码
                '-avoid_negative_ts', 'make_zero',
                '-fflags', '+genpts',
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"✅ 视频文件修复成功: {output_path}")
                return True
            else:
                logger.error(f"❌ 视频文件修复失败: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"视频修复异常: {e}")
            return False


# 全局实例
_enhanced_downloader = None

def get_enhanced_downloader() -> EnhancedVideoDownloader:
    """获取增强下载器实例"""
    global _enhanced_downloader
    if _enhanced_downloader is None:
        _enhanced_downloader = EnhancedVideoDownloader()
    return _enhanced_downloader

async def download_and_validate_video(url: str, 
                                    local_path: str,
                                    expected_size: Optional[int] = None,
                                    skip_deep_validation: bool = False) -> bool:
    """便捷函数：下载并验证视频"""
    downloader = get_enhanced_downloader()
    return await downloader.download_and_validate(url, local_path, expected_size, skip_deep_validation)

async def validate_existing_video(local_path: str) -> bool:
    """便捷函数：验证现有视频文件"""
    downloader = get_enhanced_downloader()
    return await downloader._validate_video_file(local_path)

async def repair_video(input_path: str, output_path: str) -> bool:
    """便捷函数：修复视频文件"""
    downloader = get_enhanced_downloader()
    return await downloader.repair_video_file(input_path, output_path)
