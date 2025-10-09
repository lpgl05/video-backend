import oss2
import uuid
import os
from pathlib import Path
from typing import BinaryIO, Optional
import mimetypes
from dotenv import load_dotenv
from oss2.models import PartInfo
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import hashlib
import re
from config.upload_optimization import upload_config

# 加载.env文件中的环境变量
load_dotenv()

# 设置编码以避免中文路径问题
import sys
if sys.platform.startswith('win'):
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'Chinese (Simplified)_China.utf8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
        except locale.Error:
            # 如果设置失败，使用默认编码
            print("⚠️ 无法设置中文编码，使用默认编码")
            pass

# 设置环境变量编码
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

class OSSClient:
    def __init__(self):
        """初始化OSS客户端"""
        try:
            # OSS 客户端配置，从环境变量读取
            self.access_key_id = os.getenv("OSS_ACCESS_KEY_ID", "")
            self.access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET", "")
            self.endpoint = os.getenv("OSS_ENDPOINT", "oss-cn-beijing.aliyuncs.com")
            self.bucket_name = os.getenv("OSS_BUCKET_NAME", "tian-jiu-video")
            
            # 确保所有配置都是安全的字符串，避免编码问题
            # OSS配置通常应该是ASCII字符，不需要特殊编码处理
            if self.access_key_id:
                self.access_key_id = str(self.access_key_id).strip()
            if self.access_key_secret:
                self.access_key_secret = str(self.access_key_secret).strip()
            if self.endpoint:
                self.endpoint = str(self.endpoint).strip()
            if self.bucket_name:
                self.bucket_name = str(self.bucket_name).strip()
            
            # 创建认证对象
            auth = oss2.Auth(self.access_key_id, self.access_key_secret)
            
            # 创建Bucket对象
            self.bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)
            
            # 设置超时时间（连接超时，读取超时）
            self.bucket.timeout = (upload_config.CONNECTION_TIMEOUT, upload_config.READ_TIMEOUT)
            
            # 检查OSS权限（用于决定是否启用去重功能）
            self._oss_permission_checked = self._check_oss_permissions()
            
        except Exception as e:
            print(f"❌ OSS客户端初始化失败: {e}")
            # 创建一个空的bucket对象以避免后续错误
            self.bucket = None
            self._oss_permission_checked = False
    
    def _calculate_file_hash(self, file_buffer: bytes) -> str:
        """计算文件的MD5哈希值"""
        return hashlib.md5(file_buffer).hexdigest()
    
    def _check_oss_permissions(self) -> bool:
        """检查OSS权限，决定是否启用去重功能（使用head_object方法）"""
        try:
            # 使用head_object检查权限（更轻量级）
            test_key = 'permission_test_file'
            try:
                self.bucket.head_object(test_key)
                # 如果文件存在，说明有读取权限
                print(f"✅ OSS权限检查通过（文件存在），去重功能已启用")
                return True
            except oss2.exceptions.NoSuchKey:
                # 文件不存在是正常的，说明有读取权限
                print(f"✅ OSS权限检查通过（文件不存在但可访问），去重功能已启用")
                return True
            except Exception as e:
                print(f"⚠️ OSS权限检查失败: {e}，去重功能禁用")
                return False
        except Exception as e:
            print(f"⚠️ OSS权限检查失败: {e}，去重功能禁用")
            return False
    
    async def check_file_exists(self, file_hash: str, folder: str = 'uploads') -> Optional[str]:
        """
        检查OSS中是否已存在相同哈希的文件
        
        Args:
            file_hash: 文件MD5哈希值
            folder: 文件夹路径
            
        Returns:
            如果文件存在，返回文件URL；否则返回None
        """
        try:
            # 构造基于哈希的文件路径
            file_extensions = ['.mp4', '.mov', '.avi', '.mp3', '.wav', '.flac', '.jpg', '.jpeg', '.png', '.gif']
            
            # 尝试不同的文件扩展名
            for ext in file_extensions:
                object_key = f"{folder}/hash_{file_hash}{ext}"
                
                try:
                    # 使用head_object检查文件是否存在（更轻量级）
                    self.bucket.head_object(object_key)
                    # 如果没有抛出异常，说明文件存在
                    file_url = f"https://{self.bucket_name}.{self.endpoint}/{object_key}"
                    print(f"✅ 发现重复文件: {file_url}")
                    return file_url
                except oss2.exceptions.NoSuchKey:
                    # 文件不存在，继续尝试下一个扩展名
                    continue
                except Exception as e:
                    print(f"检查文件 {object_key} 时出错: {e}")
                    continue
            
            print(f"🔍 未找到哈希为 {file_hash} 的重复文件")
            return None
            
        except Exception as e:
            print(f"检查文件存在时出错: {e}")
            return None
    
    # 将文件上传至oss上 - 使用分片上传优化大文件
    async def upload_to_oss(self, file_buffer: bytes, original_filename: str,
                           folder: str = 'uploads', mimetype: Optional[str] = None) -> str:
        """不带进度回调的上传方法"""
        return await self.upload_to_oss_with_progress(file_buffer, original_filename, folder, mimetype, None)
    
    async def upload_to_oss_with_progress(self, file_buffer: bytes, original_filename: str,
                           folder: str = 'uploads', mimetype: Optional[str] = None,
                           progress_callback = None) -> str:
        """
        文件上传到OSS
        
        Args:
            file_buffer: 文件的二进制数据
            original_filename: 原始文件名
            folder: 存储文件夹，默认为'uploads'
            mimetype: 文件MIME类型，如果不提供则自动检测
            
        Returns:
            str: 上传后的文件URL
        """
        try:
            # 处理文件名编码问题，确保文件名只包含ASCII字符
            import urllib.parse
            
            # 获取文件扩展名
            file_extension = Path(original_filename).suffix.lower()
            
            # 计算文件哈希值
            file_hash = self._calculate_file_hash(file_buffer)
            
            # 构造预期的文件路径，使用哈希值避免中文字符问题
            expected_file_name = f"{folder}/hash_{file_hash}{file_extension}"
            
            # 确保文件路径只包含ASCII字符，避免编码问题
            # 直接使用正则表达式替换所有非ASCII字符，避免编码检查
            safe_filename = re.sub(r'[^\w\-_\./]', '_', expected_file_name)
            if safe_filename != expected_file_name:
                print(f"文件路径包含非ASCII字符，已替换为安全字符: {safe_filename}")
            expected_file_name = safe_filename
            
            # 检查是否已存在完全相同的文件
            try:
                # 检查OSS权限，如果有权限才进行去重检查
                if hasattr(self, '_oss_permission_checked') and self._oss_permission_checked:
                    self.bucket.head_object(expected_file_name)
                    # 如果没有抛出异常，说明文件已存在
                    existing_url = f"https://{self.bucket_name}.{self.endpoint}/{expected_file_name}"
                    print(f"🚀 文件已存在，跳过上传: {existing_url}")
                    # 模拟进度回调（立即完成）
                    if progress_callback:
                        progress_callback(100.0, len(file_buffer), 0)
                    return existing_url
                else:
                    print(f"⚠️ OSS去重功能已禁用（权限问题），直接上传: {expected_file_name}")
            except oss2.exceptions.NoSuchKey:
                # 文件不存在，需要上传
                print(f"🔍 文件不存在，开始上传: {expected_file_name}")
            except Exception as e:
                print(f"检查文件存在时出错: {e}，继续上传")
            
            # 生成基于哈希的文件名（便于去重识别）
            file_name = expected_file_name
            
            # 如果没有提供mimetype，则自动检测
            if not mimetype:
                # 使用安全的文件名进行MIME类型检测，避免编码问题
                # 确保文件名只包含ASCII字符
                safe_filename_for_mime = re.sub(r'[^\w\-_\.]', '_', original_filename)
                try:
                    mimetype, _ = mimetypes.guess_type(safe_filename_for_mime)
                except Exception as e:
                    print(f"MIME类型检测失败: {e}，使用默认类型")
                    mimetype = 'application/octet-stream'
                if not mimetype:
                    mimetype = 'application/octet-stream'
            
            # 设置请求头
            headers = {
                'Content-Type': mimetype,
            }
            
            # 确保文件名是UTF-8编码的字符串，避免OSS SDK内部编码问题
            try:
                # 确保file_name是字符串类型且只包含ASCII字符
                if isinstance(file_name, bytes):
                    file_name = file_name.decode('utf-8')
                # 再次确保只包含安全字符
                file_name = re.sub(r'[^\w\-_\./]', '_', file_name)
                print(f"最终上传文件名: {file_name}")
            except Exception as e:
                print(f"文件名编码处理失败: {e}")
                raise Exception(f"文件名编码处理失败: {e}")
            
            # 判断文件大小，决定使用简单上传还是分片上传
            file_size = len(file_buffer)
            multipart_threshold = upload_config.MULTIPART_THRESHOLD
            
            print(f"文件大小: {file_size / (1024*1024):.2f}MB")
            
            if file_size > multipart_threshold:
                print("使用分片上传...")
                result = self._multipart_upload(file_name, file_buffer, headers, progress_callback)
            else:
                print("使用简单上传...")
                try:
                    result = self.bucket.put_object(file_name, file_buffer, headers=headers)
                    if result.status != 200:
                        raise Exception(f"上传失败，状态码: {result.status}")
                    # 简单上传也要触发进度回调
                    if progress_callback:
                        progress_callback(100.0, file_size, file_size / 1.0)
                except Exception as e:
                    print(f"简单上传失败: {e}")
                    # 如果是编码相关错误，尝试进一步处理文件名
                    if 'latin-1' in str(e).lower() or 'codec' in str(e).lower():
                        print("检测到编码错误，尝试使用更安全的文件名")
                        # 使用更严格的文件名处理
                        safe_file_name = re.sub(r'[^a-zA-Z0-9\-_\./]', '_', file_name)
                        print(f"使用更安全的文件名重试: {safe_file_name}")
                        result = self.bucket.put_object(safe_file_name, file_buffer, headers=headers)
                        file_name = safe_file_name  # 更新文件名
                        if result.status != 200:
                            raise Exception(f"重试上传失败，状态码: {result.status}")
                        if progress_callback:
                            progress_callback(100.0, file_size, file_size / 1.0)
                    else:
                        raise e
            
            # 构造并返回文件URL
            return f"https://{self.bucket_name}.{self.endpoint}/{file_name}"
                
        except Exception as error:
            print(f'OSS上传失败: {error}')
            raise Exception('文件上传失败')
    
    def _multipart_upload(self, object_name: str, file_buffer: bytes, headers: dict = None, progress_callback = None):
        """
        分片上传实现
        
        Args:
            object_name: OSS对象名称
            file_buffer: 文件二进制数据
            headers: 请求头
        """
        try:
            file_size = len(file_buffer)
            # 使用配置化的动态分片大小
            part_size = upload_config.get_optimal_part_size(file_size)
            max_workers = upload_config.get_optimal_concurrency(file_size)
            
            print(f"开始分片上传: 文件大小{file_size / (1024*1024):.2f}MB, 每片{part_size / (1024*1024)}MB, 并发数{max_workers}")
            
            # 确保object_name编码正确
            try:
                if isinstance(object_name, bytes):
                    object_name = object_name.decode('utf-8')
                # 确保只包含安全字符
                object_name = re.sub(r'[^\w\-_\./]', '_', object_name)
                print(f"分片上传对象名: {object_name}")
            except Exception as e:
                print(f"分片上传对象名编码处理失败: {e}")
                raise Exception(f"分片上传对象名编码处理失败: {e}")
            
            # 初始化分片上传
            try:
                upload_result = self.bucket.init_multipart_upload(object_name, headers=headers)
                upload_id = upload_result.upload_id
            except Exception as e:
                print(f"初始化分片上传失败: {e}")
                if 'latin-1' in str(e).lower() or 'codec' in str(e).lower():
                    print("检测到编码错误，尝试使用更安全的对象名")
                    safe_object_name = re.sub(r'[^a-zA-Z0-9\-_\./]', '_', object_name)
                    print(f"使用更安全的对象名重试: {safe_object_name}")
                    upload_result = self.bucket.init_multipart_upload(safe_object_name, headers=headers)
                    upload_id = upload_result.upload_id
                    object_name = safe_object_name  # 更新对象名
                else:
                    raise e
            
            parts = []
            offset = 0
            part_number = 1
            
            start_time = time.time()
            
            # 准备所有分片信息
            part_info_list = []
            while offset < file_size:
                end_offset = min(offset + part_size, file_size)
                part_info_list.append({
                    'part_number': part_number,
                    'start': offset,
                    'end': end_offset,
                    'data': file_buffer[offset:end_offset]
                })
                offset = end_offset
                part_number += 1
            
            total_parts = len(part_info_list)
            print(f"总共 {total_parts} 个分片，开始并发上传...")
            
            # 并发上传分片
            uploaded_parts = []
            uploaded_bytes_lock = threading.Lock()
            uploaded_bytes = [0]  # 使用列表来避免闭包问题
            completed_parts = set()  # 记录已完成的分片，避免重复计算
            
            def upload_single_part(part_info):
                part_number = part_info['part_number']
                part_data = part_info['data']
                max_retries = 3
                
                for attempt in range(max_retries):
                    try:
                        print(f"上传分片 {part_number}: {part_info['start'] / (1024*1024):.1f}MB - {part_info['end'] / (1024*1024):.1f}MB (尝试 {attempt + 1}/{max_retries})")
                        
                        # 执行分片上传
                        try:
                            part_result = self.bucket.upload_part(object_name, upload_id, part_number, part_data)
                        except Exception as upload_error:
                            print(f"分片上传API调用失败: {upload_error}")
                            # 如果是编码相关错误，记录详细信息
                            if 'latin-1' in str(upload_error).lower() or 'codec' in str(upload_error).lower():
                                print(f"分片上传编码错误详情: object_name={object_name}, part_number={part_number}")
                            raise upload_error
                        
                        # 线程安全地更新进度
                        with uploaded_bytes_lock:
                            # 避免重复计算同一分片的进度
                            if part_number not in completed_parts:
                                uploaded_bytes[0] += len(part_data)
                                completed_parts.add(part_number)
                                current_uploaded = uploaded_bytes[0]
                                
                                progress = (current_uploaded / file_size) * 100
                                elapsed_time = time.time() - start_time
                                if elapsed_time > 0:
                                    speed = (current_uploaded / (1024*1024)) / elapsed_time
                                    # 减少日志输出频率，只在关键进度点输出
                                    if int(progress) % 20 == 0 or progress >= 95:
                                        print(f"OSS上传进度: {progress:.1f}%, 速度: {speed:.2f}MB/s")
                                    
                                    # 触发进度回调
                                    if progress_callback:
                                        progress_callback(progress, current_uploaded, speed)
                        
                        print(f"分片 {part_number} 上传成功")
                        return PartInfo(part_number, part_result.etag)
                        
                    except Exception as e:
                        print(f"分片 {part_number} 上传失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                        if hasattr(e, 'status') and hasattr(e, 'details'):
                            print(f"错误详情: status={e.status}, details={e.details}")
                        
                        if attempt == max_retries - 1:
                            # 最后一次尝试失败，抛出异常
                            raise e
                        else:
                            # 等待后重试
                            time.sleep(2 ** attempt)  # 指数退避
            
            # 使用线程池并发上传
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                try:
                    uploaded_parts = list(executor.map(upload_single_part, part_info_list))
                    # 按part_number排序
                    uploaded_parts.sort(key=lambda x: x.part_number)
                    parts = uploaded_parts
                except Exception as e:
                    print(f"并发上传失败: {e}")
                    # 取消分片上传
                    try:
                        self.bucket.abort_multipart_upload(object_name, upload_id)
                        print("已取消分片上传")
                    except:
                        pass
                    
                    # 如果分片上传失败，尝试单文件上传作为降级方案
                    print("尝试单文件上传作为降级方案...")
                    try:
                        result = self.bucket.put_object(object_name, file_buffer, headers=headers)
                        print("单文件上传成功")
                        # 更新进度为100%
                        if progress_callback:
                            progress_callback(100, file_size, file_size / (1024*1024) / (time.time() - start_time))
                        return f"https://{self.bucket_name}.{self.endpoint}/{object_name}"
                    except Exception as fallback_error:
                        print(f"单文件上传也失败: {fallback_error}")
                        raise e
            
            # 完成分片上传
            print("合并分片...")
            try:
                complete_result = self.bucket.complete_multipart_upload(object_name, upload_id, parts)
            except Exception as e:
                print(f"合并分片失败: {e}")
                if 'latin-1' in str(e).lower() or 'codec' in str(e).lower():
                    print(f"合并分片编码错误详情: object_name={object_name}, upload_id={upload_id}")
                raise e
            
            total_time = time.time() - start_time
            avg_speed = (file_size / (1024*1024)) / total_time
            print(f"分片上传完成! 总耗时: {total_time:.2f}秒, 平均速度: {avg_speed:.2f}MB/s")
            
            return complete_result
            
        except Exception as error:
            print(f'分片上传失败: {error}')
            # 清理未完成的分片上传
            try:
                self.bucket.abort_multipart_upload(object_name, upload_id)
                print("已清理未完成的分片上传")
            except:
                pass
            raise Exception(f'分片上传失败: {error}')
        
    # 根据url从oss上下载视频，将视频下载到本地文件夹里面
    async def download_video(self, url: str, local_path: str) -> None:
        """
        从OSS下载视频并保存到本地（增强版本，包含验证）

        Args:
            url: 视频的完整URL
            local_path: 本地保存路径
        """
        try:
            # 从URL中提取文件key
            key = url.split('.com/')[1]

            # 确保目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # 下载文件
            result = self.bucket.get_object(key)
            if result.status == 200:
                # 获取内容长度
                content_length = result.headers.get('Content-Length')
                expected_size = int(content_length) if content_length else None

                print(f"📥 开始下载: {url[:50]}...")
                if expected_size:
                    print(f"   文件大小: {expected_size/(1024*1024):.1f}MB")

                # 写入文件
                with open(local_path, 'wb') as f:
                    content = result.read()
                    f.write(content)

                # 验证下载的文件
                if not os.path.exists(local_path):
                    raise Exception("下载的文件不存在")

                actual_size = os.path.getsize(local_path)
                if actual_size == 0:
                    raise Exception("下载的文件为空")

                # 检查文件大小是否匹配
                if expected_size and abs(actual_size - expected_size) > 1024:  # 允许1KB误差
                    raise Exception(f"文件大小不匹配: 期望{expected_size}, 实际{actual_size}")

                print(f"✅ 下载完成: {actual_size/(1024*1024):.1f}MB")

                # 对于视频文件，进行额外验证
                if local_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                    try:
                        from ..services.enhanced_video_downloader import validate_existing_video
                        is_valid = await validate_existing_video(local_path)

                        if not is_valid:
                            # 删除无效文件
                            if os.path.exists(local_path):
                                os.remove(local_path)
                            raise Exception("下载的视频文件验证失败，可能损坏")

                        print(f"✅ 视频文件验证通过")

                    except ImportError:
                        # 如果增强下载器不可用，跳过验证
                        print("⚠️ 增强验证器不可用，跳过视频验证")

            else:
                raise Exception(f"下载失败，状态码: {result.status}")

        except Exception as error:
            print(f'OSS下载失败: {error}')
            # 清理可能的损坏文件
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                    print(f"🗑️ 已清理损坏文件: {local_path}")
                except:
                    pass
            raise Exception(f'文件下载失败: {error}')
    
    async def delete_from_oss(self, object_path: str) -> bool:
        """
        从OSS删除文件
        Args:
            object_path: 文件在OSS中的路径
        Returns:
            bool: 删除是否成功
        """
        try:
            result = self.bucket.delete_object(object_path)
            print(f'成功从OSS删除文件: {object_path}')
            return True
        except Exception as error:
            print(f'OSS删除失败: {error}')
            return False

def _get_video_headers(file_path):
    """根据文件类型设置合适的HTTP头"""
    if file_path.endswith('.mp4'):
        return {
            'Content-Type': 'video/mp4',
            'Cache-Control': 'public, max-age=31536000'
        }
    elif file_path.endswith('.webm'):
        return {
            'Content-Type': 'video/webm',
            'Cache-Control': 'public, max-age=31536000'
        }
    elif file_path.endswith('.avi'):
        return {
            'Content-Type': 'video/x-msvideo',
            'Cache-Control': 'public, max-age=31536000'
        }
    else:
        return {
            'Content-Type': 'application/octet-stream',
            'Cache-Control': 'public, max-age=31536000'
        }
