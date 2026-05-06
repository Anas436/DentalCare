from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import json

from .services import get_response


def chat_page(request):
    return render(request, 'chatbot_app/chat.html')


@require_POST
@csrf_exempt
def chat_message(request):
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        if not message:
            return JsonResponse({'error': 'Message is required', 'status': 'error'}, status=400)

        history = request.session.get('chat_history', [])

        # Pass user info if logged in
        user_id = request.user.id if request.user.is_authenticated else None

        try:
            response_text = get_response(message, history, user_id=user_id)
        except Exception as e:
            return JsonResponse({'error': str(e), 'status': 'error'}, status=500)

        history.append({'role': 'user', 'content': message})
        history.append({'role': 'assistant', 'content': response_text})
        request.session['chat_history'] = history[-50:]
        request.session.modified = True

        return JsonResponse({'response': response_text, 'status': 'success'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON', 'status': 'error'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)
