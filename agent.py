import json
from config import client, MODEL_NAME, SYSTEM_INSTRUCTION
from tools import TOOLS_SCHEMA, TOOL_FUNCTIONS


def chat_with_agent(last_interaction_id: str | None, user_input) -> str:
    current_interaction_id = last_interaction_id
    current_input = user_input

    while True:
        stream = client.interactions.create(
            model=MODEL_NAME,
            input=current_input,
            system_instruction=SYSTEM_INSTRUCTION,
            store=True,
            stream=True,
            tools=TOOLS_SCHEMA,
            previous_interaction_id=current_interaction_id,
        )

        current_calls = {}

        for event in stream:
            if event.event_type == "interaction.created":
                current_interaction_id = event.interaction.id
            elif event.event_type == "step.start":
                step = event.step
                if step.type == "function_call":
                    current_calls[event.index] = {
                        "id": step.id,
                        "name": step.name,
                        "arguments": "",
                    }
                    print(f"\n[Invoking tool: {step.name}...]", flush=True)
            elif event.event_type == "step.delta":
                if event.delta.type == "text":
                    print(event.delta.text, end="", flush=True)
                elif event.delta.type == "arguments_delta":
                    current_calls[event.index]["arguments"] += event.delta.arguments
            elif event.event_type == "error":
                print(f"\n[Stream Error ({event.error.code}): {event.error.message}]\n")
                return None
            elif event.event_type == "interaction.completed":
                current_interaction_id = event.interaction.id

        if not current_calls:
            print("\n")
            break

        # Execute requested tools and prepare function_result inputs
        function_results = []
        for call in current_calls.values():
            func_name = call["name"]
            func_id = call["id"]
            raw_args = call["arguments"]

            func = TOOL_FUNCTIONS[func_name]
            args = json.loads(raw_args) if raw_args else {}
            result_content = func(**args)

            function_results.append({
                "type": "function_result",
                "name": func_name,
                "call_id": func_id,
                "result": result_content,
            })

        current_input = function_results

    return current_interaction_id
