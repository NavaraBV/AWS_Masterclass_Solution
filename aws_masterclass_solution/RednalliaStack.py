from constructs import Construct
from aws_cdk import Stack, RemovalPolicy
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_rds as rds
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_s3_notifications as s3_notifications
from aws_cdk import aws_secretsmanager as sm
import os

class RednalliaStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        account_id = Stack.of(self).account
        
        # VPC
        vpc = ec2.Vpc(self, "RednalliaVPC",
                      max_azs=3,
                      nat_gateways=1)

        # S3 Bucket
        bucket = s3.Bucket(self, f"rednallia-data",
                           bucket_name=f"rednallia-data-{account_id}",
                           versioned=True,
                           block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                           removal_policy=RemovalPolicy.DESTROY)

        # Security Group for RDS
        rds_security_group = ec2.SecurityGroup(self, "RdsSecurityGroup",
                                               vpc=vpc,
                                               description="Allow access to RDS",
                                               allow_all_outbound=True)
        rds_security_group.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block),
                                            ec2.Port.tcp(5432), "Allow internal VPC access to RDS")

        secret = sm.Secret(
            self, "RDSSecret",
            secret_name="rednallia_rds_secret",
            removal_policy=RemovalPolicy.DESTROY,
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"username":"gebruikersnaam", "password":""}',
                generate_string_key="password"
            )
        )

        
        # RDS PostgreSQL Database
        db_instance = rds.DatabaseInstance(self, "RednalliaRDS",
                                           engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_14),
                                           instance_type=ec2.InstanceType("t4g.micro"),
                                           vpc=vpc,
                                           security_groups=[rds_security_group],
                                           multi_az=False,
                                           credentials=rds.Credentials.from_secret(secret),
                                           allocated_storage=20,
                                           database_name="rednallia_db",
                                           removal_policy=RemovalPolicy.DESTROY,
                                           deletion_protection=False)
        # Lambda Layer
        layer = _lambda.LayerVersion(self, "PandasPsycopg2Layer",
                                     code=_lambda.Code.from_asset(os.path.join(os.path.dirname(__file__), "lambda/pandas_psycopg2_layer.zip")),
                                     compatible_runtimes=[_lambda.Runtime.PYTHON_3_8],
                                     description="Pandas and psycopg2-binary packages",
                                     removal_policy=RemovalPolicy.DESTROY)
        # Lambda Function
        lambda_function = _lambda.Function(self, "RednalliaLambda",
                                           runtime=_lambda.Runtime.PYTHON_3_8,
                                           handler="lambda_function.handler",
                                           code=_lambda.Code.from_asset(os.path.join(os.path.dirname(__file__), "lambda")),
                                           vpc=vpc,
                                           layers=[layer],
                                           security_groups=[rds_security_group],
                                           environment={
                                               'BUCKET': bucket.bucket_name,
                                               'DB_NAME': db_instance.instance_identifier,
                                               'SECRET': secret.secret_name,
                                               'DB_HOST': db_instance.db_instance_endpoint_address,
                                               'DB_PORT': db_instance.db_instance_endpoint_port
                                           })
        # Add S3 event notification to trigger the Lambda function on file upload
        notification = s3_notifications.LambdaDestination(lambda_function)
        bucket.add_event_notification(s3.EventType.OBJECT_CREATED, notification)


    
        # Grant permissions
        secret.grant_read(lambda_function)        
        bucket.grant_read_write(lambda_function)
        db_instance.grant_connect(lambda_function)
