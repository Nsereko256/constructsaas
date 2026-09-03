from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken


@database_sync_to_async
def get_user_from_token(token):
    if not token:
        return AnonymousUser()
    try:
        validated_token = UntypedToken(token)
        user_id = validated_token.get('user_id')
        user = get_user_model().objects.select_related('company').get(
            pk=user_id,
            is_active=True,
            company__is_active=True,
        )
        if not user.active_session_started_at or str(user.active_session_id) != str(validated_token.get('sid')):
            return AnonymousUser()
        return user
    except (InvalidToken, TokenError, get_user_model().DoesNotExist, KeyError, TypeError):
        return AnonymousUser()


class JwtWebSocketAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        user = scope.get('user')
        if not user or not user.is_authenticated:
            query = parse_qs(scope.get('query_string', b'').decode())
            token = query.get('token', [None])[0]
            scope['user'] = await get_user_from_token(token)
        return await self.inner(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    return AuthMiddlewareStack(JwtWebSocketAuthMiddleware(inner))
