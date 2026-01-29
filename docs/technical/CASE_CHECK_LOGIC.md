# Case Check Logic - Comprehensive Documentation

## Overview

The case check system evaluates financial coaching call transcripts against 25 compliance and quality criteria. It uses AWS Bedrock Claude with optional RAG (Retrieval Augmented Generation) to provide consistent, high-quality assessments.

---

## Table of Contents

1. [Assessment Framework](#assessment-framework)
2. [Status Types](#status-types)
3. [Check Categories](#check-categories)
4. [Compliance Checks (17)](#compliance-checks)
5. [Macro/Quality Checks (8)](#macro-quality-checks)
6. [Assessment Rules](#assessment-rules)
7. [Evidence Requirements](#evidence-requirements)
8. [Severity Levels](#severity-levels)
9. [Processing Flow](#processing-flow)
10. [Chunking Strategy](#chunking-strategy)
11. [Result Merging](#result-merging)
12. [Output Format](#output-format)

---

## Assessment Framework

### Philosophy

The case check system uses a **compliance-first, quality-second** approach:

1. **Compliance violations = Automatic Fail** - Steering, regulated advice, or missing high-severity items result in Fail
2. **Quality matters for Pass level** - Distinction between Competent and CompetentWithDevelopment
3. **Evidence-based decisions** - Every assessment requires specific transcript quotes
4. **Consistency through RAG** - Learning from curated examples ensures similar calls get similar assessments

---

## Status Types

### 1. **Competent** ✅
- **Meaning**: The coach fully met the requirement with clear evidence
- **Standard**: This is the expected level for good performance
- **Example**: Coach clearly confirmed call recording at start: "This call is being recorded for training and compliance purposes"

### 2. **CompetentWithDevelopment** ⚠️
- **Meaning**: Requirement met, but execution could be better
- **Standard**: Core requirement satisfied, but quality/depth lacking
- **Example**: Coach briefly mentioned call recording but didn't explain the purpose: "We're recording this"

### 3. **Fail** ❌
- **Meaning**: Requirement missed, incorrect, or violated compliance rules
- **Standard**: Any of:
  - Required item not addressed
  - Steering or regulated advice given
  - High-severity compliance violation
- **Example**: Coach gave specific product recommendation: "I think the best route for you would be to max out your ISA"

### 4. **NotApplicable** ⏭️
- **Meaning**: This check doesn't apply to this specific session
- **Standard**: Use sparingly, only when truly not applicable
- **Example**: "Pension withdrawal check" when client is under 40

### 5. **Inconclusive** ❓
- **Meaning**: Insufficient evidence to make a clear judgment
- **Standard**: Last resort - prefer Fail if truly unclear whether requirement was met
- **Example**: Audio quality poor and critical section not transcribed

---

## Check Categories

### Compliance Criteria (17 checks)
**Purpose**: Ensure regulatory compliance and risk management
**Severity**: High to Medium
**Examples**: Call recording, regulated advice detection, personal details confirmation

### Macro-Criteria (8 checks)
**Purpose**: Assess coaching quality and client engagement
**Severity**: High to Medium
**Examples**: Goal establishment, relevant suggestions, client engagement

---

## Compliance Checks

### High Severity (Must Pass)

#### 1. **call_recording_confirmed**
- **Question**: Did the coach confirm that the call is being recorded for training and compliance purposes?
- **Competent**: Clear confirmation with purpose stated
- **Fail**: No confirmation or purpose not mentioned
- **Evidence**: Look for phrases like "recorded for training and compliance"

#### 2. **regulated_advice_given**
- **Question**: Was regulated financial advice given and/or was there evidence of steering/social norming?
- **Competent**: NO regulated advice or steering detected
- **Fail**: ANY steering language detected:
  - "The best route..."
  - "You should..."
  - "I would do..."
  - Specific product recommendations
- **Evidence**: Direct quotes showing steering or confirming its absence

#### 3. **vulnerability_identified**
- **Question**: Was any vulnerability identified and addressed appropriately?
- **Competent**: Vulnerabilities proactively identified and handled sensitively
- **Fail**: Vulnerability missed or handled inappropriately
- **Evidence**: Coach's response to health, financial, or life circumstance issues

#### 4. **fees_charges_explained**
- **Question**: Were fees and charges correctly explained to the client?
- **Competent**: Clear explanation of £299 fee, salary sacrifice options, and payment structure
- **Fail**: Fees not explained or incorrectly stated
- **Evidence**: Specific mention of fees and payment options

#### 5. **high_interest_debt_addressed** (Conditional)
- **Question**: If client has high-interest unsecured debt, did coach explain no recommendations until paid off?
- **NotApplicable**: No high-interest debt mentioned
- **Fail**: Client has debt but restriction not explained
- **Evidence**: Debt discussion and restriction explanation

### Medium Severity (Important but not critical)

#### 6-15. **Personal Details Confirmation**

**dob_confirmed**
- Date of birth confirmed during call
- Evidence: "Can you confirm your date of birth?"

**client_name_confirmed**
- Full name confirmed
- Evidence: "Let me confirm I have your name correct: [Full Name]"

**marital_status_confirmed**
- Marital/partner status confirmed
- Evidence: "Are you married, in a partnership, or single?"

**citizenship_confirmed**
- UK citizenship and US tax connections checked
- Evidence: "Are you a UK citizen? Any US tax connections?"

**dependents_confirmed**
- Dependents confirmed (not just children)
- Evidence: "Do you have any dependents?"

**pension_details_confirmed**
- Current pensions, contributions, amounts confirmed
- Evidence: Detailed pension discussion

**income_expenditure_confirmed**
- Income and expenditure details confirmed
- Evidence: Monthly income and spending reviewed

**assets_liabilities_confirmed**
- Assets (savings, property) and liabilities (debts) confirmed
- Evidence: Comprehensive financial position review

**emergency_fund_confirmed**
- Emergency fund status discussed
- Evidence: Coach checked emergency fund adequacy

**pension_withdrawal_if_over_50** (Conditional)
- If over 50, plan to withdraw pension in next 5 years checked
- NotApplicable: Client under 50
- Evidence: Age-specific pension planning discussion

### Low Severity (Good practice)

#### 16. **will_confirmed**
- **Question**: Did the coach confirm whether the client has a will?
- **Competent**: Will status confirmed
- **CompetentWithDevelopment**: Briefly mentioned but not explored
- **Evidence**: Discussion about will and estate planning

#### 17. **way_forward_agreed**
- **Question**: Was a way forward agreed with the client?
- **Competent**: Clear next steps and follow-up session booked
- **Fail**: No clear plan or follow-up scheduled
- **Evidence**: Explicit agreement on next actions

---

## Macro Quality Checks

### High Severity (Core Coaching Skills)

#### 1. **client_goals_established**
- **Question**: Did the coach establish key information about the client's goals?
- **Competent**: Coach explored multiple financial goals with depth
- **CompetentWithDevelopment**: Goals mentioned but not deeply explored
- **Fail**: No goal exploration
- **Evidence**: Questions about what client wants to achieve

#### 2. **relevant_suggestions_provided**
- **Question**: Were relevant suggestions provided based on goals explored?
- **Competent**: Tailored, specific suggestions matching client's circumstances
- **CompetentWithDevelopment**: Generic suggestions
- **Fail**: No suggestions or irrelevant ones
- **Evidence**: Specific advice tied to stated goals

#### 3. **asked_client_move_forward**
- **Question**: Did coach clearly ask if client wants to move forward with the service?
- **Competent**: Direct, clear question about proceeding
- **Fail**: No explicit ask to move forward
- **Evidence**: "Would you like to move forward with us?"

### Medium Severity (Important Quality Indicators)

#### 4. **coach_introduction_signposting**
- **Question**: Did coach introduce themselves and Octopus Money, and signpost the call structure?
- **Competent**: Clear introduction with call agenda
- **CompetentWithDevelopment**: Brief introduction, no agenda
- **Evidence**: Opening statements about coach, company, and plan

#### 5. **current_actions_established**
- **Question**: Did coach establish what client is already doing toward goals?
- **Competent**: Explored existing savings, investments, actions
- **Evidence**: Questions about current financial activities

#### 6. **client_motivations_established**
- **Question**: Did coach establish WHY goals are important to client?
- **Competent**: Explored emotional/life drivers behind goals
- **Evidence**: "Why is this important to you?"

#### 7. **money_calculators_introduced**
- **Question**: Did coach introduce the money calculators?
- **Competent**: Explained calculators and how client will use them
- **Evidence**: Discussion of calculator tools

#### 8. **client_questions_opportunity**
- **Question**: Did client have opportunity to ask questions?
- **Competent**: Multiple opportunities offered throughout and at end
- **CompetentWithDevelopment**: Single opportunity at end
- **Evidence**: "Do you have any questions?"

---

## Assessment Rules

### General Principles

1. **Use Competent liberally**: If requirement is clearly met, use Competent (not CompetentWithDevelopment)
2. **CompetentWithDevelopment for quality gaps**: Use when requirement is technically met but could be better
3. **Fail for violations or omissions**: Use when requirement missed or compliance violated
4. **NotApplicable sparingly**: Only when check truly doesn't apply
5. **Inconclusive as last resort**: Prefer Fail if unable to confirm requirement was met

### Compliance Violations (Auto-Fail)

#### Steering Language Examples:
```
❌ "The best route would be..."
❌ "You should definitely..."
❌ "I would recommend..."
❌ "What I'd do in your position..."
❌ "The right thing to do here is..."
```

#### Safe Language Examples:
```
✅ "You could consider..."
✅ "Some clients in similar situations have..."
✅ "Options available to you include..."
✅ "It might be worth exploring..."
✅ "Have you thought about..."
```

### Evidence Requirements

**Every assessment must include:**
1. **Evidence Quote**: Actual transcript excerpt (not summary)
2. **Comment**: Explanation of WHY status was assigned
3. **Confidence Score**: 0.0 to 1.0

**Good Evidence Quote:**
```
Evidence: "Coach: This call is being recorded for training and compliance purposes, is that okay?"
Comment: "Coach clearly stated recording and its purpose at the start of call"
Confidence: 0.95
```

**Poor Evidence Quote (Don't do this):**
```
Evidence: "The coach mentioned recording"
Comment: "Recording was discussed"
Confidence: 0.5
```

---

## Severity Levels

### High Severity
- **Impact**: Regulatory compliance or serious quality issues
- **Examples**: Regulated advice, call recording, fees explanation, client goals
- **Consequence**: Fails in these areas trigger high-severity flags

### Medium Severity
- **Impact**: Important compliance or quality indicators
- **Examples**: Personal details, financial information, coaching structure
- **Consequence**: Multiple fails may indicate systemic issues

### Low Severity
- **Impact**: Good practice but not critical
- **Examples**: Will confirmation
- **Consequence**: Fails are noted but less impactful

---

## Processing Flow

### Step-by-Step Process

```
1. Input Validation
   ├─ Check redactedTranscriptKey exists
   └─ Check meetingId provided

2. Transcript Retrieval
   └─ Fetch from S3 using transcript key

3. Transcript Chunking (if needed)
   ├─ Check if transcript > 20,000 chars
   ├─ If yes: Split into overlapping chunks
   └─ If no: Process as single chunk

4. KB Example Retrieval (if enabled)
   ├─ Query Knowledge Base for compliance examples
   ├─ Query Knowledge Base for macro examples
   └─ Format examples for prompt injection

5. Prompt Construction
   ├─ Add system message
   ├─ Add assessment rules
   ├─ Inject KB examples
   ├─ Add checklist (25 checks)
   └─ Add transcript chunk

6. LLM Processing
   ├─ Call Bedrock Claude
   ├─ Parse JSON response
   └─ Validate against schema

7. Result Merging (if multiple chunks)
   ├─ Apply conservative merging strategy
   ├─ Fail > Competent > CompetentWithDevelopment
   └─ Combine evidence quotes

8. Post-Processing
   ├─ Normalize confidence scores
   ├─ Calculate pass rate
   ├─ Identify high-severity failures
   └─ Add metadata

9. Storage
   ├─ Save to S3
   └─ Return results to Step Functions

10. Output
    ├─ caseData: Full assessment
    ├─ caseKey: S3 location
    └─ passRate: Overall score
```

---

## Chunking Strategy

### Why Chunking?

Long transcripts (>100K tokens) may exceed Claude's context window or lead to incomplete assessments. Chunking ensures thorough review.

### Chunking Parameters

```python
CHUNK_SIZE = 20000  # ~5000 tokens per chunk
CHUNK_OVERLAP = 2000  # Ensures no missed content at boundaries
```

### Sentence-Aware Splitting

- Chunks break at sentence boundaries (not mid-sentence)
- Looks for `.!?` followed by whitespace
- Ensures compliance items aren't split across chunks

### Example:

```
Original: 65,000 character transcript
Result: 4 chunks
- Chunk 1: chars 0-20,000 (breaks at sentence)
- Chunk 2: chars 18,000-38,000 (2000 char overlap)
- Chunk 3: chars 36,000-56,000
- Chunk 4: chars 54,000-65,000
```

---

## Result Merging

### Conservative Compliance Strategy

When merging results from multiple chunks:

**Priority Order:**
1. **Fail** (highest priority - catches violations)
2. **Competent** (evidence found)
3. **CompetentWithDevelopment** (marginal evidence)
4. **Inconclusive** (no clear evidence)
5. **NotApplicable** (lowest priority)

**Rationale**: If ANY chunk shows a compliance violation, the merged result must show Fail. This prevents missing critical issues that only appear in one part of the call.

### Example Merge:

```
Check: regulated_advice_given

Chunk 1: Competent (no steering)
Chunk 2: Competent (no steering)
Chunk 3: Fail (steering detected: "the best route...")
Chunk 4: Competent (no steering)

Merged Result: Fail
Reason: Conservative approach - steering in ANY part of call is a violation
```

### Evidence Combining

```python
# Combine evidence quotes from all chunks
all_quotes = [
    "Chunk 1: Coach discussed options without steering",
    "Chunk 3: Coach said 'the best route would be to max out your ISA'"
]

merged_quote = " | ".join(all_quotes)[:500]  # Limit to 500 chars
```

---

## Output Format

### JSON Schema

```json
{
  "check_schema_version": "1.0",
  "session_type": "starter_session",
  "checklist_version": "1",
  "meeting_id": "meeting-123",
  "model_version": "claude-3-5-sonnet-20241022",
  "prompt_version": "2025-09-25-a",
  "results": [
    {
      "id": "call_recording_confirmed",
      "status": "Competent",
      "confidence": 0.95,
      "evidence_spans": [[0, 150]],
      "evidence_quote": "This call is being recorded for training and compliance purposes",
      "comment": "Coach clearly stated recording and purpose at start of call"
    }
  ],
  "overall": {
    "pass_rate": 0.88,
    "failed_ids": ["regulated_advice_given"],
    "high_severity_flags": ["regulated_advice_given"],
    "has_high_severity_failures": true
  }
}
```

### Key Fields

**Per-Check Results:**
- `id`: Check identifier
- `status`: Competent | CompetentWithDevelopment | Fail | NotApplicable | Inconclusive
- `confidence`: 0.0 to 1.0 (confidence in assessment)
- `evidence_spans`: Character positions in transcript (optional)
- `evidence_quote`: Actual transcript excerpt (max 500 chars)
- `comment`: Explanation of assessment (required)

**Overall Summary:**
- `pass_rate`: (Competent + CompetentWithDevelopment) / Total Checks
- `failed_ids`: List of check IDs with Fail status
- `high_severity_flags`: List of high-severity check IDs with Fail status
- `has_high_severity_failures`: Boolean flag for critical issues

---

## Usage Examples

### Example 1: Competent Assessment

```
Transcript: "Coach: This call is being recorded for training and compliance
purposes, is that okay with you? Client: Yes, that's fine."

Assessment:
{
  "id": "call_recording_confirmed",
  "status": "Competent",
  "confidence": 0.95,
  "evidence_quote": "This call is being recorded for training and compliance purposes, is that okay with you?",
  "comment": "Coach clearly informed client of recording and its purpose at the start of the call, and obtained confirmation"
}
```

### Example 2: CompetentWithDevelopment

```
Transcript: "Coach: Just to let you know, we're recording. Client: Okay."

Assessment:
{
  "id": "call_recording_confirmed",
  "status": "CompetentWithDevelopment",
  "confidence": 0.75,
  "evidence_quote": "Just to let you know, we're recording",
  "comment": "Coach mentioned recording but did not explain the purpose (training and compliance) which is required for full compliance"
}
```

### Example 3: Fail (Steering Detected)

```
Transcript: "Coach: I think the best route for you would be to max out your ISA
contributions and then look at a pension."

Assessment:
{
  "id": "regulated_advice_given",
  "status": "Fail",
  "confidence": 0.98,
  "evidence_quote": "I think the best route for you would be to max out your ISA contributions and then look at a pension",
  "comment": "Steering language detected. Coach used 'the best route' which is directive and could constitute regulated advice. Coach should present options without steering toward specific products or actions"
}
```

### Example 4: NotApplicable

```
Transcript: Client is 32 years old, no discussion of pension withdrawals.

Assessment:
{
  "id": "pension_withdrawal_if_over_50",
  "status": "NotApplicable",
  "confidence": 1.0,
  "evidence_quote": "",
  "comment": "Client is under 50, so pension withdrawal check does not apply to this session"
}
```

---

## Quality Guidelines

### For Developers

1. **Always test with real transcripts**: Edge cases appear in production
2. **Monitor pass rates**: Should stabilize around 80-90% for good coaching
3. **Review high-severity failures**: These require immediate attention
4. **Track consistency**: Similar calls should get similar assessments
5. **Update examples**: Add new PDFs to KB as quality standards evolve

### For Quality Reviewers

1. **Read the evidence quote**: Does it support the status?
2. **Check the comment**: Does it explain the reasoning?
3. **Verify confidence**: Low confidence may indicate ambiguity
4. **Review Fails carefully**: Are they genuine violations or false positives?
5. **Look for patterns**: Systemic issues show up across multiple calls

---

## Troubleshooting

### Low Pass Rates (<70%)

**Possible Causes:**
- Overly strict assessment criteria
- Poor transcript quality
- Actual coaching quality issues
- KB examples too stringent

**Solutions:**
- Review failed assessments manually
- Adjust prompt if criteria too strict
- Improve transcript quality (better audio)
- Add more nuanced examples to KB

### Inconsistent Assessments

**Possible Causes:**
- No KB integration (no learning from examples)
- Ambiguous check descriptions
- Low-quality transcript
- Multiple interpreters of same check

**Solutions:**
- Enable KB integration
- Clarify check descriptions in prompt
- Review and update KB examples
- Use category-based retrieval

### High-Severity False Positives

**Possible Causes:**
- Steering detection too sensitive
- Context not considered
- Example-driven confusion

**Solutions:**
- Review evidence quotes carefully
- Add counter-examples to KB (good examples of similar phrasing)
- Adjust steering detection prompt
- Include safe language examples

---

## Future Enhancements

### Planned Improvements

1. **Adaptive Confidence Thresholds**: Auto-flag low-confidence assessments for human review
2. **Check Dependencies**: Some checks logically depend on others
3. **Temporal Analysis**: Track check performance over time
4. **A/B Testing**: Test different assessment strategies
5. **Feedback Loop**: Learn from human corrections

### Research Areas

1. **Multi-model Consensus**: Use multiple LLMs for critical checks
2. **Explainable AI**: Better transparency in decision-making
3. **Active Learning**: Auto-select transcripts for human labeling
4. **Personalized Coaching**: Assess against coach's historical baseline

---

## Appendix

### Check ID Reference

| Check ID | Category | Severity | Required |
|----------|----------|----------|----------|
| call_recording_confirmed | Compliance | High | Yes |
| regulated_advice_given | Compliance | High | Yes |
| vulnerability_identified | Compliance | High | Yes |
| dob_confirmed | Compliance | Medium | Yes |
| client_name_confirmed | Compliance | Medium | Yes |
| marital_status_confirmed | Compliance | Medium | Yes |
| citizenship_confirmed | Compliance | Medium | Yes |
| dependents_confirmed | Compliance | Medium | Yes |
| pension_details_confirmed | Compliance | Medium | Yes |
| income_expenditure_confirmed | Compliance | Medium | Yes |
| assets_liabilities_confirmed | Compliance | Medium | Yes |
| emergency_fund_confirmed | Compliance | Medium | Yes |
| will_confirmed | Compliance | Low | Yes |
| pension_withdrawal_if_over_50 | Compliance | Medium | No |
| high_interest_debt_addressed | Compliance | High | No |
| fees_charges_explained | Compliance | High | Yes |
| way_forward_agreed | Compliance | Medium | Yes |
| coach_introduction_signposting | Macro | Medium | Yes |
| client_goals_established | Macro | High | Yes |
| current_actions_established | Macro | Medium | Yes |
| client_motivations_established | Macro | Medium | Yes |
| relevant_suggestions_provided | Macro | High | Yes |
| money_calculators_introduced | Macro | Medium | Yes |
| asked_client_move_forward | Macro | High | Yes |
| client_questions_opportunity | Macro | Medium | Yes |

### Severity Impact

**High Severity Failures:**
- Trigger escalation workflows
- Require immediate review
- May block coach from future calls
- Impact compliance reporting

**Medium/Low Severity Failures:**
- Inform coaching development
- Tracked for trends
- Not blocking but monitored

---

**Document Version**: 1.0
**Last Updated**: 2025-10-22
**Maintained By**: Engineering & Quality Teams
