# Coaching AI

## Overview

Coaching AI is an automated system that processes coaching call recordings and produces structured summaries enriched with insights, compliance checks, and vulnerability assessments. The service ingests call transcripts, redacts personally identifiable information (PII), and uses large‑language‑model (LLM) analysis powered by Amazon Bedrock to generate comprehensive summaries. Each summary includes:

* **Key points and themes** – the main discussion topics extracted from the call
* **Action items** – follow‑up tasks for participants
* **Sentiment and quality scores** – indicators of call quality and engagement
* **Compliance checks** – configurable rules that evaluate whether the call meets business or regulatory requirements
* **Vulnerability assessments** – deep analysis of client well-being and risk factors when vulnerabilities are detected

The system features a continuous learning pipeline that collects ground truth feedback from coaches and exports it to a golden dataset for model improvement and evaluation.

## Process Flow

The system is built on AWS using Lambda functions, AWS Step Functions, DynamoDB, and EventBridge. There are two primary workflows:

### 1. Summary Workflow (`POST /summarise`)

Clients submit a request with a `meetingId` and transcript. The API validates the request, stores a job record in DynamoDB, and starts a Step Functions workflow:

* **Fetch transcript** – Retrieves the transcript from the request or fetches it from Zoom via their API
* **Normalize roles** – Standardizes speaker labels (e.g., COACH and CLIENT)
* **PII detection & redaction** – Uses Amazon Comprehend to detect and redact personally identifiable information
* **Summarize** – Calls Amazon Bedrock (Claude 3.7 Sonnet) to generate a structured summary with themes, action items, and sentiment analysis
* **Validate & repair** – Validates the LLM output JSON and attempts repairs if needed
* **Persist summary** – Saves the validated summary to S3 and updates DynamoDB
* **Update status** – Updates the final job status in DynamoDB

### 2. Case Check Workflow (`POST /case-check`)

A separate independent workflow for compliance checking and vulnerability assessment:

* **Fetch & normalize transcript** – Same as summary workflow
* **PII detection & redaction** – Same as summary workflow
* **Case check** – Applies configurable compliance rules using Bedrock with optional RAG (Retrieval-Augmented Generation) from a knowledge base
* **Vulnerability assessment** – If vulnerabilities are detected, performs a deep analysis of client well-being and risk factors
* **A2I review (optional)** – For high-severity findings or low pass rates, initiates human review via Amazon A2I
* **Update status** – Updates the assessment status in DynamoDB

### 3. Ground Truth Collection

A continuous feedback loop for model improvement:

* **Coach review workflow** – Coaches review assessments via `GET /reviews/pending` and submit corrections via `POST /review`
* **DynamoDB Streams processor** – Automatically exports reviewed assessments to a golden dataset in S3
* **Golden dataset** – Versioned training data stored in S3 for model evaluation and fine-tuning

### 4. Retrieve Results

* `GET /summaries` – List completed summaries
* `GET /status?meetingId=<id>` – Check job status and get pre-signed URL for summary JSON
* `GET /case?meetingId=<id>` – Get pre-signed URL for case-check report
* `GET /transcript/{meetingId}` – Retrieve redacted transcript
* `GET /health` – System health check

All summaries, case-check reports, and transcripts are stored in Amazon S3 with Athena-partitioned paths for analytics.

## API Endpoints

| Endpoint & Method | Description |
| --- | --- |
| `POST /summarise` | Create a new summarisation job for a meeting ID and transcript. Returns a job identifier. |
| `POST /case-check` | Create a new case check and vulnerability assessment job. Returns an assessment identifier. |
| `GET /summaries` | List existing summary jobs and their statuses. |
| `GET /status?meetingId=<id>` | Retrieve the current status of a job and, if completed, obtain a pre‑signed URL for the summary JSON. |
| `GET /case?meetingId=<id>` | Retrieve a pre‑signed URL for the case‑check report. |
| `GET /transcript/{meetingId}` | Retrieve the redacted transcript for a specific meeting. |
| `GET /reviews/pending` | Fetch pending assessments awaiting coach review. |
| `POST /review` | Submit coach feedback and corrections for an assessment. |
| `GET /health` | System health check endpoint. |

## Output Format

The summary endpoint returns structured JSON similar to the following (fields omitted for brevity):

```json
{
  "summary_schema_version": "1.2",
  "model_version": "bedrock:claude-3-sonnet-20240229",
  "prompt_version": "2025-09-22-a",
  "meeting": {
    "id": "<meetingId>",
    "employerName": "<employer>",
    "coach": "<coach name>",
    "createdAt": "<ISO timestamp>"
  },
  "themes": [
    {
      "id": "<theme id>",
      "label": "<label>",
      "group": "<group>",
      "confidence": 0.8,
      "evidence_quote": "<quote from call>"
    },
    …
  ],
  "summary": "Concise paragraph summarising the call…",
  "actions": [
    {
      "id": "A1",
      "text": "<action item>"
    },
    …
  ],
  "call_metadata": {
    "source": "zoom_api",
    "saved_at": "<ISO timestamp>",
    "insights_version": "2025-08-30-a",
    "schema_version": "1.2"
  },
  "insights": {
    "action_count": 3,
    "theme_count": 3,
    "sentiment_label": "Positive",
    "is_escalation_candidate": false,
    "quality_score": 0.67
  }
}
```

