#!/usr/bin/env python3
"""
测试下载功能修复的脚本
"""
import requests
import sys

def test_oss_proxy_download():
    base_url = "http://localhost:9999"
    test_url = "https://example.com/test/video.mp4"
    
    print("🧪 测试 OSS 代理下载功能修复...")
    
    # 测试1: 预览模式 (download=false 或不设置)
    print("\n1️⃣ 测试预览模式 (download=false):")
    try:
        response = requests.head(f"{base_url}/api/videos/oss-proxy", 
                               params={"url": test_url, "download": False},
                               timeout=5)
        print(f"   状态码: {response.status_code}")
        content_disposition = response.headers.get('Content-Disposition', 'Not Found')
        print(f"   Content-Disposition: {content_disposition}")
        
        if content_disposition == "inline":
            print("   ✅ 预览模式正常 - Content-Disposition 为 inline")
        else:
            print("   ❌ 预览模式异常")
    except Exception as e:
        print(f"   ⚠️ 预览模式测试失败: {e}")
    
    # 测试2: 下载模式 (download=true)
    print("\n2️⃣ 测试下载模式 (download=true):")
    try:
        response = requests.head(f"{base_url}/api/videos/oss-proxy", 
                               params={"url": test_url, "download": True},
                               timeout=5)
        print(f"   状态码: {response.status_code}")
        content_disposition = response.headers.get('Content-Disposition', 'Not Found')
        print(f"   Content-Disposition: {content_disposition}")
        
        if 'attachment' in content_disposition and 'filename=' in content_disposition:
            print("   ✅ 下载模式正常 - Content-Disposition 包含 attachment 和 filename")
        else:
            print("   ❌ 下载模式异常")
    except Exception as e:
        print(f"   ⚠️ 下载模式测试失败: {e}")
    
    # 测试3: 默认模式 (不设置download参数)
    print("\n3️⃣ 测试默认模式 (不设置download参数):")
    try:
        response = requests.head(f"{base_url}/api/videos/oss-proxy", 
                               params={"url": test_url},
                               timeout=5)
        print(f"   状态码: {response.status_code}")
        content_disposition = response.headers.get('Content-Disposition', 'Not Found')
        print(f"   Content-Disposition: {content_disposition}")
        
        if content_disposition == "inline":
            print("   ✅ 默认模式正常 - Content-Disposition 为 inline")
        else:
            print("   ❌ 默认模式异常")
    except Exception as e:
        print(f"   ⚠️ 默认模式测试失败: {e}")
    
    print("\n🎉 测试完成！")

if __name__ == "__main__":
    test_oss_proxy_download()