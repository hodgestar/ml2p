# -*- coding: utf-8 -*-

""" Tests for ml2p.cli_utils. """

import datetime
from pkg_resources import resource_filename
import pytest

from ml2p import cli_utils
from ml2p.cli import ModellingProject


class TestCliUtils:
    def test_date_to_string_serializer(self):
        value = datetime.datetime(1, 1, 1)
        assert cli_utils.date_to_string_serializer(value) == "0001-01-01 00:00:00"
        with pytest.raises(TypeError) as exc_info:
            cli_utils.date_to_string_serializer("")
        assert str(exc_info.value) == ""

    def test_click_echo_json(self, capsys):
        response = {"NotebookInstanceName": "notebook-1"}
        cli_utils.click_echo_json(response)
        assert (
            capsys.readouterr().out == '{\n  "NotebookInstanceName": "notebook-1"\n}\n'
        )

    def test_endpoint_url_for_arn(self):
        endpoint_arn = (
            "arn:aws:sagemaker:eu-west-1:123456789012:endpoint/endpoint-20190612"
        )
        assert cli_utils.endpoint_url_for_arn(endpoint_arn) == (
            "https://runtime.sagemaker.eu-west-1.amazonaws.com/"
            "endpoints/endpoint-20190612/invocations"
        )
        assert cli_utils.endpoint_url_for_arn("") is None

    def test_mk_training_job(self):
        cfg = resource_filename("tests.fixture_files", "ml2p.yml")
        prj = ModellingProject(cfg)
        training_job_cfg = cli_utils.mk_training_job(prj, "training-job-1", "dataset-1")
        assert training_job_cfg == {
            "TrainingJobName": "modelling-project-training-job-1",
            "AlgorithmSpecification": {
                "TrainingImage": (
                    "123456789012.dkr.ecr.eu-west-1"
                    ".amazonaws.com/modelling-project-sagemaker:latest"
                ),
                "TrainingInputMode": "File",
            },
            "EnableNetworkIsolation": True,
            "HyperParameters": {},
            "InputDataConfig": [
                {
                    "ChannelName": "training",
                    "DataSource": {
                        "S3DataSource": {
                            "S3DataType": "S3Prefix",
                            "S3Uri": "s3://prodigyfinance-modelling-project-"
                            "sagemaker-production/datasets/dataset-1",
                        }
                    },
                }
            ],
            "OutputDataConfig": {
                "S3OutputPath": "s3://prodigyfinance-modelling-project"
                "-sagemaker-production/models/"
            },
            "ResourceConfig": {
                "InstanceCount": 1,
                "InstanceType": "ml.m5.2xlarge",
                "VolumeSizeInGB": 20,
            },
            "RoleArn": "arn:aws:iam::111111111111:role/modelling-project",
            "StoppingCondition": {"MaxRuntimeInSeconds": 60 * 60},
            "Tags": [{"Key": "ml2p-project", "Value": "modelling-project"}],
        }

    def test_mk_model(self):
        cfg = resource_filename("tests.fixture_files", "ml2p.yml")
        prj = ModellingProject(cfg)
        model_cfg = cli_utils.mk_model(prj, "model-1", "training-job-1")
        assert model_cfg == {
            "ModelName": "modelling-project-model-1",
            "PrimaryContainer": {
                "Image": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/"
                "modelling-project-sagemaker:latest",
                "ModelDataUrl": "s3://prodigyfinance-modelling-project-sagemaker"
                "-production/models/modelling-project-training-job-1/"
                "output/model.tar.gz",
                "Environment": {"ML2P_MODEL_VERSION": "modelling-project-model-1"},
            },
            "ExecutionRoleArn": "arn:aws:iam::111111111111:role/modelling-project",
            "Tags": [{"Key": "ml2p-project", "Value": "modelling-project"}],
            "EnableNetworkIsolation": False,
        }
