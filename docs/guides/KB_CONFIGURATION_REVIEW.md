# Knowledge Base Configuration Review

## Current Configuration Status

### ✅ Code Implementation
- **KB Retrieval Module**: Fully implemented in `summariser/case_check/kb_retrieval.py`
- **Integration Points**: Properly integrated into `summariser/case_check/app.py`
- **Error Handling**: Graceful degradation if KB unavailable
- **Logging**: Comprehensive logging for monitoring

### ⚠️ Infrastructure Configuration
- **KB ID**: Not yet configured (needs to be set after KB creation)
- **IAM Permissions**: Need to be added to Lambda execution role
- **Environment Variables**: Need to be added to template.yaml

---

## Required Configuration Changes

### 1. SAM Template Updates

**File**: `template.yaml`

**Current Case Check Lambda Configuration** (starting ~line 500):
```yaml
CaseCheckFunction:
  Type: AWS::Serverless::Function
  Properties:
    CodeUri: summariser/
    Runtime: python3.11
    Layers:
      - !Ref SharedDependenciesLayer
    Handler: case_check.app.lambda_handler
    Timeout: 300
    MemorySize: 1024
    Policies:
      - S3CrudPolicy:
          BucketName: !Ref SummaryBucket
      - Statement:
          - Effect: Allow
            Action:
              - bedrock:InvokeModel
            Resource:
              - arn:aws:bedrock:eu-west-2::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0
```

**Recommended Changes**:

Add these environment variables to the Globals section:
```yaml
Globals:
  Function:
    Environment:
      Variables:
        # ... existing variables ...

        # Knowledge Base Configuration (add these)
        KNOWLEDGE_BASE_ID: ""  # Set after KB creation
        USE_KNOWLEDGE_BASE: "true"
```

**OR** add environment variables specifically to CaseCheckFunction:
```yaml
CaseCheckFunction:
  Type: AWS::Serverless::Function
  Properties:
    # ... existing properties ...
    Environment:
      Variables:
        KNOWLEDGE_BASE_ID: ""  # Will be set via parameter or manual update
        USE_KNOWLEDGE_BASE: "true"
```

Add IAM permissions for KB access:
```yaml
Policies:
  - S3CrudPolicy:
      BucketName: !Ref SummaryBucket
  - Statement:
      - Effect: Allow
        Action:
          - bedrock:InvokeModel
        Resource:
          - arn:aws:bedrock:eu-west-2::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0
      # NEW: Add KB retrieval permissions
      - Effect: Allow
        Action:
          - bedrock:Retrieve
          - bedrock:RetrieveAndGenerate
        Resource:
          - !Sub "arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:knowledge-base/*"
      # NEW: Add embedding model access for KB
      - Effect: Allow
        Action:
          - bedrock:InvokeModel
        Resource:
          - !Sub "arn:aws:bedrock:${AWS::Region}::foundation-model/amazon.titan-embed-text-v2:0"
```

---

### 2. Knowledge Base Creation (AWS Console Steps)

#### Prerequisites
- 5 PDF documents ready (Pass-case-check1.pdf, Pass-case-check2.pdf, Fail-case-check.pdf, Fail-case-check2.pdf, Fail-case-check3.pdf)
- S3 bucket created for KB source data
- AWS account with Bedrock access enabled

#### Step-by-Step Setup

**Step 1: Create S3 Bucket for KB Source**

```bash
# Set variables
KB_BUCKET_NAME="call-summariser-kb-examples-${AWS_ACCOUNT_ID}"
AWS_REGION="eu-west-2"  # Or your preferred region

# Create bucket
aws s3 mb s3://${KB_BUCKET_NAME} --region ${AWS_REGION}

# Upload PDFs
aws s3 cp Pass-case-check1.pdf s3://${KB_BUCKET_NAME}/examples/
aws s3 cp Pass-case-check2.pdf s3://${KB_BUCKET_NAME}/examples/
aws s3 cp Fail-case-check.pdf s3://${KB_BUCKET_NAME}/examples/
aws s3 cp Fail-case-check2.pdf s3://${KB_BUCKET_NAME}/examples/
aws s3 cp Fail-case-check3.pdf s3://${KB_BUCKET_NAME}/examples/

# Verify
aws s3 ls s3://${KB_BUCKET_NAME}/examples/
```

**Step 2: Create Knowledge Base (AWS Console)**

