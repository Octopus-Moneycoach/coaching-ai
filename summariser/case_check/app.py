"""
Case Check Lambda - Step Functions workflow step
Performs compliance case checking using Bedrock Claude
"""
import json
import os
from typing import List, Optional, Tuple, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from utils import helper
from utils.error_handler import lambda_error_handler
from utils.prompt_management import invoke_with_prompt_management, get_prompt_arn_from_parameter_store
from utils.aws_clients import AWSClients
from constants import *

# Import KB retrieval module
try:
    from case_check.kb_retrieval import retrieve_and_format_examples
    KB_ENABLED = True
except ImportError:
    KB_ENABLED = False
    helper.log_json("WARNING", "KB_MODULE_NOT_FOUND", message="Running without Knowledge Base integration")

# Use centralized AWS clients
bedrock = AWSClients.bedrock_runtime()
s3 = AWSClients.s3()
ssm = AWSClients.ssm()

# DynamoDB client for assessment-results table
import boto3
dynamodb = boto3.resource('dynamodb')
ASSESSMENT_RESULTS_TABLE = os.environ.get('ASSESSMENT_RESULTS_TABLE', 'assessment-results')
assessment_table = dynamodb.Table(ASSESSMENT_RESULTS_TABLE)

# Prompt Management configuration
USE_PROMPT_MANAGEMENT = os.environ.get("USE_PROMPT_MANAGEMENT", "true").lower() == "true"
PROMPT_PARAM_NAME = os.environ.get("PROMPT_PARAM_NAME_CASE_CHECK", "/call-summariser/prompts/case-check/current")

# Cache for prompt ARN (loaded once per Lambda container)
_prompt_arn_cache = {}

# Get KB configuration from environment
USE_KB = os.environ.get("USE_KNOWLEDGE_BASE", "true").lower() == "true"
KB_PARAM_NAME = os.environ.get("KNOWLEDGE_BASE_PARAM_NAME", "/call-summariser/knowledge-base-id")

# Fetch KB ID from Parameter Store (cached for Lambda container lifetime)
KB_ID = None
if USE_KB:
    try:
        response = ssm.get_parameter(Name=KB_PARAM_NAME, WithDecryption=False)
        KB_ID = response['Parameter']['Value']
        helper.log_json("INFO", "KB_ID_LOADED_FROM_PARAMETER_STORE", kb_param_name=KB_PARAM_NAME)
    except Exception as e:
        helper.log_json("WARNING", "KB_ID_PARAMETER_NOT_FOUND",
                       kb_param_name=KB_PARAM_NAME,
                       error=str(e),
                       message="Knowledge Base integration will be disabled")


def get_prompt_arn() -> Optional[str]:
    """Get prompt ARN from Parameter Store (cached for Lambda container lifetime)"""
    return get_prompt_arn_from_parameter_store(
        param_name=PROMPT_PARAM_NAME,
        cache_dict=_prompt_arn_cache,
        use_prompt_management=USE_PROMPT_MANAGEMENT
    )


def get_transcript_from_s3(s3_key: str) -> str:
    """Fetch transcript from S3"""
    response = s3.get_object(Bucket=SUMMARY_BUCKET, Key=s3_key)
    return response['Body'].read().decode('utf-8')


def get_vtt_from_s3(transcript_key: str) -> Optional[str]:
    """
    Try to fetch the VTT file from S3 based on transcript key.
    VTT files are stored alongside transcripts as zoom_raw.vtt
    """
    try:
        # Derive VTT key from transcript key
        # e.g., .../meeting_id=X/redacted_transcript.txt -> .../meeting_id=X/zoom_raw.vtt
        vtt_key = transcript_key.rsplit('/', 1)[0] + '/zoom_raw.vtt'
        response = s3.get_object(Bucket=SUMMARY_BUCKET, Key=vtt_key)
        return response['Body'].read().decode('utf-8')
    except Exception:
        return None


def get_vtt_duration(vtt_content: str) -> float:
    """
    Extract total call duration from VTT file by finding the last timestamp.
    Returns duration in seconds.
    """
    import re

    if not vtt_content:
        return 0.0

    # Normalize line endings
    vtt_content = vtt_content.replace('\r\n', '\n').replace('\r', '\n')

    # Find all end timestamps (the second timestamp in each "start --> end" line)
    # Pattern matches HH:MM:SS.mmm or MM:SS.mmm
    timestamps = re.findall(r'-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d+)', vtt_content)

    if not timestamps:
        return 0.0

    # Parse the last timestamp to get total duration
    last_ts = timestamps[-1].replace(',', '.')
    parts = last_ts.split(':')

    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)

    return 0.0


