"""
GPU加速配置文件
用于配置视频处理的GPU硬件加速设置
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class GPUConfig:
    """GPU配置类"""
    
    def __init__(self):
        # 从环境变量读取配置，提供默认值
        self.enabled = os.getenv("GPU_ACCELERATION_ENABLED", "true").lower() == "true"
        self.preferred_encoder = os.getenv("GPU_PREFERRED_ENCODER", "auto")  # auto, nvenc, amf, qsv
        self.quality_mode = os.getenv("GPU_QUALITY_MODE", "balanced")  # fast, balanced, quality
        self.fallback_to_cpu = os.getenv("GPU_FALLBACK_TO_CPU", "true").lower() == "true"
        
        # NVIDIA NVENC 特定设置
        self.nvenc_preset = os.getenv("NVENC_PRESET", "p4")  # p1(fastest) to p7(slowest)
        self.nvenc_rc_mode = os.getenv("NVENC_RC_MODE", "vbr")  # cbr, vbr, cqp
        self.nvenc_cq = int(os.getenv("NVENC_CQ", "23"))  # 质量参数 (0-51)
        self.nvenc_bitrate = os.getenv("NVENC_BITRATE", "10M")  # 目标比特率
        self.nvenc_maxrate = os.getenv("NVENC_MAXRATE", "15M")  # 最大比特率
        self.nvenc_gpu_id = int(os.getenv("NVENC_GPU_ID", "0"))  # GPU设备ID
        
        # AMD AMF 特定设置
        self.amf_quality = os.getenv("AMF_QUALITY", "balanced")  # speed, balanced, quality
        self.amf_rc_mode = os.getenv("AMF_RC_MODE", "vbr_peak")  # cbr, vbr_peak, vbr_latency
        self.amf_qp_i = int(os.getenv("AMF_QP_I", "22"))
        self.amf_qp_p = int(os.getenv("AMF_QP_P", "24"))
        
        # Intel QSV 特定设置
        self.qsv_preset = os.getenv("QSV_PRESET", "medium")  # veryfast, faster, fast, medium, slow, slower, veryslow
        self.qsv_global_quality = int(os.getenv("QSV_GLOBAL_QUALITY", "23"))
        
        # 性能优化设置
        self.enable_hardware_decode = os.getenv("GPU_HARDWARE_DECODE", "true").lower() == "true"
        self.enable_memory_optimization = os.getenv("GPU_MEMORY_OPTIMIZATION", "true").lower() == "true"
        
        # 调试设置
        self.debug_mode = os.getenv("GPU_DEBUG_MODE", "false").lower() == "true"
        self.benchmark_mode = os.getenv("GPU_BENCHMARK_MODE", "false").lower() == "true"

    def get_nvenc_params(self, quality_override=None):
        """获取NVIDIA NVENC编码参数"""
        quality = quality_override or self.quality_mode
        
        base_params = [
            '-c:v', 'h264_nvenc',
            '-gpu', str(self.nvenc_gpu_id),
            '-rc', self.nvenc_rc_mode
        ]
        
        if quality == 'fast':
            return base_params + [
                '-preset', 'p1',  # 最快速度
                '-cq', '28',
                '-b:v', '8M',
                '-maxrate', '12M',
                '-bufsize', '16M'
            ]
        elif quality == 'quality':
            return base_params + [
                '-preset', 'p7',  # 最高质量
                '-cq', '19',
                '-b:v', '12M',
                '-maxrate', '18M',
                '-bufsize', '24M'
            ]
        else:  # balanced
            return base_params + [
                '-preset', self.nvenc_preset,
                '-cq', str(self.nvenc_cq),
                '-b:v', self.nvenc_bitrate,
                '-maxrate', self.nvenc_maxrate,
                '-bufsize', '20M'
            ]
    
    def get_amf_params(self, quality_override=None):
        """获取AMD AMF编码参数"""
        quality = quality_override or self.quality_mode
        
        return [
            '-c:v', 'h264_amf',
            '-quality', self.amf_quality,
            '-rc', self.amf_rc_mode,
            '-qp_i', str(self.amf_qp_i),
            '-qp_p', str(self.amf_qp_p),
            '-b:v', '10M',
            '-maxrate', '15M'
        ]
    
    def get_qsv_params(self, quality_override=None):
        """获取Intel QSV编码参数"""
        quality = quality_override or self.quality_mode
        
        return [
            '-c:v', 'h264_qsv',
            '-preset', self.qsv_preset,
            '-global_quality', str(self.qsv_global_quality),
            '-b:v', '10M',
            '-maxrate', '15M'
        ]
    
    def get_hardware_decode_params(self):
        """获取硬件解码参数"""
        if not self.enable_hardware_decode:
            return []
        
        # 根据首选编码器选择对应的硬件解码
        if self.preferred_encoder == "nvenc" or self.preferred_encoder == "auto":
            return ['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda']
        elif self.preferred_encoder == "qsv":
            return ['-hwaccel', 'qsv']
        else:
            return []
    
    def print_config(self):
        """打印当前配置"""
        print("🔧 GPU加速配置:")
        print(f"   启用状态: {'✅' if self.enabled else '❌'}")
        print(f"   首选编码器: {self.preferred_encoder}")
        print(f"   质量模式: {self.quality_mode}")
        print(f"   CPU回退: {'✅' if self.fallback_to_cpu else '❌'}")
        print(f"   硬件解码: {'✅' if self.enable_hardware_decode else '❌'}")
        print(f"   内存优化: {'✅' if self.enable_memory_optimization else '❌'}")
        print(f"   调试模式: {'✅' if self.debug_mode else '❌'}")

# 全局配置实例
gpu_config = GPUConfig()

def update_gpu_config(**kwargs):
    """更新GPU配置"""
    global gpu_config
    
    for key, value in kwargs.items():
        if hasattr(gpu_config, key):
            setattr(gpu_config, key, value)
            print(f"✅ 更新GPU配置: {key} = {value}")
        else:
            print(f"⚠️ 未知配置项: {key}")

def reset_gpu_config():
    """重置GPU配置为默认值"""
    global gpu_config
    gpu_config = GPUConfig()
    print("🔄 GPU配置已重置为默认值")

def save_gpu_config_to_env():
    """保存当前GPU配置到.env文件"""
    env_content = f"""
