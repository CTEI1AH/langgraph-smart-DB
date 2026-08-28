import asyncio
import websockets
import json
import sys

# Специальная функция, чтобы ввод текста не блокировал веб-сокеты
async def async_input(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)

async def chat_cli():
    uri = "ws://localhost:3000/v1/chat/stream"
    
    try:
        # Отключаем таймауты на стороне клиента полностью
        async with websockets.connect(uri, ping_interval=None, ping_timeout=None) as websocket:
            print("="*50)
            print("🤖 AgentOS CLI подключен! Напиши 'exit' для выхода.")
            print("="*50 + "\n")
            
            while True:
                user_msg = await async_input("👤 Ты: ")
                if user_msg.lower() in ['exit', 'quit']:
                    break
                    
                await websocket.send(json.dumps({"type": "chat", "userMessage": user_msg}))
                print("🤖 AI: ", end="", flush=True)
                
                while True:
                    response = await websocket.recv()
                    data = json.loads(response)
                    
                    if data["type"] == "chunk":
                        print(data["content"], end="", flush=True)
                        
                    elif data["type"] == "reasoning":
                        print(f"\n   \033[90m[Мысль: {data['content']}]\033[0m", end="", flush=True)
                        
                    elif data["type"] == "tool_result":
                        print(f"\n   \033[90m[Результат: {data['tool']} -> Готово]\033[0m\n🤖 AI: ", end="", flush=True)
                        
                    elif data["type"] == "hitl_request":
                        print(f"\n\n⚠️ ВНИМАНИЕ: Агент хочет выполнить '{data['toolName']}'")
                        print(f"   Аргументы: {data['args']}")
                        ans = await async_input("   Разрешить действие? (y/n): ")
                        
                        await websocket.send(json.dumps({
                            "type": "hitl_response",
                            "approvalId": data["approvalId"],
                            "approved": ans.lower() == 'y'
                        }))
                        print("🤖 AI: ", end="", flush=True)
                        
                    elif data["type"] == "done":
                        print("\n" + "-"*50)
                        break
                        
                    elif data["type"] == "error":
                        print(f"\n❌ Ошибка: {data['error']}\n")
                        break

    except ConnectionRefusedError:
        print("❌ Ошибка: Сервер не запущен. Сначала запусти 'uvicorn main:app --port 3000'")

if __name__ == "__main__":
    asyncio.run(chat_cli())