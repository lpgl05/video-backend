#!/usr/bin/env python3
"""
优化字体缓存系统
解决字体重复加载问题，提升字幕处理性能
"""

import os
import time
from typing import Dict, Optional, Tuple
from threading import Lock
import logging

logger = logging.getLogger(__name__)

class FontCache:
    """字体缓存管理器"""
    
    def __init__(self):
        self._cache: Dict[str, str] = {}  # font_family -> font_path
        self._access_times: Dict[str, float] = {}  # 访问时间记录
        self._lock = Lock()
        self._max_cache_size = 50  # 最大缓存数量
        self._cache_ttl = 3600  # 缓存TTL: 1小时
        
        # 字体映射配置
        self.font_mapping = {
            'Arial, sans-serif': None,  # 使用系统默认
            'Microsoft YaHei, sans-serif': 'msyh.ttc',
            'SimSun, serif': 'simsun.ttc',
            'SimHei, sans-serif': 'simhei.ttf',
            'KaiTi, serif': 'simkai.ttf',
            'LIULISONG': 'LIULISONG.ttf',
            'MiaobiJunli': '妙笔珺俐体.ttf',
            'MiaobiDuanmu': '妙笔段慕体.ttf',
            'SourceHanSansCN-Heavy': 'SourceHanSansCN-Heavy.otf',
        }
        
        # 默认字体路径
        self.default_font_path = os.path.join("fonts", "msyh.ttc")
        
        # 字体搜索路径
        self.font_search_paths = [
            os.path.join("..", "frontend", "public", "fonts"),
            "fonts",
            "/System/Library/Fonts",  # macOS
            "/usr/share/fonts",       # Linux
            "C:/Windows/Fonts"       # Windows
        ]
        
        logger.info("字体缓存系统已初始化")
    
    def get_font_path(self, font_family: str, font_type: str = 'title') -> str:
        """获取字体路径 - 带缓存优化"""
        
        # 生成缓存键
        cache_key = f"{font_family}_{font_type}"
        
        with self._lock:
            # 检查缓存
            if cache_key in self._cache:
                # 更新访问时间
                self._access_times[cache_key] = time.time()
                
                # 验证文件是否仍然存在
                cached_path = self._cache[cache_key]
                if os.path.exists(cached_path):
                    logger.debug(f"✅ 字体缓存命中: {font_family} -> {cached_path}")
                    return cached_path
                else:
                    # 文件不存在，移除缓存
                    del self._cache[cache_key]
                    del self._access_times[cache_key]
                    logger.warning(f"⚠️ 缓存的字体文件不存在，已清理: {cached_path}")
            
            # 缓存未命中，查找字体
            font_path = self._find_font_path(font_family)
            
            # 添加到缓存
            self._add_to_cache(cache_key, font_path)
            
            logger.info(f"🔍 字体查找完成: {font_family} -> {font_path}")
            return font_path
    
    def _find_font_path(self, font_family: str) -> str:
        """查找字体文件路径"""
        
        # 查找字体映射
        font_file = self.font_mapping.get(font_family)
        
        if not font_file:
            logger.warning(f"❌ 字体映射中未找到: {font_family}")
            return self._get_default_font_path()
        
        # 在搜索路径中查找字体文件
        for search_path in self.font_search_paths:
            if not os.path.exists(search_path):
                continue
                
            font_path = os.path.join(search_path, font_file)
            font_path = os.path.abspath(font_path)
            
            if os.path.exists(font_path):
                logger.debug(f"✅ 找到字体文件: {font_path}")
                return font_path
        
        logger.warning(f"❌ 字体文件未找到: {font_file}")
        return self._get_default_font_path()
    
    def _get_default_font_path(self) -> str:
        """获取默认字体路径"""
        
        # 尝试默认字体路径
        if os.path.exists(self.default_font_path):
            return os.path.abspath(self.default_font_path)
        
        # 尝试系统字体
        for search_path in self.font_search_paths:
            if not os.path.exists(search_path):
                continue
                
            # 查找常见字体
            common_fonts = ['msyh.ttc', 'arial.ttf', 'DejaVuSans.ttf']
            for font_name in common_fonts:
                font_path = os.path.join(search_path, font_name)
                if os.path.exists(font_path):
                    logger.info(f"🔄 使用系统默认字体: {font_path}")
                    return os.path.abspath(font_path)
        
        # 最后的回退
        logger.error("❌ 未找到任何可用字体，使用空路径")
        return ""
    
    def _add_to_cache(self, cache_key: str, font_path: str):
        """添加到缓存"""
        
        # 检查缓存大小
        if len(self._cache) >= self._max_cache_size:
            self._cleanup_cache()
        
        # 添加到缓存
        self._cache[cache_key] = font_path
        self._access_times[cache_key] = time.time()
        
        logger.debug(f"📦 字体已缓存: {cache_key} -> {font_path}")
    
    def _cleanup_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        
        # 找出过期的缓存项
        expired_keys = []
        for key, access_time in self._access_times.items():
            if current_time - access_time > self._cache_ttl:
                expired_keys.append(key)
        
        # 删除过期项
        for key in expired_keys:
            del self._cache[key]
            del self._access_times[key]
        
        # 如果还是太多，删除最久未访问的
        if len(self._cache) >= self._max_cache_size:
            # 按访问时间排序，删除最旧的
            sorted_items = sorted(self._access_times.items(), key=lambda x: x[1])
            items_to_remove = len(sorted_items) - self._max_cache_size + 10  # 多删除一些
            
            for i in range(min(items_to_remove, len(sorted_items))):
                key = sorted_items[i][0]
                del self._cache[key]
                del self._access_times[key]
        
        logger.info(f"🧹 缓存清理完成，当前缓存数量: {len(self._cache)}")
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        with self._lock:
            return {
                'cache_size': len(self._cache),
                'max_cache_size': self._max_cache_size,
                'cache_ttl': self._cache_ttl,
                'cached_fonts': list(self._cache.keys())
            }
    
    def clear_cache(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            logger.info("🗑️ 字体缓存已清空")
    
    def preload_common_fonts(self):
        """预加载常用字体"""
        common_fonts = [
            'SourceHanSansCN-Heavy',
            'Microsoft YaHei, sans-serif',
            'SimHei, sans-serif'
        ]
        
        logger.info("🚀 开始预加载常用字体...")
        
        for font_family in common_fonts:
            try:
                font_path = self.get_font_path(font_family)
                logger.info(f"✅ 预加载字体: {font_family} -> {font_path}")
            except Exception as e:
                logger.error(f"❌ 预加载字体失败: {font_family}, 错误: {e}")
        
        logger.info(f"🎉 字体预加载完成，缓存数量: {len(self._cache)}")

# 全局字体缓存实例
_font_cache = FontCache()

def get_font_path_cached(font_family: str, font_type: str = 'title') -> str:
    """获取字体路径 - 缓存版本"""
    return _font_cache.get_font_path(font_family, font_type)

def get_font_cache_stats() -> Dict:
    """获取字体缓存统计"""
    return _font_cache.get_cache_stats()

def clear_font_cache():
    """清空字体缓存"""
    _font_cache.clear_cache()

def preload_fonts():
    """预加载常用字体"""
    _font_cache.preload_common_fonts()

# 兼容性函数 - 替换原有的字体查找函数
def get_font_path_from_style(style_config, font_type='title'):
    """根据样式配置获取字体文件路径 - 优化版本"""
    if not style_config:
        return get_font_path_cached('Microsoft YaHei, sans-serif', font_type)
    
    font_style = style_config.get(font_type, {}) if isinstance(style_config, dict) else {}
    font_family = font_style.get('fontFamily', 'Microsoft YaHei, sans-serif')
    
    return get_font_path_cached(font_family, font_type)

# 批量字体路径获取
def get_batch_font_paths(font_requests: list) -> Dict[str, str]:
    """批量获取字体路径"""
    results = {}
    
    for request in font_requests:
        if isinstance(request, dict):
            font_family = request.get('fontFamily', 'Microsoft YaHei, sans-serif')
            font_type = request.get('fontType', 'title')
            key = request.get('key', f"{font_family}_{font_type}")
        else:
            font_family = request
            font_type = 'title'
            key = font_family
        
        results[key] = get_font_path_cached(font_family, font_type)
    
    return results

if __name__ == "__main__":
    # 测试字体缓存
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # 预加载字体
    preload_fonts()
    
    # 测试字体查找
    test_fonts = [
        'SourceHanSansCN-Heavy',
        'Microsoft YaHei, sans-serif',
        'SimHei, sans-serif',
        'Unknown Font'
    ]
    
    print("\n🧪 字体缓存测试:")
    for font in test_fonts:
        start_time = time.time()
        path = get_font_path_cached(font)
        end_time = time.time()
        print(f"   {font}: {path} (耗时: {(end_time-start_time)*1000:.1f}ms)")
    
    # 显示缓存统计
    stats = get_font_cache_stats()
    print(f"\n📊 缓存统计: {stats}")
