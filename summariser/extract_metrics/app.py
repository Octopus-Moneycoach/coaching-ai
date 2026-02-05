"""
Extract Metrics Lambda - Step Functions workflow step
Extracts deterministic call metrics from transcript and VTT.

This Lambda is designed to be:
- Fast (no LLM calls, pure Python)
- Cheap (no API costs)
- Deterministic (same input = same output)
- Reusable (metrics saved to S3 for all workflows to access)

Metrics extracted:
- Total duration (from VTT timestamps)
- Coach speaking time and percentage
- Client speaking time and percentage
- Coach words per minute

Storage:
- Metrics are saved to S3 as call_metrics.json alongside transcript/case/summary files
- This allows both case_check and summary workflows to access the same metrics
"""
import json
import re
import boto3
from datetime import datetime, timezone
from typing import Optional
from utils import helper
from utils.error_handler import lambda_error_handler, ValidationError
from constants import SUMMARY_BUCKET, S3_PREFIX, SCHEMA_VERSION, ATHENA_PARTITIONED

s3 = boto3.client("s3")


def get_transcript_from_s3(s3_key: str) -> str:
    """Fetch transcript from S3."""
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


def parse_timestamp(ts: str) -> float:
    """Parse VTT timestamp to seconds."""
    ts = ts.replace(',', '.').strip()
    parts = ts.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return 0.0


def parse_vtt_segments(vtt_content: str) -> list:
    """
    Parse VTT file into segments with start time, end time, and text.
    Returns list of (start_sec, end_sec, text) tuples.
    """
    if not vtt_content:
        return []

    # Normalize line endings
    vtt_content = vtt_content.replace('\r\n', '\n').replace('\r', '\n')

    segments = []
    # Pattern to match timestamp lines: "00:00:00.000 --> 00:00:05.123"
    timestamp_pattern = re.compile(r'(\d{1,2}:\d{2}:\d{2}[.,]\d+)\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d+)')

    lines = vtt_content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        match = timestamp_pattern.match(line)
        if match:
            start_sec = parse_timestamp(match.group(1))
            end_sec = parse_timestamp(match.group(2))

            # Collect text lines until blank line or next timestamp
            text_lines = []
            i += 1
            while i < len(lines):
                text_line = lines[i].strip()
                if not text_line or timestamp_pattern.match(text_line) or text_line.isdigit():
                    break
                text_lines.append(text_line)
                i += 1

            if text_lines:
                segments.append((start_sec, end_sec, ' '.join(text_lines)))
        else:
            i += 1

    return segments


def get_vtt_duration(vtt_content: str) -> float:
    """
    Extract total call duration from VTT file by finding the last timestamp.
    Returns duration in seconds.
    """
    if not vtt_content:
        return 0.0

    segments = parse_vtt_segments(vtt_content)
    if segments:
        return segments[-1][1]  # End time of last segment

    return 0.0


def parse_vtt_with_speakers(vtt_content: str, coach_name: str) -> dict:
    """
    Parse VTT file and attribute segments to COACH or CLIENT based on speaker name.

    Zoom VTT format includes speaker names before the text, e.g.:
        "John Smith: Hello, how are you today?"

    Returns dict with:
        - coach_duration_sec: Total seconds coach was speaking
        - client_duration_sec: Total seconds client was speaking
        - coach_words: Total words spoken by coach
        - client_words: Total words spoken by client
    """
    if not vtt_content or not coach_name:
        return {
            'coach_duration_sec': 0.0,
            'client_duration_sec': 0.0,
            'coach_words': 0,
            'client_words': 0,
        }

    segments = parse_vtt_segments(vtt_content)
    coach_name_lower = coach_name.lower().strip()

    coach_duration_sec = 0.0
    client_duration_sec = 0.0
    coach_words = 0
    client_words = 0

    # Pattern to extract speaker name from VTT text: "Speaker Name: actual text"
    speaker_pattern = re.compile(r'^([^:]{2,50}):\s*(.*)$')

    for start_sec, end_sec, vtt_text in segments:
        segment_duration = end_sec - start_sec

        # Try to extract speaker from the text
        match = speaker_pattern.match(vtt_text)
        if match:
            speaker_name = match.group(1).strip().lower()
            actual_text = match.group(2).strip()
            word_count = len(actual_text.split()) if actual_text else 0

            # Check if this speaker is the coach
            if coach_name_lower in speaker_name or speaker_name in coach_name_lower:
                coach_duration_sec += segment_duration
                coach_words += word_count
            else:
                client_duration_sec += segment_duration
                client_words += word_count
        else:
            # No speaker prefix - count words but can't attribute
            word_count = len(vtt_text.split()) if vtt_text else 0
            # Default to client for unattributed segments
            client_duration_sec += segment_duration
            client_words += word_count

    return {
        'coach_duration_sec': coach_duration_sec,
        'client_duration_sec': client_duration_sec,
        'coach_words': coach_words,
        'client_words': client_words,
    }


