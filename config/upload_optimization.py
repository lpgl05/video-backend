# 上传优化配置
import os
from dotenv import load_dotenv

load_dotenv()

class UploadConfig:
    """上传优化配置"""
    
    def __init__(self):
        # OSS 连接优化
        self.CONNECTION_POOL_SIZE = int(os.getenv("OSS_CONNECTION_POOL_SIZE", "50"))
        self.CONNECTION_TIMEOUT = int(os.getenv("OSS_CONNECTION_TIMEOUT", "30"))
        self.READ_TIMEOUT = int(os.getenv("OSS_READ_TIMEOUT", "300"))
        
        # 分片上传优化
        self.MAX_CONCURRENT_UPLOADS = int(os.getenv("OSS_MAX_CONCURRENT_UPLOADS", "10"))
        self.MULTIPART_THRESHOLD = int(os.getenv("OSS_MULTIPART_THRESHOLD", "10")) * 1024 * 1024  # MB转字节
        
        # 动态分片大小配置（MB）
        self.PART_SIZE_SMALL = int(os.getenv("OSS_PART_SIZE_SMALL", "10")) * 1024 * 1024   # 小文件分片大小
        self.PART_SIZE_MEDIUM = int(os.getenv("OSS_PART_SIZE_MEDIUM", "20")) * 1024 * 1024  # 中等文件分片大小
        self.PART_SIZE_LARGE = int(os.getenv("OSS_PART_SIZE_LARGE", "50")) * 1024 * 1024   # 大文件分片大小
        self.PART_SIZE_XLARGE = int(os.getenv("OSS_PART_SIZE_XLARGE", "100")) * 1024 * 1024 # 超大文件分片大小
        
        # 文件大小阈值（MB）
        self.SMALL_FILE_THRESHOLD = int(os.getenv("OSS_SMALL_FILE_THRESHOLD", "50")) * 1024 * 1024
        self.MEDIUM_FILE_THRESHOLD = int(os.getenv("OSS_MEDIUM_FILE_THRESHOLD", "200")) * 1024 * 1024
        self.LARGE_FILE_THRESHOLD = int(os.getenv("OSS_LARGE_FILE_THRESHOLD", "500")) * 1024 * 1024
        
        # 重试配置
        self.MAX_RETRIES = int(os.getenv("OSS_MAX_RETRIES", "3"))
        self.RETRY_DELAY = float(os.getenv("OSS_RETRY_DELAY", "1.0"))
        
        # 网络优化
        self.ENABLE_CRC = os.getenv("OSS_ENABLE_CRC", "false").lower() == "true"
        self.ENABLE_MD5 = os.getenv("OSS_ENABLE_MD5", "false").lower() == "true"
        
    def get_optimal_part_size(self, file_size: int) -> int:
        """根据文件大小返回最优分片大小"""
        if file_size < self.SMALL_FILE_THRESHOLD:
            return self.PART_SIZE_SMALL
        elif file_size < self.MEDIUM_FILE_THRESHOLD:
            return self.PART_SIZE_MEDIUM
        elif file_size < self.LARGE_FILE_THRESHOLD:
            return self.PART_SIZE_LARGE
        else:
            return self.PART_SIZE_XLARGE
    
    def get_optimal_concurrency(self, file_size: int) -> int:
        """根据文件大小返回最优并发数"""
        # 进一步减少并发数，专注稳定性而非速度
        if file_size < self.SMALL_FILE_THRESHOLD:
            return 1  # 小文件：单线程上传
        elif file_size < self.MEDIUM_FILE_THRESHOLD:
            return 2  # 中等文件：2个并发
        elif file_size < self.LARGE_FILE_THRESHOLD:
            return 2  # 大文件：2个并发
        else:
            return min(3, self.MAX_CONCURRENT_UPLOADS)  # 超大文件：最多3个并发

# 全局配置实例
upload_config = UploadConfig()