1. Navigate to Amazon Bedrock Console
   - URL: https://console.aws.amazon.com/bedrock
   - Select region: eu-west-2 (or your preferred region)

2. Create Knowledge Base
   - Left menu: "Knowledge bases"
   - Click: "Create knowledge base"

3. Configure Basic Settings
   - **Name**: `call-summariser-case-check-kb`
   - **Description**: "Assessment examples for case check quality improvement - retrieves Pass and Fail examples"
   - **IAM Role**:
     - Select "Create and use a new service role"
     - Role name: `AmazonBedrockExecutionRoleForKB_case_check`

4. Configure Data Source
   - **Data source name**: `case-check-examples`
   - **S3 URI**: `s3://call-summariser-kb-examples-<account-id>/examples/`
   - **Chunking strategy**:
     - Strategy: "Default chunking"
     - Max tokens: 300
     - Overlap percentage: 20%
   - Click "Next"

5. Select Embeddings Model
   - **Model**: Amazon Titan Embeddings G1 - Text v2.0
   - **Model ARN**: `arn:aws:bedrock:eu-west-2::foundation-model/amazon.titan-embed-text-v2:0`
   - **Dimensions**: 1024 (default)
   - Click "Next"

6. Configure Vector Store
   - **Option**: "Quick create a new vector store"
   - **Collection name**: `case-check-kb-collection`
   - **Note**: This creates an OpenSearch Serverless collection (~$175/month)
   - Alternative: Use existing OpenSearch if available
   - Click "Next"

7. Review and Create
   - Review all settings
   - Click "Create knowledge base"
   - **IMPORTANT**: Copy the Knowledge Base ID (format: `XXXXXXXXXX`)

8. Sync Data Source
   - After creation, navigate to the KB
   - Go to "Data sources" tab
   - Select `case-check-examples`
   - Click "Sync"
   - Wait for sync to complete (~5-10 minutes for 5 PDFs)
   - Status should show "Available" when done

**Step 3: Test Knowledge Base**

Test in Console:
1. Go to your KB in Bedrock Console
2. Click "Test" tab
3. Try queries:
   - "Show me examples of call recording confirmation"
   - "Examples showing Fail due to steering"
   - "How to assess fees explanation"
4. Verify you get relevant results with good scores (>0.7)

Test via Bedrock Console:
1. Go to Amazon Bedrock → Knowledge bases → Select your KB
2. Click "Test" tab
3. Enter query: "show call recording examples"
4. Verify results are returned with relevance score >0.7

---

### 3. Update Lambda Configuration

**Option A: Update via AWS Console**

1. Go to Lambda Console
2. Find function: `call-summariser-<stack>-CaseCheckFunction-XXXXX`
3. Configuration → Environment variables → Edit
4. Add:
   - Key: `KNOWLEDGE_BASE_ID`, Value: `<your-kb-id-from-step-2>`
   - Key: `USE_KNOWLEDGE_BASE`, Value: `true`
5. Save

**Option B: Update via AWS CLI**

```bash
# Get function name
FUNCTION_NAME=$(aws lambda list-functions \
  --query "Functions[?starts_with(FunctionName, 'call-summariser') && contains(FunctionName, 'CaseCheckFunction')].FunctionName" \
  --output text)

echo "Function name: ${FUNCTION_NAME}"

# Get KB ID
KB_ID="<your-kb-id-from-step-2>"

# Update environment variables
aws lambda update-function-configuration \
  --function-name ${FUNCTION_NAME} \
  --environment "Variables={KNOWLEDGE_BASE_ID=${KB_ID},USE_KNOWLEDGE_BASE=true}"

# Verify
aws lambda get-function-configuration \
  --function-name ${FUNCTION_NAME} \
  --query 'Environment.Variables'
```

**Option C: Update template.yaml and Redeploy**

1. Edit `template.yaml`
2. Add to CaseCheckFunction Environment Variables:
   ```yaml
   KNOWLEDGE_BASE_ID: "<your-kb-id>"
   USE_KNOWLEDGE_BASE: "true"
   ```
3. Deploy:
   ```bash
   sam build
   sam deploy --guided
   ```

---

### 4. IAM Permissions Verification

