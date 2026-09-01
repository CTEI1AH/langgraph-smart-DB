import asyncio
import json
import os
import websockets
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WS_URI = "ws://localhost:3000/v1/chat/stream"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def interact_with_agent(chat_id: int, payload: dict, status_message: Message = None):
    """Функция общения с WebSocket. Собирает ответ и отправляет в ТГ."""
    
    # Если статусное сообщение не передано, создаем его
    if not status_message:
        status_message = await bot.send_message(chat_id, "⏳ <i>Агент думает...</i>", parse_mode="HTML")
        
    full_response = ""
    
    try:
        async with websockets.connect(WS_URI, ping_interval=None) as websocket:
            # Отправляем данные (сообщение пользователя ИЛИ ответ на кнопку HITL)
            await websocket.send(json.dumps(payload))
            
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                
                if data["type"] == "chunk":
                    full_response += data["content"]
                    
                elif data["type"] == "reasoning":
                    pass # Можно выводить мысли агента, но в ТГ лучше не спамить
                    
                elif data["type"] == "tool_result":
                    pass # Инструмент отработал
                    
                elif data["type"] == "hitl_request":
                    # Агент просит подтверждения! Рисуем кнопки.
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Разрешить", callback_data=f"hitl_y_{data['approvalId']}"),
                            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"hitl_n_{data['approvalId']}")
                        ]
                    ])
                    text = f"⚠️ <b>ВНИМАНИЕ: Запрос на действие</b>\n\nАгент хочет выполнить: <code>{data['toolName']}</code>\nАргументы: <code>{data['args']}</code>"
                    await status_message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
                    return # Прерываем цикл, ждем нажатия кнопки
                    
                elif data["type"] == "done":
                    # Ответ готов, обновляем сообщение в ТГ
                    if full_response.strip():
                        try:
                            # Пытаемся отправить с красивым Markdown форматированием
                            await status_message.edit_text(full_response, parse_mode="Markdown")
                        except Exception:
                            # ЕСЛИ ТЕЛЕГРАМ РУГАЕТСЯ НА РАЗМЕТКУ ИИ - отправляем как сырой текст!
                            await status_message.edit_text(full_response, parse_mode=None)
                    else:
                        await status_message.edit_text("✅ Действие выполнено.")
                    break
                    
                elif data["type"] == "error":
                    await status_message.edit_text(f"❌ Ошибка агента: {data['error']}")
                    break

    except Exception as e:
        await status_message.edit_text(f"❌ Ошибка связи с сервером: {e}")


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я твой AgentOS. Напиши мне что-нибудь, и я отвечу, используя базу знаний!")

@dp.message()
async def handle_text(message: Message):
    """Перехватываем текст пользователя и отправляем агенту"""
    payload = {"type": "chat", "userMessage": message.text}
    # Запускаем общение с агентом
    await interact_with_agent(message.chat.id, payload)


@dp.callback_query(F.data.startswith("hitl_"))
async def handle_hitl_button(callback: CallbackQuery):
    """Перехватываем нажатие кнопок HITL (Разрешить/Отклонить)"""
    action = callback.data.split("_")[1] # 'y' или 'n'
    approval_id = callback.data.split("_")[2]
    
    approved = (action == 'y')
    
    # Меняем текст кнопки, чтобы было понятно, что нажато
    await callback.message.edit_text(
        f"{'✅ Вы разрешили' if approved else '❌ Вы отклонили'} выполнение задачи.\n⏳ <i>Агент продолжает работу...</i>", 
        parse_mode="HTML"
    )
    
    # Отправляем ответ в WebSocket
    payload = {
        "type": "hitl_response",
        "approvalId": approval_id,
        "approved": approved
    }
    
    await interact_with_agent(callback.message.chat.id, payload, status_message=callback.message)
    await callback.answer()

async def main():
    print("🤖 Telegram Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())