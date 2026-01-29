# Golden Data Collection Workflow

## Problem with Current Approach

**Issue:** Manually copy-pasting from Aveni case checks → prone to errors, inconsistent severity ratings

**Example error found:**
- "I'm dyslexic but it doesn't impact me" → Rated High/4 (should be Low/2)

## Proposed Better Workflow

### Option 1: Structured Annotation Tool (Recommended)

Create a simple web form for coaches to annotate:

```
Meeting ID: _______
Transcript snippet: [auto-loaded from S3]

Question 1: What vulnerabilities are present?
☐ Health: Chronic Illness
☐ Health: Mental Health
☐ Capability: Learning Difficulties
☐ Capability: Neurodivergence
☐ Life Events: Bereavement
☐ Resilience: Financial Crisis
☐ Other: _______

Question 2: Severity rating
Guide:
- High/4: Client says "can't" do essential activity (can't work, can't focus, can't remember)
- Medium/3: Manages but with difficulty
- Low/2: Minimal/no impact (client says "doesn't affect me")

Rating: ○ Critical/5  ○ High/4  ○ Medium/3  ○ Low/2  ○ Marginal/1

Question 3: Evidence quote
[text box - auto-suggest from transcript]

Question 4: Why this rating?
[text box - force 1 sentence explanation]
```

**Benefits:**
- Consistent severity definitions shown
- Auto-suggests evidence from transcript
- Requires explicit justification
- Exports clean CSV

### Option 2: Enhanced Google Sheets Template

Add helper columns with IF formulas:

| Column | Formula/Guide |
|--------|---------------|
| evidence_quote | Manual paste |
| contains_cant | `=IF(ISNUMBER(SEARCH("can't",evidence_quote)),"⚠️ REVIEW","")` |
| contains_manage | `=IF(ISNUMBER(SEARCH("manage",evidence_quote)),"Medium?","")` |
| contains_no_impact | `=IF(ISNUMBER(SEARCH("doesn't affect",evidence_quote)),"Low?","")` |
| suggested_severity | Auto-suggest based on keywords |
| vulnerability_rating | Manual override |
| justification | REQUIRED: Why this rating? |

**Benefits:**
- Low-tech, uses existing Google Sheets
- Auto-flags potential mismatches
- Forces justification

### Option 3: Two-Stage Annotation

**Stage 1: Quick Triage (5 min/call)**
Coaches do quick binary:
- Vulnerable (High/4+)? YES/NO
- If YES → flag for detailed review

**Stage 2: Detailed Annotation (Only flagged cases)**
Senior reviewer provides:
- Exact severity
- Evidence quote
- Justification

**Benefits:**
- Most calls are Low/Medium (quick to triage)
- Focus annotation effort on High/Critical cases
- Quality check by senior reviewer

## Recommended: Hybrid Approach

1. **Automated pre-labeling:**
   - Run model on all 46 calls
   - Model outputs severity + confidence

2. **Coach review interface:**
   ```
   Meeting: 92125626617
   Model prediction: High/4 (confidence: 0.87)
   Evidence: "I have fibromyalgia and can't get out of bed"

   ✓ Agree  ✗ Disagree (provide correct rating + reason)
   ```

3. **Focus on disagreements:**
   - Only review model predictions < 0.80 confidence
   - Only review where model says Medium/3 but keywords suggest High/4

4. **Export clean dataset:**
   - Include model prediction + human label
   - Track agreement rate
   - Use for evaluation

## Implementation Quick Start

### Minimal Version (1 hour setup)

Google Sheets with validation:

```
Column A: meeting_id (validated: numeric)
Column B: evidence_quote (required)
Column C: contains_cant (formula: =ISNUMBER(SEARCH("can't",B2)))
Column D: suggested_severity (formula below)
Column E: vulnerability_rating (dropdown: High/4, Medium/3, Low/2)
Column F: justification (required if D≠E)
```

**Suggested severity formula:**
```excel
=IF(C2,"High/4 - contains 'can't'",
 IF(ISNUMBER(SEARCH("doesn't affect",B2)),"Low/2 - no impact",
 IF(ISNUMBER(SEARCH("manage",B2)),"Medium/3 - managing",
 "REVIEW")))
```

### Script to Check Quality

```python
# scripts/validate_golden_data.py
import pandas as pd

df = pd.read_csv('evals/golden_data/vulnerability_ground_truth.csv')

# Flag potential issues
issues = []

for idx, row in df.iterrows():
    evidence = str(row['evidence_quote']).lower()
    severity = row['vulnerability_rating']

    # Check: "doesn't affect" + High severity
    if ("doesn't affect" in evidence or "doesn't impact" in evidence) and severity == "High/4":
        issues.append({
            'line': idx + 2,
            'meeting_id': row['meeting_id'],
            'issue': 'Says "no impact" but rated High/4',
            'evidence': evidence[:100]
        })

    # Check: "can't" + Low/Medium severity
    if ("can't" in evidence or "cannot" in evidence) and severity in ["Low/2", "Medium/3"]:
        issues.append({
            'line': idx + 2,
            'meeting_id': row['meeting_id'],
            'issue': 'Contains "can\'t" but rated Low/Medium',
            'evidence': evidence[:100]
        })

# Print issues
for issue in issues:
    print(f"Line {issue['line']}: {issue['issue']}")
    print(f"  Meeting: {issue['meeting_id']}")
    print(f"  Evidence: {issue['evidence']}...")
    print()

print(f"Found {len(issues)} potential annotation issues")
```

Run this before each evaluation!

## Next Steps

1. **Immediate:** Run validation script on current golden data
2. **This week:** Fix the ~5-10 annotation errors found
3. **Next sprint:** Build simple annotation UI or enhanced Sheets template
4. **Ongoing:** Validate each new batch of golden data before using for eval

**Which option do you prefer? I can build the validation script right now.**
