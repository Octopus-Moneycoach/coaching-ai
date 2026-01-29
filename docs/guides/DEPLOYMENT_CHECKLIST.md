# Deployment Checklist - RAG Knowledge Base Integration

Use this checklist to deploy the RAG Knowledge Base integration for case checking.

---

## Pre-Deployment

### ✅ Code Review
- [x] All code changes committed
- [x] `kb_retrieval.py` created
- [x] `app.py` updated with KB integration
- [x] `prompts.py` updated with new status types
- [x] Documentation created

### ✅ Prerequisites
- [ ] AWS CLI installed and configured
- [ ] Appropriate AWS permissions (Bedrock, S3, Lambda, IAM)
- [ ] 5 PDF example reports ready (2 good, 3 bad)
- [ ] Serverless Framework installed (if using)

---

## Phase 1: S3 Setup (5 minutes)

### Step 1.1: Create S3 Bucket
```bash
AWS_REGION="us-east-1"
BUCKET_NAME="call-summariser-kb-examples"

aws s3 mb s3://${BUCKET_NAME} --region ${AWS_REGION}
```
- [ ] Bucket created successfully
- [ ] Bucket name noted: `___________________`

### Step 1.2: Upload PDF Examples
```bash
# Upload your 5 PDFs
aws s3 cp /path/to/good_example_1.pdf s3://${BUCKET_NAME}/examples/
aws s3 cp /path/to/good_example_2.pdf s3://${BUCKET_NAME}/examples/
aws s3 cp /path/to/bad_example_1.pdf s3://${BUCKET_NAME}/examples/
aws s3 cp /path/to/bad_example_2.pdf s3://${BUCKET_NAME}/examples/
aws s3 cp /path/to/bad_example_3.pdf s3://${BUCKET_NAME}/examples/

# Verify
aws s3 ls s3://${BUCKET_NAME}/examples/
```
- [ ] All 5 PDFs uploaded
- [ ] Files visible in S3 console

### Step 1.3: Set Bucket Policy (Optional but Recommended)
- [ ] Apply bucket policy from [KNOWLEDGE_BASE_SETUP.md](KNOWLEDGE_BASE_SETUP.md) Section 2.3
- [ ] Verify Bedrock service has read access

---

## Phase 2: Bedrock Knowledge Base Setup (15 minutes)

### Step 2.1: Create Knowledge Base
**Via AWS Console:**
1. Go to: https://console.aws.amazon.com/bedrock
2. Click "Knowledge bases" → "Create knowledge base"

- [ ] Opened Bedrock console
- [ ] Started KB creation wizard

### Step 2.2: Configure Basic Settings
- [ ] **Name**: `call-summariser-case-check-kb`
- [ ] **Description**: "Assessment examples for case check quality"
- [ ] **IAM Role**: Auto-create new role
- [ ] Click "Next"

### Step 2.3: Configure Data Source
- [ ] **Data source name**: `assessment-examples`
- [ ] **S3 URI**: `s3://call-summariser-kb-examples/examples/`
- [ ] **Chunking strategy**: Default chunking
- [ ] **Max tokens**: 300
- [ ] **Overlap**: 20%
- [ ] Click "Next"

### Step 2.4: Select Embeddings Model
- [ ] **Model**: Amazon Titan Embeddings G1 - Text v2.0
- [ ] **Dimensions**: 1024 (default)
- [ ] Click "Next"

### Step 2.5: Configure Vector Store
- [ ] **Option**: Quick create a new vector store
- [ ] **Name**: Auto-generated or custom
- [ ] Click "Next"

### Step 2.6: Review and Create
- [ ] Review all settings
- [ ] Click "Create knowledge base"
- [ ] Wait for creation to complete (~2-3 minutes)

### Step 2.7: Sync Data Source
- [ ] Click "Sync" button on data source
- [ ] Wait for sync to complete (~5-10 minutes)
- [ ] Status shows "Available"

### Step 2.8: Note Knowledge Base ID
- [ ] Copy Knowledge Base ID from console
- [ ] Knowledge Base ID: `___________________________`

### Step 2.9: Test Retrieval (Recommended)
Test in console with these queries:
- [ ] "Show examples of call recording confirmation"
- [ ] "Examples of Fail due to steering"
- [ ] "How to assess fees and charges"

