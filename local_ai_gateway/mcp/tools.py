"""
Model Context Protocol (MCP) tool definitions and implementations for Local AI Gateway.
"""
from typing import Dict, Any, Optional
from ..config import config
from ..providers import get_provider
from ..router import model_router
from ..sessions import session_manager
from ..models import ChatRequest, ChatMessage, GenerateRequest

provider = get_provider(config.provider)

async def mcp_health() -> Dict[str, Any]:
    """Check the health and reachability of the Local AI Gateway and backend model provider."""
    health = await provider.check_health()
    return health.to_dict()

async def mcp_list_models() -> Dict[str, Any]:
    """List all AI models installed locally on the Mac with parameters, quantization, and capabilities."""
    models = await provider.list_models()
    return {
        "models": [m.to_dict() for m in models],
        "count": len(models),
        "aliases": model_router.get_aliases()
    }

async def mcp_model_info(model: str) -> Dict[str, Any]:
    """Get detailed parameter specifications, prompt templates, and license info for a specific local model."""
    resolved = model_router.resolve_model(model)
    return await provider.get_model_info(resolved)

async def mcp_chat(
    prompt: str,
    model: Optional[str] = None,
    system: Optional[str] = None,
    temperature: Optional[float] = 0.7,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Execute a chat prompt on a Mac local model and return the generated text."""
    resolved_model = model_router.resolve_model(model or "auto", prompt=prompt)
    
    messages = []
    if session_id:
        sess = session_manager.get_session(session_id)
        if sess:
            messages = list(sess.messages)

    messages.append(ChatMessage(role="user", content=prompt))

    chat_req = ChatRequest(
        model=resolved_model,
        messages=messages,
        temperature=temperature,
        system=system
    )
    result = await provider.chat(chat_req)
    content = result.get("content", "")

    if session_id:
        session_manager.add_message(session_id, ChatMessage(role="user", content=prompt))
        session_manager.add_message(session_id, ChatMessage(role="assistant", content=content))

    return {
        "model": resolved_model,
        "content": content,
        "role": result.get("role", "assistant"),
        "tool_calls": result.get("tool_calls")
    }

async def mcp_generate(
    prompt: str,
    model: Optional[str] = None,
    system: Optional[str] = None,
    temperature: Optional[float] = 0.7
) -> Dict[str, Any]:
    """Generate text completion from a prompt using a Mac local model."""
    resolved_model = model_router.resolve_model(model or "auto", prompt=prompt)
    gen_req = GenerateRequest(
        model=resolved_model,
        prompt=prompt,
        temperature=temperature,
        system=system
    )
    res = await provider.generate(gen_req)
    return {
        "model": resolved_model,
        "response": res.get("response", "")
    }

async def mcp_cancel(request_id: str) -> Dict[str, Any]:
    """Cancel an in-flight local generation request on the Mac."""
    cancelled = await provider.cancel_request(request_id)
    return {"request_id": request_id, "cancelled": cancelled}

async def mcp_create_session(
    title: Optional[str] = None,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new conversational session on the gateway."""
    sess = session_manager.create_session(
        title=title,
        model=model,
        system_prompt=system_prompt
    )
    return sess.to_dict()

async def mcp_get_session(session_id: str) -> Dict[str, Any]:
    """Retrieve history of a conversation session."""
    sess = session_manager.get_session(session_id)
    if not sess:
        return {"error": f"Session '{session_id}' not found"}
    return sess.to_dict()

async def mcp_delete_session(session_id: str) -> Dict[str, Any]:
    """Delete a conversation session."""
    deleted = session_manager.delete_session(session_id)
    return {"session_id": session_id, "deleted": deleted}
