import json
from typing import Optional, Union, List, Dict, Any, Tuple, Generator
from fastapi import HTTPException, status
from .config import client, settings
from .tools import get_agent_tools, TOOL_FUNCTIONS


def chat_with_agent_stream(
    user_input: Union[str, List[Dict[str, Any]]],
    is_admin: bool,
    last_interaction_id: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Executes a real-time streaming interaction loop with Gemini Interactions API.
    Streams incremental text tokens and automatically executes tool calls.
    Yields event dictionaries:
      - {"type": "delta", "text": "..."}
      - {"type": "tool_start", "name": "..."}
      - {"type": "done", "interaction_id": "...", "model": "..."}
    """
    tools = get_agent_tools(is_admin=is_admin)
    current_input = user_input
    current_interaction_id = last_interaction_id

    while True:
        kwargs: Dict[str, Any] = {
            "model": settings.MODEL_NAME,
            "input": current_input,
            "system_instruction": settings.get_system_instruction(is_admin=is_admin),
            "generation_config": {"thinking_level": settings.THINKING_LEVEL},
            "store": True,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = tools

        if current_interaction_id:
            kwargs["previous_interaction_id"] = current_interaction_id

        try:
            stream = client.interactions.create(**kwargs)
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit reached. Please wait a few moments and try again.",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The AI service is momentarily unavailable. Please try again shortly.",
            )

        current_calls = {}

        try:
            for event in stream:
                if event.event_type == "interaction.created":
                    current_interaction_id = event.interaction.id
                elif event.event_type == "step.start":
                    step = event.step
                    if step.type == "function_call":
                        current_calls[event.index] = {
                            "id": step.id,
                            "name": step.name,
                            "arguments": getattr(step, "arguments", None) or {},
                            "raw_arguments": "",
                        }
                        yield {"type": "tool_start", "name": step.name}
                elif event.event_type == "step.delta":
                    if event.delta.type == "text":
                        yield {"type": "delta", "text": event.delta.text}
                    elif event.delta.type == "arguments_delta":
                        if event.index in current_calls:
                            current_calls[event.index]["raw_arguments"] += event.delta.arguments
                elif event.event_type == "interaction.completed":
                    current_interaction_id = event.interaction.id
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit reached. Please wait a few moments and try again.",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error during stream generation: {error_msg}",
            )

        # If no tool calls were requested, generation is complete
        if not current_calls:
            yield {
                "type": "done",
                "interaction_id": current_interaction_id,
                "model": settings.MODEL_NAME,
            }
            break

        # Execute requested tools and prepare function_result inputs
        function_results = []
        allowed_tool_names = {t["name"] for t in tools} if tools else set()
        for call in current_calls.values():
            func_name = call["name"]
            func_id = call["id"]

            if func_name not in allowed_tool_names:
                result_content = f"Unauthorized: Tool '{func_name}' is not permitted for your current access level."
            else:
                raw_args = call.get("raw_arguments", "")
                if raw_args:
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                elif isinstance(call.get("arguments"), dict):
                    args = call["arguments"]
                elif isinstance(call.get("arguments"), str) and call["arguments"]:
                    try:
                        args = json.loads(call["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = {}

                func = TOOL_FUNCTIONS.get(func_name)
                if not func:
                    result_content = f"Function {func_name} not found"
                else:
                    result_content = func(**args)

            # If tool returned a single text content block, unwrap to plain text for Interactions API
            if isinstance(result_content, list) and len(result_content) == 1 and isinstance(result_content[0], dict) and result_content[0].get("type") == "text":
                final_result = result_content[0]["text"]
            else:
                final_result = result_content

            function_results.append({
                "type": "function_result",
                "name": func_name,
                "call_id": func_id,
                "result": final_result,
            })

        current_input = function_results


def chat_with_agent(
    user_input: Union[str, List[Dict[str, Any]]],
    is_admin: bool,
    last_interaction_id: Optional[str] = None,
) -> Tuple[str, Optional[str], str]:
    """
    Synchronous wrapper for chat_with_agent_stream.
    Accumulates streamed text deltas and returns (output_text, interaction_id, model_used).
    """
    full_text: List[str] = []
    interaction_id = last_interaction_id
    model_used = settings.MODEL_NAME

    for event in chat_with_agent_stream(user_input, is_admin, last_interaction_id):
        event_type = event.get("type")
        if event_type == "delta":
            full_text.append(event.get("text", ""))
        elif event_type == "done":
            interaction_id = event.get("interaction_id")
            model_used = event.get("model", settings.MODEL_NAME)

    return "".join(full_text), interaction_id, model_used
