"""PharmAssist CDK Stack — DynamoDB tables, S3, CloudFront, Lambda, API Gateway, Cognito."""
import os

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Tags,
    RemovalPolicy,
    CfnOutput,
    Duration,
    BundlingOptions,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_events as events,
    aws_events_targets as targets,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_apigatewayv2 as apigwv2,
    aws_cognito as cognito,
)
from aws_cdk.aws_apigatewayv2_integrations import HttpLambdaIntegration
from aws_cdk.aws_apigatewayv2_integrations import WebSocketLambdaIntegration
from aws_cdk.aws_apigatewayv2_authorizers import HttpJwtAuthorizer
from constructs import Construct
import jsii


@jsii.implements(cdk.ILocalBundling)
class _LocalBundler:
    """Local bundling fallback — used when Docker is unavailable.

    Runs ``pip install`` and copies source files into the output directory
    using the host Python, which is fine for ``cdk synth`` validation and
    for deploying from environments where Docker is not installed.
    When Docker *is* available CDK will prefer the Docker-based bundling
    (which guarantees a Linux-compatible build for Lambda).
    """

    # Packages already in Lambda runtime or not needed at runtime
    _EXCLUDE_PACKAGES = {
        "boto3", "botocore", "s3transfer", "jmespath",  # in Lambda runtime
        "sympy", "mpmath",  # transitive, not needed
        "PIL", "Pillow", "pillow",  # not needed
        "pygments",  # not needed
        "setuptools", "pip", "wheel",  # build tools
    }

    @classmethod
    def _strip_bloat(cls, output_dir: str) -> None:
        """Remove unnecessary files to shrink the Lambda package."""
        import pathlib
        import shutil

        out = pathlib.Path(output_dir)
        # Remove excluded top-level packages
        for name in cls._EXCLUDE_PACKAGES:
            for p in out.glob(f"{name}*"):
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
        # Remove __pycache__, tests dirs, *.pyc
        # Keep .dist-info for opentelemetry (needs entry_points for context providers)
        for pattern in ("**/__pycache__", "**/tests", "**/test"):
            for p in out.glob(pattern):
                if p.is_dir():
                    shutil.rmtree(p)
        # Remove .dist-info except for opentelemetry packages
        for p in out.glob("**/*.dist-info"):
            if p.is_dir() and "opentelemetry" not in p.name:
                shutil.rmtree(p)
        for p in out.rglob("*.pyc"):
            p.unlink()

    def try_bundle(self, output_dir: str, *, image, asset_hash=None, **_kw) -> bool:  # noqa: ARG002
        import shutil
        import subprocess
        import pathlib

        backend_dir = pathlib.Path(__file__).resolve().parent.parent.parent / "backend"
        req_file = backend_dir / "requirements-lambda.txt"

        if not req_file.exists():
            return False

        subprocess.check_call(
            [
                "pip", "install",
                "-r", str(req_file),
                "-t", output_dir,
                "--quiet",
                "--upgrade",
                "--platform", "manylinux2014_x86_64",
                "--implementation", "cp",
                "--python-version", "3.12",
                "--only-binary=:all:",
            ],
        )
        # Copy backend source files (skip .venv, __pycache__, .env*)
        for item in backend_dir.iterdir():
            if item.name in {".venv", "__pycache__", ".env", ".env.example"}:
                continue
            dest = pathlib.Path(output_dir) / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__", ".venv"))
            else:
                shutil.copy2(item, dest)

        # Strip bloat to stay under Lambda 250 MB limit
        self._strip_bloat(output_dir)
        return True


