from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(tags=["web-integrations"])
templates = Jinja2Templates(directory="app/templates")


def redirect_to_login() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


def get_user_from_cookie(request: Request, db: Session) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        return None
    return db.query(User).options(joinedload(User.role)).filter(User.id == user_id, User.is_active.is_(True)).first()


def require_manager_or_admin(request: Request, db: Session) -> User | RedirectResponse:
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    if user.role.code not in {"admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    user = require_manager_or_admin(request, db)
    if isinstance(user, RedirectResponse):
        return user
    notifications = db.query(Notification).order_by(Notification.created_at.desc()).limit(100).all()
    return templates.TemplateResponse("notifications.html", {"request": request, "user": user, "notifications": notifications})
