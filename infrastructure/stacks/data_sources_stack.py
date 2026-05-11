"""DataSourcesStack — VPC externa + RDS PostgreSQL + Bastion SSM simulando warehouses del laboratorio."""
import os

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Tags,
    RemovalPolicy,
    CfnOutput,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_iam as iam,
)
from constructs import Construct


class DataSourcesStack(Stack):
    """Simula los 3 warehouses externos (CRM interno, CloseUp, IQVIA).

    Crea una VPC separada con:
    - RDS PostgreSQL con 3 schemas (crm_interno, closeup, iqvia, maestros)
    - EC2 Bastion con SSM Session Manager para acceso seguro sin SSH keys
    - VPC Endpoints para SSM (sin NAT gateway, ahorra ~$45/mes)

    Acceso al RDS via SSM port forwarding:
        aws ssm start-session --target <instance-id> \\
            --document-name AWS-StartPortForwardingSessionToRemoteHost \\
            --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5432"]}'
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        tag_project: str = "PharmAssist",
        tag_environment: str = "dev",
        tag_owner: str = "team",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Automatic tagging ---
        Tags.of(self).add("Project", tag_project)
        Tags.of(self).add("Environment", tag_environment)
        Tags.of(self).add("Owner", tag_owner)
        Tags.of(self).add("ManagedBy", "cdk")

        removal = RemovalPolicy.DESTROY

        # =============================================
        # VPC — simula red "externa" del cliente
        # =============================================
        self.vpc = ec2.Vpc(
            self,
            "ExternalVpc",
            max_azs=2,
            nat_gateways=0,  # sin NAT para ahorrar costos
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
            # CIDR distinto al default VPC para evitar conflictos en peering
            ip_addresses=ec2.IpAddresses.cidr("10.100.0.0/16"),
        )

        # =============================================
        # VPC Endpoints — permiten SSM sin NAT gateway
        # =============================================
        # SSM requiere 3 endpoints para funcionar en subnets isolated
        self.vpc.add_interface_endpoint(
            "SsmEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM,
        )
        self.vpc.add_interface_endpoint(
            "SsmMessagesEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
        )
        self.vpc.add_interface_endpoint(
            "Ec2MessagesEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
        )
        # Secrets Manager endpoint (para que el bastion pueda leer credenciales RDS)
        self.vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
        )

        # =============================================
        # Security Group — RDS
        # =============================================
        self.rds_security_group = ec2.SecurityGroup(
            self,
            "RdsSecurityGroup",
            vpc=self.vpc,
            description="Allow PostgreSQL access to simulation RDS",
            allow_all_outbound=False,
        )

        # =============================================
        # Security Group — Bastion
        # =============================================
        self.bastion_security_group = ec2.SecurityGroup(
            self,
            "BastionSecurityGroup",
            vpc=self.vpc,
            description="Bastion host for SSM access",
            allow_all_outbound=True,  # needs outbound for VPC endpoints
        )

        # Allow bastion to connect to RDS
        self.rds_security_group.add_ingress_rule(
            peer=self.bastion_security_group,
            connection=ec2.Port.tcp(5432),
            description="PostgreSQL from Bastion",
        )

        # =============================================
        # RDS PostgreSQL — 3 schemas en una instancia
        # =============================================
        self.db_instance = rds.DatabaseInstance(
            self,
            "SimulationDb",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_4,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[self.rds_security_group],
            allocated_storage=20,
            max_allocated_storage=50,
            database_name="pharmassist_sources",
            multi_az=False,
            deletion_protection=False,
            removal_policy=removal,
            backup_retention=cdk.Duration.days(1),
            publicly_accessible=False,
            storage_encrypted=True,
        )

        # =============================================
        # EC2 Bastion — acceso via SSM Session Manager
        # No requiere SSH keys, no requiere IP pública
        # =============================================
        bastion_role = iam.Role(
            self,
            "BastionRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                # SSM managed policy — permite Session Manager
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        # Permitir al bastion leer el secret de RDS (para scripts de seed)
        self.db_instance.secret.grant_read(bastion_role)

        self.bastion_instance = ec2.Instance(
            self,
            "BastionHost",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, ec2.InstanceSize.NANO  # mínimo posible (~$3/mes)
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64,
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_group=self.bastion_security_group,
            role=bastion_role,
            # User data: instalar PostgreSQL client para poder ejecutar scripts
            user_data=ec2.UserData.custom(
                "#!/bin/bash\n"
                "dnf install -y postgresql16 python3.12 python3.12-pip\n"
                "python3.12 -m pip install psycopg2-binary faker numpy tqdm python-dotenv boto3\n"
            ),
        )

        # =============================================
        # Stack Outputs
        # =============================================
        CfnOutput(
            self,
            "RdsEndpoint",
            value=self.db_instance.db_instance_endpoint_address,
            description="RDS PostgreSQL endpoint",
        )
        CfnOutput(
            self,
            "RdsPort",
            value=self.db_instance.db_instance_endpoint_port,
            description="RDS PostgreSQL port",
        )
        CfnOutput(
            self,
            "RdsSecretArn",
            value=self.db_instance.secret.secret_arn,
            description="Secrets Manager ARN with RDS credentials",
        )
        CfnOutput(
            self,
            "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID of the external simulation VPC",
        )
        CfnOutput(
            self,
            "SecurityGroupId",
            value=self.rds_security_group.security_group_id,
            description="Security Group ID for RDS access",
        )
        CfnOutput(
            self,
            "DatabaseName",
            value="pharmassist_sources",
            description="Database name in the RDS instance",
        )
        CfnOutput(
            self,
            "BastionInstanceId",
            value=self.bastion_instance.instance_id,
            description="EC2 Bastion instance ID (use with SSM start-session)",
        )