class PharmAssistStack(Stack):
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

        # --- Automatic tagging on all resources ---
        Tags.of(self).add("Project", tag_project)
        Tags.of(self).add("Environment", tag_environment)
        Tags.of(self).add("Owner", tag_owner)

        removal = RemovalPolicy.DESTROY

        # =============================================
        # DynamoDB Table 1: crm_medicos
        # =============================================
        self.medicos_table = dynamodb.Table(
            self,
            "MedicosTable",
            partition_key=dynamodb.Attribute(
                name="Medico_MN", type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )
        self.medicos_table.add_global_secondary_index(
            index_name="APM-index",
            partition_key=dynamodb.Attribute(
                name="APM", type=dynamodb.AttributeType.STRING
            ),
        )
        self.medicos_table.add_global_secondary_index(
            index_name="Zona-index",
            partition_key=dynamodb.Attribute(
                name="Zona", type=dynamodb.AttributeType.STRING
            ),
        )

        # =============================================
        # DynamoDB Table 2: apm_visitas
        # =============================================
        self.visitas_table = dynamodb.Table(
            self,
            "VisitasTable",
            partition_key=dynamodb.Attribute(
                name="Visita_ID", type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )
        self.visitas_table.add_global_secondary_index(
            index_name="APM-Fecha-index",
            partition_key=dynamodb.Attribute(
                name="APM", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Fecha_Visita", type=dynamodb.AttributeType.STRING
            ),
        )
        self.visitas_table.add_global_secondary_index(
            index_name="Medico-Fecha-index",
            partition_key=dynamodb.Attribute(
                name="Medico_MN", type=dynamodb.AttributeType.NUMBER
            ),
            sort_key=dynamodb.Attribute(
                name="Fecha_Visita", type=dynamodb.AttributeType.STRING
            ),
        )

        # =============================================
        # DynamoDB Table 3: ventas_reportadas
        # =============================================
        self.ventas_table = dynamodb.Table(
            self,
            "VentasTable",
            partition_key=dynamodb.Attribute(
                name="Zona_Producto", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Anio_Mes", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )
        self.ventas_table.add_global_secondary_index(
            index_name="Zona-index",
            partition_key=dynamodb.Attribute(
                name="Zona", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Anio_Mes", type=dynamodb.AttributeType.STRING
            ),
        )

        # =============================================
        # DynamoDB Table 4: visitas_planificadas
        # =============================================
        self.planificadas_table = dynamodb.Table(
            self,
            "PlanificadasTable",
            partition_key=dynamodb.Attribute(
                name="APM_Fecha", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Medico_MN", type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )
        self.planificadas_table.add_global_secondary_index(
            index_name="APM-Fecha-index",
            partition_key=dynamodb.Attribute(
                name="APM", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Fecha_Planificada", type=dynamodb.AttributeType.STRING
            ),
        )

        # =============================================
        # DynamoDB Table 5: minutas_visitas
        # =============================================
        self.minutas_table = dynamodb.Table(
            self,
            "MinutasTable",
            partition_key=dynamodb.Attribute(
                name="Minuta_ID", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
        )
        self.minutas_table.add_global_secondary_index(
            index_name="APM-Fecha-index",
            partition_key=dynamodb.Attribute(
                name="APM", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Fecha_Creacion", type=dynamodb.AttributeType.STRING
            ),
        )
        self.minutas_table.add_global_secondary_index(
            index_name="Medico-Fecha-index",
            partition_key=dynamodb.Attribute(
                name="Medico_MN", type=dynamodb.AttributeType.NUMBER
            ),
            sort_key=dynamodb.Attribute(
                name="Fecha_Creacion", type=dynamodb.AttributeType.STRING
            ),
        )

        # =============================================
        # Cognito User Pool — APM authentication
        # =============================================
        self.user_pool = cognito.UserPool(
            self,
            "PharmAssistUsers",
            user_pool_name="PharmAssistUsers",
            sign_in_aliases=cognito.SignInAliases(email=True),
            self_sign_up_enabled=False,
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            custom_attributes={
                "apm_id": cognito.StringAttribute(mutable=True),
            },
            removal_policy=removal,
        )

        self.app_client = self.user_pool.add_client(
            "SPAClient",
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            generate_secret=False,
        )

        # =============================================
        # Cognito Identity Pool — AWS temp credentials for voice mode
        # =============================================
        self.identity_pool = cognito.CfnIdentityPool(
            self,
            "PharmAssistIdentityPool",
            identity_pool_name="PharmAssistIdentityPool",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=self.app_client.user_pool_client_id,
                    provider_name=self.user_pool.user_pool_provider_name,
                )
            ],
        )

        # IAM role for authenticated Cognito identities — only InvokeAgentRuntime
        authenticated_role = iam.Role(
            self,
            "CognitoAuthenticatedRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": self.identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated"
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )
        authenticated_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:InvokeAgentRuntimeWithWebSocketStream"],
                resources=[
                    f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:runtime/*"
                ],
            )
        )

        # Attach authenticated role to Identity Pool
        cognito.CfnIdentityPoolRoleAttachment(
            self,
            "IdentityPoolRoleAttachment",
            identity_pool_id=self.identity_pool.ref,
            roles={"authenticated": authenticated_role.role_arn},
        )

        # =============================================
        # S3 Bucket — Audio uploads (voice notes pipeline)
        # =============================================
        self.audio_bucket = s3.Bucket(
            self,
            "AudioUploadsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=removal,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(30),
                    enabled=True,
                ),
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3600,
                ),
            ],
        )

        # =============================================
        # S3 Bucket — Frontend SPA hosting
        # =============================================
        self.frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=removal,
            auto_delete_objects=True,
        )

        # =============================================
        # CloudFront Distribution
        # =============================================
        self.distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    self.frontend_bucket
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        # =============================================
        # Lambda Function — FastAPI backend (Mangum)
        # =============================================
        api_lambda = _lambda.Function(
            self,
            "ApiFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="lambda_handler.handler",
            code=_lambda.Code.from_asset(
                path="../backend",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements-lambda.txt -t /asset-output"
                        " && cp -r . /asset-output/"
                        " && cd /asset-output"
                        " && rm -rf boto3* botocore* s3transfer* jmespath*"
                        " sympy* mpmath* PIL* Pillow* pillow* pygments*"
                        " setuptools* pip* wheel*"
                        " **/__pycache__ **/*.dist-info **/*.pyc",
                    ],
                    local=_LocalBundler(),
                ),
                asset_hash_type=cdk.AssetHashType.OUTPUT,
            ),
            memory_size=1024,
            timeout=Duration.seconds(120),
            environment={
                "MEDICOS_TABLE_NAME": self.medicos_table.table_name,
                "VISITAS_TABLE_NAME": self.visitas_table.table_name,
                "VENTAS_TABLE_NAME": self.ventas_table.table_name,
                "PLANIFICADAS_TABLE_NAME": self.planificadas_table.table_name,
                "MINUTAS_TABLE_NAME": self.minutas_table.table_name,
                "AWS_REGION_NAME": os.environ.get("AWS_REGION", "us-east-1"),
                "AGENTCORE_AGENT_ARN": os.environ.get("AGENTCORE_AGENT_ARN", ""),
                "AGENTCORE_REGION": os.environ.get("AGENTCORE_REGION", "us-east-1"),
                "BEDROCK_MODEL_ID": os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-6-v1"),
                "USER_POOL_ID": self.user_pool.user_pool_id,
                "AUDIO_BUCKET_NAME": self.audio_bucket.bucket_name,
            },
        )

        # --- IAM: DynamoDB read/write for all 5 tables ---
        self.medicos_table.grant_read_write_data(api_lambda)
        self.visitas_table.grant_read_write_data(api_lambda)
        self.ventas_table.grant_read_write_data(api_lambda)
        self.planificadas_table.grant_read_write_data(api_lambda)
        self.minutas_table.grant_read_write_data(api_lambda)

        # --- IAM: Bedrock invoke for birthday message generation ---
        api_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        # --- IAM: Transcribe for direct audio upload endpoint ---
        api_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "transcribe:StartTranscriptionJob",
                    "transcribe:GetTranscriptionJob",
                ],
                resources=["*"],
            )
        )

        # --- IAM: AgentCore invoke for chat proxy ---
        api_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=["*"],
            )
        )

        # --- IAM: S3 audio bucket for presigned URLs + direct upload ---
        self.audio_bucket.grant_read_write(api_lambda)

        # =============================================
        # API Gateway HTTP API + Cognito Authorizer
        # =============================================
        integration = HttpLambdaIntegration("ApiIntegration", api_lambda)

        cognito_authorizer = HttpJwtAuthorizer(
            "CognitoAuthorizer",
            jwt_issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool.user_pool_id}",
            jwt_audience=[self.app_client.user_pool_client_id],
        )

        http_api = apigwv2.HttpApi(
            self,
            "PharmAssistApi",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_headers=["*"],
            ),
        )

        # Protected routes — require Cognito JWT
        http_api.add_routes(
            path="/{proxy+}",
            methods=[
                apigwv2.HttpMethod.GET,
                apigwv2.HttpMethod.POST,
                apigwv2.HttpMethod.PUT,
                apigwv2.HttpMethod.DELETE,
                apigwv2.HttpMethod.PATCH,
            ],
            integration=integration,
            authorizer=cognito_authorizer,
        )

        # Health check — no auth required
        http_api.add_routes(
            path="/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=integration,
        )

        # Root — no auth (for CORS preflight and basic health)
        http_api.add_routes(
            path="/",
            methods=[apigwv2.HttpMethod.ANY],
            integration=integration,
        )

        # =============================================
        # WebSocket API Gateway + Lambda Proxy
        # =============================================
        ws_lambda = _lambda.Function(
            self,
            "WebSocketProxy",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="ws_handler.handler",
            code=_lambda.Code.from_asset("../backend/ws_proxy"),
            timeout=Duration.seconds(120),
            memory_size=256,
            environment={
                "AGENTCORE_AGENT_ARN": os.environ.get("AGENTCORE_AGENT_ARN", ""),
                "AGENTCORE_REGION": os.environ.get("AGENTCORE_REGION", "us-east-1"),
                "USER_POOL_ID": self.user_pool.user_pool_id,
                "USER_POOL_REGION": self.region,
            },
        )

        # IAM: invoke AgentCore Runtime
        ws_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=["*"],
            )
        )

        # IAM: post messages back to WebSocket connections
        ws_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["execute-api:ManageConnections"],
                resources=[f"arn:aws:execute-api:{self.region}:{self.account}:*/@connections/*"],
            )
        )

        ws_integration = WebSocketLambdaIntegration("WSIntegration", ws_lambda)

        ws_api = apigwv2.WebSocketApi(
            self,
            "PharmAssistWS",
            connect_route_options=apigwv2.WebSocketRouteOptions(
                integration=WebSocketLambdaIntegration("WSConnectIntegration", ws_lambda),
            ),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(
                integration=WebSocketLambdaIntegration("WSDisconnectIntegration", ws_lambda),
            ),
        )

        ws_api.add_route(
            "sendMessage",
            integration=WebSocketLambdaIntegration("WSSendMsgIntegration", ws_lambda),
        )

        ws_stage = apigwv2.WebSocketStage(
            self,
            "WSStage",
            web_socket_api=ws_api,
            stage_name="prod",
            auto_deploy=True,
        )

        # =============================================
        # TranscribeLambda — S3 trigger → Amazon Transcribe
        # =============================================
        transcribe_lambda = _lambda.Function(
            self,
            "TranscribeLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="transcribe_trigger.handler",
            code=_lambda.Code.from_asset("../backend/lambdas"),
            timeout=Duration.seconds(60),
            memory_size=128,
            environment={
                "AUDIO_BUCKET_NAME": self.audio_bucket.bucket_name,
                "AWS_REGION_NAME": os.environ.get("AWS_REGION", "us-east-1"),
            },
        )

        # IAM: start Transcribe jobs + read audio from S3
        transcribe_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "transcribe:StartTranscriptionJob",
                ],
                resources=["*"],
            )
        )
        self.audio_bucket.grant_read(transcribe_lambda)
        self.audio_bucket.grant_put(transcribe_lambda)  # for transcript output

        # S3 event notification → TranscribeLambda on audio upload
        self.audio_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(transcribe_lambda),
            s3.NotificationKeyFilter(prefix="audio/"),
        )

        # =============================================
        # SummarizeLambda — Transcribe complete → Bedrock → DynamoDB
        # =============================================
        summarize_lambda = _lambda.Function(
            self,
            "SummarizeLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="summarize_minuta.handler",
            code=_lambda.Code.from_asset("../backend/lambdas"),
            timeout=Duration.seconds(120),
            memory_size=256,
            environment={
                "AUDIO_BUCKET_NAME": self.audio_bucket.bucket_name,
                "MINUTAS_TABLE_NAME": self.minutas_table.table_name,
                "SUMMARIZE_MODEL_ID": "us.amazon.nova-2-lite-v1:0",
                "AWS_REGION_NAME": os.environ.get("AWS_REGION", "us-east-1"),
            },
        )

        # IAM: read Transcribe results, invoke Bedrock, write to DynamoDB
        summarize_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "transcribe:GetTranscriptionJob",
                ],
                resources=["*"],
            )
        )
        summarize_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                ],
                resources=["*"],
            )
        )
        self.audio_bucket.grant_read(summarize_lambda)
        self.minutas_table.grant_write_data(summarize_lambda)

        # EventBridge rule: Transcribe job COMPLETED → SummarizeLambda
        events.Rule(
            self,
            "TranscribeCompleteRule",
            event_pattern=events.EventPattern(
                source=["aws.transcribe"],
                detail_type=["Transcribe Job State Change"],
                detail={
                    "TranscriptionJobStatus": ["COMPLETED"],
                    "TranscriptionJobName": [{"prefix": "pharmassist-"}],
                },
            ),
            targets=[targets.LambdaFunction(summarize_lambda)],
        )

        # =============================================
        # Stack Outputs
        # =============================================
        CfnOutput(self, "MedicosTableName",
                  value=self.medicos_table.table_name,
                  description="crm_medicos DynamoDB table name")
        CfnOutput(self, "VisitasTableName",
                  value=self.visitas_table.table_name,
                  description="apm_visitas DynamoDB table name")
        CfnOutput(self, "VentasTableName",
                  value=self.ventas_table.table_name,
                  description="ventas_reportadas DynamoDB table name")
        CfnOutput(self, "PlanificadasTableName",
                  value=self.planificadas_table.table_name,
                  description="visitas_planificadas DynamoDB table name")
        CfnOutput(self, "MinutasTableName",
                  value=self.minutas_table.table_name,
                  description="minutas_visitas DynamoDB table name")
        CfnOutput(self, "FrontendBucketName",
                  value=self.frontend_bucket.bucket_name,
                  description="S3 bucket for frontend SPA")
        CfnOutput(self, "CloudFrontDomain",
                  value=self.distribution.distribution_domain_name,
                  description="CloudFront distribution domain")
        CfnOutput(self, "CloudFrontDistributionId",
                  value=self.distribution.distribution_id,
                  description="CloudFront distribution ID for invalidation")
        CfnOutput(self, "ApiUrl",
                  value=http_api.url or "",
                  description="API Gateway HTTP API URL")
        CfnOutput(self, "UserPoolId",
                  value=self.user_pool.user_pool_id,
                  description="Cognito User Pool ID")
        CfnOutput(self, "UserPoolClientId",
                  value=self.app_client.user_pool_client_id,
                  description="Cognito App Client ID for SPA")
        CfnOutput(self, "IdentityPoolId",
                  value=self.identity_pool.ref,
                  description="Cognito Identity Pool ID for voice mode SigV4 credentials")
        CfnOutput(self, "WebSocketUrl",
                  value=ws_stage.url,
                  description="WebSocket API URL for chat streaming")
        CfnOutput(self, "AudioBucketName",
                  value=self.audio_bucket.bucket_name,
                  description="S3 bucket for audio uploads (voice notes)")

