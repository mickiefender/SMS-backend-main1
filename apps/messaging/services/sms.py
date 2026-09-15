import re

from django.db import transaction
from django.utils import timezone

from ..models import SMSBalance, SMSCreditLedger, SMSMessage

ALLOWED_VARIABLES = {
    "parent_name", "student_name", "class_name", "school_name", "amount",
    "date", "time", "subject", "teacher_name",
}
VARIABLE_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def message_parts(message):
    # GSM messages are 160 chars (70 for unicode); concatenated messages are
    # charged in seven/three-character chunks respectively.
    limit = 70 if any(ord(char) > 127 for char in message) else 160
    concat = 67 if limit == 70 else 153
    return 1 if len(message) <= limit else (len(message) + concat - 1) // concat


def render_message(template, context):
    names = VARIABLE_RE.findall(template)
    unknown = set(names) - ALLOWED_VARIABLES
    if unknown:
        raise ValueError("This template contains unsupported variables.")
    missing = [name for name in names if not str(context.get(name, "")).strip()]
    if missing:
        raise ValueError("Some required message variables could not be resolved.")
    return VARIABLE_RE.sub(lambda match: str(context[match.group(1)]), template)


def reserve_credits(school, amount, actor=None, job=None):
    if amount < 1:
        raise ValueError("At least one SMS recipient is required.")
    with transaction.atomic():
        balance, _ = SMSBalance.objects.select_for_update().get_or_create(school=school)
        if balance.credits < amount:
            raise ValueError("Your SMS balance is insufficient to send this message.")
        balance.credits -= amount
        balance.save(update_fields=["credits", "updated_at"])
        SMSCreditLedger.objects.create(
            school=school, amount=-amount, balance_after=balance.credits,
            reason="reserved", actor=actor, job=job,
        )
        return balance.credits


def refund_credits(school, amount, actor=None, job=None):
    if amount <= 0:
        return
    with transaction.atomic():
        balance, _ = SMSBalance.objects.select_for_update().get_or_create(school=school)
        balance.credits += amount
        balance.save(update_fields=["credits", "updated_at"])
        SMSCreditLedger.objects.create(
            school=school, amount=amount, balance_after=balance.credits,
            reason="refund", actor=actor, job=job,
        )


def provider_message_id(response):
    for key in ("message_id", "messageId", "id", "request_id"):
        if response.get(key):
            return str(response[key])
    data = response.get("data")
    if isinstance(data, dict):
        return provider_message_id(data)
    return ""


def send_sms(*, school, recipients, message, sender_id=None, triggered_by=None,
             category="custom", idempotency_key="", enqueue=True):
    """Create an idempotent SMS job and queue delivery through Celery."""
    from ..models import SMSConfiguration, SMSJob
    config = SMSConfiguration.objects.filter(school=school).first()
    if not config or not config.is_enabled or config.sender_id_status != "approved":
        raise ValueError("Your Sender ID has not been approved yet.")
    if sender_id and sender_id != config.sender_id:
        raise ValueError("The selected Sender ID is not available for this school.")
    sender_id = config.sender_id
    normalized = []
    for item in recipients:
        phone = item.get("phone") if isinstance(item, dict) else item
        if not phone:
            continue
        phone = re.sub(r"[\s().-]", "", str(phone))
        if phone.startswith("00"):
            phone = "+" + phone[2:]
        if not re.fullmatch(r"\+?[1-9]\d{6,14}", phone):
            continue
        context = item.get("context", {}) if isinstance(item, dict) else {}
        try:
            rendered = render_message(message, context)
        except ValueError:
            # The caller must provide a context for personalized messages.
            raise
        normalized.append((phone, rendered))
    if not normalized:
        raise ValueError("No valid recipients were supplied.")
    parts = message_parts(normalized[0][1])
    credits = len(normalized) * parts
    with transaction.atomic():
        job_kwargs = {
            "school": school, "requested_by": triggered_by,
            "recipient_count": len(normalized), "credits_reserved": credits,
        }
        if idempotency_key:
            job, created = SMSJob.objects.get_or_create(
                school=school, idempotency_key=idempotency_key, defaults=job_kwargs,
            )
            if not created:
                return job, False
        else:
            job = SMSJob.objects.create(**job_kwargs)
        reserve_credits(school, credits, actor=triggered_by, job=job)
        SMSMessage.objects.bulk_create([
            SMSMessage(
                school=school, job=job, sender_id=sender_id, recipient=phone,
                message=rendered, category=category, message_parts=message_parts(rendered),
                credits_used=message_parts(rendered), sent_by=triggered_by,
            )
            for phone, rendered in normalized
        ])
    if enqueue:
        try:
            from ..tasks import process_sms_job
            process_sms_job.delay(job.pk)
        except Exception:
            # A queued job can be retried when the worker becomes available.
            pass
    return job, True
