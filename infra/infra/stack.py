"""
SmartAttendanceStack — CDK stack that provisions the full AWS infrastructure.

Resources created
─────────────────
  Networking:
    ∙ VPC (2 AZs) with public + private subnets
    ∙ Internet Gateway (for EC2)
    ∙ No NAT Gateway (saves ~$32/mo; EC2 in public subnet)

  Compute:
    ∙ EC2 t3.large — runs all Docker services via docker-compose
    ∙ Elastic IP — static public address

  Database:
    ∙ RDS db.t3.small — PostgreSQL 16 — private subnet
    ∙ ElastiCache cache.t3.micro — Redis 7 — private subnet

  Security:
    ∙ EC2 security group: ingress 22/80/443 from 0.0.0.0/0
    ∙ RDS security group: ingress 5432 from EC2 SG only
    ∙ Redis security group: ingress 6379 from EC2 SG only

  IAM:
    ∙ EC2 instance role with SSM Session Manager (no bastion needed)
    ∙ Secrets Manager read permission for DB credentials

  Secrets Manager:
    ∙ DB password auto-generated, stored securely

CDK Context variables (set via cdk.json or --context flag)
───────────────────────────────────────────────────────────
  ec2_key_name       — EC2 key pair name for SSH (optional if using SSM)
  app_repo_url       — Git repo URL to clone on first boot
  app_branch         — Git branch (default: main)
  alert_email        — SNS alarm recipient email (optional)
  domain_name        — Domain for HTTPS certificate (optional)
"""

import os
from pathlib import Path
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    Tags,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_elasticache as elasticache,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
)
from constructs import Construct


class SmartAttendanceStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Context vars ──────────────────────────────────────────────────────
        ec2_key_name  = self.node.try_get_context("ec2_key_name")    # optional
        app_repo_url  = self.node.try_get_context("app_repo_url") or ""
        app_branch    = self.node.try_get_context("app_branch") or "main"
        alert_email   = self.node.try_get_context("alert_email")     # optional

        # ── Tags ──────────────────────────────────────────────────────────────
        Tags.of(self).add("Project", "SmartAttendance")
        Tags.of(self).add("ManagedBy", "CDK")

        # ─────────────────────────────────────────────────────────────────────
        # 1. VPC
        # ─────────────────────────────────────────────────────────────────────
        vpc = ec2.Vpc(
            self, "Vpc",
            max_azs=2,
            nat_gateways=0,           # cost optimisation: EC2 in public subnet
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # ─────────────────────────────────────────────────────────────────────
        # 2. Security Groups
        # ─────────────────────────────────────────────────────────────────────
        ec2_sg = ec2.SecurityGroup(
            self, "Ec2Sg",
            vpc=vpc,
            description="Smart Attendance — EC2",
            allow_all_outbound=True,
        )
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22),  "SSH")
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80),  "HTTP")
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS")
        # Direct API access (useful during debug; close in production)
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8000), "Backend API")
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(3000), "Frontend")

        rds_sg = ec2.SecurityGroup(
            self, "RdsSg",
            vpc=vpc,
            description="Smart Attendance — RDS",
            allow_all_outbound=False,
        )
        rds_sg.add_ingress_rule(ec2_sg, ec2.Port.tcp(5432), "PostgreSQL from EC2")

        redis_sg = ec2.SecurityGroup(
            self, "RedisSg",
            vpc=vpc,
            description="Smart Attendance — ElastiCache",
            allow_all_outbound=False,
        )
        redis_sg.add_ingress_rule(ec2_sg, ec2.Port.tcp(6379), "Redis from EC2")

        # ─────────────────────────────────────────────────────────────────────
        # 3. DB password in Secrets Manager
        # ─────────────────────────────────────────────────────────────────────
        db_secret = secretsmanager.Secret(
            self, "DbSecret",
            description="RDS PostgreSQL credentials for Smart Attendance",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"attendance_user"}',
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=24,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ─────────────────────────────────────────────────────────────────────
        # 4. RDS — PostgreSQL 16
        # ─────────────────────────────────────────────────────────────────────
        db_subnet_group = rds.SubnetGroup(
            self, "DbSubnetGroup",
            vpc=vpc,
            description="Smart Attendance RDS subnet group",
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
        )

        database = rds.DatabaseInstance(
            self, "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.SMALL
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            subnet_group=db_subnet_group,
            security_groups=[rds_sg],
            database_name="attendance_db",
            credentials=rds.Credentials.from_secret(db_secret),
            allocated_storage=20,
            max_allocated_storage=100,       # autoscaling up to 100 GiB
            storage_type=rds.StorageType.GP3,
            backup_retention=Duration.days(7),
            deletion_protection=True,
            removal_policy=RemovalPolicy.RETAIN,
            multi_az=False,                  # enable for production HA
            auto_minor_version_upgrade=True,
            cloudwatch_logs_exports=["postgresql"],
        )

        # ─────────────────────────────────────────────────────────────────────
        # 5. ElastiCache — Redis 7
        # ─────────────────────────────────────────────────────────────────────
        redis_subnet_group = elasticache.CfnSubnetGroup(
            self, "RedisSubnetGroup",
            description="Smart Attendance Redis subnet group",
            subnet_ids=[s.subnet_id for s in vpc.isolated_subnets],
        )

        redis_cluster = elasticache.CfnCacheCluster(
            self, "RedisCluster",
            cache_node_type="cache.t3.micro",
            engine="redis",
            engine_version="7.1",
            num_cache_nodes=1,
            cache_subnet_group_name=redis_subnet_group.ref,
            vpc_security_group_ids=[redis_sg.security_group_id],
            auto_minor_version_upgrade=True,
        )

        # ─────────────────────────────────────────────────────────────────────
        # 6. EC2 IAM Role
        # ─────────────────────────────────────────────────────────────────────
        ec2_role = iam.Role(
            self, "Ec2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                # SSM Session Manager — SSH-free shell access
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
                # CloudWatch agent
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                ),
            ],
        )
        # Allow EC2 to read the DB secret
        db_secret.grant_read(ec2_role)

        # ─────────────────────────────────────────────────────────────────────
        # 7. EC2 Instance
        # ─────────────────────────────────────────────────────────────────────
        # Read user-data bootstrap script
        userdata_path = Path(__file__).parent.parent / "scripts" / "ec2_userdata.sh"
        userdata_script = userdata_path.read_text()

        # Inject runtime values as env variables at the top of user-data
        injected_env = "\n".join([
            f'DB_HOST="{database.db_instance_endpoint_address}"',
            f'DB_SECRET_ARN="{db_secret.secret_arn}"',
            f'REDIS_HOST="{redis_cluster.attr_redis_endpoint_address}"',
            f'APP_REPO_URL="{app_repo_url}"',
            f'APP_BRANCH="{app_branch}"',
        ])
        userdata_full = f"#!/bin/bash\nset -euo pipefail\n\n# — CDK injected values —\n{injected_env}\n\n{userdata_script}"

        user_data = ec2.UserData.custom(userdata_full)

        instance = ec2.Instance(
            self, "AppServer",
            instance_type=ec2.InstanceType("t3.large"),  # 2 vCPU, 8 GB RAM
            # Ubuntu 22.04 LTS (x86_64) — latest AMI per region
            machine_image=ec2.MachineImage.from_ssm_parameter(
                "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=ec2_sg,
            role=ec2_role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/sda1",
                    volume=ec2.BlockDeviceVolume.ebs(
                        40,                              # 40 GiB root volume
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                    ),
                )
            ],
            **({"key_name": ec2_key_name} if ec2_key_name else {}),
        )

        # Elastic IP for static public address
        eip = ec2.CfnEIP(self, "AppServerEip", domain="vpc")
        ec2.CfnEIPAssociation(
            self, "AppServerEipAssoc",
            instance_id=instance.instance_id,
            eip=eip.ref,
        )

        # ─────────────────────────────────────────────────────────────────────
        # 8. CloudWatch Alarm (optional — requires alert_email context)
        # ─────────────────────────────────────────────────────────────────────
        if alert_email:
            alarm_topic = sns.Topic(self, "AlarmTopic")
            alarm_topic.add_subscription(subs.EmailSubscription(alert_email))

            cloudwatch.Alarm(
                self, "Ec2CpuAlarm",
                metric=instance.metric_cpu_utilization(),
                threshold=85,
                evaluation_periods=3,
                alarm_description="EC2 CPU > 85% for 15 min",
                alarm_actions=[cw_actions.SnsAction(alarm_topic)],
            )

            cloudwatch.Alarm(
                self, "RdsCpuAlarm",
                metric=database.metric_cpu_utilization(),
                threshold=80,
                evaluation_periods=3,
                alarm_description="RDS CPU > 80% for 15 min",
                alarm_actions=[cw_actions.SnsAction(alarm_topic)],
            )

        # ─────────────────────────────────────────────────────────────────────
        # 9. Outputs
        # ─────────────────────────────────────────────────────────────────────
        CfnOutput(self, "Ec2PublicIp",
                  value=eip.ref,
                  description="EC2 Elastic IP — point your domain here")

        CfnOutput(self, "RdsEndpoint",
                  value=database.db_instance_endpoint_address,
                  description="RDS PostgreSQL endpoint (private)")

        CfnOutput(self, "RedisEndpoint",
                  value=redis_cluster.attr_redis_endpoint_address,
                  description="ElastiCache Redis endpoint (private)")

        CfnOutput(self, "DbSecretArn",
                  value=db_secret.secret_arn,
                  description="Secrets Manager ARN for DB credentials")

        CfnOutput(self, "SsmConnectCmd",
                  value=f"aws ssm start-session --target {instance.instance_id}",
                  description="Open a shell without SSH keys via SSM")
