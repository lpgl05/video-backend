#!/usr/bin/env python3
"""
OSS上传网络优化和诊断工具
"""
import asyncio
import time
import subprocess
import os
import requests
from models.oss_client import OSSClient
from config.upload_optimization import upload_config

class NetworkOptimizer:
    def __init__(self):
        self.oss_client = OSSClient()
        
    def ping_test(self, host: str, count: int = 4) -> dict:
        """Ping测试网络延迟"""
        try:
            result = subprocess.run(
                ['ping', '-n', str(count), host] if os.name == 'nt' else ['ping', '-c', str(count), host],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout
            
            if os.name == 'nt':  # Windows
                # 解析Windows ping输出
                lines = output.split('\n')
                times = []
                for line in lines:
                    if 'time=' in line:
                        time_str = line.split('time=')[1].split('ms')[0]
                        times.append(float(time_str))
                
                if times:
                    avg_time = sum(times) / len(times)
                    min_time = min(times)
                    max_time = max(times)
                    return {
                        'success': True,
                        'avg': avg_time,
                        'min': min_time,
                        'max': max_time,
                        'times': times
                    }
            else:  # Linux/Mac
                # 解析Unix ping输出
                if 'round-trip' in output:
                    stats = output.split('round-trip')[1].split('=')[1].strip().split('/')
                    return {
                        'success': True,
                        'min': float(stats[0]),
                        'avg': float(stats[1]),
                        'max': float(stats[2])
                    }
            
            return {'success': False, 'error': 'Failed to parse ping output'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def test_oss_endpoints(self):
        """测试不同OSS接入点的延迟"""
        endpoints = [
            'oss-cn-beijing.aliyuncs.com',      # 北京
            'oss-cn-shanghai.aliyuncs.com',     # 上海
            'oss-cn-shenzhen.aliyuncs.com',     # 深圳
            'oss-cn-hangzhou.aliyuncs.com',     # 杭州
            'oss-cn-guangzhou.aliyuncs.com',    # 广州
            'oss-cn-qingdao.aliyuncs.com',      # 青岛
            'oss-cn-chengdu.aliyuncs.com',      # 成都
        ]
        
        results = {}
        print("测试不同OSS接入点延迟...")
        
        for endpoint in endpoints:
            print(f"测试 {endpoint}...")
            result = self.ping_test(endpoint.replace('https://', '').replace('http://', ''))
            results[endpoint] = result
            
            if result['success']:
                print(f"  延迟: {result['avg']:.2f}ms")
            else:
                print(f"  错误: {result.get('error', 'Unknown error')}")
        
        # 找出最快的接入点
        fastest = None
        fastest_time = float('inf')
        
        for endpoint, result in results.items():
            if result['success'] and result['avg'] < fastest_time:
                fastest_time = result['avg']
                fastest = endpoint
        
        if fastest:
            print(f"\n推荐使用最快接入点: {fastest} (延迟: {fastest_time:.2f}ms)")
        
        return results
    
    def test_upload_speed(self, test_size_mb: int = 10):
        """测试上传速度"""
        print(f"测试上传速度 (文件大小: {test_size_mb}MB)...")
        
        # 生成测试数据
        test_data = b'0' * (test_size_mb * 1024 * 1024)
        
        async def upload_test():
            try:
                start_time = time.time()
                
                # 模拟上传
                file_url = await self.oss_client.upload_to_oss(
                    file_buffer=test_data,
                    original_filename=f"speed_test_{int(time.time())}.bin",
                    folder="test"
                )
                
                end_time = time.time()
                duration = end_time - start_time
                speed = test_size_mb / duration
                
                print(f"上传完成:")
                print(f"  耗时: {duration:.2f}秒")
                print(f"  速度: {speed:.2f}MB/s")
                
                return {
                    'success': True,
                    'duration': duration,
                    'speed': speed,
                    'file_url': file_url
                }
            except Exception as e:
                print(f"上传测试失败: {e}")
                return {'success': False, 'error': str(e)}
        
        return asyncio.run(upload_test())
    
    def check_dns_resolution(self):
        """检查DNS解析"""
        import socket
        
        print("检查DNS解析...")
        endpoints = [
            'oss-cn-beijing.aliyuncs.com',
            'oss-cn-shanghai.aliyuncs.com'
        ]
        
        for endpoint in endpoints:
            try:
                start_time = time.time()
                ip = socket.gethostbyname(endpoint)
                resolve_time = (time.time() - start_time) * 1000
                print(f"{endpoint} -> {ip} ({resolve_time:.2f}ms)")
            except Exception as e:
                print(f"{endpoint} DNS解析失败: {e}")
    
    def generate_optimization_report(self):
        """生成优化报告"""
        print("=" * 60)
        print("OSS上传性能优化报告")
        print("=" * 60)
        
        # DNS检查
        self.check_dns_resolution()
        print()
        
        # 接入点测试
        endpoint_results = self.test_oss_endpoints()
        print()
        
        # 上传速度测试
        upload_result = self.test_upload_speed(5)  # 5MB测试
        print()
        
        # 配置建议
        print("优化建议:")
        print("1. 选择延迟最低的OSS接入点")
        print("2. 如果在公司网络，检查是否有代理设置")
        print("3. 如果速度仍然慢，尝试以下配置调整:")
        print("   - 增加并发数: OSS_MAX_CONCURRENT_UPLOADS=15")
        print("   - 增加分片大小: OSS_PART_SIZE_MEDIUM=30, OSS_PART_SIZE_LARGE=80")
        print("   - 增加连接池: OSS_CONNECTION_POOL_SIZE=100")
        print("   - 调整超时时间: OSS_READ_TIMEOUT=600")
        print()
        
        # 网络环境检查
        print("环境检查:")
        print("4. 检查是否在公司内网（可能有防火墙限制）")
        print("5. 检查是否使用VPN（可能影响速度）")
        print("6. 尝试使用手机热点测试（排除网络环境问题）")
        print("7. 检查本地磁盘I/O性能")

def main():
    optimizer = NetworkOptimizer()
    optimizer.generate_optimization_report()

if __name__ == "__main__":
    main()
