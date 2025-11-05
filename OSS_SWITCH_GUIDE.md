# OSS 供应商切换说明

本项目支持在阿里云 OSS 和火山云 TOS 之间无缝切换。

## 环境变量配置

### 使用阿里云 OSS（默认）

在 `.env` 文件中设置：

```bash
STORAGE_PROVIDER=alibaba

# 阿里云 OSS 配置
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
OSS_BUCKET_NAME=your_bucket_name
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
```

### 使用火山云 TOS

在 `.env` 文件中设置：

```bash
STORAGE_PROVIDER=volcengine

# 火山云 TOS 配置
TOS_ACCESS_KEY=your_access_key
TOS_SECRET_KEY=your_secret_key
TOS_BUCKET_NAME=your_bucket_name
TOS_REGION=cn-beijing
TOS_ENDPOINT=tos-s3-cn-beijing.volces.com
```

## 接口兼容性

两个客户端提供完全相同的接口：

- `upload_to_oss()` - 上传文件
- `upload_to_oss_with_progress()` - 带进度的上传
- `check_file_exists()` - 检查文件是否存在
- 自动去重功能
- 自动分片上传（大文件）

## 切换步骤

1. 修改 `.env` 文件中的 `STORAGE_PROVIDER` 变量
2. 填入对应供应商的凭证信息
3. 重启应用

无需修改任何代码！
