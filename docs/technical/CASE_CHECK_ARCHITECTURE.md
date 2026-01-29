# Case Check Architecture - Complete Design

This document outlines the complete architecture for case checking comparison between third-party (Aveni Detect) assessments and your AI model, with head coach review workflow.

## Overview

```
Google Sheets (Third-party Case Check Data)
         ↓
Import Script (Python/Lambda)
         ↓
DynamoDB (assessment-results table)
         ↓
Comparison Lambda (Test case by test case)
         ↓
S3 Website (Coach Review Interface)
         ↓
Review Submission (POST /review)
         ↓
DynamoDB Streams → Training Data (S3 JSONL)
```

---

## 1. DATA SOURCES

### 1.1 Google Sheets Structure

**Sheet 1: Test Data** (`https://docs.google.com/spreadsheets/d/1Fz5PFffYeb9Hv_2KxhlSz3n8B6bu7RoEshHlVyDZ2Gc`)
- Tabs: `Starter`, `Action`, `Intro` (one per session type)
- Columns:
  - Coach/Adviser Name
  - Email (client)
  - Reviewer
  - Session Type
  - Overall Score
  - Brand
  - Call Date
  - Status
  - Days Ago
  - Zoom Meeting ID
  - **[NEW]** Aveni Assessment URL (to add)

**Sheet 2: Case Check Definitions** (`https://docs.google.com/spreadsheets/d/1ToAI3A1qO4O6Gghux8njFIW4nSj0Mtef_ptBEQ4UABg`)
- Tabs: `Starter`, `Action`, `Intro`
- Structure: Test cases for each session type
- Columns:
  - Test Case ID
  - Test Case Name
  - Category (Compliance, Macro, etc.)
  - Required/Optional
  - Severity

### 1.2 Your AI Model Output

Currently stored in S3 from your case check Lambda:
```
s3://summaries-bucket/2025/11/meeting-123/case_check.json
```

Structure:
```json
{
  "check_schema_version": "1.0",
  "session_type": "starter_session",
  "meeting_id": "meeting-123",
  "model_version": "claude-3-7-sonnet-20250219",
  "results": [
    {
      "id": "call_recording_confirmed",
      "status": "Competent",
      "confidence": 0.95,
      "evidence_quote": "This call is being recorded...",
      "comment": "Coach clearly stated recording purpose"
    }
  ]
}
```

---

## 2. DYNAMODB SCHEMA

### 2.1 Table: `assessment-results` (Existing, Modified)

**Primary Key:**
- `meeting_id` (String) - PK
- `assessment_id` (String) - SK

**Assessment ID Patterns:**
```
case-check#third-party#{test_case_id}      # Third-party result
case-check#ai#{test_case_id}               # AI model result
case-check#coach#{test_case_id}            # Coach ground truth (after review)
vulnerability#third-party                   # Existing vulnerability pattern
```

**Example Items:**

**Third-party Case Check Result:**
```json
{
  "meeting_id": "zoom-92852394538",
  "assessment_id": "case-check#third-party#call_recording_confirmed",
  "assessment_type": "case-check",

  "test_case_id": "call_recording_confirmed",
  "test_case_name": "Call recording confirmed?",
  "test_case_number": "01",
  "test_case_category": "Compliance",
  "test_case_severity": "high",

  "result": "Competent",
  "evidence_quote": "This call is being recorded for training purposes...",
  "evidence_timestamp": "00:35",
  "comment": null,

  "source": "third-party",
  "third_party_provider": "aveni-detect",
  "assessor_name": "Crystal Tse",
  "assessor_email": "crystal.tse@octopusmoney.com",
  "completed_date": "2025-10-27",
  "form_name": "Octopus Money - Coaching - Starter. v3",

  "adviser_name": "Clare Edwards",
  "client_email": "greg.anderson@sky.uk",
  "call_date": "2025-10-23T14:01:00Z",
  "call_type": "financialCoaching.starter",
  "zoom_meeting_id": "92852394538",

  "overall_score": 96,
  "overall_result": "pass",

  "review_status": "pending",
  "reviewed_by": null,
  "reviewed_at": null,

  "created_at": "2025-11-20T14:00:00Z",
  "expires_at": 1742688000
}
```

