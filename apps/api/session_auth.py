"""Session-aware JWT validation kept free of API view imports."""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


def session_matches(user, token):
    return bool(
        user.active_session_started_at
        and token.get('sid')
        and str(user.active_session_id) == str(token.get('sid'))
    )


class CompanySessionJWTAuthentication(JWTAuthentication):
    """Reject an access token as soon as its user signs in elsewhere."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not session_matches(user, validated_token):
            raise InvalidToken({'detail': 'This session has ended because the account signed in on another device.'})
        return user