def calculate_call_analytics(transcript: str, vtt_content: Optional[str] = None) -> dict:
    """
    Calculate call analytics from normalized transcript (with COACH/CLIENT labels).

    The transcript should already be normalized with COACH: and CLIENT: prefixes
    (done by normalise_roles step). VTT is used only for total duration.

    Returns:
        - Word counts per speaker
        - Turn counts
        - Talk ratios (by word count)
        - Words per minute (if VTT duration available)
    """
    import re

    # Initialize tracking
    coach_words = 0
    client_words = 0
    coach_turns = 0
    client_turns = 0
    last_speaker_type = None

    # Parse the normalized transcript (expects COACH: and CLIENT: labels)
    lines = transcript.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match COACH: or CLIENT: at start of line
        speaker_match = re.match(r'^(COACH|CLIENT):\s*(.*)$', line)
        if speaker_match:
            speaker = speaker_match.group(1)
            text = speaker_match.group(2).strip()
            word_count = len(text.split()) if text else 0

            if speaker == 'COACH':
                coach_words += word_count
                if last_speaker_type != 'COACH':
                    coach_turns += 1
                    last_speaker_type = 'COACH'
            else:  # CLIENT
                client_words += word_count
                if last_speaker_type != 'CLIENT':
                    client_turns += 1
                    last_speaker_type = 'CLIENT'

    # Calculate derived metrics
    total_words = coach_words + client_words
    total_turns = coach_turns + client_turns

    # Get duration from VTT if available
    total_duration_sec = get_vtt_duration(vtt_content) if vtt_content else 0.0
    total_duration_min = total_duration_sec / 60.0 if total_duration_sec > 0 else 0.0

    # Talk ratios (by word count)
    if total_words > 0:
        coach_talk_ratio = round((coach_words / total_words * 100), 1)
        client_talk_ratio = round((client_words / total_words * 100), 1)
    else:
        coach_talk_ratio = 0.0
        client_talk_ratio = 0.0

    # Average words per turn
    coach_avg_words_per_turn = round(coach_words / coach_turns, 1) if coach_turns > 0 else 0.0
    client_avg_words_per_turn = round(client_words / client_turns, 1) if client_turns > 0 else 0.0

    # Words per minute (if we have duration)
    if total_duration_min > 0:
        total_words_per_min = round(total_words / total_duration_min, 1)
        coach_words_per_min = round(coach_words / total_duration_min, 1)
        client_words_per_min = round(client_words / total_duration_min, 1)
    else:
        total_words_per_min = 0.0
        coach_words_per_min = 0.0
        client_words_per_min = 0.0

    return {
        # Duration (from VTT)
        'total_duration_sec': round(total_duration_sec, 1),
        'total_duration_min': round(total_duration_min, 1),
        # Word-based metrics
        'total_words': total_words,
        'coach_words': coach_words,
        'client_words': client_words,
        # Words per minute
        'total_words_per_min': total_words_per_min,
        'coach_words_per_min': coach_words_per_min,
        'client_words_per_min': client_words_per_min,
        # Ratios (by word count)
        'coach_talk_ratio': coach_talk_ratio,
        'client_talk_ratio': client_talk_ratio,
        # Turn metrics
        'total_turns': total_turns,
        'coach_turns': coach_turns,
        'client_turns': client_turns,
        'coach_avg_words_per_turn': coach_avg_words_per_turn,
        'client_avg_words_per_turn': client_avg_words_per_turn,
    }


# ---------- Case check models ----------
Span = Tuple[int, int]
Status = Literal["Competent", "CompetentWithDevelopment", "Fail", "NotApplicable", "Inconclusive"]


class CaseCheckResult(BaseModel):
    id: str
    status: Status
    confidence: float
    evidence_spans: List[Span] = Field(default_factory=list)
    evidence_quote: Optional[str] = ""
    comment: Optional[str] = ""


class CaseCheckPayload(BaseModel):
    check_schema_version: str
    session_type: str
    checklist_version: str
    meeting_id: str
    model_version: str
    prompt_version: str
    results: List[CaseCheckResult]
    overall: dict


