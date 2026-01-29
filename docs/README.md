# Coaching AI Documentation

**Project**: Coaching AI - Call Summarization & Case Check System
**Status**: Production Ready

---

## Documentation Structure

```
docs/
├── guides/                    # Setup & Operational Guides
│   ├── QUICK_START.md                # 15-min KB setup guide
│   ├── KNOWLEDGE_BASE_SETUP.md       # Detailed AWS console walkthrough
│   ├── KB_CONFIGURATION_REVIEW.md    # Configuration & troubleshooting
│   ├── DEPLOYMENT_CHECKLIST.md       # Pre-deployment checklist
│   ├── GOLDEN_DATA_WORKFLOW.md       # Ground truth collection workflow
│   ├── VULNERABILITY_ASSESSMENT_SETUP.md  # Vulnerability detection setup
│   ├── TESTING_VULNERABILITY_FLOW.md # Testing vulnerability features
│   └── S3_ACCESS_GUIDE.md            # S3 bucket access & structure
│
├── technical/                 # Technical Architecture
│   ├── CASE_CHECK_LOGIC.md           # Complete assessment logic (25 checks)
│   └── CASE_CHECK_ARCHITECTURE.md    # Case check system architecture
│
└── README.md                  # This file
```

---

## Quick Navigation

### Getting Started
- [Quick Start Guide](guides/QUICK_START.md) - Get the Knowledge Base running (15 min)
- [Deployment Checklist](guides/DEPLOYMENT_CHECKLIST.md) - Pre-flight checklist

### Setup Guides
- [Knowledge Base Setup](guides/KNOWLEDGE_BASE_SETUP.md) - Detailed AWS console walkthrough
- [Vulnerability Assessment Setup](guides/VULNERABILITY_ASSESSMENT_SETUP.md) - Configure vulnerability detection
- [Golden Data Workflow](guides/GOLDEN_DATA_WORKFLOW.md) - Ground truth collection pipeline
- [S3 Access Guide](guides/S3_ACCESS_GUIDE.md) - S3 bucket structure and access

### Technical Reference
- [Case Check Logic](technical/CASE_CHECK_LOGIC.md) - All 25 assessment checks explained
- [Case Check Architecture](technical/CASE_CHECK_ARCHITECTURE.md) - System architecture

### Troubleshooting
- [KB Configuration Review](guides/KB_CONFIGURATION_REVIEW.md) - Configuration & troubleshooting
- [Testing Vulnerability Flow](guides/TESTING_VULNERABILITY_FLOW.md) - Test vulnerability detection

---

## Documentation by Role

### For Developers
| Document | Purpose |
|----------|---------|
| [Quick Start](guides/QUICK_START.md) | Get KB running |
| [Case Check Architecture](technical/CASE_CHECK_ARCHITECTURE.md) | Understand the system |

### For QA/Training Team
| Document | Purpose |
|----------|---------|
| [Case Check Logic](technical/CASE_CHECK_LOGIC.md) | All 25 checks explained |
| [Testing Vulnerability Flow](guides/TESTING_VULNERABILITY_FLOW.md) | Test vulnerability detection |

### For DevOps
| Document | Purpose |
|----------|---------|
| [Deployment Checklist](guides/DEPLOYMENT_CHECKLIST.md) | Pre-deployment validation |
| [KB Configuration Review](guides/KB_CONFIGURATION_REVIEW.md) | Configuration & monitoring |
| [S3 Access Guide](guides/S3_ACCESS_GUIDE.md) | S3 structure and permissions |

---

**Last Updated**: January 2026
