# Knowledge Base Setup Guide for Case Check RAG

This guide walks you through setting up AWS Bedrock Knowledge Base for retrieving assessment examples to improve case check quality and consistency.

## Architecture Overview

```
┌─────────────────────┐
│  PDF Examples       │
│  (S3 Bucket)        │
│  - good_1.pdf       │
│  - good_2.pdf       │
│  - bad_1.pdf        │
│  - bad_2.pdf        │
│  - bad_3.pdf        │
└──────────┬──────────┘
           │ Ingestion
           ▼
┌──────────────────────────┐
│ Bedrock Knowledge Base   │
│ - Vector embeddings      │
│ - Semantic search        │
└──────────┬───────────────┘
           │ Query at runtime
           ▼
┌──────────────────────────┐
│ Case Check Lambda        │
│ - Retrieves 2-4 examples │
│ - Injects into prompt    │
│ - Generates assessment   │
└──────────────────────────┘
```

---

## Step 1: Prepare Your PDF Examples

### 1.1 Organize Your Examples

You have 5 example assessment reports:
- 2 good examples (showing Competent assessments)
- 3 bad examples (showing Fail assessments)

**Best Practices:**
- Keep PDFs under 10MB each
- Use clear filenames: `good_example_1.pdf`, `bad_example_steering_fail.pdf`
- Ensure PDFs are text-based (not scanned images)

### 1.2 Add Metadata to PDFs (Optional but Recommended)

You can add metadata to help with retrieval:
- **Title**: "Good Starter Session Assessment Example 1"
- **Subject**: "Compliance, Coaching Quality"
- **Keywords**: "Competent, call recording, fees explained, goals established"

---

## Step 2: Create S3 Bucket for Examples

### 2.1 Create the Bucket

```bash
# Set your AWS region
AWS_REGION="eu-west-2"
BUCKET_NAME="call-summariser-kb-examples"

# Create bucket
aws s3 mb s3://${BUCKET_NAME} --region ${AWS_REGION}
```

### 2.2 Upload Your PDFs

```bash
# Upload all example PDFs
aws s3 cp good_example_1.pdf s3://${BUCKET_NAME}/examples/
aws s3 cp good_example_2.pdf s3://${BUCKET_NAME}/examples/
aws s3 cp bad_example_1.pdf s3://${BUCKET_NAME}/examples/
aws s3 cp bad_example_2.pdf s3://${BUCKET_NAME}/examples/
aws s3 cp bad_example_3.pdf s3://${BUCKET_NAME}/examples/

# Verify upload
aws s3 ls s3://${BUCKET_NAME}/examples/
```

### 2.3 Set Bucket Permissions

The Knowledge Base will need read access to this bucket.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBedrockKBRead",
      "Effect": "Allow",
      "Principal": {
        "Service": "bedrock.amazonaws.com"
      },
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::call-summariser-kb-examples",
        "arn:aws:s3:::call-summariser-kb-examples/*"
      ]
    }
  ]
}
```

---

## Step 3: Create Bedrock Knowledge Base

### 3.1 Via AWS Console (Recommended for First Setup)

1. **Navigate to Amazon Bedrock Console**
   - Go to: https://console.aws.amazon.com/bedrock
   - Select your region (eu-west-2)

2. **Create Knowledge Base**
   - Click "Knowledge bases" in left menu
   - Click "Create knowledge base"

3. **Configure Knowledge Base**
   - **Name**: `call-summariser-case-check-kb`
   - **Description**: "Assessment examples for case check quality improvement"
   - **IAM Role**: Create a new service role (auto-created)

4. **Configure Data Source**
   - **Data source name**: `assessment-examples`
   - **S3 URI**: `s3://call-summariser-kb-examples/examples/`
   - **Chunking strategy**:
     - Choose "Default chunking"
     - Max tokens: 300
     - Overlap: 20%

5. **Select Embeddings Model**
   - **Model**: Amazon Titan Embeddings G1 - Text v2.0
   - **Dimensions**: 1024 (default)

6. **Configure Vector Store**
   - Choose "Quick create a new vector store"
   - Or use existing OpenSearch Serverless if you have one

7. **Review and Create**
   - Review all settings
   - Click "Create knowledge base"

8. **Sync Data Source**
   - After creation, click "Sync"
   - Wait for ingestion to complete (~5-10 minutes)

9. **Note the Knowledge Base ID**
   - Copy the Knowledge Base ID (format: `XXXXXXXXXX`)
   - You'll need this for configuration

### 3.2 Via AWS CLI (Advanced)

```bash
# Create Knowledge Base
KB_NAME="call-summariser-case-check-kb"
EMBEDDING_MODEL="arn:aws:bedrock:eu-west-2::foundation-model/amazon.titan-embed-text-v2:0"

# Note: This requires pre-created IAM role and OpenSearch collection
# See AWS documentation for full CLI setup
```

---

## Step 4: Test Knowledge Base

### 4.1 Test Retrieval in Console

1. Go to your Knowledge Base in Bedrock console
2. Click "Test" tab
3. Try queries like:
   - "Show me examples of call recording confirmation"
   - "Examples of Fail due to steering"
   - "How to assess fees and charges explanation"

4. Verify you get relevant results

### 4.2 Test Retrieval Programmatically