**AI Model Result:**
```json
{
  "meeting_id": "zoom-92852394538",
  "assessment_id": "case-check#ai#call_recording_confirmed",
  "assessment_type": "case-check",

  "test_case_id": "call_recording_confirmed",
  "test_case_name": "Call recording confirmed?",
  "test_case_category": "Compliance",

  "result": "Competent",
  "evidence_quote": "This call is being recorded for training and compliance...",
  "confidence": 0.95,
  "reasoning": "Coach mentioned recording at 00:35 and explained purpose",

  "source": "ai",
  "model_name": "claude-3-7-sonnet-20250219",
  "ai_version": "1.0",
  "prompt_version": "2025-11-20-a",

  "s3_full_output_key": "s3://summaries/2025/11/meeting-123/case_check.json",

  "review_status": "pending",
  "created_at": "2025-11-20T14:00:00Z"
}
```

**GSI Updates:**

Add new GSI for test case analysis:
```yaml
TestCaseIndex:
  PartitionKey: test_case_id
  SortKey: created_at
  ProjectionType: ALL
```

---

## 3. IMPORT FLOW

### 3.1 Script: `import_google_sheets_case_checks.py`

**Location:** `/scripts/import_google_sheets_case_checks.py`

**Purpose:** Import third-party case check data from Google Sheets into DynamoDB

**Flow:**
```
1. Read Google Sheet (Test Data)
2. For each meeting row:
   a. Generate meeting_id from Zoom ID
   b. Read corresponding Case Check sheet tab
   c. For each test case:
      - Extract: result, evidence, timestamp
      - Store in DynamoDB with assessment_id pattern
   d. Store meeting metadata
3. Output: Summary report
```

**Usage:**
```bash
# Export Google Sheet to CSV
curl "https://docs.google.com/spreadsheets/d/SHEET_ID/export?format=csv&gid=GID" > test_data.csv
curl "https://docs.google.com/spreadsheets/d/SHEET_ID/export?format=csv&gid=GID2" > case_checks.csv

# Run import
python3 scripts/import_google_sheets_case_checks.py \
  --test-data test_data.csv \
  --case-checks case_checks.csv \
  --session-type starter
```