**Check Current Permissions**:
```bash
# Get Lambda role
ROLE_NAME=$(aws lambda get-function \
  --function-name ${FUNCTION_NAME} \
  --query 'Configuration.Role' \
  --output text | awk -F'/' '{print $NF}')

echo "Role name: ${ROLE_NAME}"

# List attached policies
aws iam list-attached-role-policies --role-name ${ROLE_NAME}
aws iam list-role-policies --role-name ${ROLE_NAME}
```

**Add KB Permissions (if not already added via template)**:

Create policy document:
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
      "Resource": [
        "arn:aws:bedrock:eu-west-2:<account-id>:knowledge-base/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:eu-west-2::foundation-model/amazon.titan-embed-text-v2:0"
      ]
    }
  ]
}
```

Apply policy:
```bash
# Create inline policy
aws iam put-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-name BedrockKnowledgeBaseAccess \
  --policy-document file://kb-policy.json
```

---

## Configuration Checklist

### Before Deployment
- [ ] 5 PDF documents prepared and reviewed
- [ ] AWS account has Bedrock access enabled in target region
- [ ] Decided on region (eu-west-2 recommended)
- [ ] Decided on OpenSearch pricing model (Serverless vs Provisioned)

### KB Setup (One-Time)
- [ ] S3 bucket created for KB source
- [ ] PDFs uploaded to S3
- [ ] Bedrock Knowledge Base created
- [ ] Data source configured and synced
- [ ] KB ID copied and saved
- [ ] KB tested in console (queries return relevant results)

### Lambda Configuration
- [ ] `template.yaml` updated with environment variables
- [ ] IAM permissions added to Lambda role
- [ ] Lambda environment variables set (KNOWLEDGE_BASE_ID, USE_KNOWLEDGE_BASE)
- [ ] Code deployed with kb_retrieval.py module

### Testing
- [ ] Manual KB test script executed successfully
- [ ] Sample case check run with KB enabled
- [ ] CloudWatch logs show KB_RETRIEVAL_SUCCESS
- [ ] Assessment quality reviewed and improved

### Monitoring
- [ ] CloudWatch log insights queries created
- [ ] KB retrieval success rate tracked
- [ ] Pass rate stability monitored
- [ ] Cost monitoring dashboard configured

---

## Cost Analysis

### One-Time Costs
| Item | Cost |
|------|------|
| KB Ingestion (5 PDFs, ~50 pages) | ~$0.01 |
| **Total One-Time** | **~$0.01** |

### Monthly Ongoing Costs (1000 case checks/month)
| Item | Unit Cost | Monthly Cost |
|------|-----------|--------------|
| OpenSearch Serverless (2 OCUs) | $0.24/hour/OCU | ~$350 |
| KB Retrieval (2 queries per call) | $0.00004/query | ~$0.08 |
| Claude Inference (unchanged) | ~$0.015/call | ~$15 |
| **Total Monthly** | | **~$365** |

### Cost Optimization Options

1. **Share OpenSearch Collection**
   - Use same collection for multiple KB use cases
   - Amortize $350 cost across multiple applications

2. **OpenSearch Provisioned (if high volume)**
   - Switch to provisioned OpenSearch for predictable costs
   - ~$200/month for small cluster

3. **Reduce Retrieval Calls**
   - Cache examples in Lambda /tmp (15 min TTL)
   - Reduce from 2 queries to 1 by combining compliance+macro

4. **Alternative: Use S3 + In-Memory Examples**
   - Store examples in S3, load at Lambda startup
   - No OpenSearch cost
   - Trade-off: Less sophisticated retrieval, no semantic search

---

## Monitoring Setup

### CloudWatch Log Insights Queries

**Query 1: KB Retrieval Success Rate**
```
fields @timestamp, message, meetingId, kb_id, numResults
| filter message = "KB_RETRIEVAL_SUCCESS" or message = "KB_RETRIEVAL_FAILED" or message = "KB_RETRIEVAL_ERROR"
| stats count() by message
```

**Query 2: KB Performance**
```
fields @timestamp, meetingId, examples_length
| filter message = "KB_RETRIEVAL_COMPLETE"
| stats avg(examples_length), min(examples_length), max(examples_length)
```

**Query 3: KB Disabled Cases**
```
fields @timestamp, meetingId, use_kb, kb_enabled, has_kb_id
| filter message = "KB_DISABLED"
| display @timestamp, meetingId, use_kb, kb_enabled, has_kb_id
```

### CloudWatch Alarms

**Alarm 1: High KB Failure Rate**
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "KB-Retrieval-High-Failure-Rate" \
  --metric-name KB_RETRIEVAL_FAILED \
  --namespace CallSummariser \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold
```

