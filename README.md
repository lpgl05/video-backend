# Python 后端（FastAPI）

本目录为 Python 版后端，使用 FastAPI 框架。

## 启动方式

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 启动服务：
   ```bash
   uvicorn main:app --reload
   ```
   # 或者指定端口（如8000）：
   uvicorn main:app --reload --port 8000

3. 访问接口：
   - 默认地址：http://127.0.0.1:8000
   - API文档：http://127.0.0.1:8000/docs

## 目录结构
- main.py              # FastAPI 入口
- routes/              # 路由模块
- models/              # 数据模型
- services/            # 业务服务
- config/              # 配置文件
- middleware/          # 中间件
- requirements.txt     # 依赖包

## 说明
- 路由、服务、模型等可根据原 Node.js 逻辑逐步迁移。
- 保持与前端 API 协议一致。