# ---------- Tool definition for structured output ----------
def get_case_check_tool():
    """
    Create a tool definition for structured case check output.
    This ensures the LLM returns valid JSON matching our Pydantic schema.
    """
    return {
        "toolSpec": {
            "name": "submit_case_check",
            "description": "Submit the case check assessment results. Focus on providing the 'results' array with your assessment of each check, and the 'overall' summary. Metadata fields are optional and will be populated automatically.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "check_schema_version": {"type": "string"},
                        "session_type": {"type": "string"},
                        "checklist_version": {"type": "string"},
                        "meeting_id": {"type": "string"},
                        "model_version": {"type": "string"},
                        "prompt_version": {"type": "string"},
                        "results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string", "description": "Check identifier"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["Competent", "CompetentWithDevelopment", "Fail", "NotApplicable", "Inconclusive"],
                                        "description": "Assessment status"
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0.0,
                                        "maximum": 1.0,
                                        "description": "Confidence score 0-1"
                                    },
                                    "evidence_spans": {
                                        "type": "array",
                                        "items": {
                                            "type": "array",
                                            "items": {"type": "integer"},
                                            "minItems": 2,
                                            "maxItems": 2
                                        },
                                        "description": "List of [start, end] character positions"
                                    },
                                    "evidence_quote": {
                                        "type": "string",
                                        "description": "REQUIRED: Direct quote from transcript supporting your assessment. Must be actual dialogue from the call."
                                    },
                                    "comment": {
                                        "type": "string",
                                        "description": "REQUIRED: Brief explanation of your assessment (1-2 sentences)"
                                    }
                                },
                                "required": ["id", "status", "confidence", "evidence_quote", "evidence_spans", "comment"]
                            }
                        },
                        "overall": {
                            "type": "object",
                            "properties": {
                                "pass_rate": {"type": "number"},
                                "failed_ids": {"type": "array", "items": {"type": "string"}},
                                "high_severity_flags": {"type": "array", "items": {"type": "string"}},
                                "has_high_severity_failures": {"type": "boolean"}
                            }
                        }
                    },
                    "required": ["results", "overall"]
                }
            }
        }
    }


STARTER_SESSION_CHECKS = [
    # ============================================
    # BUSINESS RISK CHECKS (Compliance/Regulatory)
    # ============================================
    {"id": "call_recording_confirmed", "prompt": "Call recording confirmed? Did the coach confirm that the call is being recorded for training and compliance purposes?", "required": True, "severity": "high", "theme": "businessRisk"},
    {"id": "regulated_advice_given", "prompt": "Was regulated financial advice given and/or was there evidence of steering/social norming? NOTE: This is NOT permitted. Regulated advice means specific product recommendations or steering towards specific actions. If the coach gave regulated advice or steered the client, the status must be 'Fail'.", "required": True, "severity": "high", "theme": "businessRisk"},
    {"id": "vulnerability_identified", "prompt": "Was any vulnerability identified and addressed appropriately? Did the coach identify any client vulnerabilities according to FCA FG21/1 guidelines and handle them appropriately?\n\nVulnerability Categories (FCA FG21/1):\n- Health: Mental Health Condition, Severe or Long-term Illness, Hearing or Visual Impairment, Physical Disability, Addiction, Low Mental Capacity\n- Life Events: Bereavement, Caring Responsibilities, Domestic Abuse, Relationship Breakdown, Income Shock, Retirement\n- Resilience: Low Emotional Resilience, Inadequate or Erratic Income, Over-indebtedness, Low Savings\n- Capability: Low Knowledge or Confidence in Managing Finances, Poor Literacy or Numeracy Skills, Poor English Language Skills, Poor Digital Skills, Learning Difficulties, Low Access to Help or Support", "required": True, "severity": "high", "theme": "businessRisk"},
    {"id": "dob_confirmed", "prompt": "Date of Birth confirmed? Was the client's date of birth confirmed during the call?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "client_name_confirmed", "prompt": "Client name confirmed? Was the client's full name confirmed during the call?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "marital_status_confirmed", "prompt": "Client's marital status confirmed? Was the client's marital/partner status confirmed?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "citizenship_confirmed", "prompt": "UK Citizenship and if any US tax connections confirmed? Did the coach confirm UK citizenship/residency and check for any US tax connections?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "dependents_confirmed", "prompt": "Dependents confirmed? Were dependents confirmed? Note: Dependents are not limited to just children.", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "pension_details_confirmed", "prompt": "Pension details confirmed? Did the coach confirm the client's pension details (current pensions, contributions, amounts)?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "income_expenditure_confirmed", "prompt": "Income and expenditure details confirmed? Did the coach confirm the client's income and expenditure details?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "assets_liabilities_confirmed", "prompt": "Assets and liabilities details confirmed? Did the coach confirm the client's assets (savings, property, investments) and liabilities (debts, loans)?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "emergency_fund_confirmed", "prompt": "Emergency fund confirmed? Did the coach discuss and confirm the client's emergency fund status?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "will_confirmed", "prompt": "Will confirmed? Did the coach confirm whether the client has a will in place?", "required": True, "severity": "low", "theme": "businessRisk"},
    {"id": "pension_withdrawal_if_over_50", "prompt": "If over 50, will the client be withdrawing from their pension within the next 5 years? If the client is over 50, did the coach check if they plan to withdraw from their pension in the next 5 years?", "required": False, "severity": "medium", "theme": "businessRisk"},
    {"id": "high_interest_debt_addressed", "prompt": "If the client has high-interest unsecured debt, did the coach let them know they won't be able to produce any recommendations until that debt is paid off?", "required": False, "severity": "high", "theme": "businessRisk"},
    {"id": "fees_charges_explained", "prompt": "Were fees and charges correctly explained to the client? Did the coach clearly explain the service fees (e.g., £299, salary sacrifice options)?", "required": True, "severity": "high", "theme": "businessRisk"},
    {"id": "way_forward_agreed", "prompt": "Was a way forward agreed with the client? Did the coach and client agree on next steps and book a follow-up session?", "required": True, "severity": "medium", "theme": "businessRisk"},
    {"id": "money_calculators_introduced", "prompt": "Did the coach introduce the money calculators? Did the coach explain and introduce the money calculators that the client will use?", "required": True, "severity": "medium", "theme": "businessRisk"},

    # ============================================
    # CUSTOMER EXPERIENCE CHECKS (Coaching Quality)
    # ============================================
    {"id": "coach_introduction_signposting", "prompt": "Did the coach introduce themselves and Octopus Money, and signpost the structure of this call? Did the coach provide a clear introduction and outline of what the call would cover?", "required": True, "severity": "medium", "theme": "customerExperience"},
    {"id": "client_goals_established", "prompt": "Did the coach establish key information about the client's goals? Did the coach ask about and explore the client's financial goals?", "required": True, "severity": "high", "theme": "customerExperience"},
    {"id": "client_motivations_established", "prompt": "Did the coach establish client motivations for achieving their goals? Did the coach explore WHY the goals are important to the client?", "required": True, "severity": "medium", "theme": "customerExperience"},
    {"id": "asked_client_move_forward", "prompt": "Did the coach clearly ask the client if they want to move forward with the service? Did the coach explicitly ask if the client wants to sign up and continue?", "required": True, "severity": "high", "theme": "customerExperience"},
    {"id": "client_questions_opportunity", "prompt": "Did the client have the opportunity to ask any questions? Did the coach provide opportunities throughout and at the end for the client to ask questions?", "required": True, "severity": "medium", "theme": "customerExperience"},
]


