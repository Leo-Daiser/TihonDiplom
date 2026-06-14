from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.notification import Notification
from app.web.deps import require_web_manager_or_admin

router = APIRouter(tags=["web-integrations"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    user = require_web_manager_or_admin(request, db)
    if isinstance(user, RedirectResponse):
        return user
    notifications = db.query(Notification).order_by(Notification.created_at.desc()).limit(100).all()
    return templates.TemplateResponse(request, "notifications.html", {"request": request, "user": user, "notifications": notifications})