def extract_metrics(transcript: str, vtt_content: Optional[str] = None, coach_name: Optional[str] = None) -> dict:
    """
    Extract call metrics from transcript with VTT-based timing.

    If VTT content and coach_name are provided, uses actual VTT timestamps
    for accurate speaking time calculation. Otherwise falls back to word
    count ratio estimation.

    Args:
        transcript: Normalized transcript with COACH:/CLIENT: labels
        vtt_content: Raw VTT file content (with original speaker names)
        coach_name: Coach's name for matching VTT speaker attribution

    Returns:
        - total_duration_min: Total call duration in minutes (from VTT)
        - coach_speaking_time_min: Coach speaking time in minutes
        - client_speaking_time_min: Client speaking time in minutes
        - coach_speaking_pct: Percentage of speaking time for coach
        - client_speaking_pct: Percentage of speaking time for client
        - coach_wpm: Coach's words per minute
    """
    # Get total duration from VTT
    vtt_segments = parse_vtt_segments(vtt_content) if vtt_content else []
    total_duration_sec = vtt_segments[-1][1] if vtt_segments else 0.0
    total_duration_min = total_duration_sec / 60.0

    # If we have VTT and coach name, use VTT timestamps for accurate timing
    if vtt_content and coach_name:
        timing = parse_vtt_with_speakers(vtt_content, coach_name)
        coach_duration_sec = timing['coach_duration_sec']
        client_duration_sec = timing['client_duration_sec']
        coach_words = timing['coach_words']
        client_words = timing['client_words']

        coach_speaking_time_min = coach_duration_sec / 60.0
        client_speaking_time_min = client_duration_sec / 60.0

        # Calculate percentages based on actual speaking time
        total_speaking_time = coach_duration_sec + client_duration_sec
        if total_speaking_time > 0:
            coach_speaking_pct = round((coach_duration_sec / total_speaking_time * 100), 1)
            client_speaking_pct = round((client_duration_sec / total_speaking_time * 100), 1)
        else:
            coach_speaking_pct = 0.0
            client_speaking_pct = 0.0

        # Coach WPM based on actual speaking time
        if coach_speaking_time_min > 0:
            coach_wpm = round(coach_words / coach_speaking_time_min, 1)
        else:
            coach_wpm = 0.0
    else:
        # Fallback: estimate from word count ratio in normalized transcript
        coach_words = 0
        client_words = 0

        for line in transcript.split('\n'):
            line = line.strip()
            if not line:
                continue
            match = re.match(r'^(COACH|CLIENT):\s*(.*)$', line)
            if match:
                speaker = match.group(1)
                text = match.group(2).strip()
                word_count = len(text.split()) if text else 0
                if speaker == 'COACH':
                    coach_words += word_count
                else:
                    client_words += word_count

        total_words = coach_words + client_words

        if total_words > 0:
            coach_speaking_pct = round((coach_words / total_words * 100), 1)
            client_speaking_pct = round((client_words / total_words * 100), 1)
            coach_speaking_time_min = round((coach_words / total_words) * total_duration_min, 1)
            client_speaking_time_min = round((client_words / total_words) * total_duration_min, 1)
        else:
            coach_speaking_pct = 0.0
            client_speaking_pct = 0.0
            coach_speaking_time_min = 0.0
            client_speaking_time_min = 0.0

        if coach_speaking_time_min > 0:
            coach_wpm = round(coach_words / coach_speaking_time_min, 1)
        else:
            coach_wpm = 0.0

    return {
        'total_duration_min': round(total_duration_min, 1),
        'coach_speaking_time_min': round(coach_speaking_time_min, 1),
        'client_speaking_time_min': round(client_speaking_time_min, 1),
        'coach_speaking_pct': coach_speaking_pct,
        'client_speaking_pct': client_speaking_pct,
        'coach_wpm': coach_wpm,
    }


