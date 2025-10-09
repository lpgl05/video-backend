#!/usr/bin/env python3
"""
简单测试下载功能的脚本
"""
import requests

def test_download_functionality():
    print("🧪 测试下载功能...")
    
    # 使用一个简单的测试URL
    test_url = "https://httpbin.org/status/200"
    base_url = "http://localhost:9999"
    
    # 测试下载模式
    print("测试下载模式 (download=true):")
    try:
        response = requests.get(f"{base_url}/api/videos/oss-proxy", 
                              params={"url": test_url, "download": True},
                              timeout=10, stream=True)
        print(f"状态码: {response.status_code}")
        content_disposition = response.headers.get('Content-Disposition', 'Not Found')
        print(f"Content-Disposition: {content_disposition}")
        
        if 'attachment' in content_disposition:
            print("✅ 下载模式正常")
        else:
            print("❌ 下载模式异常")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    
    print("\n测试预览模式 (download=false):")
    try:
        response = requests.get(f"{base_url}/api/videos/oss-proxy", 
                              params={"url": test_url, "download": False},
                              timeout=10, stream=True)
        print(f"状态码: {response.status_code}")
        content_disposition = response.headers.get('Content-Disposition', 'Not Found')
        print(f"Content-Disposition: {content_disposition}")
        
        if content_disposition == "inline":
            print("✅ 预览模式正常")
        else:
            print("❌ 预览模式异常")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    test_download_functionality(