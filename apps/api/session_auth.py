"""Session-aware JWT validation kept free of API view imports."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


def session_matches(user, token):
    return bool(
        user.active_session_started_at
        and token.get('sid')
        and str(user.active_session_id) == str(token.get('sid'))
    )


def session_is_recent(user):
    """Return whether a session should block a different browser from signing in."""
    if not user.active_session_started_at:
        return False
    timeout = getattr(settings, 'ACTIVE_SESSION_CONFLICT_WINDOW', timedelta(minutes=5))
    return user.active_session_started_at >= timezone.now() - timeout


def touch_session(user):
    """Keep the active marker current without writing on every API request."""
    now = timezone.now()
    touch_interval = getattr(settings, 'ACTIVE_SESSION_TOUCH_INTERVAL', timedelta(seconds=60))
    if user.active_session_started_at and user.active_session_started_at >= now - touch_interval:
        return
    type(user).objects.filter(pk=user.pk, active_session_id=user.active_session_id).update(
        active_session_started_at=now,
    )
    user.active_session_started_at = now


class CompanySessionJWTAuthentication(JWTAuthentication):
    """Reject an access token as soon as its user signs in elsewhere."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not session_matches(user, validated_token):
            raise InvalidToken({'detail': 'This session has ended because the account signed in from another browser or device.'})
        touch_session(user)
        return user
