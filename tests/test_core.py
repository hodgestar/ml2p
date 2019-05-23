# -*- coding: utf-8 -*-

""" Tests for ml2p.core. """

import pathlib

import pytest

from ml2p.core import ModelPredictor, ModelTrainer, SageMakerEnv, import_string


class TestSageMakerEnv:
    def test_create_env_without_model_version(self, tmpdir, monkeypatch):
        monkeypatch.delenv("ML2P_MODEL_VERSION", raising=False)
        env = SageMakerEnv(str(tmpdir))
        assert env.model_version == "Unknown"

    def test_create_env_with_model_version(self, sagemaker):
        assert sagemaker.env.model_version == "test-model-1.2.3"

    def test_hyperparameters(self, sagemaker):
        sagemaker.ml_folder.mkdir("input").mkdir("config").join(
            "hyperparameters.json"
        ).write('{"param": "value"}')
        assert sagemaker.env.hyperparameters() == {"param": "value"}

    def test_resourceconfig(self, sagemaker):
        sagemaker.ml_folder.mkdir("input").mkdir("config").join(
            "resourceconfig.json"
        ).write('{"config": "value"}')
        assert sagemaker.env.resourceconfig() == {"config": "value"}

    def test_dataset_folder(self, sagemaker):
        assert sagemaker.env.dataset_folder("foo") == pathlib.Path(
            str(sagemaker.ml_folder.join("input/data/foo"))
        )

    def test_model_folder(self, sagemaker):
        assert sagemaker.env.model_folder() == pathlib.Path(
            str(sagemaker.ml_folder.join("model"))
        )

    def test_write_failure(self, sagemaker):
        failure_path = sagemaker.ml_folder.mkdir("output").join("failure")
        text = "\n".join(["BadModel", "no biscuit"])
        sagemaker.env.write_failure(text)
        assert failure_path.read() == text


class TestImportString:
    def test_import_string(self):
        cls = import_string("tests.test_core.TestImportString")
        assert cls is TestImportString


class TestModelTrainer:
    def test_create(self, sagemaker):
        trainer = ModelTrainer(sagemaker.env)
        assert trainer.env is sagemaker.env

    def test_train(self, sagemaker):
        trainer = ModelTrainer(sagemaker.env)
        with pytest.raises(NotImplementedError) as exc_info:
            trainer.train()
        assert str(exc_info.value) == "Sub-classes should implement .train()"


class TestModelPredictor:
    def test_create(self, sagemaker):
        predictor = ModelPredictor(sagemaker.env)
        assert predictor.env is sagemaker.env

    def test_setup(self, sagemaker):
        predictor = ModelPredictor(sagemaker.env)
        predictor.setup()

    def test_teardown(self, sagemaker):
        predictor = ModelPredictor(sagemaker.env)
        predictor.teardown()

    def test_invoke_with_result_not_implemented(self, sagemaker):
        predictor = ModelPredictor(sagemaker.env)
        with pytest.raises(NotImplementedError) as exc_info:
            predictor.invoke({})
        assert str(exc_info.value) == "Sub-classes should implement .result(...)"

    def test_invoke_with_result_implemented(self, sagemaker, fake_utcnow):
        class MyPredictor(ModelPredictor):
            def result(self, data):
                return {"probability": 0.5, "input": data["input"]}

        predictor = MyPredictor(sagemaker.env)
        assert predictor.invoke({"input": 1}) == {
            "metadata": {
                "model_version": "test-model-1.2.3",
                "timestamp": 1548936002.0,
            },
            "result": {"probability": 0.5, "input": 1},
        }

    def test_metadata(self, sagemaker, fake_utcnow):
        predictor = ModelPredictor(sagemaker.env)
        assert predictor.metadata({}) == {
            "model_version": "test-model-1.2.3",
            "timestamp": 1548936002.0,
        }

    def test_result(self, sagemaker):
        predictor = ModelPredictor(sagemaker.env)
        with pytest.raises(NotImplementedError) as exc_info:
            predictor.result({})
        assert str(exc_info.value) == "Sub-classes should implement .result(...)"
