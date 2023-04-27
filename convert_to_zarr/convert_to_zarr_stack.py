# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_logs as logs,
    aws_iam as iam,
    aws_s3 as s3,
    aws_kms as kms,
    aws_sagemaker as sagemaker,
    aws_elasticloadbalancingv2 as elb,
    aws_servicediscovery as sd
)
from aws_cdk.aws_ecr_assets import DockerImageAsset
from constructs import Construct


class ConvertToZarrStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket

        bucket = s3.Bucket(
            self,
            "Convert-To-Zarr",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            encryption=s3.BucketEncryption.S3_MANAGED)

        # VPC networking

        vpc = ec2.Vpc(
            self,
            "Convert-To-Zarr-Vpc",
            max_azs=1,
            gateway_endpoints={"s3": ec2.GatewayVpcEndpointOptions(service=ec2.GatewayVpcEndpointAwsService.S3)}
        )

        public_subnets = vpc.public_subnets
        private_subnets = vpc.private_subnets

        # Dask Cluster setup

        dask_asset = DockerImageAsset(
            self, "dask", directory="./docker", file="Dockerfile"
        )

        s_logs = logs.LogGroup(
            self, 'Dask-Scheduler-logs',
            log_group_name='Scheduler-logs',
            removal_policy=RemovalPolicy.DESTROY)

        w_logs = logs.LogGroup(
            self, 'Dask-Worker-logs',
            log_group_name='Worker-logs',
            removal_policy=RemovalPolicy.DESTROY)

        nRole = iam.Role(self, 'ECSExecutionRole', assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'))

        nPolicy = iam.Policy(self, "ECSExecutionPolicy", policy_name="ECSExecutionPolicy")
        nPolicy.add_statements(iam.PolicyStatement(
            actions=[
                'ecr:BatchCheckLayerAvailability',
                'ecr:GetDownloadUrlForLayer',
                'ecr:BatchGetImage',
                'ecr:GetAuthorizationToken'],
            # resources=[f'arn:aws:ecr:{self.region}:{self.account}:repository/*'])
            resources=[dask_asset.repository.repository_arn])
        )

        nPolicy.add_statements(iam.PolicyStatement(
            actions=[
                'logs:CreateLogStream',
                'logs:PutLogEvents'],
            resources=[
                s_logs.log_group_arn,
                w_logs.log_group_arn])
        )
        nPolicy.add_statements(iam.PolicyStatement(
            actions=[
                "s3:ListBucket",
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:GetObjectAcl",
                "s3:DeleteObject"
            ],
            resources=[bucket.bucket_arn, bucket.arn_for_objects("*")])
        )
        nPolicy.attach_to_role(nRole)

        cluster = ecs.Cluster(
            self, 'Dask-Cluster',
            vpc=vpc,
            container_insights=True,
            cluster_name='Dask-Cluster')

        nspace = cluster.add_default_cloud_map_namespace(  # noqa: F841
            name='local-dask',
            type=sd.NamespaceType.DNS_PRIVATE, vpc=vpc)

        # Dask Scheduler

        schedulerTask = ecs.TaskDefinition(
            self, 'taskDefinitionScheduler',
            compatibility=ecs.Compatibility.FARGATE,
            cpu='8192', memory_mib='16384',
            network_mode=ecs.NetworkMode.AWS_VPC,
            placement_constraints=None, execution_role=nRole,
            family='Dask-Scheduler', task_role=nRole
        )

        schedulerTask.add_container(
            'DaskSchedulerImage', image=ecs.ContainerImage.from_docker_image_asset(dask_asset),
            command=['dask', 'scheduler'], cpu=8192, essential=True,
            logging=ecs.LogDriver.aws_logs(stream_prefix='ecs', log_group=s_logs),
            memory_limit_mib=16384, memory_reservation_mib=16384)

        # Dask Worker

        workerTask = ecs.TaskDefinition(
            self, 'taskDefinitionWorker',
            compatibility=ecs.Compatibility.FARGATE,
            cpu='8192', memory_mib='16384',
            network_mode=ecs.NetworkMode.AWS_VPC,
            placement_constraints=None, execution_role=nRole,
            family='Dask-Worker', task_role=nRole)

        workerTask.add_container(
            'DaskWorkerImage', image=ecs.ContainerImage.from_docker_image_asset(dask_asset),
            command=[
                'dask', 'worker', 'dask-scheduler.local-dask:8786',
                '--worker-port', '9000', '--nanny-port', '9001'
            ],
            cpu=8192, essential=True,
            logging=ecs.LogDriver.aws_logs(stream_prefix='ecs', log_group=w_logs),
            memory_limit_mib=16384, memory_reservation_mib=16384)

        # Dask security group

        sg = ec2.SecurityGroup(
            self, 'DaskSecurityGroup',
            vpc=vpc, description='Enable Scheduler ports access',
            security_group_name='DaskSecurityGroup')

        sg.connections.allow_from(
            ec2.Peer.ipv4(public_subnets[0].ipv4_cidr_block),
            ec2.Port.tcp_range(8786, 8789),
            'Inbound dask from public subnet'
        )
        sg.connections.allow_internally(
            ec2.Port.all_tcp(),
            'Inbound from within the SG'
        )

        # Dask Cluster services

        cmap1 = ecs.CloudMapOptions(dns_ttl=Duration.seconds(60), failure_threshold=10, name='Dask-Scheduler')

        schedulerService = ecs.FargateService(  # noqa: F841
            self, 'DaskSchedulerService',
            task_definition=schedulerTask,
            security_groups=[sg],
            cluster=cluster, desired_count=1,
            max_healthy_percent=200, min_healthy_percent=100,
            service_name='Dask-Scheduler', cloud_map_options=cmap1)

        cmap2 = ecs.CloudMapOptions(dns_ttl=Duration.seconds(60), failure_threshold=10, name='Dask-Worker')

        workerService = ecs.FargateService(  # noqa: F841
            self, 'DaskWorkerService',
            task_definition=workerTask,
            security_groups=[sg],
            cluster=cluster, desired_count=1,
            max_healthy_percent=200, min_healthy_percent=100,
            service_name='Dask-Worker', cloud_map_options=cmap2)

        # SageMaker notebook instance (in the same private subnet as Dask Cluster)

        smRole = iam.Role(
            self,
            "notebookAccessRole",
            assumed_by=iam.ServicePrincipal('sagemaker.amazonaws.com'))

        smPolicy = iam.Policy(self, "notebookAccessPolicy", policy_name="notebookAccessPolicy")

        smPolicy.add_statements(iam.PolicyStatement(
            actions=[
                "s3:ListBucket",
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:GetObjectAcl",
                "s3:DeleteObject"
            ],
            resources=[bucket.bucket_arn, bucket.arn_for_objects("*")])
        )
        smPolicy.add_statements(iam.PolicyStatement(
            actions=[
                'ecs:ListClusters',
                'ecs:ListServices',
                'ecs:ListTasks',
                'ecs:DescribeClusters',
                'ecs:DescribeServices',
                'ecs:DescribeTasks',
                'ecs:UpdateService',
                'ecs:RunTask',
                'ecs:StartTask',
                'ecs:StopTask'
            ],
            resources=[cluster.cluster_arn, schedulerService.service_arn, workerService.service_arn])
        )
        smPolicy.attach_to_role(smRole)

        nb_kms_key = kms.Key(self, "Convert-To-Zarr-Notebook-Key", enable_key_rotation=True)

        notebook = sagemaker.CfnNotebookInstance(  # noqa: F841
            self,
            'Convert-To-Zarr-Notebook',
            instance_type='ml.t3.2xlarge',
            volume_size_in_gb=50,
            security_group_ids=[sg.security_group_id],
            subnet_id=private_subnets[0].subnet_id,
            direct_internet_access='Disabled',
            notebook_instance_name='Convert-To-Zarr-Notebook',
            role_arn=smRole.role_arn,
            root_access='Enabled',
            kms_key_id=nb_kms_key.key_id
        )

        # Network Load balancer in public subnet to forward requests to Dask Scheduler

        nlb = elb.NetworkLoadBalancer(
            self,
            id='dask-dashboard-nlb',
            vpc=vpc,
            internet_facing=True
        )
        listener = nlb.add_listener("listener", port=80)
        nlb_tg = elb.NetworkTargetGroup(
            self,
            id="dask-scheduler-tg",
            target_type=elb.TargetType.IP,
            protocol=elb.Protocol.TCP,
            port=8787,
            vpc=vpc
        )
        listener.add_target_groups("fwd-to-dask-scheduler-tg", nlb_tg)
