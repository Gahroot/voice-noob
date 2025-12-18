"""Text agent service for AI-powered SMS responses.

Handles:
- LLM calls for generating text responses
- Tool execution in text conversations
- Message context building
- Response generation with debouncing
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.integrations import get_workspace_integrations
from app.api.settings import get_user_api_keys
from app.core.auth import user_id_to_uuid
from app.core.config import settings
from app.models.agent import Agent
from app.models.sms import MessageDirection, SMSConversation, SMSMessage
from app.services.sms_service import SMSService
from app.services.tools.registry import ToolRegistry

logger = structlog.get_logger()

# Pending responses waiting for debounce
_pending_responses: dict[str, asyncio.Task[None]] = {}


def build_text_instructions(
    system_prompt: str,
    language: str,
    timezone: str | None = None,
) -> str:
    """Build instructions for text agent.

    Args:
        system_prompt: The agent's custom system prompt
        language: Language code (e.g., "en-US", "es-ES")
        timezone: Workspace timezone

    Returns:
        Complete instructions string for text conversations
    """
    from app.services.gpt_realtime import LANGUAGE_NAMES

    language_name = LANGUAGE_NAMES.get(language, language)
    tz_name = timezone or "UTC"

    # Get current date/time
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        current_datetime = now.strftime("%A, %B %d, %Y at %I:%M %p")
    except Exception:
        current_datetime = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    return f"""[CONTEXT]
Language: {language_name}
Timezone: {tz_name}
Current: {current_datetime}
Channel: SMS/Text Message

[RULES]
- Respond ONLY in {language_name}
- All times are in {tz_name} timezone
- For booking tools, use ISO format with timezone offset
- Keep responses concise - SMS has character limits
- Be conversational but efficient
- Do not use markdown formatting (plain text only)
- Summarize tool results naturally