**Implementation:**
```python
#!/usr/bin/env python3
"""
Import third-party case check data from Google Sheets into DynamoDB

Usage:
    python3 import_google_sheets_case_checks.py \
        --test-data test_data.csv \
        --case-checks case_checks.csv \
        --session-type starter
"""

import csv
import boto3
import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Dict, List

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('assessment-results')

def generate_meeting_id(row: Dict) -> str:
    """Generate meeting ID from Zoom ID or hash"""
    zoom_id = row.get('Zoom Meeting ID', '').strip()
    if zoom_id:
        return f"zoom-{zoom_id}"

    # Fallback: hash of unique identifiers
    unique_str = f"{row['Coach/Adviser Name']}-{row['Email']}-{row['Call Date']}"
    hash_id = hashlib.md5(unique_str.encode()).hexdigest()[:12]
    return f"meeting-{hash_id}"

def parse_test_case_result(case_check_row: Dict) -> Dict:
    """Parse test case result from case check sheet"""
    # Expected columns: Test Case ID, Name, Result, Evidence, Timestamp, Comment
    return {
        'test_case_id': generate_test_case_id(case_check_row['Name']),
        'test_case_name': case_check_row['Name'],
        'test_case_number': case_check_row.get('Number', ''),
        'test_case_category': case_check_row.get('Category', 'Unknown'),
        'result': normalize_result(case_check_row['Result']),
        'evidence_quote': case_check_row.get('Evidence', ''),
        'evidence_timestamp': extract_timestamp(case_check_row.get('Evidence', '')),
        'comment': case_check_row.get('Comment', None)
    }

def generate_test_case_id(test_case_name: str) -> str:
    """
    Convert test case name to standardized ID

    Examples:
    "Call recording confirmed?" → "call_recording_confirmed"
    "Was regulated financial advice given?" → "regulated_advice_given"
    """
    import re
    # Remove punctuation, lowercase, replace spaces with underscores
    cleaned = re.sub(r'[^\w\s]', '', test_case_name.lower())
    cleaned = re.sub(r'\s+', '_', cleaned.strip())

    # Truncate to key words (simple heuristic)
    words = cleaned.split('_')
    if len(words) > 5:
        cleaned = '_'.join(words[:5])

    return cleaned

def normalize_result(result: str) -> str:
    """Normalize result values"""
    mapping = {
        'Competent': 'Competent',
        'Competent with Development': 'CompetentWithDevelopment',
        'Fail': 'Fail',
        'NA': 'NA',
        'N/A': 'NA',
        'Inconclusive': 'Inconclusive'
    }
    return mapping.get(result.strip(), result)

def extract_timestamp(evidence: str) -> str:
    """Extract timestamp like '00:35' from evidence text"""
    import re
    match = re.search(r'\b(\d{1,2}:\d{2})\b', evidence)
    return match.group(1) if match else None

def import_meeting(test_data_row: Dict, case_checks: List[Dict], session_type: str):
    """Import all test cases for a meeting"""
    meeting_id = generate_meeting_id(test_data_row)

    print(f"\nImporting meeting: {meeting_id}")
    print(f"  Adviser: {test_data_row['Coach/Adviser Name']}")
    print(f"  Client: {test_data_row['Email']}")
    print(f"  Call Date: {test_data_row['Call Date']}")

    # Store each test case
    for case_check_row in case_checks:
        test_case = parse_test_case_result(case_check_row)

        item = {
            'meeting_id': meeting_id,
            'assessment_id': f"case-check#third-party#{test_case['test_case_id']}",
            'assessment_type': 'case-check',

            # Test Case Info
            'test_case_id': test_case['test_case_id'],
            'test_case_name': test_case['test_case_name'],
            'test_case_number': test_case['test_case_number'],
            'test_case_category': test_case['test_case_category'],

            # Assessment Result
            'result': test_case['result'],
            'evidence_quote': test_case['evidence_quote'],
            'evidence_timestamp': test_case['evidence_timestamp'],
            'comment': test_case['comment'],

            # Source Info
            'source': 'third-party',
            'third_party_provider': 'aveni-detect',
            'assessor_name': test_data_row.get('Reviewer', ''),
            'form_name': f"Case Check - {session_type.title()}",

            # Call Metadata
            'adviser_name': test_data_row['Coach/Adviser Name'],
            'client_email': test_data_row['Email'],
            'call_date': test_data_row['Call Date'],
            'call_type': f"{test_data_row.get('Brand', 'octopusmoney')}.{session_type}",
            'session_type': session_type,
            'zoom_meeting_id': test_data_row.get('Zoom Meeting ID', ''),

            # Overall Assessment Context
            'overall_score': Decimal(str(test_data_row.get('Overall', '0').replace('%', ''))),
            'overall_result': 'pass' if float(test_data_row.get('Overall', '0').replace('%', '')) >= 80 else 'fail',

            # Review Status
            'review_status': 'pending',

            # Timestamps
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': int((datetime.utcnow().timestamp() + 7776000))  # 90 days
        }

        table.put_item(Item=item)
        print(f"  ✓ Stored: {test_case['test_case_id']} = {test_case['result']}")

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--test-data', required=True, help='Path to test data CSV')
    parser.add_argument('--case-checks', required=True, help='Path to case checks CSV')
    parser.add_argument('--session-type', required=True, choices=['starter', 'action', 'intro'])
    args = parser.parse_args()

    # Read test data
    with open(args.test_data, 'r') as f:
        test_data = list(csv.DictReader(f))

    # Read case checks
    with open(args.case_checks, 'r') as f:
        case_checks = list(csv.DictReader(f))

    print(f"Found {len(test_data)} meetings to import")
    print(f"Found {len(case_checks)} test cases per meeting")

    # Import each meeting
    for row in test_data:
        import_meeting(row, case_checks, args.session_type)

    print(f"\n✅ Import complete!")

if __name__ == '__main__':
    main()
```

