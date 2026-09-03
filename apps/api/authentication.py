from django.utils import timezone
from uuid import uuid4
from rest_framework import serializers
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .session_auth import session_matches


class ActiveSessionConflict(APIException):
    status_code = 409
    default_detail = 'This account is already active on another device. Confirm to sign out that device and continue here.'
    default_code = 'active_session'


def _blacklist_other_refresh_tokens(user, current_jti):
    for token in OutstandingToken.objects.filter(user=user).exclude(jti=current_jti):
        BlacklistedToken.objects.get_or_create(token=token)


class CompanyTokenObtainPairSerializer(TokenObtainPairSerializer):
    terminate_other_session = serializers.BooleanField(required=False, default=False, write_only=True)

    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.company_id or not self.user.company.is_active:
            raise AuthenticationFailed(
                'No active company account was found for these credentials.',
                code='no_active_account',
            )
        if self.user.active_session_started_at and not attrs.get('terminate_other_session'):
            raise ActiveSessionConflict()
        refresh = RefreshToken(data['refresh'])
        self.user.active_session_id = uuid4()
        self.user.active_session_started_at = timezone.now()
        self.user.save(update_fields=['active_session_id', 'active_session_started_at'])
        _blacklist_other_refresh_tokens(self.user, refresh['jti'])
        refresh['sid'] = str(self.user.active_session_id)
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)
        return data


class CompanyTokenObtainPairView(TokenObtainPairView):
    serializer_class = CompanyTokenObtainPairSerializer


class CompanyTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs['refresh'])
        from apps.accounts.models import User
        try:
            user = User.objects.get(pk=refresh['user_id'], is_active=True)
        except (User.DoesNotExist, KeyError):
            raise InvalidToken({'detail': 'Invalid refresh token.'})
        if not session_matches(user, refresh):
            raise InvalidToken({'detail': 'This session has ended because the account signed in on another device.'})
        return super().validate(attrs)


class CompanyTokenRefreshView(TokenRefreshView):
    serializer_class = CompanyTokenRefreshSerializer


class CompanyTokenLogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_value = request.data.get('refresh')
        if not refresh_value:
            return Response({'detail': 'Refresh token is required.'}, status=400)
        try:
            refresh = RefreshToken(refresh_value)
            if str(refresh.get('user_id')) != str(request.user.id) or not session_matches(request.user, refresh):
                raise InvalidToken()
            OutstandingToken.objects.filter(user=request.user, jti=refresh['jti']).first()
            _blacklist_other_refresh_tokens(request.user, None)
            request.user.active_session_started_at = None
            request.user.save(update_fields=['active_session_started_at'])
        except Exception:
            return Response({'detail': 'Session could not be closed.'}, status=400)
        return Response(status=204)
