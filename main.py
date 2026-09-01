import os
from dotenv import load_dotenv
load_dotenv()
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import HumanMessage
from agent import workflow
from config import settings, logger

app_graph = None

# FastAPI для управления жизненным циклом приложения
@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_graph
    logger.info("Connecting to PostgreSQL for LangGraph Checkpointer...")
    
    # Используем async with, так как это асинхронный контекстный менеджер
    async with AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL) as checkpointer:
        await checkpointer.setup()
        app_graph = workflow.compile(checkpointer=checkpointer)
        logger.info("LangGraph compiled and ready.")
        
        # Передаем управление серверу (он будет работать, пока не нажмут Ctrl+C)
        yield  
        
    logger.info("Disconnected from PostgreSQL Checkpointer")

# Инициализируем FastAPI с нашим lifespan
app = FastAPI(lifespan=lifespan)

@app.websocket("/v1/chat/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Хардкодим ID треда 
    # Первый диалог thread_id = "uuid-7742-x992-langgraph"
    thread_id = "270820765-langgraph"
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            
            # --- ОБРАБОТКА HITL (Продолжение замороженного графа) ---
            if data.get("type") == "hitl_response":
                from langgraph.types import Command # Импортируем команду для возобновления
                
                await websocket.send_json({"type": "tool_result", "tool": "HITL", "result": "Решение получено, продолжаю..."})
                
                # Возобновляем граф и СРАЗУ стримим его ответ (не ainvoke)
                async for event in app_graph.astream_events(
                    Command(resume={"approved": data.get("approved")}),
                    config,
                    version="v2"
                ):
                    kind = event["event"]
                    
                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, 'content') and chunk.content:
                            await websocket.send_json({"type": "chunk", "content": chunk.content})
                            
                    elif kind == "on_tool_end":
                        tool_name = event["name"]
                        result = event["data"].get("output")
                        # Не выводим результат самого перехватчика в чат
                        if tool_name != "hitl": 
                            await websocket.send_json({"type": "tool_result", "tool": tool_name, "result": str(result)})
                            
                await websocket.send_json({"type": "done"})
                continue

            # --- ОБРАБОТКА НОВОГО СООБЩЕНИЯ ---
            if data.get("type") == "chat":
                user_message = data.get("userMessage")
                
                # Запускаем граф с подпиской на события (стриминг)
                async for event in app_graph.astream_events(
                    {"messages": [HumanMessage(content=user_message)]}, 
                    config, 
                    version="v2"
                ):
                    kind = event["event"]
                    
                    # 1. Стриминг текста (токенов) от LLM
                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, 'content') and chunk.content:
                            await websocket.send_json({"type": "chunk", "content": chunk.content})
                    
                    # 2. Агент решил вызвать инструмент
                    elif kind == "on_tool_start":
                        tool_name = event["name"]
                        args = event["data"].get("input", {})
                        await websocket.send_json({"type": "reasoning", "content": f"[Thought] -> Calling tool: {tool_name}({args})"})
                    
                    # 3. Инструмент отработал
                    elif kind == "on_tool_end":
                        tool_name = event["name"]
                        result = event["data"].get("output")
                        await websocket.send_json({"type": "tool_result", "tool": tool_name, "result": str(result)})

                    # 4. Граф прерван для HITL (interrupt)
                    elif kind == "on_custom_event" and event["name"] == "hitl_request":
                        hitl_data = event["data"]
                        await websocket.send_json({
                            "type": "hitl_request",
                            "approvalId": "langgraph-hitl",
                            "toolName": hitl_data["tool"],
                            "args": hitl_data["args"]
                        })
                        
                await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WS Error: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "error": str(e)})