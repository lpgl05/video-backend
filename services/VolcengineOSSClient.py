import os
import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Optional, BinaryIO
from dotenv import load_dotenv
import tos
from tos import exceptions
from config.upload_optimization import upload_config

# 加载环境变量
load_dotenv()


class VolcengineOSSClient:
    """
    火山云 TOS 客户端
    接口和返回格式与阿里云 OSS 客户端保持一致，实现无缝切换
    """
    
    def __init__(self):
        """初始化火山云 TOS 客户端"""
        try:
            # 从环境变量读取配置
            self.access_key = os.getenv("TOS_ACCESS_KEY") or os.getenv("VOLCENGINE_ACCESS_KEY", "")
            self.secret_key = os.getenv("TOS_SECRET_KEY") or os.getenv("VOLCENGINE_SECRET_KEY", "")
            self.region = os.getenv("TOS_REGION", "cn-beijing")
            self.endpoint = os.getenv("TOS_ENDPOINT", "tos-s3-cn-beijing.volces.com")
            self.bucket_name = os.getenv("TOS_BUCKET_NAME") or os.getenv("VOLCENGINE_BUCKET", "")
            
            # 清理 endpoint 中的 https:// 前缀（TOS SDK 不需要）
            if self.endpoint.startswith("https://"):
                self.endpoint = self.endpoint.replace("https://", "")
            if self.endpoint.startswith("http://"):
                self.endpoint = self.endpoint.replace("http://", "")
            
            # 确保所有配置都是字符串
            if self.access_key:
                self.access_key = str(self.access_key).strip()
            if self.secret_key:
                self.secret_key = str(self.secret_key).strip()
            if self.endpoint:
                self.endpoint = str(self.endpoint).strip()
            if self.bucket_name:
                self.bucket_name = str(self.bucket_name).strip()
            
            # 创建 TOS 客户端
            self.client = tos.TosClientV2(
                ak=self.access_key,
                sk=self.secret_key,
                endpoint=self.endpoint,
                region=self.region
            )
            
            # 检查权限
            self._oss_permission_checked = self._check_oss_permissions()
            
            print(f"✅ 火山云 TOS 客户端初始化成功")
            print(f"   Bucket: {self.bucket_name}")
            print(f"   Region: {self.region}")
            print(f"   Endpoint: {self.endpoint}")
            
        except Exception as e:
            print(f"❌ 火山云 TOS 客户端初始化失败: {e}")
            self.client = None
            self._oss_permission_checked = False
    
    def _calculate_file_hash(self, file_buffer: bytes) -> str:
        """计算文件的 MD5 哈希值"""
        return hashlib.md5(file_buffer).hexdigest()
    
    def _check_oss_permissions(self) -> bool:
        """检查 TOS 权限"""
        try:
            test_key = 'permission_test_file'
            try:
                self.client.head_object(bucket=self.bucket_name, key=test_key)
                print(f"✅ TOS 权限检查通过（文件存在），去重功能已启用")
                return True
            except exceptions.TosServerError as e:
                if e.status_code == 404:
                    # 文件不存在是正常的，说明有读取权限
                    print(f"✅ TOS 权限检查通过（文件不存在但可访问），去重功能已启用")
                    return True
                else:
                    print(f"⚠️ TOS 权限检查失败: {e}，去重功能禁用")
                    return False
        except Exception as e:
            print(f"⚠️ TOS 权限检查失败: {e}，去重功能禁用")
            return False
    
    async def check_file_exists(self, file_hash: str, folder: str = 'uploads') -> Optional[str]:
        """
        检查 TOS 中是否已存在相同哈希的文件
        与阿里云 OSS 接口保持一致
        
        Args:
            file_hash: 文件 MD5 哈希值
            folder: 文件夹路径
            
        Returns:
            如果文件存在，返回文件 URL；否则返回 None
        """
        try:
            file_extensions = ['.mp4', '.mov', '.avi', '.mp3', '.wav', '.flac', '.jpg', '.jpeg', '.png', '.gif']
            
            for ext in file_extensions:
                object_key = f"{folder}/hash_{file_hash}{ext}"
                
                try:
                    self.client.head_object(bucket=self.bucket_name, key=object_key)
                    # 文件存在
                    file_url = f"https://{self.bucket_name}.{self.endpoint}/{object_key}"
                    print(f"✅ 发现重复文件: {file_url}")
                    return file_url
                except exceptions.TosServerError as e:
                    if e.status_code == 404:
                        # 文件不存在，继续
                        continue
                except Exception as e:
                    print(f"检查文件 {object_key} 时出错: {e}")
                    continue
            
            print(f"🔍 未找到哈希为 {file_hash} 的重复文件")
            return None
            
        except Exception as e:
            print(f"检查文件存在时出错: {e}")
            return None
    
    async def upload_to_oss(self, file_buffer: bytes, original_filename: str,
                           folder: str = 'uploads', mimetype: Optional[str] = None) -> str:
        """不带进度回调的上传方法（与阿里云 OSS 接口一致）"""
        return await self.upload_to_oss_with_progress(file_buffer, original_filename, folder, mimetype, None)
    
    async def upload_to_oss_with_progress(self, file_buffer: bytes, original_filename: str,
                           folder: str = 'uploads', mimetype: Optional[str] = None,
                           progress_callback = None) -> str:
        """
        文件上传到火山云 TOS
        接口和返回格式与阿里云 OSS 完全一致
        
        Args:
            file_buffer: 文件的二进制数据
            original_filename: 原始文件名
            folder: 存储文件夹，默认为 'uploads'
            mimetype: 文件 MIME 类型
            progress_callback: 进度回调函数
            
        Returns:
            str: 上传后的文件 URL
        """
        try:
            # 获取文件扩展名
            file_extension = Path(original_filename).suffix.lower()
            
            # 计算文件哈希值
            file_hash = self._calculate_file_hash(file_buffer)
            
            # 构造文件路径
            expected_file_name = f"{folder}/hash_{file_hash}{file_extension}"
            
            # 确保文件路径只包含安全字符
            safe_filename = re.sub(r'[^\w\-_\./]', '_', expected_file_name)
            if safe_filename != expected_file_name:
                print(f"文件路径包含非ASCII字符，已替换为安全字符: {safe_filename}")
            expected_file_name = safe_filename
            
            # 检查文件是否已存在（去重）
            try:
                if self._oss_permission_checked:
                    self.client.head_object(bucket=self.bucket_name, key=expected_file_name)
                    # 文件已存在
                    existing_url = f"https://{self.bucket_name}.{self.endpoint}/{expected_file_name}"
                    print(f"🚀 文件已存在，跳过上传: {existing_url}")
                    if progress_callback:
                        progress_callback(100.0, len(file_buffer), 0)
                    return existing_url
                else:
                    print(f"⚠️ TOS 去重功能已禁用（权限问题），直接上传: {expected_file_name}")
            except exceptions.TosServerError as e:
                if e.status_code == 404:
                    # 文件不存在，需要上传
                    print(f"🔍 文件不存在，开始上传: {expected_file_name}")
            except Exception as e:
                print(f"检查文件存在时出错: {e}，继续上传")
            
            file_name = expected_file_name
            
            # 自动检测 MIME 类型
            if not mimetype:
                safe_filename_for_mime = re.sub(r'[^\w\-_\.]', '_', original_filename)
                try:
                    mimetype, _ = mimetypes.guess_type(safe_filename_for_mime)
                except Exception as e:
                    print(f"MIME 类型检测失败: {e}，使用默认类型")
                    mimetype = 'application/octet-stream'
                if not mimetype:
                    mimetype = 'application/octet-stream'
            
            # 判断文件大小，决定使用简单上传还是分片上传
            file_size = len(file_buffer)
            multipart_threshold = upload_config.MULTIPART_THRESHOLD
            
            print(f"文件大小: {file_size / (1024*1024):.2f}MB")
            
            if file_size > multipart_threshold:
                print("使用分片上传...")
                result = self._multipart_upload(file_name, file_buffer, mimetype, progress_callback)
            else:
                print("使用简单上传...")
                try:
                    # TOS 简单上传
                    self.client.put_object(
                        bucket=self.bucket_name,
                        key=file_name,
                        content=file_buffer,
                        content_type=mimetype
                    )
                    
                    # 触发进度回调
                    if progress_callback:
                        progress_callback(100.0, file_size, file_size / 1.0)
                        
                except Exception as e:
                    print(f"简单上传失败: {e}")
                    raise e
            
            # 构造并返回文件 URL
            return f"https://{self.bucket_name}.{self.endpoint}/{file_name}"
                
        except Exception as error:
            print(f'TOS 上传失败: {error}')
            raise Exception('文件上传失败')
    
    def _multipart_upload(self, object_name: str, file_buffer: bytes, content_type: str = None, progress_callback = None):
        """
        分片上传实现
        与阿里云 OSS 分片上传逻辑保持一致
        
        Args:
            object_name: 对象名称
            file_buffer: 文件二进制数据
            content_type: 内容类型
            progress_callback: 进度回调
        """
        try:
            file_size = len(file_buffer)
            part_size = upload_config.get_optimal_part_size(file_size)
            max_workers = upload_config.get_optimal_concurrency(file_size)
            
            print(f"开始分片上传: 文件大小{file_size / (1024*1024):.2f}MB, 每片{part_size / (1024*1024)}MB, 并发数{max_workers}")
            
            # 初始化分片上传
            result = self.client.create_multipart_upload(
                bucket=self.bucket_name,
                key=object_name,
                content_type=content_type
            )
            upload_id = result.upload_id
            
            print(f"分片上传 ID: {upload_id}")
            
            # 计算分片数量
            total_parts = (file_size + part_size - 1) // part_size
            uploaded_parts = []
            uploaded_bytes = 0
            
            # 逐个上传分片
            for part_number in range(1, total_parts + 1):
                offset = (part_number - 1) * part_size
                chunk_size = min(part_size, file_size - offset)
                chunk = file_buffer[offset:offset + chunk_size]
                
                try:
                    # 上传分片
                    part_result = self.client.upload_part(
                        bucket=self.bucket_name,
                        key=object_name,
                        part_number=part_number,
                        upload_id=upload_id,
                        content=chunk
                    )
                    
                    uploaded_parts.append(tos.models2.UploadedPart(
                        part_number=part_number,
                        etag=part_result.etag
                    ))
                    
                    uploaded_bytes += chunk_size
                    
                    # 计算进度
                    if progress_callback:
                        progress_percent = (uploaded_bytes / file_size) * 100
                        speed_mbps = chunk_size / (1024 * 1024)  # 简化的速度计算
                        progress_callback(progress_percent, uploaded_bytes, speed_mbps)
                    
                    print(f"已上传分片 {part_number}/{total_parts}, 进度: {uploaded_bytes / file_size * 100:.1f}%")
                    
                except Exception as e:
                    print(f"上传分片 {part_number} 失败: {e}")
                    # 取消分片上传
                    try:
                        self.client.abort_multipart_upload(
                            bucket=self.bucket_name,
                            key=object_name,
                            upload_id=upload_id
                        )
                    except:
                        pass
                    raise e
            
            # 完成分片上传
            self.client.complete_multipart_upload(
                bucket=self.bucket_name,
                key=object_name,
                upload_id=upload_id,
                parts=uploaded_parts
            )
            
            print(f"✅ 分片上传完成: {object_name}")
            
        except Exception as e:
            print(f"分片上传失败: {e}")
            raise e