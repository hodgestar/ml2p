# -*- coding: utf-8 -*-

""" Tests for ml2p.cli_utils. """

import base64
import datetime
from unittest.mock import patch

import pytest
from pkg_resources import resource_filename

from ml2p import cli_utils
from ml2p.cli import ModellingProject


@pytest.fixture
def prj():
    with patch("boto3.client"):
        cfg = resource_filename("tests.fixture_files", "ml2p.yml")
        prj = ModellingProject(cfg)
    return prj


@pytest.fixture
def prj_no_vpc():
    with patch("boto3.client"):
        cfg_no_vpc = resource_filename("tests.fixture_files", "ml2p-no-vpc.yml")
        prj_no_vpc = ModellingProject(cfg_no_vpc)
    return prj_no_vpc


def on_start_fixture():
    with open(resource_filename("tests.fixture_files", "on_start.sh"), "rb") as f:
        return f.read()


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

    def test_mk_training_job(self, prj):
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
            "HyperParameters": {
                "ML2P_ENV.ML2P_PROJECT": '"modelling-project"',
                "ML2P_ENV.ML2P_S3_URL": (
                    '"s3://prodigyfinance-modelling-project-sagemaker-production/"'
                ),
            },
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

    def test_mk_model(self, prj):
        model_cfg = cli_utils.mk_model(prj, "model-1", "training-job-1")
        assert model_cfg == {
            "ModelName": "modelling-project-model-1",
            "PrimaryContainer": {
                "Image": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/"
                "modelling-project-sagemaker:latest",
                "ModelDataUrl": "s3://prodigyfinance-modelling-project-sagemaker"
                "-production/models/modelling-project-training-job-1/"
                "output/model.tar.gz",
                "Environment": {
                    "ML2P_MODEL_VERSION": "modelling-project-model-1",
                    "ML2P_PROJECT": "modelling-project",
                    "ML2P_S3_URL": (
                        "s3://prodigyfinance-modelling-project-sagemaker-production/"
                    ),
                },
            },
            "ExecutionRoleArn": "arn:aws:iam::111111111111:role/modelling-project",
            "Tags": [{"Key": "ml2p-project", "Value": "modelling-project"}],
            "EnableNetworkIsolation": False,
        }

    def test_mk_endpoint_config(self, prj):
        endpoint_cfg = cli_utils.mk_endpoint_config(prj, "endpoint-1", "model-1")
        assert endpoint_cfg == {
            "EndpointConfigName": "modelling-project-endpoint-1-config",
            "ProductionVariants": [
                {
                    "VariantName": "modelling-project-model-1-variant-1",
                    "ModelName": "modelling-project-model-1",
                    "InitialInstanceCount": 1,
                    "InstanceType": "ml.t2.medium",
                    "InitialVariantWeight": 1.0,
                }
            ],
            "Tags": [{"Key": "ml2p-project", "Value": "modelling-project"}],
        }

    def test_mk_notebook(self, prj):
        notebook_cfg_no_repo = cli_utils.mk_notebook(prj, "notebook-1")
        assert notebook_cfg_no_repo == {
            "NotebookInstanceName": "modelling-project-notebook-1",
            "DirectInternetAccess": "Disabled",
            "InstanceType": "ml.t2.medium",
            "RoleArn": "arn:aws:iam::111111111111:role/modelling-project",
            "Tags": [{"Key": "ml2p-project", "Value": "modelling-project"}],
            "LifecycleConfigName": "modelling-project-notebook-1-lifecycle-config",
            "VolumeSizeInGB": 8,
            "SubnetId": "subnet-1",
            "SecurityGroupIds": ["sg-1"],
        }
        notebook_cfg_repo = cli_utils.mk_notebook(
            prj, "notebook-1", repo_name="notebook-1-repo"
        )
        assert notebook_cfg_repo == {
            "NotebookInstanceName": "modelling-project-notebook-1",
            "InstanceType": "ml.t2.medium",
            "DirectInternetAccess": "Disabled",
            "RoleArn": "arn:aws:iam::111111111111:role/modelling-project",
            "Tags": [{"Key": "ml2p-project", "Value": "modelling-project"}],
            "LifecycleConfigName": "modelling-project-notebook-1-lifecycle-config",
            "VolumeSizeInGB": 8,
            "DefaultCodeRepository": "modelling-project-notebook-1-repo",
            "SubnetId": "subnet-1",
            "SecurityGroupIds": ["sg-1"],
        }

    def test_mk_notebook_no_onstart(self, prj_no_vpc):
        notebook_cfg_no_vpc = cli_utils.mk_notebook(prj_no_vpc, "notebook-1")
        assert notebook_cfg_no_vpc == {
            "NotebookInstanceName": "modelling-project-notebook-1",
            "InstanceType": "ml.t2.medium",
            "DirectInternetAccess": "Disabled",
            "RoleArn": "arn:aws:iam::111111111111:role/modelling-project",
            "Tags": [{"Key": "ml2p-project", "Value": "modelling-project"}],
            "LifecycleConfigName": "modelling-project-notebook-1-lifecycle-config",
            "VolumeSizeInGB": 8,
        }

    def test_mk_notebook_with_direct_internet_access_enabled(self, prj):
        prj.cfg["notebook"]["direct_internet_access"] = "Enabled"
        notebook_cfg = cli_utils.mk_notebook(prj, "notebook-1")
        assert notebook_cfg["DirectInternetAccess"] == "Enabled"

    def test_mk_notebook_with_direct_internet_access_disabled_by_default(self, prj):
        notebook_cfg = cli_utils.mk_notebook(prj, "notebook-1")
        assert notebook_cfg["DirectInternetAccess"] == "Disabled"

    def test_mk_lifecycle_config(self, prj):
        notebook_lifecycle_cfg = cli_utils.mk_lifecycle_config(prj, "notebook-1")
        assert (
            base64.b64decode(notebook_lifecycle_cfg["OnStart"][0]["Content"])
            == on_start_fixture()
        )
        assert notebook_lifecycle_cfg == {
            "NotebookInstanceLifecycleConfigName": "modelling-project-"
            "notebook-1-lifecycle-config",
            "OnStart": [
                {"Content": base64.b64encode(on_start_fixture()).decode("utf-8")}
            ],
        }

    def test_mk_lifecycle_config_no_onstart(self, prj_no_vpc):
        notebook_lifecycle_cfg_no_onstart = cli_utils.mk_lifecycle_config(
            prj_no_vpc, "notebook-1"
        )
        assert notebook_lifecycle_cfg_no_onstart == {
            "NotebookInstanceLifecycleConfigName": "modelling-project-"
            "notebook-1-lifecycle-config"
        }

    def test_mk_repo(self, prj):
        repo_cfg = cli_utils.mk_repo(prj, "repo-1")
        assert repo_cfg == {
            "CodeRepositoryName": "modelling-project-repo-1",
            "GitConfig": {
                "RepositoryUrl": "https://github.example.com/modelling-project",
                "Branch": "master",
                "SecretArn": "arn:aws:secretsmanager:eu-west-1:111111111111:"
                "secret:sagemaker-github-authentication-fLJGfa",
            },
        }