### Case Check Output

Case‑check results include a checklist of compliance tests with detailed findings:

```json
{
  "meeting_id": "<meetingId>",
  "assessment_type": "case_check",
  "checklist": [
    {
      "check_id": "CC001",
      "status": "Pass",
      "severity": "medium",
      "finding": "Coach established rapport...",
      "evidence_spans": ["line 5-8"],
      "suggestion": null
    }
  ],
  "overall_pass_rate": 0.85,
  "high_severity_failures": [],
  "vulnerabilities_detected": true,
  "vulnerability_assessment": {
    "severity": "high",
    "risk_factors": ["chronic pain", "medication concerns"],
    "recommended_actions": ["Refer to medical professional"]
  }
}
```

## Key Features

### Prompt Management
The system uses AWS Systems Manager Parameter Store for centralized prompt versioning and management. Prompts are versioned and can be updated without code deployment.

### RAG-Enhanced Case Checking
Optional knowledge base integration using Amazon Bedrock Knowledge Bases for retrieval-augmented generation, allowing case checks to reference organizational policies and best practices.

### Vulnerability Assessment
Automated detection and assessment of client vulnerabilities (health concerns, emotional distress, safeguarding issues) with severity scoring and recommended coach actions.

### Golden Dataset Pipeline
DynamoDB Streams-powered automation that collects coach reviews and exports them to S3 as training data for continuous model improvement.

### Two-Stage Workflow Architecture
Decoupled summary and case-check workflows allow independent execution, parallel processing, and targeted re-runs of specific analysis types.

## Technology Stack

* **AWS Lambda** (Python 3.11) – serverless functions for API, processing, and streaming
* **AWS Step Functions** – orchestrates summary and case-check workflows
* **Amazon DynamoDB** – stores job status, assessment results, and metadata with TTL and streams
* **Amazon S3** – Athena-partitioned storage for summaries, transcripts, case-checks, and golden datasets
* **Amazon Bedrock** – Claude 3.7 Sonnet for summarization, case checking, and vulnerability assessment
* **Amazon Bedrock Knowledge Bases** – optional RAG for enhanced case checking
* **Amazon Comprehend** – PII detection and redaction
* **Amazon A2I (Augmented AI)** – human-in-the-loop review for high-severity findings
* **AWS Systems Manager Parameter Store** – centralized prompt and configuration management
* **Amazon EventBridge** – event-driven architecture for workflow coordination
* **AWS SAM** – Infrastructure as Code for deployment

### Python Dependencies
* **boto3** – AWS SDK
* **pydantic** – data validation and schema management
* **requests** – HTTP client for Zoom API integration

## Deployment

The system is deployed using AWS SAM (Serverless Application Model):

```bash
# Build the application
sam build

# Deploy to AWS
sam deploy --guided
```

### Configuration Options

The [template.yaml](template.yaml) supports the following parameters:

* `SummaryBucketName` – Optionally use an existing S3 bucket for summaries (creates new bucket if empty)
* `GoldenDataBucketName` – Optionally use an existing S3 bucket for training data (creates new bucket if empty)

### Environment Variables

Key environment variables are configured in `template.yaml`:

* `MODEL_VERSION` – Currently `bedrock:claude-3-7-sonnet-20250219`
* `SUMMARY_SCHEMA_VERSION` – Current schema version `1.2`
* `USE_KNOWLEDGE_BASE` – Enable/disable RAG integration (`true`/`false`)
* `USE_PROMPT_MANAGEMENT` – Enable centralized prompt management (`true`)
* `SAVE_TRANSCRIPTS` – Store transcripts in S3 (`true`)

## Project Structure

```
.
├── summariser/              # Lambda function code
│   ├── fetch_transcript/    # Zoom API integration
│   ├── normalise_roles/     # Speaker label normalization
│   ├── pii_detect_redact/   # PII handling
│   ├── summarise/           # Summary generation
│   ├── case_check/          # Compliance checking
│   ├── assess_vulnerability/# Vulnerability analysis
│   ├── persist_summary/     # S3 persistence
│   ├── feedback_stream_processor/  # Golden dataset export
│   └── utils/               # Shared utilities
├── statemachine/            # Step Functions definitions
├── layers/                  # Shared Python dependencies
├── setup/                   # Setup scripts and utilities
├── docs/                    # Documentation
└── template.yaml            # SAM infrastructure template
```

## Documentation

* [Quick Start Guide](docs/guides/QUICK_START.md)
* [Deployment Checklist](docs/guides/DEPLOYMENT_CHECKLIST.md)
* [Knowledge Base Setup](docs/guides/KNOWLEDGE_BASE_SETUP.md)
* [Case Check Architecture](docs/CASE_CHECK_ARCHITECTURE.md)
* [Vulnerability Assessment Setup](docs/VULNERABILITY_ASSESSMENT_SETUP.md)
* [Ground Truth Workflow](docs/GOLDEN_DATA_WORKFLOW.md)

## Contributing

Contributions are welcome! Please fork the repository, create a feature branch, and open a pull request describing your changes. For significant changes or new functionality, please open an issue first to discuss the proposal.