def save_metrics_to_s3(meeting_id: str, call_metrics: dict, year: int = None, month: int = None) -> str:
    """
    Save call metrics to S3 as JSON (alongside transcript/case/summary files).
    Returns the S3 key where metrics were saved.
    """
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month

    if ATHENA_PARTITIONED:
        key = f"{S3_PREFIX}/call_metrics/version={SCHEMA_VERSION}/year={year}/month={month:02d}/meeting_id={meeting_id}/call_metrics.json"
    else:
        key = f"{S3_PREFIX}/{year}/{month:02d}/{meeting_id}/call_metrics.json"

    # Add metadata
    payload = {
        "meeting_id": meeting_id,
        "extracted_at": now.isoformat(),
        "metrics": call_metrics
    }

    s3.put_object(
        Bucket=SUMMARY_BUCKET,
        Key=key,
        Body=json.dumps(payload, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    helper.log_json("INFO", "METRICS_SAVED_TO_S3", meetingId=meeting_id, s3Key=key)
    return key


def load_metrics_from_s3(meeting_id: str) -> Optional[dict]:
    """
    Try to load existing call metrics from S3.
    Returns metrics dict if found, None otherwise.
    """
    now = datetime.now(timezone.utc)

    # Try current and previous months
    for month_offset in [0, -1, -2]:
        try_month = now.month + month_offset
        try_year = now.year
        if try_month < 1:
            try_month += 12
            try_year -= 1

        if ATHENA_PARTITIONED:
            key = f"{S3_PREFIX}/call_metrics/version={SCHEMA_VERSION}/year={try_year}/month={try_month:02d}/meeting_id={meeting_id}/call_metrics.json"
        else:
            key = f"{S3_PREFIX}/{try_year}/{try_month:02d}/{meeting_id}/call_metrics.json"

        try:
            response = s3.get_object(Bucket=SUMMARY_BUCKET, Key=key)
            data = json.loads(response['Body'].read().decode('utf-8'))
            helper.log_json("INFO", "METRICS_LOADED_FROM_S3", meetingId=meeting_id, s3Key=key)
            return data.get('metrics')
        except s3.exceptions.NoSuchKey:
            continue
        except Exception:
            continue

    return None


@lambda_error_handler()
def lambda_handler(event, context):
    """
    Extract deterministic call metrics from transcript and save to S3.

    This step runs BEFORE PII redaction to access original transcript text
    that matches the VTT file for accurate speaker timing attribution.

    Input:
        - transcriptKey: str (S3 key to normalized transcript - before PII redaction)
        - meetingId: str
        - coachName: str (required for accurate VTT-based timing)
        - source: str (optional, passed through)
        - forceReprocess: bool (optional, if true skip cache check)

    Output:
        - callMetrics: dict (extracted metrics)
        - metricsKey: str (S3 key where metrics are saved)
    """
    transcript_key = event.get("transcriptKey")
    meeting_id = event.get("meetingId")
    coach_name = event.get("coachName")
    source = event.get("source")
    force_reprocess = event.get("forceReprocess", False)

    if not transcript_key:
        raise ValidationError("transcriptKey is required")

    if not meeting_id:
        raise ValidationError("meetingId is required")

    # Check if metrics already exist (skip re-extraction unless forced)
    if not force_reprocess:
        existing_metrics = load_metrics_from_s3(meeting_id)
        if existing_metrics:
            helper.log_json("INFO", "USING_CACHED_METRICS", meetingId=meeting_id)
            return {
                "redactedTranscriptKey": transcript_key,
                "meetingId": meeting_id,
                "source": source,
                "callMetrics": existing_metrics,
                "metricsKey": "cached"
            }

    # Fetch transcript from S3
    helper.log_json("INFO", "LOADING_TRANSCRIPT", meetingId=meeting_id, transcriptKey=transcript_key)
    transcript = get_transcript_from_s3(transcript_key)

    # Fetch VTT for accurate timing calculation
    vtt_content = get_vtt_from_s3(transcript_key)
    has_vtt = vtt_content is not None

    # Extract all metrics (VTT + coach_name enables accurate timing)
    call_metrics = extract_metrics(transcript, vtt_content, coach_name)

    # Save metrics to S3 for reuse by other workflows
    metrics_key = save_metrics_to_s3(meeting_id, call_metrics)

    helper.log_json("INFO", "METRICS_EXTRACTED",
                    meetingId=meeting_id,
                    has_vtt=has_vtt,
                    has_coach_name=bool(coach_name),
                    total_duration_min=call_metrics['total_duration_min'],
                    coach_speaking_pct=call_metrics['coach_speaking_pct'],
                    client_speaking_pct=call_metrics['client_speaking_pct'],
                    coach_wpm=call_metrics['coach_wpm'],
                    metricsKey=metrics_key)

    return {
        "callMetrics": call_metrics,
        "metricsKey": metrics_key
    }
