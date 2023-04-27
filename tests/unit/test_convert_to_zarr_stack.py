# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as core
import aws_cdk.assertions as assertions

from convert_to_zarr.convert_to_zarr_stack import ConvertToZarrStack


# example tests. To run these tests, uncomment this file along with the example
# resource in convert_to_zarr/convert_to_zarr_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = ConvertToZarrStack(app, "convert-to-zarr")
    template = assertions.Template.from_stack(stack)  # noqa:F841

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
