from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_access_token
from app.models.user import User


def redirect_to_login() -> RedirectResponse:
    """Единый redirect для web-страниц при отсутствии валидной сессии."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


def get_user_from_cookie(request: Request, db: Session) -> User | None:
    """Возвращает активного пользователя из web-cookie access_token."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        return None
    return db.query(User).options(joinedload(User.role)).filter(User.id == user_id, User.is_active.is_(True)).first()


def require_web_user(request: Request, db: Session) -> User | RedirectResponse:
    """Для web-страниц возвращает пользователя или redirect на login."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    return user


def require_web_roles(request: Request, db: Session, *role_codes: str) -> User | RedirectResponse:
    """Проверяет роль пользователя на web-страницах."""
    user = require_web_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    if user.role.code not in role_codes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


def require_web_admin(request: Request, db: Session) -> User | RedirectResponse:
    return require_web_roles(request, db, "admin")


def require_web_manager_or_admin(request: Request, db: Session) -> User | RedirectResponse:
    return require_web_roles(request, db, "admin", "manager")