---

## 4. COMPARISON LAMBDA

### 4.1 Lambda: `compare_case_checks`

**Purpose:** Compare third-party vs AI results test-case-by-test-case

**Trigger:** EventBridge schedule (daily) or manual invoke

**Logic:**
```python
def lambda_handler(event, context):
    """
    Compare third-party and AI case check results

    1. Query all meetings with pending third-party results
    2. For each meeting:
       a. Fetch all test cases from both sources
       b. Compare results
       c. Calculate match rate
       d. Mark as ready for review
    """

    # Query pending reviews
    response = table.query(
        IndexName='ReviewStatusTypeIndex',
        KeyConditionExpression=Key('review_status').eq('pending') &
                              Key('assessment_type').eq('case-check')
    )

    # Group by meeting
    meetings = group_by_meeting(response['Items'])

    for meeting_id, items in meetings.items():
        third_party = [i for i in items if i['source'] == 'third-party']
        ai = [i for i in items if i['source'] == 'ai']

        # Build comparison
        comparison = build_comparison(third_party, ai)

        # Store comparison result (optional, for caching)
        store_comparison(meeting_id, comparison)
```

---

## 5. COACH REVIEW UI

### 5.1 S3 Website Structure

```
s3://coach-review-interface/
├── index.html                    # Main dashboard
├── case-check-review.html       # Case check review interface (NEW)
├── vulnerability-review.html     # Existing vulnerability interface
├── assets/
│   ├── styles.css
│   └── app.js
└── config.js                     # API endpoint configuration
```

### 5.2 UI Flow

**Dashboard (index.html):**
```html
<div class="dashboard">
  <h1>Coach Review Dashboard</h1>

  <div class="stats">
    <div class="stat-card">
      <h3>Pending Case Checks</h3>
      <p class="stat-number" id="pending-case-checks">0</p>
    </div>
    <div class="stat-card">
      <h3>Pending Vulnerabilities</h3>
      <p class="stat-number" id="pending-vulnerabilities">0</p>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="showTab('case-checks')">Case Checks</button>
    <button class="tab" onclick="showTab('vulnerabilities')">Vulnerabilities</button>
  </div>

  <div id="case-checks-tab" class="tab-content">
    <!-- Case check meetings list -->
  </div>
</div>
```

**Case Check Review (case-check-review.html):**

Shows side-by-side comparison for each test case:

```html
<div class="meeting-review">
  <h2>Meeting: zoom-92852394538</h2>
  <div class="meeting-meta">
    <p>Adviser: Clare Edwards</p>
    <p>Client: greg.anderson@sky.uk</p>
    <p>Call Date: 2025-10-23</p>
    <p>Overall Score: 96% (Third-party)</p>
  </div>

  <div class="test-cases-grid">
    <!-- Test Case 1 -->
    <div class="test-case-card">
      <h3>Call recording confirmed?</h3>
      <span class="category-badge">Compliance</span>

      <div class="comparison">
        <!-- Third-party column -->
        <div class="assessment-column third-party">
          <h4>Third-party (Aveni Detect)</h4>
          <div class="result-badge competent">Competent</div>
          <div class="evidence">
            <strong>Evidence:</strong>
            <p>"This call is being recorded for training purposes..."</p>
            <span class="timestamp">00:35</span>
          </div>
        </div>

        <!-- AI column -->
        <div class="assessment-column ai">
          <h4>AI Model (Claude)</h4>
          <div class="result-badge competent">Competent</div>
          <div class="confidence">Confidence: 95%</div>
          <div class="evidence">
            <strong>Evidence:</strong>
            <p>"This call is being recorded for training and compliance..."</p>
          </div>
          <div class="reasoning">
            <strong>Reasoning:</strong>
            <p>Coach mentioned recording at 00:35 and explained purpose</p>
          </div>
        </div>

        <!-- Match indicator -->
        <div class="match-indicator match">
          ✓ Results Match
        </div>
      </div>

      <!-- Review actions -->
      <div class="review-actions">
        <button class="btn-agree" onclick="agreeWithThirdParty('call_recording_confirmed')">
          ✓ Agree with Third-party
        </button>
        <button class="btn-correct" onclick="showCorrectionForm('call_recording_confirmed')">
          ✎ Provide Correction
        </button>
      </div>

      <!-- Correction form (hidden) -->
      <div id="correction-form-call_recording_confirmed" class="correction-form" style="display:none;">
        <select class="corrected-result">
          <option value="Competent">Competent</option>
          <option value="CompetentWithDevelopment">Competent with Development</option>
          <option value="Fail">Fail</option>
          <option value="NA">Not Applicable</option>
        </select>
        <textarea placeholder="Explain your correction..." class="corrected-reasoning"></textarea>
        <button class="btn-submit" onclick="submitCorrection('call_recording_confirmed')">Submit</button>
      </div>
    </div>

    <!-- More test cases... -->
  </div>

  <!-- Meeting-level actions -->
  <div class="meeting-actions">
    <button class="btn-approve-all">Approve All Matches</button>
    <button class="btn-skip">Skip for Now</button>
  </div>
</div>
```

**JavaScript (app.js):**
```javascript
const API_BASE = 'https://YOUR_API_GATEWAY_URL';

async function loadPendingCaseChecks() {
    const response = await fetch(`${API_BASE}/reviews/pending-case-checks`);
    const data = await response.json();

    document.getElementById('pending-case-checks').textContent = data.count;
    renderCaseCheckMeetings(data.meetings);
}

function renderCaseCheckMeetings(meetings) {
    const container = document.getElementById('case-checks-container');
    container.innerHTML = '';

    for (const meeting of meetings) {
        const card = createMeetingCard(meeting);
        container.appendChild(card);
    }
}

function createMeetingCard(meeting) {
    // Build HTML for meeting with test case comparisons
    // ...
}

async function agreeWithThirdParty(testCaseId) {
    const meetingId = getCurrentMeetingId();

    await fetch(`${API_BASE}/review`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            meeting_id: meetingId,
            assessment_id: `case-check#third-party#${testCaseId}`,
            test_case_id: testCaseId,
            action: 'agree',
            coach_email: getCoachEmail(),
            timestamp: new Date().toISOString()
        })
    });

    // Refresh UI
    loadPendingCaseChecks();
}