Verify you get relevant results from your PDFs.

---

## Phase 3: Lambda Configuration (10 minutes)

### Step 3.1: Set Environment Variables
```bash
LAMBDA_FUNCTION_NAME="call-summariser-dev-case_check"  # Adjust for your stage
KB_ID="<paste-your-kb-id-here>"

aws lambda update-function-configuration \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --environment "Variables={KNOWLEDGE_BASE_ID=${KB_ID},USE_KNOWLEDGE_BASE=true}"
```

- [ ] Environment variables set
- [ ] Verified in Lambda console

### Step 3.2: Update Lambda IAM Role

**Find your Lambda execution role:**
```bash
aws lambda get-function-configuration \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --query 'Role' \
  --output text
```
- [ ] Role ARN noted: `___________________________`

**Add KB permissions:**
1. Go to IAM Console → Roles
2. Find your Lambda role
3. Click "Add permissions" → "Create inline policy"
4. Use JSON editor, paste:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate"
      ],
      "Resource": "arn:aws:bedrock:us-east-1:*:knowledge-base/*"
    },
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
    }
  ]
}
```

5. Name it: `BedrockKnowledgeBaseAccess`

- [ ] Policy created
- [ ] Policy attached to Lambda role

---

## Phase 4: Code Deployment (5 minutes)

### Step 4.1: Deploy Lambda Function

**Option A: Serverless Framework**
```bash
cd /path/to/call-summariser
serverless deploy --stage dev
```

**Option B: Deploy specific function**
```bash
serverless deploy function -f case_check --stage dev
```

**Option C: Manual upload (if needed)**
```bash
# Package code
zip -r function.zip summariser/

# Upload
aws lambda update-function-code \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --zip-file fileb://function.zip
```

- [ ] Deployment successful
- [ ] No errors in deployment output

### Step 4.2: Verify Deployment
```bash
aws lambda get-function-configuration \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --query 'Environment.Variables'
```

- [ ] `KNOWLEDGE_BASE_ID` is set
- [ ] `USE_KNOWLEDGE_BASE` is `true`
- [ ] Code version updated

---

## Phase 5: Testing (10 minutes)

### Step 5.1: Run Test Case Check

**Trigger via Step Functions:**
1. Go to Step Functions console
2. Find your state machine
3. Start execution with test payload:
```json
{
  "meetingId": "test-kb-integration-001",
  "redactedTranscriptKey": "path/to/test/transcript.txt"
}
```

- [ ] Execution started
- [ ] Execution completed successfully

**Or trigger Lambda directly:**
```bash
aws lambda invoke \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --payload '{"meetingId":"test-001","redactedTranscriptKey":"path/to/transcript"}' \
  response.json

cat response.json
```

- [ ] Lambda invoked successfully
- [ ] Response received

### Step 5.2: Check CloudWatch Logs

Go to CloudWatch Logs → Lambda function log group

Look for these log messages:
- [ ] `KB_RETRIEVAL_START` - KB query initiated
- [ ] `KB_RETRIEVAL_COMPLETE` - Examples retrieved successfully
- [ ] `CASE_CHECK_START` - Assessment started
- [ ] No errors or warnings (except expected ones)

**Expected logs:**
```json
{
  "level": "INFO",
  "message": "KB_RETRIEVAL_START",
  "meetingId": "test-001",
  "kb_id": "XXXXXXXXXX"
}

{
  "level": "INFO",
  "message": "KB_RETRIEVAL_COMPLETE",
  "meetingId": "test-001",
  "examples_length": 1250
}
```

- [ ] KB retrieval logs present
- [ ] No errors in KB retrieval

### Step 5.3: Review Assessment Quality

Check the generated assessment JSON:

```bash
# Download from S3
aws s3 cp s3://your-bucket/path/to/case_check.json ./test_result.json

# Review
cat test_result.json | jq .
```

**Quality Checks:**
- [ ] All 25 checks present in results
- [ ] Status values are: Competent/CompetentWithDevelopment/Fail/NotApplicable/Inconclusive
- [ ] Evidence quotes are specific (not empty)
- [ ] Comments explain reasoning
- [ ] Pass rate calculated correctly

### Step 5.4: Compare With/Without KB (Optional)

**Test without KB:**
```bash
aws lambda update-function-configuration \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --environment "Variables={USE_KNOWLEDGE_BASE=false}"

