from dental_agent.agent import get_response as agent_get_response


def get_response(message: str, history: list, user_id: int = None) -> str:
    return agent_get_response(message, history, user_id=user_id)


def stream_response(message: str, history: list, user_id: int = None):
    # Simple non-streaming fallback
    text = agent_get_response(message, history, user_id=user_id)
    yield text