async function submitCorrection(testCaseId) {
    const meetingId = getCurrentMeetingId();
    const form = document.getElementById(`correction-form-${testCaseId}`);

    const correctedResult = form.querySelector('.corrected-result').value;
    const reasoning = form.querySelector('.corrected-reasoning').value;

    await fetch(`${API_BASE}/review`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            meeting_id: meetingId,
            assessment_id: `case-check#third-party#${testCaseId}`,
            test_case_id: testCaseId,
            action: 'correct',
            coach_corrected_result: correctedResult,
            coach_reasoning: reasoning,
            coach_email: getCoachEmail(),
            timestamp: new Date().toISOString()
        })
    });

    // Refresh UI
    loadPendingCaseChecks();
}
```

---

## 6. TRAINING DATA COLLECTION

### 6.1 DynamoDB Streams → feedback_stream_processor

**Already exists!** Just need to modify to handle case-check type.

**Update:** `/summariser/feedback_stream_processor/app.py`

Add case check handling:
```python
def process_case_check_feedback(new_image: Dict, old_image: Dict) -> Dict:
    """Process case check review feedback"""

    # Extract coach correction
    coach_action = new_image.get('coach_action', {}).get('S')

    if coach_action == 'agree':
        # Coach agreed with third-party
        ground_truth_result = new_image.get('result', {}).get('S')
    else:
        # Coach provided correction
        ground_truth_result = new_image.get('coach_corrected_result', {}).get('S')

    # Fetch transcript
    meeting_id = new_image['meeting_id']['S']
    transcript = fetch_transcript_from_s3(meeting_id)

    # Build training example
    training_example = {
        'input': transcript,
        'case_check': {
            'test_case_id': new_image['test_case_id']['S'],
            'test_case_name': new_image['test_case_name']['S'],
            'test_case_category': new_image.get('test_case_category', {}).get('S'),

            # Results from different sources
            'third_party_result': new_image.get('result', {}).get('S'),  # Original third-party
            'ai_result': get_ai_result(meeting_id, new_image['test_case_id']['S']),
            'coach_result': ground_truth_result,

            # Evidence
            'third_party_evidence': new_image.get('evidence_quote', {}).get('S'),
            'ai_evidence': get_ai_evidence(meeting_id, new_image['test_case_id']['S']),

            # Coach feedback
            'coach_verified': coach_action == 'agree',
            'results_match': check_results_match(new_image),
            'coach_reasoning': new_image.get('coach_reasoning', {}).get('S')
        },
        'metadata': {
            'meeting_id': meeting_id,
            'test_case_id': new_image['test_case_id']['S'],
            'coach_email': new_image.get('reviewed_by', {}).get('S'),
            'reviewed_at': new_image.get('reviewed_at', {}).get('S'),
            'feedback_type': coach_action,
            'model_name': get_ai_model_name(meeting_id),
            'ai_version': get_ai_version(meeting_id)
        }
    }

    return training_example

def store_training_example(example: Dict, assessment_type: str):
    """Store training example to S3"""

    now = datetime.utcnow()
    year = now.year
    month = now.month

    # S3 key with partitioning
    s3_key = f"training-data/{assessment_type}/year={year}/month={month:02d}/labeled_{assessment_type}.jsonl"

    # Append to JSONL file
    append_jsonl_to_s3(s3_key, example)
```

**Output Format (JSONL):**
```jsonl
{"input": "Coach: This call is being recorded... Client: Okay", "case_check": {"test_case_id": "call_recording_confirmed", "test_case_name": "Call recording confirmed?", "test_case_category": "Compliance", "third_party_result": "Competent", "ai_result": "Competent", "coach_result": "Competent", "coach_verified": true, "results_match": true, "third_party_evidence": "00:35 - This call is being recorded...", "ai_evidence": "Coach mentioned recording at 00:35", "coach_reasoning": null}, "metadata": {"meeting_id": "zoom-92852394538", "test_case_id": "call_recording_confirmed", "coach_email": "head.coach@octopusmoney.com", "reviewed_at": "2025-11-20T15:00:00Z", "feedback_type": "agree", "model_name": "claude-3-7-sonnet-20250219", "ai_version": "1.0"}}
```

---

## 7. DEPLOYMENT STEPS

### Step 1: Update DynamoDB Schema
```yaml
# In template.yaml, add TestCaseIndex GSI
TestCaseIndex:
  Type: AWS::DynamoDB::GlobalSecondaryIndex
  Properties:
    IndexName: TestCaseIndex
    KeySchema:
      - AttributeName: test_case_id
        KeyType: HASH
      - AttributeName: created_at
        KeyType: RANGE
    Projection:
      ProjectionType: ALL
```

### Step 2: Create Import Script
```bash
# Create script
touch scripts/import_google_sheets_case_checks.py
chmod +x scripts/import_google_sheets_case_checks.py

# Test with sample data
python3 scripts/import_google_sheets_case_checks.py \
  --test-data sample_test_data.csv \
  --case-checks sample_case_checks.csv \
  --session-type starter
