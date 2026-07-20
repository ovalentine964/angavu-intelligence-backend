"""
AI Chat API — /api/v1/ai/*

Endpoints:
    POST /ai/chat                    — Send message to AI
    GET  /ai/chat/{conversationId}   — Get conversation history
    POST /ai/voice                   — Voice input
    GET  /ai/insights                — Get AI insights for home screen
    POST /ai/feedback                — Submit feedback
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.services.cloud_reasoning import CloudReasoningService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/ai", tags=["AI Chat"])

# In-memory conversation store (would be Redis/DB in production)
_conversations: dict[str, list[dict]] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str
    timestamp: str | None = None


class ChatRequest(BaseModel):
    """Send a message to the AI assistant."""

    message: str = Field(..., min_length=1, max_length=5000, description="User message")
    conversation_id: str | None = Field(None, description="Existing conversation ID (omit for new)")
    language: str = Field("sw", pattern=r"^(sw|en|sh)$", description="Preferred response language")
    context: dict | None = Field(None, description="Additional context (transaction data, etc.)")


class ChatResponse(BaseModel):
    """AI response."""

    conversation_id: str
    message: str
    source: str = Field(..., description="cloud or local")
    confidence: float | None = None
    suggestions: list[str] | None = None
    model: str | None = None


class ConversationHistoryResponse(BaseModel):
    """Conversation history."""

    conversation_id: str
    messages: list[ChatMessage]
    created_at: str
    updated_at: str


class VoiceRequest(BaseModel):
    """Voice input for AI processing."""

    audio_base64: str = Field(..., description="Base64-encoded audio data")
    audio_format: str = Field("wav", pattern=r"^(wav|mp3|ogg|m4a)$", description="Audio format")
    language: str = Field("sw", pattern=r"^(sw|en|sh)$", description="Spoken language")
    conversation_id: str | None = Field(None, description="Existing conversation ID")


class VoiceResponse(BaseModel):
    """Voice processing response."""

    conversation_id: str
    transcript: str
    intent: str | None = None
    response: str
    source: str


class InsightItem(BaseModel):
    """A single AI insight."""

    id: str
    type: str = Field(..., description="alert, tip, opportunity, warning")
    title: str
    title_sw: str | None = None
    body: str
    body_sw: str | None = None
    priority: str = Field("normal", pattern=r"^(low|normal|high|urgent)$")
    action_label: str | None = None
    action_route: str | None = None
    icon: str | None = None
    created_at: str


class InsightsResponse(BaseModel):
    """AI insights for home screen."""

    insights: list[InsightItem]
    daily_briefing: str | None = None
    daily_briefing_sw: str | None = None
    generated_at: str


class FeedbackRequest(BaseModel):
    """Submit feedback on AI response."""

    conversation_id: str = Field(..., description="Conversation ID")
    message_index: int = Field(..., ge=0, description="Index of the message being rated")
    rating: int = Field(..., ge=1, le=5, description="1-5 star rating")
    comment: str | None = Field(None, max_length=1000, description="Optional feedback comment")
    feedback_type: str = Field(
        "general",
        pattern=r"^(general|accurate|helpful|wrong|inappropriate)$",
        description="Feedback type",
    )


class FeedbackResponse(BaseModel):
    """Feedback submission result."""

    status: str
    feedback_id: str


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to the AI assistant.

    The AI assistant helps informal workers with business questions,
    transaction analysis, and financial advice. Responses are provided
    in the user's preferred language.

    If conversation_id is provided, the message is appended to the
    existing conversation. Otherwise, a new conversation is created.
    """
    # Get or create conversation
    conv_id = request.conversation_id or str(uuid.uuid4())
    if conv_id not in _conversations:
        _conversations[conv_id] = {
            "user_id": str(current_user.id),
            "messages": [],
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

    conversation = _conversations[conv_id]

    # Verify ownership
    if conversation["user_id"] != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your conversation",
        )

    # Add user message
    conversation["messages"].append({
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    # Build context for AI
    context_prompt = ""
    if request.context:
        context_prompt = f"\nContext: {request.context}"

    # Get recent transactions for context
    from app.models.transaction import Transaction
    recent_txns = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.timestamp.desc())
        .limit(5)
    )
    txn_context = ""
    for txn in recent_txns.scalars().all():
        txn_context += f"\n- {txn.transaction_type}: {txn.item} KES {txn.amount}"

    full_prompt = (
        f"You are a business assistant for an informal worker in Kenya. "
        f"Business type: {current_user.business_type}. "
        f"Language: {request.language}. "
        f"Recent transactions:{txn_context}{context_prompt}\n\n"
        f"User: {request.message}"
    )

    # Call AI service
    try:
        cloud_service = CloudReasoningService()
        if cloud_service.enabled:
            response = await cloud_service.reason(
                query=full_prompt,
                user_id=str(current_user.id),
                language=request.language,
            )
            ai_message = response.text
            source = response.source
            confidence = response.confidence
        else:
            # Fallback response when cloud is not available
            ai_message = _generate_local_response(request.message, request.language, current_user.business_type)
            source = "local"
            confidence = 0.5
    except Exception as e:
        logger.error("ai_chat_error", error=str(e), user_id=str(current_user.id))
        ai_message = _generate_local_response(request.message, request.language, current_user.business_type)
        source = "local"
        confidence = 0.3

    # Add assistant message
    conversation["messages"].append({
        "role": "assistant",
        "content": ai_message,
        "timestamp": datetime.now(UTC).isoformat(),
    })
    conversation["updated_at"] = datetime.now(UTC).isoformat()

    # Generate suggestions
    suggestions = _generate_suggestions(request.language, current_user.business_type)

    return ChatResponse(
        conversation_id=conv_id,
        message=ai_message,
        source=source,
        confidence=confidence,
        suggestions=suggestions,
    )