# JSON repair and extraction functions removed - no longer needed with structured output via Tool Use


def _save_case_json(meeting_id: str, payload: dict, year: int = None, month: int = None) -> str:
    """Save case check JSON to S3"""
    if year is None or month is None:
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.month

    if ATHENA_PARTITIONED:
        key = f"{S3_PREFIX}/supplementary/version={SCHEMA_VERSION}/year={year}/month={month:02d}/meeting_id={meeting_id}/case_check.v{CASE_CHECK_SCHEMA_VERSION}.json"
    else:
        key = f"{S3_PREFIX}/{year:04d}/{month:02d}/{meeting_id}/case_check.v{CASE_CHECK_SCHEMA_VERSION}.json"

    s3.put_object(
        Bucket=SUMMARY_BUCKET,
        Key=key,
        Body=json.dumps(payload).encode("utf-8"),
        ContentType="application/json",
    )
    helper.log_json("INFO", "CASE_CHECK_SAVED", meetingId=meeting_id, s3Key=key)
    return key


def _save_checks_to_assessment_table(meeting_id: str, case_data: dict, transcript_key: str, call_analytics: dict = None):
    """
    Save individual case check results to assessment-results DynamoDB table.
    Each check becomes a separate item for granular coach review.
    Also saves an overall case assessment record for triage and call analytics.
    """
    try:
        expires_at = int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp())
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build lookup for check themes
        theme_by_id = {c["id"]: c.get("theme", "businessRisk") for c in STARTER_SESSION_CHECKS}

        # Track failed questions by theme
        failed_business_risk = []
        failed_customer_exp = []
        all_failed_ids = []

        for check_result in case_data.get('results', []):
            check_id = check_result.get('id')
            if not check_id:
                continue

            # Determine if this is the vulnerability check
            is_vulnerability_check = (check_id == 'vulnerability_identified')
            check_failed = (check_result.get('status') == 'Fail')
            theme = theme_by_id.get(check_id, 'businessRisk')

            # Track failures by theme
            if check_failed:
                all_failed_ids.append(check_id)
                # Get the human-readable label from check definition
                check_def = next((c for c in STARTER_SESSION_CHECKS if c["id"] == check_id), None)
                check_label = check_def["prompt"].split("?")[0] + "?" if check_def else check_id

                if theme == 'businessRisk':
                    failed_business_risk.append(check_label)
                else:
                    failed_customer_exp.append(check_label)

            assessment_table.put_item(Item={
                'meeting_id': meeting_id,
                'assessment_id': f"case-check#{check_id}",
                'assessment_type': 'case-check',
                'ai_version': case_data.get('prompt_version', PROMPT_VERSION),
                'model_name': case_data.get('model_version', MODEL_VERSION),

                # AI Output
                'ai_output': json.dumps({
                    'status': check_result.get('status'),
                    'evidence_quote': check_result.get('evidence_quote', ''),
                    'evidence_spans': check_result.get('evidence_spans', []),
                    'comment': check_result.get('comment', ''),
                    'confidence': float(check_result.get('confidence', 0.0))
                }),

                # Review status
                'review_status': 'pending',
                'created_at': now_iso,

                # Links
                'transcript_s3_key': transcript_key,

                # Case-check specific fields
                'check_id': check_id,
                'result': check_result.get('status'),
                'evidence': check_result.get('evidence_quote', ''),
                'confidence': Decimal(str(check_result.get('confidence', 0.0))),

                # Theme categorization (matching Thirdparty's structure)
                'theme': theme,

                # Vulnerability trigger flag
                'has_detailed_assessment': (is_vulnerability_check and check_failed),

                # Session metadata
                'session_type': case_data.get('session_type', 'starter_session'),

                # TTL
                'expires_at': expires_at
            })

            helper.log_json("INFO", "CASE_CHECK_ASSESSMENT_SAVED",
                          meetingId=meeting_id,
                          checkId=check_id,
                          status=check_result.get('status'),
                          theme=theme)

        # ============================================
        # Save OVERALL case assessment record (like Thirdparty's triage)
        # ============================================
        overall = case_data.get('overall', {})
        pass_rate = float(overall.get('pass_rate', 0.0))
        failed_count = len(all_failed_ids)

        # Determine triage outcome (Pass if no failures, Fail otherwise)
        triage_outcome = "Pass" if failed_count == 0 else "Fail"
        triage_grade = "pass" if failed_count == 0 else "fail"

        # Build the overall assessment item
        item = {
            'meeting_id': meeting_id,
            'assessment_id': 'case-check#overall',
            'assessment_type': 'case-check-overall',
            'ai_version': case_data.get('prompt_version', PROMPT_VERSION),
            'model_name': case_data.get('model_version', MODEL_VERSION),

            # Triage outcome (matching Thirdparty's structure)
            'triage_outcome': triage_outcome,
            'triage_grade': triage_grade,
            'pass_rate': Decimal(str(pass_rate)),

            # Failed question counts
            'failed_question_count': failed_count,
            'failed_ids': all_failed_ids,

            # Failed questions by theme (matching Thirdparty's structure)
            'business_risk_failures': failed_business_risk,
            'business_risk_failure_count': len(failed_business_risk),
            'customer_exp_failures': failed_customer_exp,
            'customer_exp_failure_count': len(failed_customer_exp),

            # High severity flags
            'has_high_severity_failures': overall.get('has_high_severity_failures', False),
            'high_severity_flags': overall.get('high_severity_flags', []),

            # Review status
            'review_status': 'pending',
            'created_at': now_iso,

            # Links
            'transcript_s3_key': transcript_key,

            # Session metadata
            'session_type': case_data.get('session_type', 'starter_session'),

            # TTL
            'expires_at': expires_at
        }

        # Add call analytics (convert floats to Decimal for DynamoDB)
        if call_analytics:
            for key, value in call_analytics.items():
                if isinstance(value, float):
                    item[key] = Decimal(str(value))
                elif isinstance(value, list) and key == 'speakers_detected':
                    item[key] = value  # Keep list as-is
                else:
                    item[key] = value

        assessment_table.put_item(Item=item)

        helper.log_json("INFO", "CASE_CHECK_OVERALL_SAVED",
                      meetingId=meeting_id,
                      triage_outcome=triage_outcome,
                      failed_count=failed_count,
                      business_risk_failures=len(failed_business_risk),
                      customer_exp_failures=len(failed_customer_exp),
                      coach_talk_ratio=call_analytics.get("coach_talk_ratio") if call_analytics else None,
                      total_words=call_analytics.get("total_words") if call_analytics else None)

    except Exception as e:
        # Log error but don't fail the Lambda (S3 save is primary)
        helper.log_json("ERROR", "ASSESSMENT_TABLE_UPDATE_FAILED",
                       meetingId=meeting_id,
                       error=str(e))