# GPU加速配置
GPU_ACCELERATION_ENABLED={str(gpu_config.enabled).lower()}
GPU_PREFERRED_ENCODER={gpu_config.preferred_encoder}
GPU_QUALITY_MODE={gpu_config.quality_mode}
GPU_FALLBACK_TO_CPU={str(gpu_config.fallback_to_cpu).lower()}

# NVIDIA NVENC配置
NVENC_PRESET={gpu_config.nvenc_preset}
NVENC_RC_MODE={gpu_config.nvenc_rc_mode}
NVENC_CQ={gpu_config.nvenc_cq}
NVENC_BITRATE={gpu_config.nvenc_bitrate}
NVENC_MAXRATE={gpu_config.nvenc_maxrate}
NVENC_GPU_ID={gpu_config.nvenc_gpu_id}

# AMD AMF配置
AMF_QUALITY={gpu_config.amf_quality}
AMF_RC_MODE={gpu_config.amf_rc_mode}
AMF_QP_I={gpu_config.amf_qp_i}
AMF_QP_P={gpu_config.amf_qp_p}

# Intel QSV配置
QSV_PRESET={gpu_config.qsv_preset}
QSV_GLOBAL_QUALITY={gpu_config.qsv_global_quality}

# 性能优化
GPU_HARDWARE_DECODE={str(gpu_config.enable_hardware_decode).lower()}
GPU_MEMORY_OPTIMIZATION={str(gpu_config.enable_memory_optimization).lower()}

# 调试
GPU_DEBUG_MODE={str(gpu_config.debug_mode).lower()}
GPU_BENCHMARK_MODE={str(gpu_config.benchmark_mode).lower()}
"""
    
    # 追加到.env文件
    with open('.env', 'a', encoding='utf-8') as f:
        f.write(env_content)
    
    print("💾 GPU配置已保存到.env文件")

if __name__ == "__main__":
    # 配置测试
    gpu_config.print_config()
