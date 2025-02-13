import logging

from ray.rllib.agents.a3c.a3c_tf_policy import A3CTFPolicy
from ray.rllib.agents.trainer import with_common_config
from ray.rllib.agents.trainer_template import build_trainer
from ray.rllib.evaluation.worker_set import WorkerSet
from ray.rllib.execution.rollout_ops import AsyncGradients
from ray.rllib.execution.train_ops import ApplyGradients
from ray.rllib.execution.metric_ops import StandardMetricsReporting
from ray.rllib.execution.rollout_ops import ParallelRollouts, ConcatBatches
from ray.rllib.execution.train_ops import ComputeGradients, AverageGradients, \
    ApplyGradients, TrainTFMultiGPU, TrainOneStep

logger = logging.getLogger(_name_)

# yapf: disable
# _sphinx_doc_begin_
DEFAULT_CONFIG = with_common_config({
    # Should use a critic as a baseline (otherwise don't use value baseline;
    # required for using GAE).
    "use_critic": True,
    # If true, use the Generalized Advantage Estimator (GAE)
    # with a value function, see https://arxiv.org/pdf/1506.02438.pdf.
    "use_gae": True,
    # Size of rollout batch
    "rollout_fragment_length": 10,
    # GAE(gamma) parameter
    "lambda": 1.0,
    # Max global norm for each gradient calculated by worker
    "grad_clip": 40.0,
    # Learning rate
    "lr": 0.0001,
    # Learning rate schedule
    "lr_schedule": None,
    # Value Function Loss coefficient
    "vf_loss_coeff": 0.5,
    # Entropy coefficient
    "entropy_coeff": 0.01,
    # Min time per iteration
    "min_iter_time_s": 5,
    # Workers sample async. Note that this increases the effective
    # rollout_fragment_length by up to 5x due to async buffering of batches.
    "sample_async": True,
})
# _sphinx_doc_end_
# yapf: enable


def get_policy_class(config):
    if config["framework"] == "torch":
        from ray.rllib.agents.a3c.a3c_torch_policy import \
            A3CTorchPolicy
        return A3CTorchPolicy
    else:
        return A3CTFPolicy


def validate_config(config):
    if config["entropy_coeff"] < 0:
        raise ValueError("`entropy_coeff` must be >= 0.0!")
    if config["num_workers"] <= 0 and config["sample_async"]:
        raise ValueError("`num_workers` for A3C must be >= 1!")

from itertools import chain
def execution_plan(workers, config):
    # For A3C, compute policy gradients remotely on the rollout workers.
    # rollouts = ParallelRollouts(workers, mode="bulk_sync")

    grads = AsyncGradients(workers)
    
    # Apply the gradients as they arrive. We set update_all to False so that
    # only the worker sending the gradient is updated with new weights.
    #train_op = grads.for_each(ApplyGradients(workers, update_all=False))
    print("_____")
    print(workers)
    temp1 = workers
    temp2 = workers
    rem1 = workers.remote_workers()[0:6]
    rem2 = workers.remote_workers()[6:11]
    temp1.reset(rem1)
    temp2.reset(rem2)
  
    rollouts1 = ParallelRollouts(temp1, mode="bulk_sync")
    rollouts2 = ParallelRollouts(temp2, mode="bulk_sync")


    train_step_op1 = TrainTFMultiGPU(
                workers=temp1,
                sgd_minibatch_size=config["train_batch_size"],
                num_sgd_iter=1,
                num_gpus=config["num_gpus"],
                shuffle_sequences=True,
                _fake_gpus=config["_fake_gpus"],
                framework=config.get("framework"))

    train_step_op2 = TrainTFMultiGPU(
                    workers=temp2,
                    sgd_minibatch_size=config["train_batch_size"],
                    num_sgd_iter=1,
                    num_gpus=config["num_gpus"],
                    shuffle_sequences=True,
                    _fake_gpus=config["_fake_gpus"],
                    framework=config.get("framework"))

    train_op1 = rollouts1.combine(
            ConcatBatches(
                min_batch_size=config["train_batch_size"],
                count_steps_by=config["multiagent"][
                    "count_steps_by"])).for_each(train_step_op1)
    train_op2 = rollouts2.combine(
            ConcatBatches(
                min_batch_size=config["train_batch_size"],
                count_steps_by=config["multiagent"][
                    "count_steps_by"])).for_each(train_step_op2)
    
    #train_op = grads.for_each(ApplyGradients(workers, update_all=False))
    
    
    return StandardMetricsReporting(train_op1, temp1, config).union(StandardMetricsReporting(train_op2, temp2, config))


A3CTrainer = build_trainer(
    name="A3C",
    default_config=DEFAULT_CONFIG,
    default_policy=A3CTFPolicy,
    get_policy_class=get_policy_class,
    validate_config=validate_config,
    execution_plan=execution_plan)
