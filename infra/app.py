#!/usr/bin/env python3
"""
AWS CDK application entry-point for Smart Attendance AIoT.

Architecture
────────────
  VPC (2 AZs)
    ├─ Public subnets  → EC2 + Elastic IP
    └─ Private subnets → RDS PostgreSQL + ElastiCache Redis

  EC2 (t3.large, Ubuntu 22.04)
    └─ Docker Compose: backend · frontend · ai-service · (nginx proxy)

  RDS (db.t3.small, PostgreSQL 16)
  ElastiCache (cache.t3.micro, Redis 7)

  Security groups enforce least privilege:
    EC2  ←→  RDS   (port 5432)
    EC2  ←→  Redis (port 6379)
    0.0.0.0/0 → EC2 (80, 443, 22)

Deploy
──────
    cd infra
    pip install -r requirements.txt
    cdk bootstrap        # first time only
    cdk deploy
"""

import aws_cdk as cdk
from infra.stack import SmartAttendanceStack

app = cdk.App()

SmartAttendanceStack(
    app,
    "SmartAttendanceStack",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),   # or set AWS_ACCOUNT_ID
        region=app.node.try_get_context("region") or "ap-southeast-1",
    ),
    description="Smart Attendance AIoT — EC2/RDS/ElastiCache stack",
)

app.synth()
