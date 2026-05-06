from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import ToolNode
from dental_agent.config.settings import GROQ_API_KEY, MODEL_NAME, TEMPERATURE
from dental_agent.models.state import AppointmentState
from dental_agent.tools.db_reader import get_patient_appointments
from dental_agent.tools.db_writer import cancel_appointment
from dental_agent.utils import sanitize_messages

CANCEL_TOOLS = [get_patient_appointments, cancel_appointment]

CANCEL_SYSTEM = """You are the Cancellation Agent for a dental appointment management system. You must always maintain a formal, professional, and courteous tone.

Your ONLY job is to cancel existing appointments.

## Workflow
1. Collect REQUIRED information:
    - patient_phone  : patient's phone number (e.g., +1234567890)
    - date_slot      : the specific slot to cancel in M/D/YYYY H:MM format

2. If the patient does not know the exact slot, call get_patient_appointments(patient_phone)
    to list their bookings, then ask which one to cancel.

3. Confirm with the user before proceeding:
    "Kindly confirm: Are you sure you want to cancel the appointment at {date_slot} with {doctor_name}? Please reply with 'yes' to proceed or 'no' to keep the appointment."

4. On user confirmation, call cancel_appointment(patient_phone, date_slot).

5. Inform the user of the outcome in a professional manner.

## Rules
- Always use formal language (e.g., "I can assist you with cancelling your appointment.", "Please provide your phone number.", "Kindly confirm the cancellation.").
- Always confirm before cancelling — ask "yes/no" explicitly.
- If the patient has no appointments, inform them kindly and formally.
- Do NOT cancel if the phone number does not match the booking.
- If the user already confirmed in their message (e.g. "yes, cancel it"), skip asking again.
- Always summarize the completed cancellation formally (e.g., "Your appointment at {date_slot} with Dr. {doctor_name} has been successfully cancelled.").

## Date Format
M/D/YYYY H:MM (e.g., 5/8/2026 8:30)
"""

CANCEL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", CANCEL_SYSTEM),
    ("placeholder", "{messages}"),
])

cancellation_tool_node = ToolNode(tools=CANCEL_TOOLS)


def cancellation_agent_node(state: AppointmentState) -> dict:
    llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model=MODEL_NAME,
        temperature=TEMPERATURE,
    ).bind_tools(CANCEL_TOOLS)

    chain = CANCEL_PROMPT | llm
    response = chain.invoke({"messages": sanitize_messages(state["messages"])})
    return {
        "messages": [response],
        "final_response": response.content if not response.tool_calls else None,
    }
