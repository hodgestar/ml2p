# -*- coding: utf-8 -*-

""" ML2P core utilities.
"""

import datetime
import enum
import importlib
import json
import os
import pathlib
import urllib.parse
import uuid
import warnings

import boto3

from . import __version__ as ml2p_version
from . import hyperparameters


class S3URL:
    """ A friendly interface to an S3 URL. """

    def __init__(self, s3folder):
        self._s3url = urllib.parse.urlparse(s3folder)
        self._s3root = self._s3url.path.strip("/")

    def bucket(self):
        return self._s3url.netloc

    def path(self, suffix):
        path = self._s3root + "/" + suffix.lstrip("/")
        return path.lstrip("/")  # handles empty s3root

    def url(self, suffix=""):
        return "s3://{}/{}".format(self._s3url.netloc, self.path(suffix))


class SageMakerEnvType(enum.Enum):
    """ The type of SageMakerEnvironment.
    """

    TRAIN = "train"
    SERVE = "serve"


class SageMakerEnv:
    """ An interface to the SageMaker docker environment.

        Attributes that are expected to be available in both training and serving
        environments:

        * `env_type` - Whether this is a training or serving environment
          (type: ml2p.core.SageMakerEnvType).

        * `project` - The ML2P project name (type: str).

        * `model_cls` - The fulled dotted Python name of the ml2p.core.Model class to
          be used for training and prediction (type: str). This may be None if the
          docker image itself specifies the name with `ml2p-docker --model ...`.

        * `s3` - The URL of the project S3 bucket (type: ml2p.core.S3URL).

        Attributes that are only expected to be available while training (and that will
        be None when serving the model):

        * `training_job_name` - The full job name of the training job (type: str).

        Attributes that are only expected to be available while serving the model (and
        that will be None when serving the model):

        * `model_version` - The full job name of the deployed model, or None
          during training (type: str).

        * `record_invokes` - Whether to store a record of each invocation of the
          endpoint in S3 (type: bool).

        In the training environment settings are loaded from hyperparameters stored by
        ML2P when the training job is created.

        In the serving environment settings are loaded from environment variables stored
        by ML2P when the model is created.
    """

    TRAIN = SageMakerEnvType.TRAIN
    SERVE = SageMakerEnvType.SERVE

    def __init__(self, ml_folder):
        self._ml_folder = pathlib.Path(ml_folder)
        if "TRAINING_JOB_NAME" in os.environ:
            # this is a training job instance
            self.env_type = self.TRAIN
            environ = self.hyperparameters().get("ML2P_ENV", {})
            self.training_job_name = os.environ.get("TRAINING_JOB_NAME", None)
            self.model_version = None
            self.record_invokes = None
        else:
            # this is a serving instance
            self.env_type = self.SERVE
            environ = os.environ
            self.training_job_name = None
            self.model_version = environ.get("ML2P_MODEL_VERSION", None)
            self.record_invokes = environ.get("ML2P_RECORD_INVOKES", "false") == "true"
        self.project = environ.get("ML2P_PROJECT", None)
        self.model_cls = environ.get("ML2P_MODEL_CLS", None)
        self.s3 = None
        if "ML2P_S3_URL" in environ:
            self.s3 = S3URL(environ["ML2P_S3_URL"])

    def hyperparameters(self):
        hp_path = self._ml_folder / "input" / "config" / "hyperparameters.json"
        if not hp_path.exists():
            return {}
        with hp_path.open() as f:
            return hyperparameters.decode(json.load(f))

    def resourceconfig(self):
        rc_path = self._ml_folder / "input" / "config" / "resourceconfig.json"
        if not rc_path.exists():
            return {}
        with rc_path.open() as f:
            return json.load(f)

    def dataset_folder(self, dataset=None):
        if dataset is None:
            dataset = "training"
        else:
            warnings.warn(
                "Passing a dataset name to dataset_folder method(...) is deprecated."
                " If you wish to access the ML2P training dataset, do not pass any"
                " parameters. If you wish to access data for a specific channel, please"
                " use data_channel_folder(...) instead, which matches the terminology"
                " used by AWS SageMaker more accurately.",
                DeprecationWarning,
            )
        return self._ml_folder / "input" / "data" / dataset

    def data_channel_folder(self, channel):
        return self._ml_folder / "input" / "data" / channel

    def model_folder(self):
        return self._ml_folder / "model"

    def write_failure(self, text):
        with open(self._ml_folder / "output" / "failure", "w") as f:
            f.write(text)


def import_string(name):
    """ Import a class given its absolute name.

        :param str name:
            The name of the model, e.g. mypackage.submodule.ModelTrainerClass.
    """
    modname, _, classname = name.rpartition(".")
    mod = importlib.import_module(modname)
    return getattr(mod, classname)


class ModelTrainer:
    """ An interface that allows ml2p-docker to train models within SageMaker.
    """

    def __init__(self, env):
        self.env = env

    def train(self):
        """ Train the model.

            This method should:

            * Read training data (using self.env to determine where to read data from).
            * Train the model.
            * Write the model out (using self.env to determine where to write the model
              to).
            * Write out any validation or model analysis alongside the model.
        """
        raise NotImplementedError("Sub-classes should implement .train()")


