import json
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, RemoveMessage
from langgraph.types import interrupt
from agent_tools.registry import AGENT_TOOLS
from config import settings, logger

class State(MessagesState):
    summary: str

llm = ChatOpenAI(
    base_url=settings.OPENAI_API_BASE,
    api_key=settings.OPENAI_API_KEY,
    model=settings.LLM_MODEL_NAME,
    temperature=settings.LLM_TEMPERATURE,
    streaming=True
)
llm_with_tools = llm.bind_tools(AGENT_TOOLS)

async def safe_tool_node(state: State):
    """Узел выполнения инструментов с перехватом HITL и Очистки памяти"""
    last_message = state["messages"][-1]
    
    # 1. Проверяем, нужна ли санкция человека на инструмент
    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "update_database":
            response = interrupt({"action": "hitl", "tool": tool_call["name"], "args": tool_call["args"]})
            if not response.get("approved"):
                from langchain_core.messages import ToolMessage
                return {"messages": [ToolMessage(tool_call_id=tool_call["id"], name=tool_call["name"], content="ОТКЛОНЕНО")]}

    # 2. Выполняем инструмент
    node = ToolNode(AGENT_TOOLS)
    result = await node.ainvoke(state)
    
    # 3. ПЕРЕХВАТ ОЧИСТКИ ПАМЯТИ
    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "save_summary_and_clear_memory":
            logger.info("Агент запустил очистку памяти. Удаляем старые сообщения...")
            
            # В LangChain v0.2 args УЖЕ является словарем! Никакого json.loads не нужно.
            args = tool_call.get("args", {})
            new_summary = args.get("new_summary", "")
            
            # Мы удаляем все сообщения, КРОМЕ последних 2-х 
            msgs_to_remove = [RemoveMessage(id=m.id) for m in state["messages"][:-2]]
            
            if "messages" not in result:
                result["messages"] = []
            result["messages"].extend(msgs_to_remove)
            
            # Сохраняем новую выжимку в состояние
            result["summary"] = new_summary

    return result

async def call_model(state: State):
    """Мозг агента (Динамический системный промпт)"""
    messages = state["messages"]
    summary = state.get("summary", "")
    msg_count = len(messages)
    
    sys_prompt = settings.SYSTEM_PROMPT
    
    if summary:
        sys_prompt += f"\n\n[ВАЖНЫЙ КОНТЕКСТ ИЗ ПРОШЛОГО ОБЩЕНИЯ]:\n{summary}"
        
    # ДАЕМ АГЕНТУ ЧУВСТВО ВРЕМЕНИ И РАЗМЕРА:
    sys_prompt += f"\n\n[СТАТУС ПАМЯТИ]:\nВ нашей истории сейчас {msg_count} сообщений."
    
    if msg_count >= 8:
        sys_prompt += (
            "\nВНИМАНИЕ: Твоя оперативная память переполняется! В своем ответе вежливо ПРЕДЛОЖИ пользователю "
            "сжать память (сделать выжимку диалога). "
            "ЕСЛИ пользователь УЖЕ ответил согласием в последнем сообщении, "
            "НЕМЕДЛЕННО вызови инструмент 'save_summary_and_clear_memory', передав в него "
            "самые важные детали из этого разговора."
        )

    messages_for_llm = [SystemMessage(content=sys_prompt)] + messages
    response = await llm_with_tools.ainvoke(messages_for_llm)
    return {"messages": [response]}

def should_continue(state: State) -> str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# Сборка графа
workflow = StateGraph(State)
workflow.add_node("agent", call_model)
workflow.add_node("tools", safe_tool_node)
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue, ["tools", END])
workflow.add_edge("tools", "agent")