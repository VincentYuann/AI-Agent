import json
from typing import Optional, Union, List, Dict, Any, Tuple
from fastapi import HTTPException, status
from google.genai.errors import APIError
from .config import client, settings
from .tools import get_agent_tools, TOOL_FUNCTIONS


def chat_with_agent(
    user_input: Union[str, List[Dict[str, Any]]],
    is_admin: bool,
    last_interaction_id: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """
    Executes an interaction loop with the Gemini Interactions API.
    Handles function calls automatically and returns (output_text, interaction_id).
    """
    tools = get_agent_tools(is_admin=is_admin)

    # Initial request payload
    kwargs: Dict[str, Any] = {
        "model": settings.MODEL_NAME,
        "input": user_input,
        "system_instruction": settings.SYSTEM_INSTRUCTION,
        "store": True,
    }

    if tools:
        kwargs["tools"] = tools

    if last_interaction_id:
        kwargs["previous_interaction_id"] = last_interaction_id

    try:
        interaction = client.interactions.create(**kwargs)
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Google Gemini Free Tier Rate Limit reached ({settings.MODEL_NAME}). Please retry in a few seconds.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API Error: {error_msg}",
        )

    # Tool execution loop
    while True:
        # Check if the model requested any function calls
        tool_calls = [s for s in interaction.steps if s.type == "function_call"]
        if not tool_calls:
            break

        function_results = []
        for call in tool_calls:
            func = TOOL_FUNCTIONS.get(call.name)
            if not func:
                result_content = [{"type": "text", "text": f"Function {call.name} not found"}]
            else:
                args = call.arguments or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args else {}
                    except json.JSONDecodeError:
                        args = {}
                result_content = func(**args)

            function_results.append({
                "type": "function_result",
                "name": call.name,
                "call_id": call.id,
                "result": result_content,
            })

        try:
            # Send tool results back to Gemini in the same conversation
            interaction = client.interactions.create(
                model=settings.MODEL_NAME,
                previous_interaction_id=interaction.id,
                input=function_results,
            )
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Google Gemini Free Tier Rate Limit reached. Please retry in a few seconds.",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gemini API Tool Follow-up Error: {error_msg}",
            )

    output = interaction.output_text or ""
    return output, interaction.id
