"""
WhatsApp Bot service — OpenWA integration.

Handles incoming WhatsApp messages and routes them to the appropriate
service. Supports:
- Transaction recording via text
- Voice note transcription
- Daily/weekly report requests
- Share link generation
- Market price queries

All responses are in the user's preferred language (Swahili/English/Sheng).
"""

import re
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

import httpx
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.services.report_gen import ReportGenerator

logger = structlog.get_logger(__name__)
settings = get_settings()


class WhatsAppBot:
    """
    Processes incoming WhatsApp messages and generates responses.

    Integrates with OpenWA (self-hosted WhatsApp Web API) to send
    and receive messages. The bot supports natural language commands
    in Swahili, English, and Sheng.
    """

    # Command patterns (Swahili + English)
    COMMANDS = {
        "report": r"(ripoti|report|summary|muhtasari)",
        "sales": r"(mauzo|sales|sold|nimeuza)",
        "expenses": r"(gharama|expenses|cost|costs)",
        "profit": r"(faida|profit|earnings)",
        "inventory": r"(mali|stock|inventory|bidhaa)",
        "debts": r"(deni|debts|owe|outstanding)",
        "market": r"(soko|market|prices|bei)",
        "share": r"(share|shiriki|tuma|send|download)",
        "help": r"(msaada|help|commands|amri)",
        "record": r"(rekodi|record|add|ongeza)",
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.report_gen = ReportGenerator(db)
        self.openwa_url = settings.OPENWA_URL

    async def process_message(
        self,
        phone: str,
        message: str,
        message_type: str = "text",
        media_url: Optional[str] = None,
    ) -> str:
        """
        Process an incoming WhatsApp message and return a response.

        Args:
            phone: Sender's phone number
            message: Message text (or transcription for voice)
            message_type: Type of message (text, voice, image)
            media_url: URL if message contains media

        Returns:
            Response text to send back
        """
        logger.info(
            "whatsapp_message_received",
            phone=phone[:6] + "****",  # Mask phone for logging
            type=message_type,
            length=len(message),
        )

        # Find or create user
        user = await self._get_user_by_phone(phone)
        if not user:
            return await self._handle_new_user(phone, message)

        # Normalize message
        msg = message.strip().lower()

        # Route to command handler
        command, args = self._parse_command(msg)

        handlers = {
            "report": self._handle_report,
            "sales": self._handle_sales_query,
            "expenses": self._handle_expenses_query,
            "profit": self._handle_profit_query,
            "inventory": self._handle_inventory_query,
            "debts": self._handle_debts_query,
            "market": self._handle_market_query,
            "share": self._handle_share,
            "help": self._handle_help,
            "record": self._handle_record,
        }

        handler = handlers.get(command)
        if handler:
            return await handler(user, args)

        # If no command matched, try to parse as a transaction
        txn_result = await self._try_parse_transaction(user, msg)
        if txn_result:
            return txn_result

        # Default response
        return self._default_response(user.language)

    def _parse_command(self, message: str) -> Tuple[Optional[str], str]:
        """
        Parse a message to extract command and arguments.

        Returns:
            Tuple of (command_name, remaining_args)
        """
        for command, pattern in self.COMMANDS.items():
            if re.search(pattern, message, re.IGNORECASE):
                # Remove the matched command word to get args
                remaining = re.sub(pattern, "", message, flags=re.IGNORECASE).strip()
                return command, remaining
        return None, message

    async def _get_user_by_phone(self, phone: str) -> Optional[User]:
        """Look up user by phone number hash."""
        import hashlib
        phone_hash = hashlib.sha256(phone.encode()).hexdigest()
        result = await self.db.execute(
            select(User).where(
                and_(User.phone_hash == phone_hash, User.is_active == True)
            )
        )
        return result.scalar_one_or_none()

    async def _handle_new_user(self, phone: str, message: str) -> str:
        """Handle message from unknown user — registration flow."""
        # In production, this would trigger a registration flow
        # For now, return welcome message
        return (
            "🇰🇪 *Karibu Msaidizi!*\n\n"
            "Mimi ni msaidizi wako wa biashara. "
            "Ninakusaidia kurekodi mauzo, kufuatilia faida, na kupata ripoti.\n\n"
            "📋 *Jinsi ya kutumia:*\n"
            "• Tuma ujumbe: \"Nimeuza sukari 5 kwa 500\"\n"
            "• Tuma voice note ya mauzo yako\n"
            "• Andika \"ripoti\" kuona ripoti ya leo\n"
            "• Andika \"msaada\" kuona amri zote\n\n"
            "Pakua app: https://msaidizi.app/download"
        )

    # =========================================================================
    # Command Handlers
    # =========================================================================

    async def _handle_report(self, user: User, args: str) -> str:
        """Handle report request — daily or weekly."""
        if "wiki" in args or "week" in args:
            report = await self.report_gen.generate_weekly_report(user)
            return self._format_weekly_report(report, user.language)
        else:
            report = await self.report_gen.generate_daily_report(user)
            return self._format_daily_report(report, user.language)

    async def _handle_sales_query(self, user: User, args: str) -> str:
        """Handle sales query."""
        from app.services.pipeline import DataPipeline
        pipeline = DataPipeline(self.db)

        metrics = await pipeline.aggregate_user_metrics(
            user.id, date.today(), date.today()
        )

        lang = user.language or "sw"
        if lang == "sw":
            return (
                f"💰 *Mauzo ya Leo*\n\n"
                f"Jumla: KES {metrics['total_sales']:,.0f}\n"
                f"Transactions: {metrics['transaction_count']}\n"
                f"Average: KES {metrics['avg_transaction_value']:,.0f}\n\n"
                f"Tuma \"ripoti\" kuona maelezo zaidi."
            )
        else:
            return (
                f"💰 *Today's Sales*\n\n"
                f"Total: KES {metrics['total_sales']:,.0f}\n"
                f"Transactions: {metrics['transaction_count']}\n"
                f"Average: KES {metrics['avg_transaction_value']:,.0f}\n\n"
                f"Send \"report\" for more details."
            )

    async def _handle_expenses_query(self, user: User, args: str) -> str:
        """Handle expenses query."""
        from app.services.pipeline import DataPipeline
        pipeline = DataPipeline(self.db)

        metrics = await pipeline.aggregate_user_metrics(
            user.id, date.today(), date.today()
        )

        lang = user.language or "sw"
        if lang == "sw":
            return (
                f"📉 *Gharama za Leo*\n\n"
                f"Manunuzi: KES {metrics['total_purchases']:,.0f}\n"
                f"Mengineyo: KES {metrics['total_expenses']:,.0f}\n"
                f"Jumla: KES {metrics['total_purchases'] + metrics['total_expenses']:,.0f}"
            )
        else:
            return (
                f"📉 *Today's Expenses*\n\n"
                f"Purchases: KES {metrics['total_purchases']:,.0f}\n"
                f"Other: KES {metrics['total_expenses']:,.0f}\n"
                f"Total: KES {metrics['total_purchases'] + metrics['total_expenses']:,.0f}"
            )

    async def _handle_profit_query(self, user: User, args: str) -> str:
        """Handle profit query."""
        from app.services.pipeline import DataPipeline
        pipeline = DataPipeline(self.db)

        metrics = await pipeline.aggregate_user_metrics(
            user.id, date.today(), date.today()
        )

        lang = user.language or "sw"
        emoji = "📈" if metrics["net_profit"] > 0 else "📉"
        if lang == "sw":
            return (
                f"{emoji} *Faida ya Leo*\n\n"
                f"Mauzo: KES {metrics['total_sales']:,.0f}\n"
                f"Gharama: KES {metrics['total_purchases'] + metrics['total_expenses']:,.0f}\n"
                f"Faida: KES {metrics['net_profit']:,.0f}\n"
                f"Margin: {metrics['profit_margin_pct']:.1f}%"
            )
        else:
            return (
                f"{emoji} *Today's Profit*\n\n"
                f"Sales: KES {metrics['total_sales']:,.0f}\n"
                f"Costs: KES {metrics['total_purchases'] + metrics['total_expenses']:,.0f}\n"
                f"Profit: KES {metrics['net_profit']:,.0f}\n"
                f"Margin: {metrics['profit_margin_pct']:.1f}%"
            )

    async def _handle_inventory_query(self, user: User, args: str) -> str:
        """Handle inventory/stock query."""
        from app.models.transaction import Inventory
        from sqlalchemy import and_, select

        result = await self.db.execute(
            select(Inventory).where(Inventory.user_id == user.id)
            .order_by(Inventory.current_stock)
        )
        items = result.scalars().all()

        lang = user.language or "sw"
        if not items:
            if lang == "sw":
                return "📦 *Hakuna mali*\n\nRekodi mauzo yako kuanza kufuatilia stock."
            else:
                return "📦 *No inventory*\n\nRecord sales to start tracking stock."

        lines = []
        for item in items[:10]:
            alert = " ⚠️" if item.needs_restock else ""
            lines.append(
                f"• {item.item}: {item.current_stock:.0f} {item.unit or ''}{alert}"
            )

        if lang == "sw":
            return f"📦 *Mali Yako*\n\n" + "\n".join(lines) + "\n\n⚠️ = Inahitaji kununuliwa"
        else:
            return f"📦 *Your Stock*\n\n" + "\n".join(lines) + "\n\n⚠️ = Needs restocking"

    async def _handle_debts_query(self, user: User, args: str) -> str:
        """Handle debts query."""
        lang = user.language or "sw"
        # Placeholder — would query debts table
        if lang == "sw":
            return "💳 *Madeni*\n\nHakuna madeni yaliyorekodiwa.\n\nRekodi deni: \"deni Mama Njeri 500\""
        else:
            return "💳 *Debts*\n\nNo debts recorded.\n\nRecord debt: \"debt Mama Njeri 500\""

    async def _handle_market_query(self, user: User, args: str) -> str:
        """Handle market prices query."""
        lang = user.language or "sw"
        # Placeholder — would query market_prices table
        if lang == "sw":
            return (
                "🏪 *Bei za Soko*\n\n"
                "🍅 Nyanya: KES 80/kg\n"
                "🧅 Vitunguu: KES 120/kg\n"
                "🥬 Sukuma Wiki: KES 30/bunch\n"
                "🥔 Viazi: KES 50/kg\n\n"
                "💡 Bei zinaweza kutofautiana kulingana na soko."
            )
        else:
            return (
                "🏪 *Market Prices*\n\n"
                "🍅 Tomatoes: KES 80/kg\n"
                "🧅 Onions: KES 120/kg\n"
                "🥬 Kale: KES 30/bunch\n"
                "🥔 Potatoes: KES 50/kg\n\n"
                "💡 Prices may vary by market."
            )

    async def _handle_share(self, user: User, args: str) -> str:
        """Handle share link request."""
        lang = user.language or "sw"
        if lang == "sw":
            return (
                "📲 *Shiriki Msaidizi*\n\n"
                "Tuma link hii kwa marafiki zako:\n"
                "https://msaidizi.app/download\n\n"
                "App ya bure ya biashara yako! 🚀"
            )
        else:
            return (
                "📲 *Share Msaidizi*\n\n"
                "Send this link to your friends:\n"
                "https://msaidizi.app/download\n\n"
                "Free business app! 🚀"
            )

    async def _handle_help(self, user: User, args: str) -> str:
        """Handle help request."""
        lang = user.language or "sw"
        if lang == "sw":
            return (
                "🇰🇷 *Msaidizi — Msaada*\n\n"
                "📋 *Amri Zote:*\n"
                "• \"mauzo\" — Ona mauzo ya leo\n"
                "• \"faida\" — Ona faida ya leo\n"
                "• \"gharama\" — Ona gharama za leo\n"
                "• \"ripoti\" — Ripoti ya leo\n"
                "• \"ripoti ya wiki\" — Ripoti ya wiki\n"
                "• \"mali\" — Angalia stock yako\n"
                "• \"deni\" — Angalia madeni\n"
                "• \"soko\" — Bei za soko\n"
                "• \"shiriki\" — Tuma link ya download\n\n"
                "🎤 *Voice Note:*\n"
                "Tuma voice note ya mauzo yako na nitarekodi!\n\n"
                "✏️ *Mfano:*\n"
                "\"Nimeuza sukari 5 kwa 500\""
            )
        else:
            return (
                "🇰🇷 *Msaidizi — Help*\n\n"
                "📋 *All Commands:*\n"
                "• \"sales\" — See today's sales\n"
                "• \"profit\" — See today's profit\n"
                "• \"expenses\" — See today's expenses\n"
                "• \"report\" — Today's report\n"
                "• \"weekly report\" — Weekly report\n"
                "• \"stock\" — Check inventory\n"
                "• \"debts\" — Check outstanding debts\n"
                "• \"market\" — Market prices\n"
                "• \"share\" — Download link\n\n"
                "🎤 *Voice Note:*\n"
                "Send a voice note of your sales and I'll record it!\n\n"
                "✏️ *Example:*\n"
                "\"Sold sugar 5 at 500\""
            )

    async def _handle_record(self, user: User, args: str) -> str:
        """Handle explicit record request."""
        lang = user.language or "sw"
        if lang == "sw":
            return (
                "✏️ *Rekodi Mauzo*\n\n"
                "Tuma ujumbe kwa mfumo huu:\n"
                "\"Nimeuza [bidhaa] [idadi] kwa [bei]\"\n\n"
                "Mfano:\n"
                "• \"Nimeuza sukari 5 kwa 500\"\n"
                "• \"Nimeuza nyanya 10 kwa 800\"\n"
                "• \"Nimenunua mafuta 2 kwa 300\"\n\n"
                "🎤 Au tuma voice note!"
            )
        else:
            return (
                "✏️ *Record Sales*\n\n"
                "Send a message in this format:\n"
                "\"Sold [item] [quantity] at [price]\"\n\n"
                "Examples:\n"
                "• \"Sold sugar 5 at 500\"\n"
                "• \"Sold tomatoes 10 at 800\"\n"
                "• \"Bought oil 2 at 300\"\n\n"
                "🎤 Or send a voice note!"
            )

    async def _try_parse_transaction(
        self, user: User, message: str
    ) -> Optional[str]:
        """
        Try to parse a message as a transaction record.

        Supports formats like:
        - "Nimeuza sukari 5 kwa 500"
        - "Sold sugar 5 at 500"
        - "Nimenunua mafuta 2 kwa 300"
        - "500 sukari 5"

        Returns:
            Confirmation message if parsed, None otherwise
        """
        # Pattern: [verb] [item] [quantity] [connector] [price]
        patterns = [
            # Swahili: "Nimeuza sukari 5 kwa 500"
            r"(?:nime)?(?:uza|uzia|uzi)\s+(\w+)\s+(\d+(?:\.\d+)?)\s+(?:kwa|@|ksh|kes)\s+(\d+(?:\.\d+)?)",
            # English: "Sold sugar 5 at 500"
            r"(?:sold|sell)\s+(\w+)\s+(\d+(?:\.\d+)?)\s+(?:at|for|@|ksh|kes)\s+(\d+(?:\.\d+)?)",
            # Purchase Swahili: "Nimenunua mafuta 2 kwa 300"
            r"(?:nime)?(?:nunua|nunulia)\s+(\w+)\s+(\d+(?:\.\d+)?)\s+(?:kwa|@|ksh|kes)\s+(\d+(?:\.\d+)?)",
            # Purchase English: "Bought oil 2 at 300"
            r"(?:bought|buy)\s+(\w+)\s+(\d+(?:\.\d+)?)\s+(?:at|for|@|ksh|kes)\s+(\d+(?:\.\d+)?)",
            # Simple: "sukari 5 500"
            r"^(\w+)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                item = match.group(1).strip()
                quantity = float(match.group(2))
                price = float(match.group(3))

                # Determine transaction type
                is_purchase = any(
                    word in message.lower()
                    for word in ["nunua", "nunulia", "bought", "buy"]
                )
                txn_type = "PURCHASE" if is_purchase else "SALE"

                # Record the transaction
                from app.models.transaction import Transaction
                from app.services.pipeline import DataPipeline
                pipeline = DataPipeline(self.db)

                normalized_item = pipeline.normalize_product_name(item) or item
                category = pipeline.categorize_product(normalized_item)

                txn = Transaction(
                    user_id=user.id,
                    transaction_type=txn_type,
                    item=normalized_item,
                    item_category=category,
                    quantity=quantity,
                    amount=price * quantity,
                    unit_price=price,
                    recorded_via="text",
                    timestamp=datetime.now(timezone.utc),
                )
                self.db.add(txn)

                lang = user.language or "sw"
                if lang == "sw":
                    return (
                        f"✅ *Umerekodi {txn_type.lower()}!*\n\n"
                        f"📦 {normalized_item} × {quantity:.0f} @ KES {price:.0f}\n"
                        f"💰 Jumla: KES {price * quantity:,.0f}\n\n"
                        f"Tuma \"mauzo\" kuona mauzo ya leo."
                    )
                else:
                    return (
                        f"✅ *{txn_type.title()} recorded!*\n\n"
                        f"📦 {normalized_item} × {quantity:.0f} @ KES {price:.0f}\n"
                        f"💰 Total: KES {price * quantity:,.0f}\n\n"
                        f"Send \"sales\" to see today's sales."
                    )

        return None

    def _default_response(self, language: str) -> str:
        """Default response when no command is recognized."""
        if language == "sw":
            return (
                "Sielewi ujumbe wako. 🤔\n\n"
                "Andika \"msaada\" kuona jinsi ya kutumia.\n"
                "Au tuma voice note ya mauzo yako! 🎤"
            )
        else:
            return (
                "I don't understand that message. 🤔\n\n"
                "Type \"help\" to see how to use me.\n"
                "Or send a voice note of your sales! 🎤"
            )

    def _format_daily_report(self, report, language: str) -> str:
        """Format daily report for WhatsApp display."""
        s = report.summary
        if language == "sw":
            text = (
                f"📊 *Ripoti ya Leo — {report.report_date.strftime('%d %B %Y')}*\n\n"
                f"💰 Mauzo: KES {s.total_sales:,.0f} ({s.transaction_count} mauzo)\n"
                f"📉 Gharama: KES {s.total_purchases + s.total_expenses:,.0f}\n"
                f"📈 Faida: KES {s.net_profit:,.0f} ({s.profit_margin_pct:.1f}%)\n"
            )
            if report.vs_yesterday_pct is not None:
                arrow = "↑" if report.vs_yesterday_pct > 0 else "↓"
                text += f"\n📊 Vs jana: {arrow} {abs(report.vs_yesterday_pct):.1f}%\n"
            if report.top_products:
                text += "\n🏆 *Bidhaa Bora:*\n"
                for p in report.top_products[:3]:
                    text += f"• {p.item}: KES {p.revenue:,.0f}\n"
            if report.low_stock_items:
                text += "\n⚠️ *Stock Ndogo:*\n"
                for item in report.low_stock_items:
                    text += f"• {item}\n"
        else:
            text = (
                f"📊 *Daily Report — {report.report_date.strftime('%d %B %Y')}*\n\n"
                f"💰 Sales: KES {s.total_sales:,.0f} ({s.transaction_count} txns)\n"
                f"📉 Costs: KES {s.total_purchases + s.total_expenses:,.0f}\n"
                f"📈 Profit: KES {s.net_profit:,.0f} ({s.profit_margin_pct:.1f}%)\n"
            )
            if report.vs_yesterday_pct is not None:
                arrow = "↑" if report.vs_yesterday_pct > 0 else "↓"
                text += f"\n📊 vs yesterday: {arrow} {abs(report.vs_yesterday_pct):.1f}%\n"
            if report.top_products:
                text += "\n🏆 *Top Products:*\n"
                for p in report.top_products[:3]:
                    text += f"• {p.item}: KES {p.revenue:,.0f}\n"

        return text

    def _format_weekly_report(self, report, language: str) -> str:
        """Format weekly report for WhatsApp display."""
        s = report.summary
        if language == "sw":
            text = (
                f"📊 *Ripoti ya Wiki*\n"
                f"{report.week_start} — {report.week_end}\n\n"
                f"💰 Mauzo: KES {s.total_sales:,.0f}\n"
                f"📈 Faida: KES {s.net_profit:,.0f}\n"
                f"📊 Transactions: {s.transaction_count}\n"
            )
            if report.wow_sales_change_pct is not None:
                arrow = "↑" if report.wow_sales_change_pct > 0 else "↓"
                text += f"\n📈 Wiki wiki: {arrow} {abs(report.wow_sales_change_pct):.1f}%\n"
            if report.best_day:
                text += f"\n🏆 Siku bora: {report.best_day}\n"
            if report.worst_day:
                text += f"📉 Siku dhaifu: {report.worst_day}\n"
        else:
            text = (
                f"📊 *Weekly Report*\n"
                f"{report.week_start} — {report.week_end}\n\n"
                f"💰 Sales: KES {s.total_sales:,.0f}\n"
                f"📈 Profit: KES {s.net_profit:,.0f}\n"
                f"📊 Transactions: {s.transaction_count}\n"
            )
            if report.wow_sales_change_pct is not None:
                arrow = "↑" if report.wow_sales_change_pct > 0 else "↓"
                text += f"\n📈 Week-over-week: {arrow} {abs(report.wow_sales_change_pct):.1f}%\n"
            if report.best_day:
                text += f"\n🏆 Best day: {report.best_day}\n"
            if report.worst_day:
                text += f"📉 Worst day: {report.worst_day}\n"

        return text

    # =========================================================================
    # Outbound Messaging
    # =========================================================================

    async def send_message(
        self,
        phone: str,
        message: str,
    ) -> bool:
        """
        Send a WhatsApp message via OpenWA.

        Args:
            phone: Recipient phone number (with country code)
            message: Message text

        Returns:
            True if sent successfully
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.openwa_url}/send-message",
                    json={
                        "to": phone,
                        "message": message,
                    },
                    headers={
                        "Authorization": f"Bearer {settings.OPENWA_WEBHOOK_SECRET}",
                    },
                    timeout=10.0,
                )
                if response.status_code == 200:
                    logger.info("whatsapp_message_sent", phone=phone[:6] + "****")
                    return True
                else:
                    logger.error(
                        "whatsapp_send_failed",
                        status=response.status_code,
                        body=response.text,
                    )
                    return False
        except Exception as e:
            logger.error("whatsapp_send_error", error=str(e))
            return False

    async def send_daily_reports(self) -> int:
        """
        Send daily reports to all active users.

        Called by a cron job at 7 PM EAT daily.

        Returns:
            Number of reports sent successfully
        """
        result = await self.db.execute(
            select(User).where(
                and_(
                    User.is_active == True,
                    User.channel == "whatsapp",
                )
            )
        )
        users = result.scalars().all()

        sent = 0
        for user in users:
            try:
                phone = user.phone_encrypted  # Would need decryption
                report = await self.report_gen.generate_daily_report(user)
                message = self._format_daily_report(report, user.language or "sw")
                if await self.send_message(phone, message):
                    sent += 1
            except Exception as e:
                logger.error(
                    "daily_report_send_failed",
                    user_id=str(user.id),
                    error=str(e),
                )

        logger.info("daily_reports_sent", total=len(users), sent=sent)
        return sent
