import requests
from uuid import uuid4
from datetime import datetime
import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

FASTGPT_API_URL = os.getenv("FASTGPT_API_URL", "https://api.fastgpt.in/api/v1/chat/completions")
FASTGPT_API_KEY = os.getenv("FASTGPT_API_KEY", "")

style_prompts = {
    'professional': '请用专业正式的语气改写以下文案，保持内容的准确性和权威性：',
    'casual': '请用轻松活泼的语气改写以下文案，让内容更加亲切自然：',
    'emotional': '请用富有情感的语气改写以下文案，增强内容的感染力：',
    'marketing': '请用营销导向的语气改写以下文案，突出产品卖点和价值主张：',
    '': '请改写以下文案，保持原意的同时让表达更加清晰有力：'
}
rewrite_style = 'professional'
style_prompt = style_prompts.get(rewrite_style, style_prompts[''])

async def generate_scripts_service(base_script: str, video_duration: int, video_count: int):
    try:
        # 专门调用FastGPT插件API
        print("调用FastGPT文案改写插件...")
        
        # 方案1: 使用简化的插件调用格式
        request_data_v1 = {
            "chatId": f"script_rewrite_{hash(base_script) % 10000}",
            "stream": False,
            "detail": True,
            "messages": [
                {
                    "content": base_script,
                    "role": "user"
                }
            ],
            "variables": {
                "video_duration": video_duration,
                "original_text": base_script,
                "rewrite_count": video_count
            }
        }

        print(f"尝试方案1 - 简化插件调用: {request_data_v1}")

        response = requests.post(
            url=FASTGPT_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {FASTGPT_API_KEY}"
            },
            json=request_data_v1,
            timeout=600
        )
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"方案1响应: {response_data}")
            
            # 检查是否仍有AI_input_is_empty错误
            has_error = False
            if "responseData" in response_data:
                for item in response_data.get("responseData", []):
                    if "errorText" in item and "AI_input_is_empty" in item["errorText"]:
                        has_error = True
                        break
            
            if has_error:
                print("方案1失败，尝试方案2 - 直接传递插件参数...")
                
                # 方案2: 直接按照您提供的插件格式
                request_data_v2 = {
                    "chatId": f"plugin_call_{hash(base_script) % 10000}",
                    "stream": False,
                    "detail": True,
                    "variables": {
                        "video_duration": video_duration,
                        "original_text": base_script,
                        "rewrite_count": video_count
                    }
                }
                
                print(f"尝试方案2 - 插件参数格式: {request_data_v2}")
                
                response = requests.post(
                    url=FASTGPT_API_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {FASTGPT_API_KEY}"
                    },
                    json=request_data_v2,
                    timeout=600
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    print(f"方案2响应: {response_data}")
                    
                    # 如果方案2还是失败，尝试方案3
                    has_error_v2 = False
                    if "responseData" in response_data:
                        for item in response_data.get("responseData", []):
                            if "errorText" in item and "AI_input_is_empty" in item["errorText"]:
                                has_error_v2 = True
                                break
                    
                    if has_error_v2:
                        print("方案2失败，尝试方案3 - 最简格式...")
                        
                        # 方案3: 最简格式，只传变量
                        request_data_v3 = {
                            "variables": {
                                "video_duration": video_duration,
                                "original_text": base_script,
                                "rewrite_count": video_count
                            }
                        }
                        
                        print(f"尝试方案3 - 最简格式: {request_data_v3}")
                        
                        response = requests.post(
                            url=FASTGPT_API_URL,
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {FASTGPT_API_KEY}"
                            },
                            json=request_data_v3,
                            timeout=600
                        )
                        
                        if response.status_code == 200:
                            response_data = response.json()
                            print(f"方案3响应: {response_data}")
        
        print(f"最终FastGPT请求完成，状态码: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"最终FastGPT响应: {response_data}")
            
            # 检查FastGPT插件是否有错误
            if "responseData" in response_data:
                response_data_list = response_data.get("responseData", [])
                for item in response_data_list:
                    if "errorText" in item:
                        error_msg = item["errorText"]
                        print(f"FastGPT插件错误: {error_msg}")
                        return {"success": False, "error": f"FastGPT插件错误: {error_msg}"}
            
            # 优先查找插件输出结果
            plugin_result = None
            if "responseData" in response_data:
                for item in response_data.get("responseData", []):
                    if "pluginOutput" in item and "result" in item["pluginOutput"]:
                        plugin_result = item["pluginOutput"]["result"]
                        print(f"找到插件输出结果: {plugin_result}")
                        break
            
            if plugin_result and isinstance(plugin_result, list):
                # 直接使用插件输出的结果
                cleaned_lines = []
                for script in plugin_result:
                    if isinstance(script, str) and len(script.strip()) > 10:
                        cleaned_lines.append(script.strip())
                
                print(f"插件返回的文案: {cleaned_lines}")
                
                if len(cleaned_lines) >= video_count:
                    return {"success": True, "data": cleaned_lines[:video_count], "source": "FastGPT插件"}
                elif len(cleaned_lines) > 0:
                    # 补充不足的文案
                    while len(cleaned_lines) < video_count:
                        cleaned_lines.append(cleaned_lines[0])
                    return {"success": True, "data": cleaned_lines[:video_count], "source": "FastGPT插件"}
                else:
                    return {"success": False, "error": "FastGPT插件返回的文案质量不足"}
            
            # 如果没有找到插件输出，尝试解析标准choices格式
            choices = response_data.get("choices", [])
            if choices and len(choices) > 0:
                choice = choices[0]
                message = choice.get("message", {})
                content = message.get("content", "")
                
                # FastGPT插件的content可能是字符串或复杂结构
                text_content = ""
                if isinstance(content, str):
                    text_content = content
                elif isinstance(content, list) and len(content) > 0:
                    # 处理插件工作流格式的content
                    for item in content:
                        if isinstance(item, dict):
                            if "text" in item:
                                if isinstance(item["text"], dict):
                                    text_content += item["text"].get("content", "")
                                else:
                                    text_content += str(item["text"])
                            elif "content" in item:
                                text_content += str(item["content"])
                        else:
                            text_content += str(item)
                
                print(f"解析到的插件文本内容: {text_content}")
                
                if text_content.strip():
                    # 按行分割并清理文案
                    lines = [line.strip() for line in text_content.strip().split('\n') if line.strip()]
                    
                    cleaned_lines = []
                    for line in lines:
                        clean_line = line.strip()
                        # 移除序号前缀
                        if clean_line.startswith(('1.', '2.', '3.', '4.', '5.', '1、', '2、', '3、', '4、', '5、')):
                            clean_line = clean_line[2:].strip()
                        # 移除其他前缀
                        if clean_line.startswith(('版本1:', '版本2:', '版本3:', '改写1:', '改写2:', '改写3:')):
                            clean_line = clean_line.split(':', 1)[1].strip()
                        
                        if clean_line and len(clean_line) > 10:  # 确保文案有足够长度
                            cleaned_lines.append(clean_line)
                    
                    print(f"清理后的插件文案: {cleaned_lines}")
                    
                    if len(cleaned_lines) >= video_count:
                        return {"success": True, "data": cleaned_lines[:video_count], "source": "FastGPT插件"}
                    elif len(cleaned_lines) > 0:
                        # 补充不足的文案
                        while len(cleaned_lines) < video_count:
                            cleaned_lines.append(cleaned_lines[0])
                        return {"success": True, "data": cleaned_lines[:video_count], "source": "FastGPT插件"}
                    else:
                        return {"success": False, "error": "FastGPT插件返回的文案质量不足"}
                else:
                    return {"success": False, "error": "FastGPT插件返回内容为空"}
            else:
                return {"success": False, "error": "FastGPT插件响应格式异常，缺少choices和pluginOutput"}
        else:
            print(f"FastGPT插件请求失败，状态码: {response.status_code}, 错误信息: {response.text}")
            return {"success": False, "error": f"FastGPT插件请求失败: {response.status_code}"}
            
    except Exception as e:
        print(f"调用FastGPT插件异常: {str(e)}")
        return {"success": False, "error": f"调用FastGPT插件异常: {str(e)}"}

def call_fastGPT_rewrite_plugin(original_text: str, video_duration: int, rewrite_count: int):
    """
    调用FastGPT文案改写插件 - 尝试多种API格式
    """
    try:
        # 方法1: 尝试插件格式
        response = requests.post(
            url=FASTGPT_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {FASTGPT_API_KEY}"
            },
            json={
                "video_duration": video_duration,
                "original_text": original_text,
                "rewrite_count": rewrite_count
            },
            timeout=600
        )
        print(f"FastGPT插件格式请求参数: video_duration={video_duration}, original_text={original_text}, rewrite_count={rewrite_count}")
        
        # 如果插件格式失败，尝试标准ChatGPT格式
        if response.status_code != 200:
            print(f"插件格式失败 ({response.status_code})，尝试ChatGPT格式...")
            prompt = f"""请根据以下要求改写文案：

原始文案：{original_text}

要求：
1. 改写后的文案适合{video_duration}秒的视频使用
2. 保持原意不变，但表达方式要更加吸引人
3. 内容长度控制在{video_duration * 3}字以内
4. 生成{rewrite_count}个不同的改写版本
5. 每个版本用换行符分隔

请直接输出{rewrite_count}个改写后的文案，每行一个，不要添加序号或其他解释。"""

            response = requests.post(
                url=FASTGPT_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {FASTGPT_API_KEY}"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                },
                timeout=600
            )
            print(f"FastGPT ChatGPT格式请求完成，状态码: {response.status_code}")
        
        print(f"FastGPT请求URL: {FASTGPT_API_URL}")
        return response
    except Exception as e:
        print(f"FastGPT请求异常: {str(e)}")
        raise e

def call_fastGPT(base_script: str, video_duration: int, i: int):
    """保留原有的ChatGPT格式调用方法作为备用"""
    prompt = f"""{style_prompt}
原始文案：{base_script}

要求：
1. 改写后的文案适合{video_duration}秒的视频使用
2. 保持原意不变，但表达方式要更加吸引人
3. 内容长度控制在{video_duration * 3}字以内
5. 生成的内容有正确的标点符号和语法
5. 这是第{i+1}个改写版本，请确保与之前版本有所区别

请直接输出改写后的文案，不要添加任何解释，不要添加emoji、表情符号、特殊字符、乱码字符。
"""
    user_text = prompt.strip()
    response = requests.post(
        url=FASTGPT_API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {FASTGPT_API_KEY}"
        },
        json={
            "model": "gpt-3.5-turbo",
            "messages": [
                {
                    "role": "user",
                    "content": user_text
                }
            ]
        },
        timeout=600
    )
    return response

# 移除本地降级方案，专注于FastGPT插件调用