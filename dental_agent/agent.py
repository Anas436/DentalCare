from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from typing import List, Dict
import json

from dental_agent.config.settings import (
    GROQ_API_KEY, MODEL_NAME, TEMPERATURE,
    VALID_SPECIALIZATIONS, VALID_DOCTORS
)

SPECIALIZATIONS_STR = ", ".join(VALID_SPECIALIZATIONS)

SYSTEM_PROMPT = f"""You are a professional dental appointment assistant. Help patients book, cancel, and reschedule appointments politely.

AVAILABLE SPECIALIZATIONS: {SPECIALIZATIONS_STR}

IMPORTANT: "endodontist" IS available. "Endodontist" (capital E) = "endodontist" (lowercase).

RULES:
10. If the user only provides a specialization and no doctor name, automatically select the first available doctor for that specialization.
9. Never mention that the user ID is fictional; if no real ID is available, simply state that the booking will be created for the provided phone number.
1. Always maintain a formal, professional tone. Address users respectfully.
2. If user requests a specialization, check the AVAILABLE SPECIALIZATIONS list above.
3. For "emergency dentist", use "emergency_dentist" (with underscore).
4. Help user step-by-step: specialization -> doctor -> date -> phone.
5. NEVER make up values like phone numbers. Ask the user.
6. Always confirm appointment details with the user before booking or cancelling.
7. After completing a booking or cancellation, provide a clear summary of the action taken.
8. Use the tools available to you when you need to query or modify appointment data.
9. When using tools, provide all required parameters accurately.
10. If the user requests a list of doctors for a specialization, you MUST call `list_doctors_by_specialization` with that specialization and use its result; never fabricate doctor names.
"""


def get_response(message: str, history: List[Dict[str, str]], user_id: int = None) -> str:
    # Pre-check for invalid specializations
    message_lower = message.lower()
    for inv in ["periodontist"]:
        if inv in message_lower:
            return f"Thank you for your inquiry. We do not have {inv} available. The available specializations are: {SPECIALIZATIONS_STR}"

    # Lazy-load tools (avoids Django import error at module level)
    from dental_agent.tools.db_reader import (
        get_available_slots,
        get_patient_appointments,
        check_slot_availability,
        list_doctors_by_specialization,
    )
    from dental_agent.tools.db_writer import (
        appointment,
        cancel_appointment,
        reschedule_appointment,
    )

    ALL_TOOLS = [
        get_available_slots,
        get_patient_appointments,
        check_slot_availability,
        list_doctors_by_specialization,
        appointment,
        cancel_appointment,
        reschedule_appointment,
    ]

    llm = ChatGroq(api_key=GROQ_API_KEY, model=MODEL_NAME, temperature=TEMPERATURE).bind_tools(ALL_TOOLS)

    # Keep only last 10 messages to stay within token limits
    recent_history = history[-5:] if len(history) > 5 else history

    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    for msg in recent_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=message))

    for _ in range(5):
        try:
            response = llm.invoke(messages)
        except Exception as e:
            return f"Thank you for your patience. I encountered an error: {str(e)}"

        # No tool call — return conversational response
        if not response.tool_calls:
            return response.content

        # Process tool calls
        messages.append(response)
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {}).copy()

            # Remove user_id if LLM hallucinated it (not part of tool schema)
            tool_args.pop("user_id", None)

            # Inject logged-in user's phone number for tools that need it
            if user_id and tool_name in ["appointment", "cancel_appointment"]:
                if not tool_args.get("patient_phone"):
                    try:
                        from django.contrib.auth.models import User
                        from appointments.models import PatientProfile
                        user = User.objects.get(id=user_id)
                        profile = PatientProfile.objects.get(user=user)
                        # Strip any leading non‑digit characters (e.g., '+')
                        cleaned = ''.join(ch for ch in profile.phone if ch.isdigit())
                        tool_args["patient_phone"] = cleaned
                    except Exception:
                        pass

            # Find and execute the tool
            tool_func = next((t for t in ALL_TOOLS if t.name == tool_name), None)
            if not tool_func:
                result = f"Tool '{tool_name}' is not available."
            else:
                try:
                    # Inject user_id for logged-in users (not exposed to LLM schema)
                    if user_id and tool_name in ["appointment", "cancel_appointment"]:
                        tool_args["user_id"] = user_id
                    # Call underlying function directly to pass user_id
                    result = tool_func.func(**tool_args)
                except Exception as e:
                    result = f"Error executing {tool_name}: {str(e)}"

            # Format result for the LLM
            if isinstance(result, (dict, list)):
                result_str = json.dumps(result)
            else:
                result_str = str(result)

            messages.append(ToolMessage(content=result_str, tool_call_id=tool_call["id"]))

    return "Thank you for your patience. I was unable to fully process your request. Please try again or rephrase your request."
