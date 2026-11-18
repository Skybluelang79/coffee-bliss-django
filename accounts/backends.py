from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        email = username or kwargs.get(UserModel.USERNAME_FIELD) or kwargs.get("email")
        if not email or password is None:
            return None

        user = (
            UserModel._default_manager.filter(email__iexact=str(email).strip())
            .order_by("pk")
            .first()
        )
        if user is None:
            UserModel().set_password(password)
            return None

        if not user.check_password(password) or not self.user_can_authenticate(user):
            return None
        return user