```python
import boto3

bedrock_agent = boto3.client("bedrock-agent-runtime", region_name="eu-west-2")

response = bedrock_agent.retrieve(
    knowledgeBaseId="YOUR_KB_ID_HERE",
    retrievalQuery={'text': 'Show examples of competent call recording confirmation'},
    retrievalConfiguration={
        'vectorSearchConfiguration': {
            'numberOfResults': 3
        }
    }
)

for result in response['retrievalResults']:
    print(f"Score: {result['score']}")
    print(f"Content: {result['content']['text'][:200]}...")
    print("-" * 60)
```

---

## Step 5: Configure Lambda Environment Variables

### 5.1 Set Environment Variables

Add these to your Case Check Lambda function:

```bash
KNOWLEDGE_BASE_ID=<your-kb-id>
USE_KNOWLEDGE_BASE=true
```

### 5.2 Via AWS Console

1. Go to Lambda console
2. Select your `case-check` function
3. Go to "Configuration" > "Environment variables"
4. Click "Edit"
5. Add:
   - Key: `KNOWLEDGE_BASE_ID`, Value: `<your-kb-id>`
   - Key: `USE_KNOWLEDGE_BASE`, Value: `true`
6. Save

### 5.3 Via AWS CLI

```bash
LAMBDA_FUNCTION_NAME="call-summariser-dev-case_check"
KB_ID="<your-kb-id>"

aws lambda update-function-configuration \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --environment "Variables={KNOWLEDGE_BASE_ID=${KB_ID},USE_KNOWLEDGE_BASE=true}"
```

---

## Step 6: Update Lambda IAM Permissions

Your Lambda execution role needs permission to query the Knowledge Base.

### 6.1 Required IAM Policy

Add this policy to your Lambda execution role:

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
        "arn:aws:bedrock:eu-west-2:<account-id>:knowledge-base/<kb-id>"
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

### 6.2 Apply Policy via Console

1. Go to IAM Console
2. Find your Lambda execution role (e.g., `call-summariser-dev-case_check-role`)
3. Click "Add permissions" > "Create inline policy"
4. Paste the JSON above (replace `<account-id>` and `<kb-id>`)
5. Name it: `BedrockKnowledgeBaseAccess`
6. Create policy

---

## Step 7: Deploy Updated Code

### 7.1 Deploy Lambda Updates

If using Serverless Framework:

```bash
cd /path/to/call-summariser
serverless deploy --stage dev
```

Or deploy specific function:

```bash
serverless deploy function -f case_check --stage dev
```

### 7.2 Verify Deployment

Check CloudWatch Logs for:
- `KB_ENABLED: true`
- `KB_RETRIEVAL_START` log entries
- No errors in KB retrieval

---

## Step 8: Monitor and Optimize

### 8.1 CloudWatch Metrics to Watch

Monitor these log patterns:
- `KB_RETRIEVAL_SUCCESS` - Successful retrievals
- `KB_RETRIEVAL_FAILED` - Failed retrievals
- `KB_RETRIEVAL_ERROR` - Errors during retrieval

### 8.2 Cost Optimization

**Knowledge Base Costs:**
- Titan Embeddings: ~$0.0001 per 1000 tokens for ingestion
- OpenSearch Serverless: ~$0.24/hour (OCU pricing)
- Retrieval: ~$0.00004 per query

**For 5 PDFs (~50 pages total):**
- One-time ingestion: ~$0.01
- Monthly OpenSearch: ~$175 (if using dedicated collection)
- Per retrieval: ~$0.00004

**Optimization Tips:**
1. Use OpenSearch Serverless (scales to zero)
2. Share KB across multiple use cases
3. Cache frequently retrieved examples in Lambda

### 8.3 Quality Optimization

After running several assessments:

1. **Review Logs**: Check which examples are being retrieved
2. **Refine PDFs**: If certain checks aren't getting good examples, add more targeted PDFs
3. **Adjust Retrieval**: Tune `numberOfResults` (currently 2-4) based on quality
4. **Monitor Pass Rates**: Track if consistency improves

---

## Troubleshooting

### Issue: "Knowledge Base not found"

**Solution**: Verify KB ID is correct in environment variables

```bash
aws bedrock-agent get-knowledge-base --knowledge-base-id <your-kb-id>
```

### Issue: "Access denied when retrieving"

**Solution**: Check Lambda IAM permissions include `bedrock:Retrieve`

### Issue: "No relevant examples found"

**Solution**:
1. Check PDFs are properly synced
2. Test queries in console
3. Try broader queries
4. Consider adding more example PDFs

### Issue: "Retrieval is slow"

**Solution**:
1. Reduce `numberOfResults` to 2
2. Consider caching examples in Lambda /tmp
3. Use hybrid search (already enabled)

---

## Disabling Knowledge Base (Fallback)

If you need to temporarily disable KB:

```bash
aws lambda update-function-configuration \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --environment "Variables={USE_KNOWLEDGE_BASE=false}"
```

The system will continue to work without KB examples (graceful degradation).

---

## Next Steps

After setup:

1. ✅ Run test case check on a sample transcript
2. ✅ Review quality of evidence quotes and comments
3. ✅ Compare consistency before/after KB integration
4. ✅ Add more examples if needed
5. ✅ Monitor CloudWatch for KB performance

---

## Support & Resources

- [AWS Bedrock Knowledge Bases Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Titan Embeddings Model](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html)
- [OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html)

---

**Questions?** Check the CloudWatch logs or open an issue in the repository.
