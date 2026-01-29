# S3 Documentation Access Guide

**S3 Bucket**: `s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/`

---

## 📍 S3 Locations

All documentation is stored in S3 for centralized access:

```
s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/
├── README.md                                     # Documentation hub
│
├── guides/                                       # Setup & configuration guides
│   ├── QUICK_START.md
│   ├── KNOWLEDGE_BASE_SETUP.md
│   ├── KB_CONFIGURATION_REVIEW.md
│   ├── DEPLOYMENT_CHECKLIST.md
│   ├── GOLDEN_DATA_WORKFLOW.md
│   ├── VULNERABILITY_ASSESSMENT_SETUP.md
│   ├── TESTING_VULNERABILITY_FLOW.md
│   └── S3_ACCESS_GUIDE.md
│
└── technical/                                    # Technical reference
    ├── CASE_CHECK_LOGIC.md
    └── CASE_CHECK_ARCHITECTURE.md
```

---

## 🔗 Accessing Documentation

### Option 1: AWS Console (Web Browser)

1. **Navigate to S3**:
   - Go to: https://eu-west-2.console.aws.amazon.com/s3/buckets/call-summariser-summarybucket-3wtnjhb9vvq0?region=eu-west-2
   - Navigate to: `implementation-docs/`

2. **View HTML Index**:
   - Click on `index.html`
   - Click "Open" or "Download" to view

3. **Browse Documentation**:
   - Navigate through folders (guides, technical)
   - Click on any `.md` file to preview or download

### Option 2: AWS CLI

**List all files**:
```bash
aws s3 ls s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ --recursive
```

**Download entire documentation**:
```bash
aws s3 sync s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ ./local-docs/
```

**Download specific file**:
```bash
aws s3 cp s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/guides/QUICK_START.md ./
```

**View file directly** (requires jq):
```bash
aws s3 cp s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/README.md - | cat
```

### Option 3: Pre-signed URLs (Share with others)

Generate a temporary shareable link (valid for 1 hour):

```bash
# For the main index
aws s3 presign s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/index.html --expires-in 3600

# For Quick Start guide
aws s3 presign s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/guides/QUICK_START.md --expires-in 3600
```

Share the generated URL with team members (valid for 1 hour by default).

---

## 🌐 Setting Up Public Access (Optional)

If you want to make documentation publicly accessible:

### Enable Static Website Hosting

```bash
# 1. Configure bucket for static website hosting
aws s3 website s3://call-summariser-summarybucket-3wtnjhb9vvq0 \
  --index-document implementation-docs/index.html

# 2. Add bucket policy for public read access (only for implementation-docs)
cat > bucket-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadImplementationDocs",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/*"
    }
  ]
}
EOF

aws s3api put-bucket-policy \
  --bucket call-summariser-summarybucket-3wtnjhb9vvq0 \
  --policy file://bucket-policy.json

# 3. Update block public access settings
aws s3api put-public-access-block \
  --bucket call-summariser-summarybucket-3wtnjhb9vvq0 \
  --public-access-block-configuration \
    "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
```

**Access URL**: `http://call-summariser-summarybucket-3wtnjhb9vvq0.s3-website-eu-west-2.amazonaws.com/implementation-docs/index.html`

⚠️ **Warning**: Only do this if documentation doesn't contain sensitive information!

---

## 🔒 Private Access with CloudFront (Recommended)

For secure, fast access without making bucket public:

### Create CloudFront Distribution

```bash
# Create CloudFront distribution pointing to S3
aws cloudfront create-distribution \
  --origin-domain-name call-summariser-summarybucket-3wtnjhb9vvq0.s3.amazonaws.com \
  --default-root-object implementation-docs/index.html
```

**Benefits**:
- HTTPS by default
- Fast global access (CDN)
- Private S3 bucket
- Access control via CloudFront

---

## 📤 Updating Documentation

### Upload new/updated files:

```bash
# From local docs folder
cd /path/to/call-summariser/docs

# Sync all changes to S3
aws s3 sync . s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ \
  --exclude "*.pyc" \
  --exclude "__pycache__/*" \
  --exclude ".DS_Store"
```

### Update single file:

```bash
aws s3 cp guides/QUICK_START.md \
  s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/guides/QUICK_START.md
```

### View what would be uploaded (dry-run):

```bash
aws s3 sync . s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ --dryrun
```

---

## 🔍 Searching Documentation in S3

### Search for specific content:

```bash
# Download all docs and search locally
aws s3 sync s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ ./temp-docs/
grep -r "knowledge base" ./temp-docs/
```

### List files by pattern:

```bash
# Find all guide files
aws s3 ls s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/guides/ --recursive

# Find markdown files
aws s3 ls s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ --recursive | grep "\.md$"
```

---

## 📋 Quick Reference

### Most Used Commands

```bash
# List all files
aws s3 ls s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ --recursive

# Download all docs
aws s3 sync s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ ./docs/

# Upload all docs
aws s3 sync ./docs/ s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/

# Generate shareable link (1 hour)
aws s3 presign s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/index.html --expires-in 3600

# View file size
aws s3 ls s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ --recursive --human-readable --summarize
```

---

## 🎯 Recommended Workflow

### For Team Members Without AWS Access:

1. Generate pre-signed URLs for key documents
2. Share URLs via email/Slack (valid for specified duration)
3. URLs provide direct download access without AWS credentials

**Example**:
```bash
# Generate 7-day URLs for main documents
aws s3 presign s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/index.html --expires-in 604800
aws s3 presign s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/guides/QUICK_START.md --expires-in 604800
```

### For Team Members With AWS Access:

1. Access via AWS Console (easiest)
2. Or sync to local machine for offline viewing
3. Or use AWS CLI for specific files

### For Presentations/Meetings:

1. Download to local machine beforehand
2. Or generate long-lived pre-signed URLs
3. Or set up CloudFront for permanent access

---

## 🚀 Alternative Viewing Options

### Convert to PDF (for sharing):

```bash
# Download markdown and convert to PDF using pandoc
aws s3 cp s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/guides/QUICK_START.md ./
pandoc QUICK_START.md -o QUICK_START.pdf --toc
```

### View in Markdown Viewer:

```bash
# Download and open in VS Code or Typora
aws s3 sync s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ ./docs/
code docs/  # Opens in VS Code
```

### Host Locally:

```bash
# Download all docs
aws s3 sync s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/ ./docs/

# Serve with Python
cd docs
python3 -m http.server 8000

# Access at: http://localhost:8000/index.html
```

---

## 📊 Documentation Stats

**Total Files**: 10 markdown files + 1 HTML index

**Total Size**: ~121 KB

**Structure**:
- 4 setup/configuration guides
- 4 implementation/architecture docs
- 1 technical reference
- 1 web index

**Last Updated**: 2025-10-23

---

## 📞 Support

**Need access?** Contact your AWS administrator to grant S3 read permissions:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:ListBucket"
  ],
  "Resource": [
    "arn:aws:s3:::call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/*",
    "arn:aws:s3:::call-summariser-summarybucket-3wtnjhb9vvq0"
  ]
}
```

**Having issues?** Check:
1. AWS credentials configured (`aws configure`)
2. Permissions to access bucket
3. Correct region configured
4. Internet connectivity

---

**S3 Location**: `s3://call-summariser-summarybucket-3wtnjhb9vvq0/implementation-docs/`

**Web Index**: See `index.html` for visual navigation
