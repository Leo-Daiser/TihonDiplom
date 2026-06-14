from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User

router = APIRouter(tags=["web-admin-users"])
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


def require_admin(request: Request, db: Session) -> User | RedirectResponse:
    user = get_user_from_cookie(request, db)
    if user is None:
        return redirect_to_login()
    if user.role.code != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


def users_query(db: Session):
    return db.query(User).options(joinedload(User.role))


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_admin(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user
    users = users_query(db).order_by(User.is_active.desc(), User.id.asc()).all()
    roles = db.query(Role).order_by(Role.id.asc()).all()
    return templates.TemplateResponse("admin_users.html", {"request": request, "user": current_user, "users": users, "roles": roles})
