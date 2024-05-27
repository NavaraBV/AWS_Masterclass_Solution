from aws_cdk import core
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_rds as rds
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam

class RednalliaStack(core.Stack):
    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        account_id = core.Stack.of(self).account
        
        # VPC
        vpc = ec2.Vpc(self, "RednalliaVPC",
                      max_azs=3,
                      nat_gateways=1)

        # S3 Bucket
        bucket = s3.Bucket(self, f"rednallia-data-{account_id}",
                           versioned=True,
                           block_public_access=s3.BlockPublicAccess.BLOCK_ALL)

        # Security Group for RDS
        rds_security_group = ec2.SecurityGroup(self, "RdsSecurityGroup",
                                               vpc=vpc,
                                               description="Allow access to RDS",
                                               allow_all_outbound=True)
        rds_security_group.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block),
                                            ec2.Port.tcp(5432), "Allow internal VPC access to RDS")

        # RDS PostgreSQL Database
        db_instance = rds.DatabaseInstance(self, "RednalliaRDS",
                                           engine=rds.DatabaseInstanceEngine.postgres(
                                               version=rds.PostgresEngineVersion.VER_14_2),
                                           instance_type=ec2.InstanceType.of(
                                               ec2.InstanceClass.BURSTABLE2, ec2.InstanceSize.MICRO),
                                           vpc=vpc,
                                           security_groups=[rds_security_group],
                                           multi_az=True,
                                           allocated_storage=100,
                                           storage_encrypted=True,
                                           database_name="rednallia_db",
                                           removal_policy=core.RemovalPolicy.DESTROY,
                                           deletion_protection=False)

        # Lambda Function
        lambda_function = _lambda.Function(self, "RednalliaLambda",
                                           runtime=_lambda.Runtime.PYTHON_3_10,
                                           handler="lambda_function.handler",
                                           code=_lambda.Code.from_asset("lambda"),
                                           vpc=vpc,
                                           security_groups=[rds_security_group],
                                           environment={
                                               'BUCKET': bucket.bucket_name,
                                               'DB_NAME': db_instance.db_name,
                                               'DB_USER': db_instance.secret.secret_value_from_json('username').to_string(),
                                               'DB_PASSWORD': db_instance.secret.secret_value_from_json('password').to_string(),
                                               'DB_HOST': db_instance.db_instance_endpoint_address,
                                               'DB_PORT': db_instance.db_instance_endpoint_port
                                           })

        # Grant permissions
        bucket.grant_read_write(lambda_function)
        db_instance.grant_connect(lambda_function)
