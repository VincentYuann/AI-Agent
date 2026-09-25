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
) -> Tuple[str, Optional[str], str]:
    """
    Executes an interaction loop with the Gemini Interactions API.
    Attempts primary model (settings.MODEL_NAME), and falls back to
    settings.FALLBACK_MODEL_NAME if rate limited or unavailable.
    Handles function calls automatically and returns (output_text, interaction_id, model_used).
    """
    tools = get_agent_tools(is_admin=is_admin)

    models_to_try = [settings.MODEL_NAME]
    if settings.FALLBACK_MODEL_NAME and settings.FALLBACK_MODEL_NAME != settings.MODEL_NAME:
        models_to_try.append(settings.FALLBACK_MODEL_NAME)

    last_error_msg = ""

    for index, active_model in enumerate(models_to_try):
        kwargs: Dict[str, Any] = {
            "model": active_model,
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
            last_error_msg = error_msg
            has_fallback = index < len(models_to_try) - 1

            if has_fallback:
                print(f"[AGENT] Model {active_model} failed: {error_msg}. Retrying with fallback {models_to_try[index + 1]}...")
                continue

            if "429" in error_msg or "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit reached. Please wait a few moments and try again.",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The AI service is momentarily unavailable. Please try again shortly.",
            )

        # Tool execution loop
        while True:
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
                interaction = client.interactions.create(
                    model=active_model,
                    previous_interaction_id=interaction.id,
                    input=function_results,
                )
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "rate limit" in error_msg.lower():
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit reached. Please wait a few moments and try again.",
                    )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="The AI service encountered an issue processing tool data. Please try again.",
                )

        output = interaction.output_text or ""
        return output, interaction.id, active_model

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="The AI service is momentarily unavailable. Please try again shortly.",
    )
