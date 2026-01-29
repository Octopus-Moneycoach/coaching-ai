# Quick Start Guide - Knowledge Base Setup

**5-Minute Setup Overview** | Full details in [KB_CONFIGURATION_REVIEW.md](KB_CONFIGURATION_REVIEW.md)

---

## Prerequisites Checklist

- [ ] 5 PDFs ready: Pass-case-check1.pdf, Pass-case-check2.pdf, Fail-case-check.pdf, Fail-case-check2.pdf, Fail-case-check3.pdf
- [ ] AWS CLI configured
- [ ] Bedrock access enabled in eu-west-2
- [ ] AWS account ID handy

---

## 5-Step Setup

### Step 1: Upload PDFs to S3 (2 minutes)

```bash
# Set variables
KB_BUCKET="call-summariser-kb-examples-${AWS_ACCOUNT_ID}"

# Create bucket and upload
aws s3 mb s3://${KB_BUCKET}
aws s3 cp Pass-case-check1.pdf s3://${KB_BUCKET}/examples/
aws s3 cp Pass-case-check2.pdf s3://${KB_BUCKET}/examples/
aws s3 cp Fail-case-check.pdf s3://${KB_BUCKET}/examples/
aws s3 cp Fail-case-check2.pdf s3://${KB_BUCKET}/examples/
aws s3 cp Fail-case-check3.pdf s3://${KB_BUCKET}/examples/

# Verify
aws s3 ls s3://${KB_BUCKET}/examples/
```

**Expected**: 5 PDFs listed

---

### Step 2: Create Knowledge Base (5 minutes via Console)

1. Go to: https://console.aws.amazon.com/bedrock
2. Click: "Knowledge bases" → "Create knowledge base"
3. Settings:
   - **Name**: `call-summariser-case-check-kb`
   - **S3 URI**: `s3://call-summariser-kb-examples-<account-id>/examples/`
   - **Embeddings**: Amazon Titan Embeddings G1 - Text v2.0
   - **Vector store**: Quick create new
4. Click "Create"
5. **Copy KB ID** (you'll need this!)
6. Click "Sync" → Wait ~5 min

**Expected**: Status shows "Available", 5 documents synced

---

### Step 3: Test KB (1 minute)

Test in Bedrock Console:
1. Go to Knowledge Base → Select your KB → "Test" tab
2. Try query: "show call recording examples"

**Expected**: Relevant results returned with score >0.7

---

### Step 4: Configure Lambda (2 minutes)

```bash
# Get function name
FUNCTION_NAME=$(aws lambda list-functions \
  --query "Functions[?contains(FunctionName, 'CaseCheckFunction')].FunctionName" \
  --output text | head -1)

# Set KB ID (from Step 2)
KB_ID="<your-kb-id>"

# Update Lambda
aws lambda update-function-configuration \
  --function-name ${FUNCTION_NAME} \
  --environment "Variables={KNOWLEDGE_BASE_ID=${KB_ID},USE_KNOWLEDGE_BASE=true}"
```

**Expected**: Command succeeds, returns updated config

---

### Step 5: Add IAM Permissions (2 minutes)

```bash
# Get Lambda role
ROLE_NAME=$(aws lambda get-function \
  --function-name ${FUNCTION_NAME} \
  --query 'Configuration.Role' \
  --output text | awk -F'/' '{print $NF}')

# Create policy file
cat > kb-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
      "Resource": "arn:aws:bedrock:eu-west-2:*:knowledge-base/*"
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:eu-west-2::foundation-model/amazon.titan-embed-text-v2:0"
    }
  ]
}
EOF

# Apply policy
aws iam put-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-name BedrockKnowledgeBaseAccess \
  --policy-document file://kb-policy.json
```

**Expected**: Policy created successfully

---

## Verification

### Check Lambda Configuration

```bash
aws lambda get-function-configuration \
  --function-name ${FUNCTION_NAME} \
  --query 'Environment.Variables' | grep KNOWLEDGE_BASE_ID
```

**Expected**: Shows your KB ID

### Run Test Case Check

Trigger a case check and check CloudWatch logs for:

```
✅ "KB_RETRIEVAL_START" - KB queried
✅ "KB_RETRIEVAL_SUCCESS" - Examples retrieved
✅ "KB_RETRIEVAL_COMPLETE" - Examples formatted
```

**Expected**: All 3 log entries present, no errors

---

## Troubleshooting

### "Access Denied"
→ Rerun Step 5 (IAM permissions)

### "KB not found"
→ Check KB ID in Step 4 matches Step 2

### "No examples retrieved"
→ Ensure KB synced (Step 2, status = "Available")

### Module import error
→ Redeploy code: `sam build && sam deploy`

---

## Cost Estimate

- Setup: ~$0.01 (one-time)
- Monthly: ~$365
  - OpenSearch: ~$350
  - KB queries: ~$0.08
  - Claude: ~$15 (unchanged)

**Optimization**: Share OpenSearch collection across multiple use cases

---

## What's Next?

1. **Baseline Test**: Run 10 calls, note quality
2. **KB Test**: Rerun same 10 calls, compare improvement
3. **Monitor**: Track consistency and pass rates
4. **Iterate**: Add more PDFs if needed

---

## Full Documentation

| Document | Purpose |
|----------|---------|
| [KB_CONFIGURATION_REVIEW.md](KB_CONFIGURATION_REVIEW.md) | Detailed setup guide |
| [KNOWLEDGE_BASE_SETUP.md](KNOWLEDGE_BASE_SETUP.md) | Step-by-step setup |
| [CASE_CHECK_LOGIC.md](../technical/CASE_CHECK_LOGIC.md) | Assessment logic explained |

---

## Support

**Verify KB**: Test in Bedrock Console → Knowledge Base → Test tab

**Disable KB** (if needed):
```bash
aws lambda update-function-configuration \
  --function-name ${FUNCTION_NAME} \
  --environment "Variables={USE_KNOWLEDGE_BASE=false}"
```

---

**Time to Complete**: ~15 minutes
**Difficulty**: Medium
**Production Ready**: Yes ✅