@lambda_error_handler()
def lambda_handler(event, context):
    """
    Perform case check on redacted transcript.

    Input:
        - redactedTranscriptKey: str (S3 key to redacted transcript)
        - meetingId: str
        - forceReprocess: bool (optional, default False)
        - callMetrics: dict (optional, pre-extracted metrics from ExtractMetrics step)

    Output:
        - caseData: dict
        - caseKey: str
        - passRate: float
        - hasVulnerability: bool
        - callAnalytics: dict
    """
    transcript_key = event.get("redactedTranscriptKey")
    meeting_id = event.get("meetingId")
    force_reprocess = event.get("forceReprocess", False)
    call_metrics_from_event = event.get("callMetrics")  # Pre-extracted metrics from ExtractMetrics step

    if not transcript_key:
        raise ValueError("redactedTranscriptKey is required")

    if not meeting_id:
        raise ValueError("meetingId is required")

    # Determine expected case check S3 key
    now = datetime.now(timezone.utc)
    if ATHENA_PARTITIONED:
        case_key = f"{S3_PREFIX}/supplementary/version={SCHEMA_VERSION}/year={now.year}/month={now.month:02d}/meeting_id={meeting_id}/case_check.v{CASE_CHECK_SCHEMA_VERSION}.json"
    else:
        case_key = f"{S3_PREFIX}/{now.year:04d}/{now.month:02d}/{meeting_id}/case_check.v{CASE_CHECK_SCHEMA_VERSION}.json"

    # Idempotency check: If case check already exists and not forcing reprocess, return it
    if not force_reprocess:
        try:
            response = s3.get_object(Bucket=SUMMARY_BUCKET, Key=case_key)
            case_data = json.loads(response['Body'].read().decode('utf-8'))
            pass_rate = float(case_data.get("overall", {}).get("pass_rate", 0.0))
            helper.log_json("INFO", "CASE_CHECK_EXISTS", meetingId=meeting_id, caseKey=case_key, reused=True)
            return {
                "caseData": case_data,
                "caseKey": case_key,
                "passRate": pass_rate
            }
        except s3.exceptions.NoSuchKey:
            # File doesn't exist, proceed with case check
            pass
        except Exception as e:
            # Log error but continue with processing
            helper.log_json("WARN", "CASE_CHECK_CHECK_FAILED", meetingId=meeting_id, error=str(e))

    # Fetch transcript from S3 (already normalized with COACH/CLIENT labels)
    full_transcript = get_transcript_from_s3(transcript_key)

    # Use pre-extracted metrics if provided, otherwise calculate locally (fallback)
    if call_metrics_from_event:
        call_analytics = call_metrics_from_event
        helper.log_json("INFO", "USING_PREEXTRACTED_METRICS",
                       meetingId=meeting_id,
                       total_words=call_analytics.get('total_words', 0),
                       total_duration_min=call_analytics.get('total_duration_min', 0),
                       coach_talk_ratio=call_analytics.get('coach_talk_ratio', 0))
    else:
        # Fallback: Calculate locally if metrics not passed (backward compatibility)
        helper.log_json("INFO", "CALCULATING_METRICS_LOCALLY", meetingId=meeting_id,
                       message="callMetrics not provided, calculating locally")
        vtt_content = get_vtt_from_s3(transcript_key)
        call_analytics = calculate_call_analytics(full_transcript, vtt_content)
        helper.log_json("INFO", "CALL_ANALYTICS_CALCULATED",
                       meetingId=meeting_id,
                       total_words=call_analytics.get('total_words', 0),
                       total_duration_min=call_analytics.get('total_duration_min', 0),
                       coach_talk_ratio=call_analytics.get('coach_talk_ratio', 0),
                       total_words_per_min=call_analytics.get('total_words_per_min', 0),
                       total_turns=call_analytics.get('total_turns', 0))

    # Claude 3.7 Sonnet context window: 200K tokens (sufficient for max 1.5h calls)
    # Max call: 1.5h ≈ 90K chars ≈ 22.5K tokens input + 5K output = 27.5K total (13% of context)
    # No chunking needed - process entire transcript in one API call for better context
    helper.log_json("INFO", "CASE_CHECK_START",
                   meetingId=meeting_id,
                   transcript_length=len(full_transcript),
                   transcript_tokens_approx=len(full_transcript) // 4)

    # Retrieve KB examples for compliance checks
    kb_examples = ""
    if USE_KB and KB_ENABLED and KB_ID:
        try:
            import time
            kb_start_time = time.time()
            helper.log_json("INFO", "KB_RETRIEVAL_START", meetingId=meeting_id, kb_id=KB_ID)

            check_ids = [c["id"] for c in STARTER_SESSION_CHECKS]
            check_descriptions = {c["id"]: c["prompt"] for c in STARTER_SESSION_CHECKS}

            kb_examples = retrieve_and_format_examples(
                check_ids=check_ids,
                check_descriptions=check_descriptions,
                max_per_check=1,
                kb_id=KB_ID
            )

            kb_elapsed = time.time() - kb_start_time
            helper.log_json("INFO", "KB_RETRIEVAL_COMPLETE",
                          meetingId=meeting_id,
                          examples_length=len(kb_examples),
                          kb_retrieval_time_ms=int(kb_elapsed * 1000))
        except Exception as e:
            helper.log_json("WARNING", "KB_RETRIEVAL_ERROR",
                          meetingId=meeting_id,
                          error=str(e),
                          message="Continuing without KB examples")
            kb_examples = ""
    else:
        helper.log_json("INFO", "KB_DISABLED",
                       meetingId=meeting_id,
                       use_kb=USE_KB,
                       kb_enabled=KB_ENABLED,
                       has_kb_id=bool(KB_ID))

    # Process full transcript in single API call
    case_check_tool = get_case_check_tool()
    prompt_arn = get_prompt_arn()

    if prompt_arn:
        checklist_json = json.dumps(
            {"session_type": "starter_session", "version": "1", "checks": STARTER_SESSION_CHECKS},
            ensure_ascii=False,
        )

        variables = {
            "kb_examples": kb_examples if kb_examples else "",
            "checklist_json": checklist_json,
            "cleaned_transcript": full_transcript
        }

        resp, latency_ms = invoke_with_prompt_management(
            prompt_arn=prompt_arn,
            variables=variables,
            model_id=MODEL_ID,
            tools=[case_check_tool],
            tool_choice={"tool": {"name": "submit_case_check"}},
            max_tokens_override=8000
        )
    else:
        helper.log_json("ERROR", "NO_PROMPT_ARN", message="Prompt Management disabled or failed")
        raise ValueError("Prompt Management is required but prompt ARN not available")

    # Extract structured output from tool use
    output_message = resp.get("output", {}).get("message", {})
    content_blocks = output_message.get("content", [])

    tool_use_block = None
    for block in content_blocks:
        if "toolUse" in block:
            tool_use_block = block["toolUse"]
            break

    if not tool_use_block:
        raise ValueError("No tool use block found in response")

    stop_reason = resp.get("stopReason", "")
    if stop_reason == "max_tokens":
        helper.log_json("ERROR", "CASE_CHECK_TRUNCATED",
                       meetingId=meeting_id,
                       message="Response hit max_tokens - increase max_tokens_override or reduce transcript length")
        raise ValueError(f"Response truncated at max_tokens for meeting {meeting_id}")

    validated_json = tool_use_block["input"]

    # Inject metadata fields
    validated_json.setdefault("check_schema_version", CASE_CHECK_SCHEMA_VERSION)
    validated_json.setdefault("session_type", "starter_session")
    validated_json.setdefault("checklist_version", "1")
    validated_json.setdefault("meeting_id", meeting_id)
    validated_json.setdefault("model_version", MODEL_VERSION)
    validated_json.setdefault("prompt_version", PROMPT_VERSION)

    # Defensive parsing for stringified fields (only if needed)
    # Tool Use should return structured JSON, but handle edge cases
    if "results" in validated_json and isinstance(validated_json["results"], str):
        helper.log_json("WARNING", "RESULTS_AS_STRING",
                       meetingId=meeting_id,
                       message="results field unexpectedly returned as string, attempting to parse",
                       stopReason=stop_reason,
                       resultsLength=len(validated_json["results"]))

        try:
            validated_json = helper.parse_stringified_fields(
                data=validated_json,
                fields=["results"],
                meeting_id=meeting_id,
                context="case_check"
            )
        except ValueError as e:
            # If parsing fails, log safe metadata without PII
            helper.log_json("ERROR", "RESULTS_PARSE_FAILED",
                           meetingId=meeting_id,
                           parseError=str(e),
                           stopReason=stop_reason,
                           resultsLength=len(validated_json["results"]),
                           resultsType=str(type(validated_json["results"])),
                           message="Failed to parse results field - may be truncated or malformed")
            raise ValueError(f"Failed to parse case check results for meeting {meeting_id}. "
                           f"Stop reason: {stop_reason}. Error: {str(e)}") from e

    # Calculate 'overall' if model didn't provide it (fallback calculation)
    if "overall" not in validated_json or not validated_json.get("overall"):
        helper.log_json("WARNING", "OVERALL_MISSING_FROM_MODEL",
                       meetingId=meeting_id,
                       message="Model did not return 'overall' field - calculating from results")

        results_list = validated_json.get("results", [])
        if isinstance(results_list, list):
            # Calculate pass rate and failed IDs
            total_checks = len(results_list)
            failed_ids = []
            high_severity_flags = []
            severity_by_id = {c["id"]: c.get("severity", "low") for c in STARTER_SESSION_CHECKS}

            for r in results_list:
                if isinstance(r, dict) and r.get("status") == "Fail":
                    check_id = r.get("id", "")
                    failed_ids.append(check_id)
                    if severity_by_id.get(check_id) == "high":
                        high_severity_flags.append(check_id)

            passed_count = total_checks - len(failed_ids)
            pass_rate = (passed_count / total_checks * 100) if total_checks > 0 else 0.0

            validated_json["overall"] = {
                "pass_rate": round(pass_rate, 1),
                "failed_ids": failed_ids,
                "high_severity_flags": high_severity_flags,
                "has_high_severity_failures": len(high_severity_flags) > 0
            }

            helper.log_json("INFO", "OVERALL_CALCULATED",
                           meetingId=meeting_id,
                           pass_rate=pass_rate,
                           failed_count=len(failed_ids),
                           high_severity_count=len(high_severity_flags))
        else:
            # Fallback empty overall if results is malformed
            validated_json["overall"] = {
                "pass_rate": 0.0,
                "failed_ids": [],
                "high_severity_flags": [],
                "has_high_severity_failures": False
            }

    # Clean up and calculate evidence_spans
    if "results" in validated_json and isinstance(validated_json["results"], list):
        for result_item in validated_json["results"]:
            if isinstance(result_item, dict):
                evidence_quote = result_item.get("evidence_quote", "")
                evidence_spans = result_item.get("evidence_spans", [])

                # Filter out invalid spans (must be [int, int] with 2 elements)
                if evidence_spans:
                    valid_spans = []
                    for span in evidence_spans:
                        if isinstance(span, (list, tuple)) and len(span) == 2:
                            try:
                                valid_spans.append([int(span[0]), int(span[1])])
                            except (ValueError, TypeError):
                                pass  # Skip invalid spans
                    result_item["evidence_spans"] = valid_spans
                    evidence_spans = valid_spans

                if evidence_quote and not evidence_spans:
                    clean_quote = evidence_quote.strip()
                    if clean_quote:
                        pos = full_transcript.find(clean_quote)
                        if pos != -1:
                            result_item["evidence_spans"] = [[pos, pos + len(clean_quote)]]
                        else:
                            short_quote = clean_quote[:50]
                            pos = full_transcript.find(short_quote)
                            if pos != -1:
                                result_item["evidence_spans"] = [[pos, pos + len(clean_quote)]]
                            else:
                                result_item["evidence_spans"] = []
                                helper.log_json("WARNING", "EVIDENCE_QUOTE_NOT_FOUND",
                                               meetingId=meeting_id,
                                               check_id=result_item.get("id"),
                                               quote_preview=clean_quote[:100])

    usage = resp.get("usage", {})
    cost_breakdown = helper.calculate_bedrock_cost(usage, model_id="claude-3-7-sonnet")

    log_data = {
        "meetingId": meeting_id,
        "operation": "case_check",
        "latency_ms": latency_ms,
        "stop_reason": stop_reason,
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
        "structured_output": True,
        "cost_usd": cost_breakdown["total_cost"],
        "input_cost_usd": cost_breakdown["input_cost"],
        "output_cost_usd": cost_breakdown["output_cost"]
    }

    if "cacheReadInputTokens" in usage:
        log_data["cache_read_tokens"] = usage.get("cacheReadInputTokens", 0)
        log_data["cache_creation_tokens"] = usage.get("cacheCreationInputTokens", 0)
        log_data["cache_read_cost_usd"] = cost_breakdown["cache_read_cost"]
        log_data["cache_write_cost_usd"] = cost_breakdown["cache_write_cost"]
        log_data["cache_savings_usd"] = cost_breakdown["cache_savings"]

    helper.log_json("INFO", "CASE_CHECK_LLM_OK", **log_data)

    # Validate with Pydantic
    parsed = CaseCheckPayload.model_validate(validated_json)
    data = parsed.model_dump()

    data["meeting_id"] = meeting_id
    data["model_version"] = MODEL_VERSION
    data["prompt_version"] = PROMPT_VERSION

    severity_by_id = {c["id"]: c.get("severity", "low") for c in STARTER_SESSION_CHECKS}
    has_high_severity_failures = False
    has_vulnerability = False

    for r in data.get("results", []):
        r["evidence_quote"] = r.get("evidence_quote") or ""
        r["comment"] = r.get("comment") or ""
        r["confidence"] = max(0.0, min(1.0, float(r.get("confidence", 0.0))))

        if r.get("status") == "Fail" and severity_by_id.get(r.get("id")) == "high":
            has_high_severity_failures = True

        # Check if vulnerability exists (triggers detailed FCA FG21/1 assessment)
        # Trigger when: Competent (found & handled) OR Fail (found but not handled)
        # Don't trigger when: NotApplicable (no vulnerability present)
        if r.get("id") == "vulnerability_identified" and r.get("status") in ["Competent", "Fail"]:
            has_vulnerability = True

    data["overall"]["has_high_severity_failures"] = has_high_severity_failures

    # Add call analytics to case data
    data["call_analytics"] = call_analytics

    # Save to S3
    key = _save_case_json(meeting_id, data)

    # Save to assessment-results DynamoDB table (for coach review & training data)
    _save_checks_to_assessment_table(meeting_id, data, transcript_key, call_analytics)

    # Calculate pass rate
    pass_rate = float(data.get("overall", {}).get("pass_rate", 0.0))

    return {
        "caseData": data,
        "caseKey": key,
        "passRate": pass_rate,
        "hasVulnerability": has_vulnerability,  # Trigger detailed vulnerability assessment
        "callAnalytics": call_analytics  # Call analytics for downstream use
    }