```

### Step 3: Add Lambda: get_pending_case_check_reviews
```python
# In summariser/get_pending_case_check_reviews/app.py
# Similar to get_pending_reviews but for case checks
```

### Step 4: Update feedback_stream_processor
```bash
# Edit summariser/feedback_stream_processor/app.py
# Add case_check handling
```

### Step 5: Deploy S3 Website
```bash
# Create S3 bucket
aws s3 mb s3://coach-review-interface-case-checks --region eu-west-2

# Enable website hosting
aws s3 website s3://coach-review-interface-case-checks \
  --index-document index.html

# Upload files
aws s3 sync evals/ s3://coach-review-interface-case-checks/ --acl public-read
```

### Step 6: Deploy Stack
```bash
sam build
sam deploy --guided
```

---

## 8. USAGE WORKFLOW

### For Head Coaches:

1. **Navigate to Review Dashboard**
   ```
   http://coach-review-interface-case-checks.s3-website.eu-west-2.amazonaws.com
   ```

2. **Enter Email**
   - Required for attribution

3. **View Pending Meetings**
   - See list of meetings with case checks ready for review
   - Sorted by date

4. **Review Each Test Case**
   - See third-party result vs AI result side-by-side
   - View evidence and reasoning
   - Check if results match

5. **Take Action**
   - **Agree:** Click "Agree with Third-party"
   - **Correct:** Click "Provide Correction", select correct result, add reasoning

6. **Move to Next**
   - After all test cases reviewed, move to next meeting

---

## 9. ANALYTICS & INSIGHTS

### Queries You Can Run:

**1. Overall Match Rate:**
```sql
SELECT
  COUNT(*) as total_test_cases,
  SUM(CASE WHEN results_match = true THEN 1 ELSE 0 END) as matches,
  AVG(CASE WHEN results_match = true THEN 1.0 ELSE 0.0 END) * 100 as match_rate_pct
FROM assessment_results
WHERE assessment_type = 'case-check'
  AND review_status = 'reviewed'
```

**2. Match Rate by Test Case:**
```sql
SELECT
  test_case_id,
  test_case_name,
  COUNT(*) as occurrences,
  SUM(CASE WHEN results_match = true THEN 1 ELSE 0 END) as matches,
  AVG(CASE WHEN results_match = true THEN 1.0 ELSE 0.0 END) * 100 as match_rate_pct
FROM assessment_results
WHERE assessment_type = 'case-check'
  AND review_status = 'reviewed'
GROUP BY test_case_id, test_case_name
ORDER BY match_rate_pct ASC
```

**3. Most Problematic Test Cases:**
```sql
SELECT
  test_case_id,
  test_case_category,
  COUNT(*) as disagreements
FROM assessment_results
WHERE assessment_type = 'case-check'
  AND review_status = 'reviewed'
  AND results_match = false
GROUP BY test_case_id, test_case_category
ORDER BY disagreements DESC
LIMIT 10
```

---

## 10. FUTURE ENHANCEMENTS

### Phase 2: PDF Extraction
- Add Lambda to extract case checks from Aveni Detect PDFs
- Auto-import when PDFs are uploaded to S3

### Phase 3: Aveni Detect API
- Once API access granted, replace manual import with API calls
- Real-time sync of assessments

### Phase 4: Automated Insights
- Dashboard showing model performance over time
- Alert when match rate drops below threshold
- Suggested prompt improvements based on disagreements

---

## Summary

This architecture provides:
- ✅ **Complete traceability**: Third-party → AI → Coach ground truth
- ✅ **Test-case-level comparison**: Granular insights
- ✅ **Easy coach workflow**: Simple UI for review
- ✅ **Automatic training data collection**: Via DynamoDB Streams
- ✅ **Scalable**: Same pattern for all assessment types
- ✅ **Production-ready**: Based on proven vulnerability assessment architecture

Next step: Would you like me to start implementing these components?
