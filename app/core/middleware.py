from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin

from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken


class JWTAuthMiddleware(MiddlewareMixin):
    def process_request(self, request):
        token = self._extract_bearer_token(request)

        if not token:
            request.user = AnonymousUser()
            return

        try:
            validated_token = AccessToken(token)
            payload = validated_token.payload
            user_model = get_user_model()
            user = user_model.objects.get(public_id=payload.get("user_id"))
            request.user = user
            request.auth_session_id = payload.get("sid")
        except (InvalidToken, TokenError, KeyError, get_user_model().DoesNotExist):
            request.user = AnonymousUser()
            request.auth_session_id = None

    @staticmethod
    def _extract_bearer_token(request):
        authorization_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not authorization_header.startswith("Bearer "):
            return None
        return authorization_header.split(" ", 1)[1].strip()
