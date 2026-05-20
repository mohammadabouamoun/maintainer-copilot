import uuid
import structlog
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from typing import List

from app.services.auth import current_active_user, require_role
from app.repositories.models import Widget
from app.domain.schemas import WidgetCreate, WidgetUpdate, WidgetRead, WidgetPublicRead
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger()
router = APIRouter()

@router.post("", response_model=WidgetRead, status_code=201)
async def create_widget(
    request: Request,
    body: WidgetCreate,
    admin_user=Depends(require_role("admin"))
):
    """Admin only: Create a new widget configuration."""
    logger.info("Creating widget", user_id=str(admin_user.id))
    db_engine = request.app.state.db_engine
    
    async with AsyncSession(db_engine) as session:
        async with session.begin():
            widget = Widget(
                allowed_origins=body.allowed_origins,
                theme=body.theme,
                greeting=body.greeting,
                enabled_tools=body.enabled_tools,
                created_by=admin_user.id
            )
            session.add(widget)
            await session.flush()
            
            return {
                "id": widget.id,
                "widget_id": widget.widget_id,
                "allowed_origins": widget.allowed_origins,
                "theme": widget.theme,
                "greeting": widget.greeting,
                "enabled_tools": widget.enabled_tools,
                "created_by": widget.created_by,
                "created_at": widget.created_at
            }

@router.get("", response_model=List[WidgetRead])
async def list_widgets(
    request: Request,
    admin_user=Depends(require_role("admin"))
):
    """Admin only: List all widgets."""
    db_engine = request.app.state.db_engine
    async with AsyncSession(db_engine) as session:
        stmt = select(Widget).order_by(Widget.created_at.desc())
        res = await session.execute(stmt)
        widgets = res.scalars().all()
        
    return [
        {
            "id": w.id,
            "widget_id": w.widget_id,
            "allowed_origins": w.allowed_origins,
            "theme": w.theme,
            "greeting": w.greeting,
            "enabled_tools": w.enabled_tools,
            "created_by": w.created_by,
            "created_at": w.created_at
        }
        for w in widgets
    ]

@router.get("/{widget_id}/public", response_model=WidgetPublicRead)
async def get_widget_public(
    widget_id: str,
    request: Request,
    response: Response
):
    """
    Public no-auth endpoint used by the embedded iframe to fetch theme configuration.
    Injects Content-Security-Policy frame-ancestors headers dynamically based on allowed_origins.
    """
    db_engine = request.app.state.db_engine
    try:
        w_uuid = uuid.UUID(widget_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid widget ID format")
        
    async with AsyncSession(db_engine) as session:
        stmt = select(Widget).where(Widget.widget_id == w_uuid)
        res = await session.execute(stmt)
        widget = res.scalar_one_or_none()
        
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
        
    # Inject CSP Header to prevent clickjacking except from allowed origins
    # Format: Content-Security-Policy: frame-ancestors 'self' https://docs.example.com
    origins = " ".join(widget.allowed_origins) if widget.allowed_origins else "'none'"
    response.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {origins}"
    
    return {
        "theme": widget.theme,
        "greeting": widget.greeting,
        "enabled_tools": widget.enabled_tools
    }

@router.put("/{id}", response_model=WidgetRead)
async def update_widget(
    id: str,
    body: WidgetUpdate,
    request: Request,
    admin_user=Depends(require_role("admin"))
):
    """Admin only: Update an existing widget configuration."""
    db_engine = request.app.state.db_engine
    async with AsyncSession(db_engine) as session:
        async with session.begin():
            stmt = select(Widget).where(Widget.id == uuid.UUID(id))
            res = await session.execute(stmt)
            widget = res.scalar_one_or_none()
            
            if not widget:
                raise HTTPException(status_code=404, detail="Widget not found")
                
            if body.allowed_origins is not None:
                widget.allowed_origins = body.allowed_origins
            if body.theme is not None:
                widget.theme = body.theme
            if body.greeting is not None:
                widget.greeting = body.greeting
            if body.enabled_tools is not None:
                widget.enabled_tools = body.enabled_tools
                
            await session.flush()
            return {
                "id": widget.id,
                "widget_id": widget.widget_id,
                "allowed_origins": widget.allowed_origins,
                "theme": widget.theme,
                "greeting": widget.greeting,
                "enabled_tools": widget.enabled_tools,
                "created_by": widget.created_by,
                "created_at": widget.created_at
            }
