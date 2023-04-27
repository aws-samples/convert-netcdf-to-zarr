# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

FROM amazonlinux:2

RUN yum update -y
RUN yum install wget -y

RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
RUN bash Miniconda3-latest-Linux-x86_64.sh -b -p /miniconda
ENV PATH=$PATH:/miniconda/pcondabin:/miniconda/bin
COPY ./environment.yml .
RUN conda install -y mamba -c conda-forge
RUN mamba env update --name base --file ./environment.yml && conda clean -tipy