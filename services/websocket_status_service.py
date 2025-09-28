#!/usr/bin/env python3
"""
WebSocket状态推送服务
减少频繁的API轮询，实现实时状态推送
"""

import asyncio
import json
import time
from typing import Dict, Set, Any, Optional, List
import logging
from datetime import datetime
import weakref

logger = logging.getLogger(__name__)

class WebSocketStatusService:
    """WebSocket状态推送服务"""
    
    def __init__(self):
        self.connections: Dict[str, Set[Any]] = {}  # task_id -> websocket connections
        self.task_subscribers: Dict[str, Set[str]] = {}  # connection_id -> task_ids
        self.connection_registry: Dict[str, Any] = {}  # connection_id -> websocket
        self.push_stats = {
            'total_connections': 0,
            'active_connections': 0,
            'total_messages_sent': 0,
            'total_subscriptions': 0,
            'failed_sends': 0
        }
        
        # 状态缓存
        self.status_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = 300  # 5分钟缓存TTL
        
        logger.info("🔌 WebSocket状态推送服务已初始化")
    
    async def register_connection(self, websocket, connection_id: str):
        """注册WebSocket连接"""
        
        self.connection_registry[connection_id] = websocket
        self.task_subscribers[connection_id] = set()
        
        self.push_stats['total_connections'] += 1
        self.push_stats['active_connections'] += 1
        
        logger.info(f"🔌 WebSocket连接已注册: {connection_id}")
        logger.info(f"   当前活跃连接数: {self.push_stats['active_connections']}")
        
        # 发送欢迎消息
        await self._send_to_connection(connection_id, {
            'type': 'connection_established',
            'connection_id': connection_id,
            'timestamp': datetime.now().isoformat(),
            'message': 'WebSocket连接已建立'
        })
    
    async def unregister_connection(self, connection_id: str):
        """注销WebSocket连接"""
        
        if connection_id in self.connection_registry:
            # 清理任务订阅
            if connection_id in self.task_subscribers:
                subscribed_tasks = self.task_subscribers[connection_id].copy()
                for task_id in subscribed_tasks:
                    await self.unsubscribe_task(connection_id, task_id)
                
                del self.task_subscribers[connection_id]
            
            # 移除连接
            del self.connection_registry[connection_id]
            self.push_stats['active_connections'] -= 1
            
            logger.info(f"🔌 WebSocket连接已注销: {connection_id}")
            logger.info(f"   当前活跃连接数: {self.push_stats['active_connections']}")
    
    async def subscribe_task(self, connection_id: str, task_id: str):
        """订阅任务状态更新"""
        
        if connection_id not in self.connection_registry:
            logger.warning(f"⚠️ 连接不存在: {connection_id}")
            return False
        
        # 添加订阅
        if task_id not in self.connections:
            self.connections[task_id] = set()
        
        self.connections[task_id].add(connection_id)
        self.task_subscribers[connection_id].add(task_id)
        
        self.push_stats['total_subscriptions'] += 1
        
        logger.info(f"📋 任务订阅已添加: {connection_id} -> {task_id}")
        
        # 发送当前状态（如果有缓存）
        if task_id in self.status_cache:
            cached_status = self.status_cache[task_id]
            if time.time() - cached_status.get('cached_at', 0) < self.cache_ttl:
                await self._send_to_connection(connection_id, {
                    'type': 'task_status_update',
                    'task_id': task_id,
                    'status': cached_status['status'],
                    'from_cache': True
                })
        
        # 发送订阅确认
        await self._send_to_connection(connection_id, {
            'type': 'subscription_confirmed',
            'task_id': task_id,
            'timestamp': datetime.now().isoformat()
        })
        
        return True
    
    async def unsubscribe_task(self, connection_id: str, task_id: str):
        """取消订阅任务状态"""
        
        # 移除订阅
        if task_id in self.connections:
            self.connections[task_id].discard(connection_id)
            
            # 如果没有订阅者了，清理任务
            if not self.connections[task_id]:
                del self.connections[task_id]
        
        if connection_id in self.task_subscribers:
            self.task_subscribers[connection_id].discard(task_id)
        
        logger.info(f"📋 任务订阅已移除: {connection_id} -> {task_id}")
        
        # 发送取消订阅确认
        await self._send_to_connection(connection_id, {
            'type': 'unsubscription_confirmed',
            'task_id': task_id,
            'timestamp': datetime.now().isoformat()
        })
    
    async def push_task_status(self, task_id: str, status_data: Dict[str, Any]):
        """推送任务状态更新"""
        
        if task_id not in self.connections:
            # 没有订阅者，只更新缓存
            self._update_status_cache(task_id, status_data)
            return
        
        # 更新缓存
        self._update_status_cache(task_id, status_data)
        
        # 构建推送消息
        message = {
            'type': 'task_status_update',
            'task_id': task_id,
            'status': status_data,
            'timestamp': datetime.now().isoformat()
        }
        
        # 推送给所有订阅者
        subscribers = self.connections[task_id].copy()
        successful_sends = 0
        failed_sends = 0
        
        for connection_id in subscribers:
            success = await self._send_to_connection(connection_id, message)
            if success:
                successful_sends += 1
            else:
                failed_sends += 1
                # 移除失效连接
                await self.unregister_connection(connection_id)
        
        self.push_stats['total_messages_sent'] += successful_sends
        self.push_stats['failed_sends'] += failed_sends
        
        logger.debug(f"📤 任务状态已推送: {task_id}")
        logger.debug(f"   成功: {successful_sends}, 失败: {failed_sends}")
    
    async def push_system_message(self, message_type: str, data: Dict[str, Any]):
        """推送系统消息给所有连接"""
        
        message = {
            'type': message_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        successful_sends = 0
        failed_sends = 0
        
        # 推送给所有活跃连接
        connection_ids = list(self.connection_registry.keys())
        
        for connection_id in connection_ids:
            success = await self._send_to_connection(connection_id, message)
            if success:
                successful_sends += 1
            else:
                failed_sends += 1
                # 移除失效连接
                await self.unregister_connection(connection_id)
        
        self.push_stats['total_messages_sent'] += successful_sends
        self.push_stats['failed_sends'] += failed_sends
        
        logger.info(f"📢 系统消息已推送: {message_type}")
        logger.info(f"   成功: {successful_sends}, 失败: {failed_sends}")
    
    async def _send_to_connection(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """发送消息到指定连接"""
        
        if connection_id not in self.connection_registry:
            return False
        
        websocket = self.connection_registry[connection_id]
        
        try:
            # 检查连接状态
            if websocket.closed:
                logger.warning(f"⚠️ WebSocket连接已关闭: {connection_id}")
                return False
            
            # 发送消息
            await websocket.send(json.dumps(message, ensure_ascii=False))
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送WebSocket消息失败: {connection_id}, 错误: {e}")
            return False
    
    def _update_status_cache(self, task_id: str, status_data: Dict[str, Any]):
        """更新状态缓存"""
        
        self.status_cache[task_id] = {
            'status': status_data,
            'cached_at': time.time()
        }
        
        # 清理过期缓存
        self._cleanup_expired_cache()
    
    def _cleanup_expired_cache(self):
        """清理过期缓存"""
        
        current_time = time.time()
        expired_tasks = []
        
        for task_id, cache_data in self.status_cache.items():
            if current_time - cache_data.get('cached_at', 0) > self.cache_ttl:
                expired_tasks.append(task_id)
        
        for task_id in expired_tasks:
            del self.status_cache[task_id]
        
        if expired_tasks:
            logger.debug(f"🧹 清理过期缓存: {len(expired_tasks)}个任务")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计"""
        
        # 计算任务订阅统计
        task_subscription_count = len(self.connections)
        total_subscriptions = sum(len(subscribers) for subscribers in self.connections.values())
        
        stats = self.push_stats.copy()
        stats.update({
            'task_subscription_count': task_subscription_count,
            'active_subscriptions': total_subscriptions,
            'cached_tasks': len(self.status_cache),
            'avg_subscriptions_per_connection': (
                total_subscriptions / max(1, self.push_stats['active_connections'])
            )
        })
        
        return stats
    
    def get_task_subscribers(self, task_id: str) -> List[str]:
        """获取任务的订阅者列表"""
        
        if task_id in self.connections:
            return list(self.connections[task_id])
        return []
    
    def get_connection_subscriptions(self, connection_id: str) -> List[str]:
        """获取连接的订阅列表"""
        
        if connection_id in self.task_subscribers:
            return list(self.task_subscribers[connection_id])
        return []
    
    async def broadcast_performance_update(self, performance_data: Dict[str, Any]):
        """广播性能更新"""
        
        await self.push_system_message('performance_update', {
            'gpu_utilization': performance_data.get('gpu_utilization', 0),
            'cpu_utilization': performance_data.get('cpu_utilization', 0),
            'memory_usage': performance_data.get('memory_usage', 0),
            'active_tasks': performance_data.get('active_tasks', 0),
            'queue_size': performance_data.get('queue_size', 0)
        })
    
    async def cleanup_inactive_connections(self):
        """清理不活跃的连接"""
        
        inactive_connections = []
        
        for connection_id, websocket in self.connection_registry.items():
            try:
                if websocket.closed:
                    inactive_connections.append(connection_id)
            except Exception:
                inactive_connections.append(connection_id)
        
        for connection_id in inactive_connections:
            await self.unregister_connection(connection_id)
        
        if inactive_connections:
            logger.info(f"🧹 清理不活跃连接: {len(inactive_connections)}个")

# 全局WebSocket状态推送服务实例
websocket_service = WebSocketStatusService()

async def register_websocket_connection(websocket, connection_id: str):
    """注册WebSocket连接"""
    await websocket_service.register_connection(websocket, connection_id)

async def unregister_websocket_connection(connection_id: str):
    """注销WebSocket连接"""
    await websocket_service.unregister_connection(connection_id)

async def subscribe_task_status(connection_id: str, task_id: str) -> bool:
    """订阅任务状态"""
    return await websocket_service.subscribe_task(connection_id, task_id)

async def unsubscribe_task_status(connection_id: str, task_id: str):
    """取消订阅任务状态"""
    await websocket_service.unsubscribe_task(connection_id, task_id)

async def push_task_status_update(task_id: str, status_data: Dict[str, Any]):
    """推送任务状态更新"""
    await websocket_service.push_task_status(task_id, status_data)

async def broadcast_system_message(message_type: str, data: Dict[str, Any]):
    """广播系统消息"""
    await websocket_service.push_system_message(message_type, data)

def get_websocket_stats() -> Dict[str, Any]:
    """获取WebSocket统计"""
    return websocket_service.get_connection_stats()

async def cleanup_websocket_connections():
    """清理WebSocket连接"""
    await websocket_service.cleanup_inactive_connections()

if __name__ == "__main__":
    # 测试WebSocket服务
    import logging
    logging.basicConfig(level=logging.INFO)
    
    class MockWebSocket:
        def __init__(self, connection_id):
            self.connection_id = connection_id
            self.closed = False
            self.messages = []
        
        async def send(self, message):
            self.messages.append(message)
            print(f"WebSocket {self.connection_id} 收到消息: {message}")
    
    async def test_websocket_service():
        # 创建模拟连接
        ws1 = MockWebSocket("conn1")
        ws2 = MockWebSocket("conn2")
        
        # 注册连接
        await register_websocket_connection(ws1, "conn1")
        await register_websocket_connection(ws2, "conn2")
        
        # 订阅任务
        await subscribe_task_status("conn1", "task1")
        await subscribe_task_status("conn2", "task1")
        await subscribe_task_status("conn1", "task2")
        
        # 推送状态更新
        await push_task_status_update("task1", {
            'status': 'processing',
            'progress': 50,
            'message': '处理中...'
        })
        
        # 广播系统消息
        await broadcast_system_message('system_maintenance', {
            'message': '系统维护通知',
            'scheduled_time': '2024-01-01 02:00:00'
        })
        
        # 显示统计
        stats = get_websocket_stats()
        print(f"WebSocket统计: {stats}")
        
        # 清理连接
        await unregister_websocket_connection("conn1")
        await unregister_websocket_connection("conn2")
    
    # 运行测试
    asyncio.run(test_websocket_service())
