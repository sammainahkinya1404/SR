from uuid import UUID

from fastapi import APIRouter

from app.api.deps import Ctx
from app.schemas.products import SuggestionOut
from app.services import pricing
from app.services.pricing import SuggestionStatus

router = APIRouter(prefix="/price-suggestions", tags=["pricing"])


@router.get("", response_model=list[SuggestionOut])
def list_suggestions(ctx: Ctx, status: SuggestionStatus | None = SuggestionStatus.PENDING):
    return pricing.list_suggestions(ctx.session, status)


@router.post("/{suggestion_id}/approve", response_model=SuggestionOut)
def approve(suggestion_id: UUID, ctx: Ctx):
    return pricing.decide_suggestion(ctx.session, ctx.actor, suggestion_id, approve=True)


@router.post("/{suggestion_id}/reject", response_model=SuggestionOut)
def reject(suggestion_id: UUID, ctx: Ctx):
    return pricing.decide_suggestion(ctx.session, ctx.actor, suggestion_id, approve=False)