class ModelPredictor:
    """ An interface that allows ml2p-docker to make predictions from a model within
        SageMaker.
    """

    def __init__(self, env):
        self.env = env
        self.s3_client = boto3.client("s3")

    def setup(self):
        """ Called once before any calls to .predict(...) are made.

            This method should:

            * Load the model (using self.env to determine where to read the model from).
            * Allocate any other resources needed in order to make predictions.
        """
        pass

    def teardown(self):
        """ Called once after all calls to .predict(...) have ended.

            This method should:

            * Cleanup any resources acquired in .setup().
        """
        pass

    def invoke(self, data):
        """ Invokes the model and returns the full result.

            :param dict data:
                The input data the model is being invoked with.
            :rtype: dict
            :returns:
                The result as a dictionary.

            By default this method results a dictionary containing:

              * metadata: The result of calling .metadata().
              * result: The result of calling .result(data).
        """
        prediction = {"metadata": self.metadata(), "result": self.result(data)}
        if self.env.record_invokes:
            self.record_invoke(data, prediction)
        return prediction

    def metadata(self):
        """ Return metadata for a prediction that is about to be made.

            :rtype: dict
            :returns:
                The metadata as a dictionary.

            By default this method returns a dictionary containing:

              * model_version: The ML2P_MODEL_VERSION (str).
              * timestamp: The UTC POSIX timestamp in seconds (float).
        """
        return {
            "model_version": self.env.model_version,
            "ml2p_version": ml2p_version,
            "timestamp": datetime.datetime.utcnow().timestamp(),
        }

    def result(self, data):
        """ Make a prediction given the input data.

            :param dict data:
                The input data to make a prediction from.
            :rtype: dict
            :returns:
                The prediction result as a dictionary.
        """
        raise NotImplementedError("Sub-classes should implement .result(...)")

    def batch_invoke(self, data):
        """ Invokes the model on a batch of input data and returns the full result for
            each instance.

            :param dict data:
                The batch of input data the model is being invoked with.
            :rtype: list
            :returns:
                The result as a list of dictionaries.

            By default this method results a list of dictionaries containing:

              * metadata: The result of calling .metadata().
              * result: The result of calling .batch_result(data).
        """
        metadata = self.metadata()
        results = self.batch_result(data)
        predictions = [{"metadata": metadata, "result": result} for result in results]
        if self.env.record_invokes:
            for datum, prediction in zip(data, predictions):
                self.record_invoke(datum, prediction)
        return {"predictions": predictions}

    def batch_result(self, data):
        """ Make a batch prediction given a batch of input data.

            :param dict data:
                The batch of input data to make a prediction from.
            :rtype: list
            :returns:
                The list of predictions made for instance of the input data.

            This method can be overrided for sub-classes in order to improve
            performance of batch predictions.
        """
        return [self.result(datum) for datum in data]

    def record_invoke_id(self, datum, prediction):
        """ Return an id for an invocation record.

            :param dict datum:
                The dictionary of input values passed when invoking the endpoint.

            :param dict result:
                The prediction returned for datum by this predictor.

            :returns dict:
                Returns an *ordered* dictionary of key-value pairs that make up
                the unique identifier for the invocation request.

            By default this method returns a dictionary containing the following:

                * "ts": an ISO8601 formatted UTC timestamp.
                * "uuid": a UUID4 unique identifier.

            Sub-classes may override this method to return their own identifiers,
            but including these default identifiers is recommended.

            The name of the record in S3 is determined by combining the key value pairs
            with a dash ("-") and then separating each pair with a double dash ("--").
        """
        return {"ts": datetime.datetime.utcnow().isoformat(), "uuid": str(uuid.uuid4())}

    def record_invoke(self, datum, prediction):
        """ Store an invocation of the endpoint in the ML2P project S3 bucket.

            :param dict datum:
                The dictionary of input values passed when invoking the endpoint.

            :param dict result:
                The prediction returned for datum by this predictor.
        """
        invoke_id = self.record_invoke_id(datum, prediction)
        record_filename = (
            "--".join(["{}-{}".format(k, v) for k, v in invoke_id.items()]) + ".json"
        )
        record = {"input": datum, "result": prediction}
        record_bytes = json.dumps(record).encode("utf-8")
        s3_key = self.env.s3.path(
            "/predictions/{}/{}".format(self.env.model_version, record_filename)
        )
        self.s3_client.put_object(
            Bucket=self.env.s3.bucket(), Key=s3_key, Body=record_bytes
        )


class Model:
    """ A holder for a trainer and predictor.

        Sub-classes should:

        * Set the attribute TRAINER to a ModelTrainer sub-class.
        * Set the attribute PREDICTOR to a ModelPredictor sub-class.
    """

    TRAINER = None
    PREDICTOR = None

    def trainer(self, env):
        if self.TRAINER is None:
            raise ValueError(".TRAINER should be an instance of ModelTrainer")
        return self.TRAINER(env)

    def predictor(self, env):
        if self.PREDICTOR is None:
            raise ValueError(".PREDICTOR should be an instance of ModelPredictor")
        return self.PREDICTOR(env)
