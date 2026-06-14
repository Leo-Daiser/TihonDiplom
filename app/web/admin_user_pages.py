from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_access_token, hash_password
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import write_audit_log

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


def get_role_by_code(db: Session, code: str) -> Role:
    role = db.query(Role).filter(Role.code == code).first()
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестная роль")
    return role


def parse_is_active(value: str | None) -> bool:
    return value == "on"


def page_context(request: Request, current_user: User, db: Session, **extra):
    context = {"request": request, "user": current_user, "roles": db.query(Role).order_by(Role.id.asc()).all()}
    context.update(extra)
    return context


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_admin(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user
    users = users_query(db).order_by(User.is_active.desc(), User.id.asc()).all()
    return templates.TemplateResponse("admin_users.html", {"request": request, "user": current_user, "users": users})


@router.get("/admin/users/new", response_class=HTMLResponse)
def new_admin_user_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_admin(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user
    return templates.TemplateResponse("admin_user_form.html", page_context(request, current_user, db, edited_user=None, page_title="Новый пользователь", form_action="/admin/users/new", submit_label="Создать пользователя"))


@router.post("/admin/users/new")
def create_admin_user(request: Request, email: str = Form(...), full_name: str = Form(...), password: str = Form(...), role_code: str = Form(...), is_active: str | None = Form(default=None), db: Session = Depends(get_db)):
    current_user = require_admin(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким email уже существует")
    role = get_role_by_code(db, role_code)
    created_user = User(email=email, full_name=full_name, hashed_password=hash_password(password), role_id=role.id, is_active=parse_is_active(is_active))
    db.add(created_user)
    db.flush()
    write_audit_log(db, actor_id=current_user.id, entity_type="user", entity_id=created_user.id, action="create_user", diff={"email": email, "role": role.code, "is_active": created_user.is_active})
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
def edit_admin_user_page(request: Request, user_id: int, db: Session = Depends(get_db)):
    current_user = require_admin(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user
    edited_user = users_query(db).filter(User.id == user_id).first()
    if edited_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return templates.TemplateResponse("admin_user_form.html", page_context(request, current_user, db, edited_user=edited_user, page_title=f"Редактирование пользователя #{edited_user.id}", form_action=f"/admin/users/{edited_user.id}/edit", submit_label="Сохранить изменения"))


@router.post("/admin/users/{user_id}/edit")
def edit_admin_user(request: Request, user_id: int, full_name: str = Form(...), password: str | None = Form(default=None), role_code: str = Form(...), is_active: str | None = Form(default=None), db: Session = Depends(get_db)):
    current_user = require_admin(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user
    edited_user = users_query(db).filter(User.id == user_id).first()
    if edited_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    role = get_role_by_code(db, role_code)
    new_is_active = parse_is_active(is_active)
    changes = {}
    if full_name != edited_user.full_name:
        changes["full_name"] = {"old": edited_user.full_name, "new": full_name}
        edited_user.full_name = full_name
    if password:
        changes["password"] = "changed"
        edited_user.hashed_password = hash_password(password)
    if role.id != edited_user.role_id:
        changes["role"] = {"old": edited_user.role.code, "new": role.code}
        edited_user.role_id = role.id
    if new_is_active != edited_user.is_active:
        changes["is_active"] = {"old": edited_user.is_active, "new": new_is_active}
        edited_user.is_active = new_is_active
    if changes:
        write_audit_log(db, actor_id=current_user.id, entity_type="user", entity_id=edited_user.id, action="update_user", diff=changes)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)