[YOUR ROLE]
{system_prompt}"""


async def build_message_context(
    conversation: SMSConversation,
    db: AsyncSession,
    max_messages: int = 20,
) -> list[dict[str, str]]:
    """Build message history for LLM context.

    Args:
        conversation: The SMS conversation
        db: Database session
        max_messages: Maximum messages to include

    Returns:
        List of message dicts in OpenAI format
    """
    # Get recent messages ordered by time (oldest first for context)
    result = await db.execute(
        select(SMSMessage)
        .where(SMSMessage.conversation_id == conversation.id)
        .order_by(SMSMessage.created_at.desc())
        .limit(max_messages)
    )
    messages = list(reversed(result.scalars().all()))

    context: list[dict[str, str]] = []
    for msg in messages:
        role = "user" if msg.direction == MessageDirection.INBOUND.value else "assistant"
        context.append({"role": role, "content": msg.body})

    return context


async def generate_text_response(  # noqa: PLR0912, PLR0915
    agent: Agent,
    conversation: SMSConversation,
    db: AsyncSession,
    workspace_id: uuid.UUID,
) -> str | None:
    """Generate AI response for a text conversation.

    Args:
        agent: The text agent to use
        conversation: The SMS conversation
        db: Database session
        workspace_id: Workspace ID for credentials

    Returns:
        Generated response text, or None if failed
    """
    log = logger.bind(
        agent_id=str(agent.id),
        conversation_id=str(conversation.id),
    )
    log.info("generating_text_response")

    # Get user API keys for OpenAI
    user_uuid = user_id_to_uuid(agent.user_id)
    user_settings = await get_user_api_keys(user_uuid, db, workspace_id=workspace_id)

    # If workspace settings don't have OpenAI key, try user-level settings as fallback
    if not user_settings or not user_settings.openai_api_key:
        log.info("workspace_settings_missing_openai_key_trying_user_level")
        user_settings = await get_user_api_keys(user_uuid, db, workspace_id=None)

    if not user_settings or not user_settings.openai_api_key:
        log.error("no_openai_api_key")
        return None

    # Build message context
    messages = await build_message_context(
        conversation, db, max_messages=agent.text_max_context_messages
    )

    if not messages:
        log.warning("no_messages_in_context")
        return None

    # Build system instructions
    system_prompt = build_text_instructions(
        system_prompt=agent.system_prompt,
        language=agent.language,
        timezone=None,  # TODO: Get from workspace settings
    )

    # Get workspace integrations for tools
    integrations = await get_workspace_integrations(user_uuid, workspace_id, db)

    # Initialize tool registry
    tool_registry = ToolRegistry(
        db=db,
        user_id=agent.user_id,
        integrations=integrations,
        workspace_id=workspace_id,
    )

    # Get tool definitions (exclude voice-only tools)
    voice_only_tools = {"end_call", "transfer_call", "send_dtmf"}
    all_tools = tool_registry.get_all_tool_definitions(
        enabled_tools=agent.enabled_tools,
        enabled_tool_ids=agent.enabled_tool_ids,
        agent_settings=agent.integration_settings,
    )

    # Filter out voice-only tools and convert to Chat Completions API format
    # Tool registry returns Realtime API format: {"type": "function", "name": "...", ...}
    # Chat Completions API needs: {"type": "function", "function": {"name": "...", ...}}
    tools = []
    for t in all_tools:
        tool_name = t.get("name") or t.get("function", {}).get("name")
        if tool_name in voice_only_tools:
            continue

        # Check if already in Chat Completions format (has nested "function" object)
        if "function" in t and isinstance(t["function"], dict):
            tools.append(t)
        else:
            # Convert from Realtime API format to Chat Completions format
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.get("name"),
                        "description": t.get("description"),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
            )

    # Create OpenAI client
    client = AsyncOpenAI(api_key=user_settings.openai_api_key)

    # Determine model based on pricing tier
    model = _get_text_model_for_tier(agent.pricing_tier)

    try:
        # Build messages for API call
        api_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        # Build create kwargs
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "temperature": agent.temperature,
            "max_tokens": min(agent.max_tokens, 500),  # Limit for SMS
        }
        if tools:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = "auto"

        # Initial LLM call with timeout to prevent indefinite hangs
        openai_timeout = settings.OPENAI_TIMEOUT
        response = await asyncio.wait_for(
            client.chat.completions.create(**create_kwargs),
            timeout=openai_timeout,
        )

        assistant_message = response.choices[0].message

        # Handle tool calls if any
        if assistant_message.tool_calls:
            log.info("executing_tool_calls", count=len(assistant_message.tool_calls))

            # Execute each tool call
            tool_results: list[dict[str, Any]] = []
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                log.info("executing_tool", tool=tool_name, arguments=arguments)
                result = await tool_registry.execute_tool(tool_name, arguments)
                log.info(
                    "tool_execution_result",
                    tool=tool_name,
                    success=result.get("success"),
                    error=result.get("error"),
                    result_keys=list(result.keys()) if isinstance(result, dict) else None,
                )
                tool_results.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "content": json.dumps(result),
                    }
                )

            # Get final response with tool results
            messages_with_tools = [
                {"role": "system", "content": system_prompt},
                *messages,
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_message.tool_calls
                    ],
                },
                *tool_results,
            ]

            final_response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages_with_tools,  # type: ignore[arg-type]
                    temperature=agent.temperature,
                    max_tokens=min(agent.max_tokens, 500),
                ),
                timeout=openai_timeout,
            )
            response_text = final_response.choices[0].message.content
        else:
            response_text = assistant_message.content

        # Close tool registry
        await tool_registry.close()

        log.info("text_response_generated", length=len(response_text) if response_text else 0)
        return response_text

    except TimeoutError:
        log.warning("openai_api_timeout", timeout=settings.OPENAI_TIMEOUT)
        await tool_registry.close()
        return None
    except Exception as e:
        log.exception("text_response_error", error=str(e))
        await tool_registry.close()
        return None


def _get_text_model_for_tier(pricing_tier: str) -> str:
    """Get the appropriate text model for a pricing tier.

    Args:
        pricing_tier: Agent pricing tier

    Returns:
        OpenAI model name
    """
    # Use cheaper models for text since we're not doing real-time
    tier_models = {
        "budget": "gpt-4o-mini",
        "balanced": "gpt-4o-mini",
        "premium-mini": "gpt-4o-mini",
        "premium": "gpt-4o",
    }
    return tier_models.get(pricing_tier, "gpt-4o-mini")


async def process_inbound_message_with_ai(  # noqa: PLR0911, PLR0912, PLR0915
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    db: AsyncSession,
    provider: str = "telnyx",
) -> None:
    """Process an inbound message and generate AI response.

    This is called after the debounce delay to handle message batching.

    Args:
        conversation_id: The conversation ID
        workspace_id: Workspace ID
        db: Database session
        provider: SMS provider to use for response ("telnyx" or "slicktext")
    """
    log = logger.bind(conversation_id=str(conversation_id), workspace_id=str(workspace_id))
    log.info("processing_inbound_for_ai")

    # Get conversation with agent
    result = await db.execute(select(SMSConversation).where(SMSConversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        log.warning("conversation_not_found")
        return

    log.info(
        "conversation_state",
        ai_enabled=conversation.ai_enabled,
        ai_paused=conversation.ai_paused,
        assigned_agent_id=str(conversation.assigned_agent_id)
        if conversation.assigned_agent_id
        else None,
    )

    # Check if AI is enabled and not paused
    if not conversation.ai_enabled:
        log.info("ai_disabled_for_conversation")  # Changed to INFO for visibility
        return

    if conversation.ai_paused:
        # Check if pause has expired
        if conversation.ai_paused_until and datetime.now(UTC) > conversation.ai_paused_until:
            conversation.ai_paused = False
            conversation.ai_paused_until = None
        else:
            log.info("ai_paused_for_conversation")  # Changed to INFO for visibility
            return

    # Get assigned agent
    if not conversation.assigned_agent_id:
        log.info("no_agent_assigned")  # Changed to INFO for visibility
        return

    agent_result = await db.execute(select(Agent).where(Agent.id == conversation.assigned_agent_id))
    agent = agent_result.scalar_one_or_none()

    if not agent:
        log.warning("agent_not_found")
        return

    log.info(
        "agent_state",
        agent_id=str(agent.id),
        agent_name=agent.name,
        channel_mode=agent.channel_mode,
        is_active=agent.is_active,
    )

    # Check if agent supports text channel
    if agent.channel_mode not in ("text", "both"):
        log.warning("agent_does_not_support_text", channel_mode=agent.channel_mode)
        return

    if not agent.is_active:
        log.warning("agent_not_active")
        return

    # Generate response
    response_text = await generate_text_response(
        agent=agent,
        conversation=conversation,
        db=db,
        workspace_id=workspace_id,
    )

    if not response_text:
        log.warning("no_response_generated")
        return

    # Send response via SMS using the appropriate provider
    user_uuid = user_id_to_uuid(agent.user_id)
    user_settings = await get_user_api_keys(user_uuid, db, workspace_id=workspace_id)

    if not user_settings:
        log.error("no_user_settings")
        return

    # Route to appropriate SMS provider
    if provider == "slicktext":
        # Use SlickText for response
        from app.services.tools.sms_tools import SlickTextSMSTools

        has_v1_creds = bool(
            getattr(user_settings, "slicktext_public_key", None)
            and getattr(user_settings, "slicktext_private_key", None)
        )
        has_v2_creds = bool(user_settings.slicktext_api_key)

        if not has_v1_creds and not has_v2_creds:
            log.error("no_slicktext_credentials")
            return

        slicktext_service = SlickTextSMSTools(
            api_key=user_settings.slicktext_api_key or "",
            public_key=getattr(user_settings, "slicktext_public_key", None),
            private_key=getattr(user_settings, "slicktext_private_key", None),
            textword_id=getattr(user_settings, "slicktext_textword_id", None),
        )

        try:
            send_result = await slicktext_service.send_sms(
                to=conversation.to_number,
                body=response_text,
            )

            if send_result.get("success"):
                # Store the outbound message
                provider_msg_id = send_result.get("message_id") or send_result.get("campaign_id")
                message = SMSMessage(
                    conversation_id=conversation.id,
                    provider="slicktext",
                    provider_message_id=provider_msg_id,
                    direction=MessageDirection.OUTBOUND.value,
                    from_number=conversation.from_number,
                    to_number=conversation.to_number,
                    body=response_text,
                    status="sent",
                    agent_id=agent.id,
                )
                db.add(message)

                # Update conversation metadata
                conversation.last_message_preview = response_text[:255] if response_text else None
                conversation.last_message_at = datetime.now(UTC)
                conversation.last_message_direction = MessageDirection.OUTBOUND.value

                await db.commit()
                log.info("ai_response_sent_slicktext", message_id=str(message.id))
            else:
                log.error("slicktext_send_failed", error=send_result.get("error"))
        finally:
            await slicktext_service.close()
    else:
        # Default: Use Telnyx
        if not user_settings.telnyx_api_key:
            log.error("no_telnyx_credentials")
            return

        sms_service = SMSService(
            api_key=user_settings.telnyx_api_key,
            messaging_profile_id=getattr(user_settings, "telnyx_messaging_profile_id", None),
        )

        try:
            message = await sms_service.send_message(
                to_number=conversation.to_number,
                from_number=conversation.from_number,
                body=response_text,
                db=db,
                workspace_id=workspace_id,
                user_id=user_uuid,
                agent_id=agent.id,
            )
            log.info("ai_response_sent", message_id=str(message.id))
        finally:
            await sms_service.close()


async def schedule_ai_response(
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    delay_ms: int = 3000,
    provider: str = "telnyx",
) -> None:
    """Schedule an AI response after a delay (for message batching).

    If called multiple times for the same conversation within the delay,
    the timer resets to wait for more messages.

    Args:
        conversation_id: The conversation ID
        workspace_id: Workspace ID
        delay_ms: Delay in milliseconds before responding
        provider: SMS provider to use for response ("telnyx" or "slicktext")
    """
    from app.db.session import AsyncSessionLocal

    key = str(conversation_id)
    log = logger.bind(conversation_id=key, delay_ms=delay_ms, provider=provider)

    # Cancel any existing pending response
    if key in _pending_responses:
        _pending_responses[key].cancel()
        log.debug("cancelled_pending_response")

    async def delayed_response() -> None:
        """Execute response after delay."""
        log.info("delayed_response_task_started", delay_seconds=delay_ms / 1000.0)
        try:
            await asyncio.sleep(delay_ms / 1000.0)
            log.info("delayed_response_sleep_completed")

            # Process in new database session
            async with AsyncSessionLocal() as db:
                log.info("delayed_response_db_session_created")
                await process_inbound_message_with_ai(
                    conversation_id, workspace_id, db, provider=provider
                )
                log.info("delayed_response_processing_completed")

        except asyncio.CancelledError:
            log.info("response_cancelled")  # Changed to INFO for visibility
        except Exception:
            log.exception("delayed_response_error")
        finally:
            # Clean up
            _pending_responses.pop(key, None)
            log.info("delayed_response_task_finished")

    # Schedule new response
    task = asyncio.create_task(delayed_response())
    _pending_responses[key] = task
    log.info("scheduled_ai_response")
