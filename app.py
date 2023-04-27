#!/usr/bin/env python3

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as cdk
from convert_to_zarr.convert_to_zarr_stack import ConvertToZarrStack
# from cdk_nag import AwsSolutionsChecks, NagSuppressions

app = cdk.App()
stack = ConvertToZarrStack(app, "ConvertToZarrStack")

# cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
# NagSuppressions.add_stack_suppressions(stack, [
#   {"id": "AwsSolutions-S1", "reason": "Public acess to bucket is blocked. Customers can choose to enable server access logs and incur costs."},  # noqa: E501
#   {"id": "AwsSolutions-VPC7", "reason": "Dask cluster and notebook are within a security group in the VPC with restricted ingress. Customer can choose to enable VPC flow logs and incur costs."},  # noqa: E501
#   {"id": "AwsSolutions-ELB2", "reason": "Customer can choose to enable ELB access logs."}
# ])

app.synth()
