# Smart Attendance — AWS Infrastructure

AWS CDK (Python) stack that deploys the full Smart Attendance AIoT system
on a single EC2 instance backed by managed RDS PostgreSQL and ElastiCache Redis.

## Architecture

```
Internet
  │
  ▼
EC2 t3.large (Ubuntu 22.04) — Elastic IP
  │  ┌──────────────────────────────────────┐
  │  │  Docker Compose (port 80 via nginx) │
  │  │  ├─ nginx         (reverse proxy)   │
  │  │  ├─ backend       (:8000 FastAPI)   │
  │  │  ├─ frontend      (:3000 Next.js)   │
  │  │  └─ ai-service    (:8001 InsightFace)│
  │  └──────────────────────────────────────┘
  │            │                   │
  │     RDS PostgreSQL 16   ElastiCache Redis 7
  │     (private subnet)    (private subnet)
  │
Edge Devices (on-premise Raspberry Pi — connect to EC2 IP)
```

## Prerequisites

| Tool        | Version  | Install                          |
|-------------|----------|----------------------------------|
| Python      | ≥ 3.11   | `brew install python`           |
| AWS CLI     | ≥ 2.x    | `brew install awscli`           |
| AWS CDK     | ≥ 2.130  | `npm install -g aws-cdk`        |
| Node.js     | ≥ 18     | (required by CDK CLI)           |

## Quick Start

### 1. Configure AWS credentials
```bash
aws configure
# or use IAM Identity Center / AWS_PROFILE environment variable
```

### 2. Create an EC2 Key Pair (optional — you can use SSM instead)
```bash
aws ec2 create-key-pair \
    --key-name smart-attendance-key \
    --query 'KeyMaterial' \
    --output text > ~/.ssh/smart-attendance-key.pem
chmod 400 ~/.ssh/smart-attendance-key.pem
```

### 3. Install CDK dependencies
```bash
cd infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Bootstrap CDK (first time per account/region)
```bash
cdk bootstrap aws://YOUR_ACCOUNT_ID/ap-southeast-1
```

### 5. Deploy
```bash
cdk deploy \
    --context account=YOUR_ACCOUNT_ID \
    --context region=ap-southeast-1 \
    --context app_repo_url=https://github.com/YOUR_ORG/smart-attendance-aiot \
    --context app_branch=main \
    --context ec2_key_name=smart-attendance-key \
    --context alert_email=admin@your-domain.com
```

CDK will print outputs including:
- `Ec2PublicIp` — Point your DNS A record here
- `RdsEndpoint` — Private RDS host
- `RedisEndpoint` — Private Redis host
- `SsmConnectCmd` — Open shell without SSH keys

### 6. Connect to the server (two options)

**Option A — SSM (no key required)**
```bash
aws ssm start-session --target INSTANCE_ID
# or copy the command from CDK output: SsmConnectCmd
```

**Option B — SSH**
```bash
ssh -i ~/.ssh/smart-attendance-key.pem ubuntu@ELASTIC_IP
```

### 7. Set up HTTPS with Let's Encrypt
```bash
# On the EC2 instance:
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# Update env files with HTTPS URLs:
sudo nano /opt/smart-attendance/backend/.env          # ALLOWED_ORIGINS
sudo nano /opt/smart-attendance/frontend/.env.local   # NEXT_PUBLIC_API_URL
# Restart services:
cd /opt/smart-attendance
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Day-2 Operations

### View logs
```bash
cd /opt/smart-attendance
docker compose logs -f backend         # backend logs
docker compose logs -f ai-service      # AI service logs
docker compose logs -f frontend        # frontend logs
```

### Redeploy after code changes
```bash
cd /opt/smart-attendance
git pull origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Alembic migrations
```bash
docker exec $(docker ps -qf name=backend) alembic upgrade head
docker exec $(docker ps -qf name=backend) alembic current
```

### Generate a new migration (after ORM model changes)
```bash
docker exec $(docker ps -qf name=backend) \
    alembic revision --autogenerate -m "your_change_description"
# Copy the generated file back to the repo:
docker cp CONTAINER:/app/app/database/migrations/versions/. \
    /opt/smart-attendance/backend/app/database/migrations/versions/
git add -A && git commit -m "migration: your_change_description"
```

## CDK Context Variables

| Key           | Required | Description                                  |
|---------------|----------|----------------------------------------------|
| account       | Yes      | AWS account ID                               |
| region        | No       | AWS region (default: ap-southeast-1)         |
| app_repo_url  | No       | Git repo to clone on first boot              |
| app_branch    | No       | Git branch (default: main)                   |
| ec2_key_name  | No       | EC2 key pair for SSH access                  |
| alert_email   | No       | Email for CloudWatch alarm notifications     |

## Cost Estimate (ap-southeast-1)

| Resource                          | Monthly  |
|-----------------------------------|----------|
| EC2 t3.large (on-demand)          | ~$67     |
| RDS db.t3.small (PostgreSQL 16)   | ~$27     |
| ElastiCache cache.t3.micro        | ~$13     |
| EBS gp3 40 GiB                    | ~$3      |
| Data transfer (10 GB out)         | ~$0.90   |
| Elastic IP (associated = free)    | $0       |
| **Total**                         | **~$111**|

> Reduce cost: use EC2 t3.medium (~$33) if AI model is pre-loaded; purchase
> 1-year Reserved Instances (~40% saving).

## Destroy Infrastructure

```bash
cdk destroy
# Note: RDS and Secrets Manager have deletion_protection=True and
# RemovalPolicy.RETAIN — delete them manually in the console to avoid accidents.
```