# Run another test
# Compare results
```

- [ ] Tested without KB
- [ ] Compared quality (evidence, comments, consistency)
- [ ] Re-enabled KB: `USE_KNOWLEDGE_BASE=true`

---

## Phase 6: Monitoring Setup (5 minutes)

### Step 6.1: Create CloudWatch Dashboard (Optional)

Create dashboard with these metrics:
- [ ] Lambda invocation count
- [ ] Lambda duration
- [ ] Lambda errors
- [ ] Log insights queries for KB metrics

### Step 6.2: Set Up Alarms (Recommended)

```bash
# Create alarm for KB retrieval errors
aws cloudwatch put-metric-alarm \
  --alarm-name "KB-Retrieval-Errors" \
  --metric-name "KB_RETRIEVAL_ERROR" \
  --namespace "CaseSummariser" \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1
```

- [ ] Error alarm created
- [ ] Notification configured (SNS topic)

### Step 6.3: Document Monitoring

- [ ] CloudWatch log group noted: `___________________________`
- [ ] Dashboard URL (if created): `___________________________`
- [ ] Alarm ARN: `___________________________`

---

## Phase 7: Post-Deployment Validation (Ongoing)

### Week 1: Initial Monitoring
- [ ] Run 10+ test cases
- [ ] Review assessment quality
- [ ] Check KB retrieval success rate (target: >95%)
- [ ] Verify no KB-related errors

### Week 2: Quality Assessment
- [ ] Compare pass rates before/after KB
- [ ] Review consistency of similar cases
- [ ] Collect feedback from users
- [ ] Identify any quality issues

### Month 1: Optimization
- [ ] Analyze which examples are most retrieved
- [ ] Consider adding more examples if gaps found
- [ ] Tune retrieval parameters if needed
- [ ] Review cost vs. quality tradeoff

---

## Rollback Plan (If Issues Occur)

### Quick Rollback: Disable KB
```bash
aws lambda update-function-configuration \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --environment "Variables={USE_KNOWLEDGE_BASE=false}"
```
- [ ] System continues with base prompts
- [ ] No functionality lost

### Full Rollback: Revert Code
```bash
# Rollback to previous version
serverless rollback --stage dev --timestamp <previous-timestamp>
```

---

## Success Criteria

### ✅ Deployment Successful If:
- [x] All 5 phases completed without errors
- [x] KB retrieval logs show successful queries
- [x] Assessments include evidence quotes and comments
- [x] No increase in Lambda errors
- [x] Pass rate is stable or improved

### ⚠️ Issues to Watch:
- [ ] KB retrieval failures (>5%)
- [ ] Increased Lambda duration (>30%)
- [ ] Empty evidence quotes
- [ ] Generic comments
- [ ] Access denied errors

---

## Cost Tracking

### Estimated Monthly Cost (1000 assessments):
- KB Retrieval: ~$0.04
- OpenSearch Serverless: ~$175
- Claude (unchanged): ~$15
- **Total: ~$190/month**

### Monitor Actual Costs:
- [ ] Week 1 cost: $________
- [ ] Week 2 cost: $________
- [ ] Month 1 cost: $________

---

## Support & Documentation

### Documentation:
- [KNOWLEDGE_BASE_SETUP.md](KNOWLEDGE_BASE_SETUP.md) - Full setup guide
- [CASE_CHECK_LOGIC.md](../technical/CASE_CHECK_LOGIC.md) - Assessment logic
- [CASE_CHECK_ARCHITECTURE.md](../technical/CASE_CHECK_ARCHITECTURE.md) - System architecture
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) - This file

### Get Help:
- AWS Bedrock Docs: https://docs.aws.amazon.com/bedrock/
- CloudWatch Logs: `/aws/lambda/${LAMBDA_FUNCTION_NAME}`
- Issue Tracker: (Add your repo link)

---

## Sign-Off

### Deployment Completed By:
- **Name**: ____________________
- **Date**: ____________________
- **Environment**: Dev / Staging / Production (circle one)
- **KB ID**: ____________________
- **Notes**: ____________________

### Validated By:
- **Name**: ____________________
- **Date**: ____________________
- **Validation Results**: Pass / Fail (circle one)

---

**Checklist Version**: 1.0
**Last Updated**: 2025-10-22
