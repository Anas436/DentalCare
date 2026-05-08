from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from typing import List, Dict
import json
import re

from dental_agent.config.settings import (
    GROQ_API_KEY, MODEL_NAME, TEMPERATURE,
    VALID_SPECIALIZATIONS, VALID_DOCTORS
)

SPECIALIZATIONS_STR = ", ".join(VALID_SPECIALIZATIONS)

SYSTEM_PROMPT = f"""You are a professional dental appointment assistant. Help patients book, cancel, and reschedule appointments politely.

AVAILABLE SPECIALIZATIONS: {SPECIALIZATIONS_STR}

AVAILABLE TOOLS (use these EXACT names):
- get_available_slots: Find available appointment slots
- get_patient_appointments: Get a patient's existing appointments
- check_slot_availability: Check if a specific slot is available
- list_doctors_by_specialization: List doctors by specialization
- appointment: Book a new appointment
- cancel_appointment: Cancel an existing appointment
- reschedule_appointment: Reschedule an existing appointment

RULES:
- Never fabricate phone numbers. Ask the user.
- If only a specialization is given, pick the first available doctor.
- Always confirm details before booking.
- Use `appointment` ONLY for NEW bookings. NEVER for rescheduling.
- Use `reschedule_appointment` ONLY for rescheduling existing bookings. NEVER use `appointment` for rescheduling.
- Use `cancel_appointment` when the user asks to cancel a booking.
- When user says "cancel", call `cancel_appointment` IMMEDIATELY. Do NOT call `get_available_slots` or `check_slot_availability`.
- When user says "reschedule" or "reschdule", call `reschedule_appointment` IMMEDIATELY. Do NOT call `appointment`.
- All tools accept aliases: patientphone, doctorname, dateslot, currentdateslot, newdateslot.
"""


TOOL_NAME_ALIASES = {
    "availableslots": "get_available_slots",
    "availableslot": "get_available_slots",
    "available_slots": "get_available_slots",
    "getavailableslots": "get_available_slots",
    "patientappointments": "get_patient_appointments",
    "patient_appointments": "get_patient_appointments",
    "checkavailability": "check_slot_availability",
    "slotavailability": "check_slot_availability",
    "doctorsbyspecialization": "list_doctors_by_specialization",
    "listdoctors": "list_doctors_by_specialization",
}


def _lenient_json_parse(s: str) -> dict | None:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r'(?<=:)\s*0+(\d+)', r' \1', s)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


def _parse_failed_generation(error: Exception) -> tuple[str | None, dict | None]:
    body = getattr(error, 'body', None)
    if isinstance(body, dict):
        fg = body.get('error', {}).get('failedgeneration', '')
    else:
        error_str = str(error)
        m = re.search(r"'failedgeneration':\s*'([^']*)'", error_str)
        if m:
            fg = m.group(1)
        else:
            return None, None
    if not fg or ">" not in fg:
        return None, None
    name, _, remainder = fg.partition(">")
    brace_start = remainder.find("{")
    brace_end = remainder.rfind("}")
    if brace_start == -1 or brace_end == -1:
        return None, None
    args_json = remainder[brace_start:brace_end + 1]
    args = _lenient_json_parse(args_json)
    if args is None:
        return None, None
    return name.strip(), args


def _execute_tool_directly(
    tool_name: str, tool_args: dict, all_tools: list, user_id: int | None
) -> tuple[str, dict] | None:
    corrected = TOOL_NAME_ALIASES.get(tool_name, tool_name)
    tool_func = next((t for t in all_tools if t.name == corrected), None)
    if not tool_func:
        return None
    for key in ("user_id", "userid", "kwargs"):
        tool_args.pop(key, None)
    if user_id and corrected in ["appointment", "cancel_appointment", "reschedule_appointment"]:
        if not tool_args.get("patient_phone"):
            try:
                from django.contrib.auth.models import User
                from appointments.models import PatientProfile
                user = User.objects.get(id=user_id)
                profile = PatientProfile.objects.get(user=user)
                cleaned = "".join(ch for ch in profile.phone if ch.isdigit())
                tool_args["patient_phone"] = cleaned
            except Exception:
                pass
        tool_args["user_id"] = user_id
    try:
        result = tool_func.func(**tool_args)
    except Exception as e:
        result = f"Error executing {corrected}: {str(e)}"
    if isinstance(result, (dict, list)):
        result_str = json.dumps(result)
    else:
        result_str = str(result)
    if len(result_str) > 500:
        result_str = result_str[:500] + "..."
    return corrected, {"content": result_str}


