# 开始生成 - 使用任务调度器
@router.post("/api/generation/start")
async def start_generation(req: StartGenerationRequest):
    """启动视频生成任务 - 使用任务调度器"""
    try:
        # 检查项目是否存在
        if req.projectId not in _project_storage:
            return {
                "success": False,
                "error": f"项目 {req.projectId} 不存在"
            }
        
        clip_req = _project_storage[req.projectId]
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 使用任务调度器提交任务
        from task_scheduler import task_scheduler
        initial_status = await task_scheduler.submit_task(task_id, clip_req)
        
        print(f"🎬 任务 {task_id} 已提交，初始状态: {initial_status}")
        
        return {
            "success": True,
            "data": {
                "id": task_id,
                "status": initial_status,
                "progress": 0,
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
                "message": "已提交到任务调度器"
            }
        }
    
    except Exception as e:
        print(f"❌ 启动生成任务失败: {e}")
        return {
            "success": False,
            "error": f"启动生成失败: {str(e)}"
        }