@router.get("/chat/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get conversation history.

    Returns all messages in the conversation, ordered chronologically.
    """
    if conversation_id not in _conversations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conversation = _conversations[conversation_id]

    if conversation["user_id"] != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your conversation",
        )

    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        messages=[
            ChatMessage(
                role=msg["role"],
                content=msg["content"],
                timestamp=msg.get("timestamp"),
            )
            for msg in conversation["messages"]
        ],
        created_at=conversation["created_at"],
        updated_at=conversation["updated_at"],
    )


@router.post("/voice", response_model=VoiceResponse)
async def process_voice_input(
    request: VoiceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process voice input for the AI assistant.

    Accepts base64-encoded audio, transcribes it, and returns
    an AI response. This is the primary voice interface for the
    Msaidizi assistant.

    Note: In production, this would use Whisper STT for transcription.
    For now, it delegates to the chat endpoint with a voice context flag.
    """
    # In production, this would:
    # 1. Decode base64 audio
    # 2. Send to Whisper STT service
    # 3. Get transcription
    # 4. Process through chat pipeline

    # For now, return a placeholder that indicates voice processing
    # The actual Whisper integration would go here
    logger.info(
        "voice_input_received",
        user_id=str(current_user.id),
        audio_format=request.audio_format,
        audio_size=len(request.audio_base64),
    )

    # Simulate transcription (in production, call Whisper API)
    transcript = "[Voice transcription would appear here]"

    # Process as chat message
    chat_request = ChatRequest(
        message=transcript,
        conversation_id=request.conversation_id,
        language=request.language,
        context={"source": "voice", "audio_format": request.audio_format},
    )
    chat_response = await send_chat_message(chat_request, current_user, db)

    return VoiceResponse(
        conversation_id=chat_response.conversation_id,
        transcript=transcript,
        intent="business_question",
        response=chat_response.message,
        source=chat_response.source,
    )


@router.get("/insights", response_model=InsightsResponse)
async def get_ai_insights(
    language: str = Query("sw", pattern=r"^(sw|en|sh)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get AI-generated insights for the home screen.

    Returns actionable insights based on the user's recent transactions,
    business type, and market conditions. Designed to be the "daily
    briefing" that keeps workers informed.

    Insights include:
    - Sales trends and alerts
    - Restocking reminders
    - Market price changes
    - Business tips
    - Credit opportunities
    """
    from app.models.transaction import Transaction

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    # Get today's sales
    today_sales = await db.execute(
        select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= today_start,
            )
        )
    )
    today_total = float(today_sales.scalar() or 0)

    # Get this week's sales
    week_sales = await db.execute(
        select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= week_start,
            )
        )
    )
    week_total = float(week_sales.scalar() or 0)

    # Get transaction count
    txn_count = await db.execute(
        select(func.count(Transaction.id)).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.timestamp >= today_start,
            )
        )
    )
    today_count = txn_count.scalar() or 0

    # Build insights
    insights = []
    generated_at = now.isoformat()

    # Sales insight
    if today_total > 0:
        insights.append(InsightItem(
            id=str(uuid.uuid4()),
            type="tip",
            title=f"Today's Sales: KES {today_total:,.0f}",
            title_sw="Mauzo ya Leo: KES {:,.0f}".format(today_total),
            body=f"You've made {today_count} transactions today totaling KES {today_total:,.0f}.",
            body_sw="Umefanya miamala {today_count} leo yenye jumla ya KES {:,.0f}.".format(today_count, today_total),
            priority="normal",
            icon="chart-line",
            created_at=generated_at,
        ))

    # Weekly trend
    if week_total > 0:
        insights.append(InsightItem(
            id=str(uuid.uuid4()),
            type="tip",
            title=f"This Week: KES {week_total:,.0f}",
            title_sw="Wiki Hii: KES {:,.0f}".format(week_total),
            body=f"Your weekly sales are KES {week_total:,.0f}. Keep tracking to see your growth!",
            body_sw="Mauzo yako ya wiki ni KES {:,.0f}. Endelea kufuatilia kuona ukuaji wako!".format(week_total),
            priority="normal",
            icon="calendar-week",
            created_at=generated_at,
        ))

    # Business tip based on type
    tips = {
        "dukawallah": ("Track your fast-moving items to optimize stock", "Fuatilia bidhaa zinazoua haraka kuboresha stock"),
        "mama_mboga": ("Record all sales, even small ones — they add up!", "Andika mauzo yote, hata madogo — yanajumlisha!"),
        "boda_boda": ("Track fuel costs to know your true profit", "Fuatilia gharama za mafuta kujua faida yako halisi"),
        "vendor": ("Compare supplier prices to maximize margins", "Linganisha bei za wasambazaji kuongeza faida"),
        "tailor": ("Track fabric costs per garment for accurate pricing", "Fuatilia gharama za kitambaa kwa nguo kwa bei sahihi"),
        "restaurant": ("Monitor ingredient costs to maintain profit margins", "Fuatilia gharama za viungo kudumisha faida"),
    }
    tip_key = current_user.business_type if current_user.business_type in tips else "vendor"
    tip_en, tip_sw = tips[tip_key]

    insights.append(InsightItem(
        id=str(uuid.uuid4()),
        type="tip",
        title="Business Tip",
        title_sw="Njia ya Biashara",
        body=tip_en,
        body_sw=tip_sw,
        priority="low",
        icon="lightbulb",
        created_at=generated_at,
    ))

    # Daily briefing
    if language == "sw":
        briefing = f"Habari za leo! Umefanya mauzo ya KES {today_total:,.0f} kupitia miamala {today_count}. Wiki hii jumla ni KES {week_total:,.0f}."
    else:
        briefing = f"Good day! You've made KES {today_total:,.0f} in sales across {today_count} transactions today. This week totals KES {week_total:,.0f}."

    return InsightsResponse(
        insights=insights,
        daily_briefing=briefing if language == "en" else None,
        daily_briefing_sw=briefing if language == "sw" else None,
        generated_at=generated_at,
    )


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Submit feedback on an AI response.

    Feedback is used to improve the AI assistant's quality.
    Ratings and comments help fine-tune responses for the
    informal worker context.
    """
    feedback_id = str(uuid.uuid4())

    logger.info(
        "ai_feedback_received",
        feedback_id=feedback_id,
        user_id=str(current_user.id),
        conversation_id=request.conversation_id,
        rating=request.rating,
        feedback_type=request.feedback_type,
    )

    # In production, this would store feedback in a database table
    # and use it for model fine-tuning / quality monitoring

    return FeedbackResponse(
        status="ok",
        feedback_id=feedback_id,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _generate_local_response(message: str, language: str, business_type: str) -> str:
    """Generate a local fallback response when cloud AI is unavailable."""
    message_lower = message.lower()

    if any(word in message_lower for word in ["sales", "mauzo", "sold"]):
        if language == "sw":
            return "Nakuhimiza uendelee kufuatilia mauzo yako kila siku. Hii itakusaidia kujua bidhaa zinazoua vizuri."
        return "I encourage you to keep tracking your sales daily. This will help you understand which products sell best."

    if any(word in message_lower for word in ["stock", "inventory", "bidhaa", "product"]):
        if language == "sw":
            return "Hakikisha unafuatilia stock yako mara kwa mara. Omba bidhaa kabla hazijaisha ili usipoteze mauzo."
        return "Make sure you track your inventory regularly. Reorder products before they run out so you don't lose sales."

    if any(word in message_lower for word in ["profit", "faida", "money", "pesa"]):
        if language == "sw":
            return "Kupata faida, hakikisha unajua gharama za kila bidhaa. Ondoa gharama kutoka kwa mauzo kupata faida halisi."
        return "To make a profit, make sure you know the cost of each item. Subtract costs from sales to get your true profit."

    if language == "sw":
        return "Habari! Mimi ni msaidizi wako wa biashara. Naweza kukusaidia kufuatilia mauzo, stock, na faida yako. Uliza chochote!"
    return "Hello! I'm your business assistant. I can help you track sales, inventory, and profits. Ask me anything!"


def _generate_suggestions(language: str, business_type: str) -> list[str]:
    """Generate contextual follow-up suggestions."""
    if language == "sw":
        return [
            "Ni bidhaa gani zinauzwa zaidi?",
            "Nionyeshe mauzo ya wiki hii",
            "Nifanye nini kuongeza faida?",
        ]
    return [
        "What are my best-selling items?",
        "Show me this week's sales",
        "How can I increase my profits?",
    ]
