"""
Voice Trigger — Factor 11: Trigger from Anywhere.

Voice call integration for IVR (Interactive Voice Response) systems.
Supports Africa's Talking Voice API and SIP-based systems.

Flow:
    Voice Call → IVR Gateway → VoiceTrigger.receive() → TriggerIntent
    TriggerResponse → VoiceTrigger.send() → TTS → Voice Call

Voice Menu:
    "Press 1 to record a sale"
    "Press 2 to check your balance"
    "Say 'record sale' followed by the item and amount"
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

import structlog

from app.triggers.base import (
    BaseTrigger,
    IntentType,
    TriggerChannel,
    TriggerIntent,
    TriggerResponse,
)

logger = structlog.get_logger(__name__)

# IVR menu prompts (bilingual: Swahili primary, English fallback)
IVR_PROMPTS = {
    "welcome": {
        "sw": "Karibu Angavu Intelligence. Bonyeza 1 kurekodi mauzo, 2 kuangalia salio, 3 mauzo ya leo, 4 msaada.",
        "en": "Welcome to Angavu Intelligence. Press 1 to record a sale, 2 to check balance, 3 for today's sales, 4 for help.",
    },
    "record_sale": {
        "sw": "Sema jina la bidhaa na bei. Kwa mfano: nyanya mia tano.",
        "en": "Say the item name and price. For example: tomatoes five hundred.",
    },
    "check_balance": {
        "sw": "Salio lako ni {balance} shilingi.",
        "en": "Your balance is {balance} shillings.",
    },
    "help": {
        "sw": "Bonyeza 1 kurekodi mauzo, 2 kuangalia salio, 3 mauzo ya leo, 0 kuacha.",
        "en": "Press 1 to record a sale, 2 to check balance, 3 for today's sales, 0 to exit.",
    },
    "error": {
        "sw": "Samahani, sijaelewa. Tafadhali jaribu tena.",
        "en": "Sorry, I didn't understand. Please try again.",
    },
    "goodbye": {
        "sw": "Asante kwa kutumia Angavu Intelligence. Kwaheri!",
        "en": "Thank you for using Angavu Intelligence. Goodbye!",
    },
}


class VoiceTrigger(BaseTrigger):
    """
    Voice/IVR trigger for users who prefer calling.

    Handles:
    - DTMF input (key presses)
    - Speech recognition results (from ASR engine)
    - IVR menu navigation
    - Text-to-speech response generation

    Integration points:
    - Africa's Talking Voice API
    - SIP/VoIP gateways
    - Custom ASR engines
    """

    def __init__(self, tts_engine: str = "africastalking"):
        super().__init__()
        self.tts_engine = tts_engine
        self._ivr_states: Dict[str, Dict[str, Any]] = {}

    def get_channel(self) -> TriggerChannel:
        return TriggerChannel.VOICE

    async def receive(self, raw_input: Any) -> TriggerIntent:
        """
        Parse voice/IVR input into a TriggerIntent.

        Args:
            raw_input: Dict with keys:
                - call_id: Unique call identifier
                - caller: Caller's phone number
                - dtmf: DTMF digits pressed (if any)
                - speech: Speech-to-text result (if ASR enabled)
                - language: Detected language
                - session_data: IVR session state
        """
        if isinstance(raw_input, dict):
            call_id = raw_input.get("call_id", "")
            caller = raw_input.get("caller", "")
            dtmf = raw_input.get("dtmf", "")
            speech = raw_input.get("speech", "")
            language = raw_input.get("language", "sw")
        else:
            call_id = getattr(raw_input, "call_id", "")
            caller = getattr(raw_input, "caller", "")
            dtmf = getattr(raw_input, "dtmf", "")
            speech = getattr(raw_input, "speech", "")
            language = getattr(raw_input, "language", "sw")

        # Get IVR session state
        session_id = f"voice:{call_id}"
        ivr_state = self._get_ivr_state(call_id)

        # Determine intent from DTMF or speech
        if dtmf:
            intent_type, extracted_data, confidence = self._parse_dtmf(
                dtmf, ivr_state
            )
            raw_text = f"DTMF:{dtmf}"
        elif speech:
            intent_type, extracted_data, confidence = self._parse_speech(
                speech, language
            )
            raw_text = speech
        else:
            # Initial call — return welcome prompt
            intent_type = IntentType.UNKNOWN
            extracted_data = {"action": "welcome"}
            confidence = 1.0
            raw_text = "[INCOMING_CALL]"

        # Update IVR state
        self._update_ivr_state(call_id, intent_type, extracted_data)

        intent = TriggerIntent(
            intent_type=intent_type,
            raw_input=raw_text,
            channel=TriggerChannel.VOICE,
            user_id=caller,
            session_id=session_id,
            language=language,
            extracted_data=extracted_data,
            metadata={
                "call_id": call_id,
                "dtmf": dtmf,
                "speech": speech,
                "ivr_state": ivr_state,
            },
            confidence=confidence,
        )

        self._logger.info(
            "voice_intent_parsed",
            caller=caller[:6] + "****",
            intent=intent_type.value,
            input_type="dtmf" if dtmf else "speech" if speech else "initial",
        )

        return intent

    async def send(
        self,
        response: TriggerResponse,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Send voice response.

        Generates TTS audio or sends DTMF instructions to the IVR gateway.
        """
        # Get language for TTS
        language = response.metadata.get("language", "sw")

        # Format response for voice
        voice_text = self._format_for_voice(response.text, language)

        self._logger.info(
            "voice_response_sent",
            to=user_id[:6] + "****",
            text_length=len(voice_text),
            language=language,
        )

        if response.session_end and session_id:
            call_id = session_id.replace("voice:", "")
            self._ivr_states.pop(call_id, None)
            self.end_session(session_id)

        return True

    def _parse_dtmf(
        self,
        dtmf: str,
        ivr_state: Dict[str, Any],
    ) -> tuple:
        """Parse DTMF key presses into intent."""
        dtmf_map = {
            "1": (IntentType.RECORD_SALE, {"action": "record_sale"}),
            "2": (IntentType.CHECK_BALANCE, {}),
            "3": (IntentType.CHECK_SALES, {"timeframe": "today"}),
            "4": (IntentType.HELP, {}),
            "0": (IntentType.UNKNOWN, {"action": "exit"}),
        }

        if dtmf in dtmf_map:
            intent_type, data = dtmf_map[dtmf]
            return intent_type, data, 0.95

        return IntentType.UNKNOWN, {"dtmf": dtmf}, 0.5

    def _parse_speech(
        self,
        speech: str,
        language: str,
    ) -> tuple:
        """Parse speech-to-text result into intent."""
        if not speech:
            return IntentType.UNKNOWN, {}, 0.0

        speech_lower = speech.lower()

        # Sale patterns
        sale_match = re.search(
            r'(?:nimeuza|nauza|sold|sell)\s+(\w+)\s+(?:shilingi?\s+)?(\d+)',
            speech_lower,
        )
        if sale_match:
            return IntentType.RECORD_SALE, {
                "item": sale_match.group(1),
                "amount": sale_match.group(2),
            }, 0.8

        # Balance
        if any(w in speech_lower for w in ["salio", "balance", "pesa"]):
            return IntentType.CHECK_BALANCE, {}, 0.8

        # Sales
        if any(w in speech_lower for w in ["mauzo", "sales", "nimeuza"]):
            return IntentType.CHECK_SALES, {"timeframe": "today"}, 0.8

        # Help
        if any(w in speech_lower for w in ["msaada", "help", "saidia"]):
            return IntentType.HELP, {}, 0.8

        return IntentType.UNKNOWN, {"raw": speech}, 0.4

    def _get_ivr_state(self, call_id: str) -> Dict[str, Any]:
        """Get or create IVR session state."""
        if call_id not in self._ivr_states:
            self._ivr_states[call_id] = {
                "call_id": call_id,
                "menu_level": "root",
                "history": [],
                "collected_data": {},
                "attempts": 0,
            }
        return self._ivr_states[call_id]

    def _update_ivr_state(
        self,
        call_id: str,
        intent_type: IntentType,
        data: Dict[str, Any],
    ) -> None:
        """Update IVR session state after processing."""
        state = self._ivr_states.get(call_id, {})
        state["history"] = state.get("history", []) + [intent_type.value]
        state["collected_data"] = {**state.get("collected_data", {}), **data}
        state["menu_level"] = intent_type.value

    def _format_for_voice(self, text: str, language: str) -> str:
        """Format text for TTS output."""
        # Remove markdown, emojis, special characters
        clean = re.sub(r'[*_~`]', '', text)
        clean = re.sub(r'[📈📉💰📊✅❌]', '', clean)
        clean = re.sub(r'\n+', '. ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()

        # Ensure it ends with a pause
        if clean and not clean.endswith(('.', '!', '?')):
            clean += '.'

        return clean

    def get_welcome_prompt(self, language: str = "sw") -> str:
        """Get the welcome prompt for the IVR."""
        return IVR_PROMPTS["welcome"].get(language, IVR_PROMPTS["welcome"]["en"])

    def get_error_prompt(self, language: str = "sw") -> str:
        """Get the error prompt for the IVR."""
        return IVR_PROMPTS["error"].get(language, IVR_PROMPTS["error"]["en"])

    def get_goodbye_prompt(self, language: str = "sw") -> str:
        """Get the goodbye prompt for the IVR."""
        return IVR_PROMPTS["goodbye"].get(language, IVR_PROMPTS["goodbye"]["en"])