**Alarm 2: OpenSearch Health**
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "OpenSearch-Unhealthy" \
  --metric-name ClusterStatus.red \
  --namespace AWS/ES \
  --statistic Maximum \
  --period 60 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold
```

---

## Troubleshooting Guide

### Issue: "Module 'case_check.kb_retrieval' not found"

**Cause**: Module not included in Lambda deployment package

**Solution**:
1. Verify `summariser/case_check/kb_retrieval.py` exists
2. Rebuild and redeploy:
   ```bash
   sam build
   sam deploy
   ```
3. Check Lambda code includes file:
   ```bash
   aws lambda get-function --function-name ${FUNCTION_NAME} \
     --query 'Code.Location' --output text | xargs curl -s | tar tz | grep kb_retrieval
   ```

### Issue: "Knowledge Base not found"

**Cause**: KB ID not set or incorrect

**Solution**:
1. Verify KB exists:
   ```bash
   aws bedrock-agent get-knowledge-base --knowledge-base-id <kb-id>
   ```
2. Check Lambda environment variable:
   ```bash
   aws lambda get-function-configuration \
     --function-name ${FUNCTION_NAME} \
     --query 'Environment.Variables.KNOWLEDGE_BASE_ID'
   ```
3. Update if needed (see Configuration section)

### Issue: "Access Denied" when retrieving

**Cause**: Lambda lacks IAM permissions

**Solution**:
1. Check role permissions (see IAM section above)
2. Add missing permissions:
   - `bedrock:Retrieve`
   - `bedrock:RetrieveAndGenerate`
3. Verify resource ARN matches your KB region

### Issue: "No relevant examples found"

**Cause**: KB not synced or PDFs not properly indexed

**Solution**:
1. Check sync status in Bedrock console
2. Re-sync data source if needed
3. Test queries in console first
4. Verify PDFs are text-based (not scanned images)
5. Try broader queries

### Issue: "KB retrieval slow (>2 seconds)"

**Cause**: OpenSearch cold start or network latency

**Solution**:
1. Check OpenSearch collection status
2. Increase OCUs if needed (scale up)
3. Consider caching examples in Lambda
4. Monitor KB retrieval latency:
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AWS/Bedrock \
     --metric-name Duration \
     --dimensions Name=KnowledgeBaseId,Value=<kb-id>
   ```

---

## Rollback Plan

If KB integration causes issues:

### Option 1: Disable KB (Keep Code)
```bash
# Disable via environment variable
aws lambda update-function-configuration \
  --function-name ${FUNCTION_NAME} \
  --environment "Variables={USE_KNOWLEDGE_BASE=false}"
```

### Option 2: Rollback Deployment
```bash
# List previous versions
aws lambda list-versions-by-function --function-name ${FUNCTION_NAME}

# Rollback to previous version
aws lambda update-function-configuration \
  --function-name ${FUNCTION_NAME} \
  --environment "Variables={USE_KNOWLEDGE_BASE=false}"
```

### Option 3: Remove KB Module
1. Remove `kb_retrieval.py`
2. Remove KB integration from `app.py`
3. Redeploy

System will gracefully continue without KB - assessments will still work, just without example-guided quality.

---

## Next Steps After Configuration

1. **Run Baseline Test**
   - Process 10 sample calls without KB
   - Record pass rates and quality scores

2. **Enable KB and Retest**
   - Process same 10 calls with KB enabled
   - Compare quality improvements

3. **Monitor for 1 Week**
   - Track consistency improvements
   - Monitor costs
   - Collect feedback from reviewers

4. **Iterate on Examples**
   - Add more PDFs if needed
   - Re-sync KB
   - Test quality improvements

5. **Scale Gradually**
   - Start with dev/test environment
   - Roll out to production gradually
   - Monitor at scale

---

## Support & Resources

- **Setup Guide**: [KNOWLEDGE_BASE_SETUP.md](KNOWLEDGE_BASE_SETUP.md)
- **Case Check Logic**: [CASE_CHECK_LOGIC.md](../technical/CASE_CHECK_LOGIC.md)
- **AWS Bedrock KB Docs**: https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html

---

## Document Metadata

**Version**: 1.0
**Last Updated**: 2025-10-22
**Reviewed By**: Engineering Team
**Next Review**: After first production deployment