def _handle_failed_tool_call(
    error: Exception, messages: list, all_tools: list, user_id: int | None
) -> bool:
    tool_name, tool_args = _parse_failed_generation(error)
    if not tool_name:
        return False
    result = _execute_tool_directly(tool_name, tool_args, all_tools, user_id)
    if not result:
        return False
    corrected_name, tool_output = result
    placeholder = AIMessage(content=f"I'll retrieve that information for you.")
    messages.append(placeholder)
    messages.append(ToolMessage(content=tool_output["content"], tool_call_id="fallback"))
    return True


def get_response(message: str, history: List[Dict[str, str]], user_id: int = None) -> str:
    # Pre-check for invalid specializations
    message_lower = message.lower()
    for inv in ["periodontist"]:
        if inv in message_lower:
            return f"Thank you for your inquiry. We do not have {inv} available. The available specializations are: {SPECIALIZATIONS_STR}"

    # Collect user info for system prompt
    user_info = ""
    if user_id:
        try:
            from django.contrib.auth.models import User
            from appointments.models import PatientProfile
            user = User.objects.get(id=user_id)
            profile = PatientProfile.objects.get(user=user)
            user_info = f"\nLOGGED-IN USER: {user.get_full_name() or user.username}, PHONE: {profile.phone}\n"
        except Exception:
            pass

    prompt = SYSTEM_PROMPT + user_info + (
        "\nIMPORTANT: Do NOT fabricate phone numbers. The logged-in user's phone number is shown above. "
        "Use it when booking. Do NOT ask the user for their phone number or show a fake one."
        if user_info else ""
    )

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

    # Keep only last 3 messages to stay within token limits
    recent_history = history[-3:] if len(history) > 3 else history

    messages = [SystemMessage(content=prompt)]
    for msg in recent_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=message))

    for _ in range(3):
        try:
            response = llm.invoke(messages)
        except Exception as e:
            handled = _handle_failed_tool_call(e, messages, ALL_TOOLS, user_id)
            if not handled:
                messages.append(HumanMessage(
                    content="Use ONLY one of these exact tool names: get_available_slots, get_patient_appointments, check_slot_availability, list_doctors_by_specialization, appointment, cancel_appointment, reschedule_appointment. Try again with the correct name."
                ))
            continue

        # No tool call — return conversational response
        if not response.tool_calls:
            return response.content

        # Process tool calls
        messages.append(response)
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {}).copy()

            # Remove hallucinated params that aren't in schema
            for key in ("user_id", "userid", "kwargs"):
                tool_args.pop(key, None)

            # Inject logged-in user's phone number for tools that need it
            if user_id and tool_name in ["appointment", "cancel_appointment", "reschedule_appointment"]:
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
                    if user_id and tool_name in ["appointment", "cancel_appointment", "reschedule_appointment"]:
                        tool_args["user_id"] = user_id
                    # Call underlying function directly to pass user_id
                    result = tool_func.func(**tool_args)
                except Exception as e:
                    result = f"Error executing {tool_name}: {str(e)}"

            # Format result for the LLM (truncate to avoid token limits)
            if isinstance(result, (dict, list)):
                result_str = json.dumps(result)
            else:
                result_str = str(result)
            if len(result_str) > 500:
                result_str = result_str[:500] + "..."

            messages.append(ToolMessage(content=result_str, tool_call_id=tool_call["id"]))

    return "Thank you for your patience. I was unable to fully process your request. Please try again or rephrase your request."
