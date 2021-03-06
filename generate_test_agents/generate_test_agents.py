from typing import List, Dict
import dill
import time
import yaml
import argparse
import logging
import os

import numpy as np
import gym_connect4


import regym
from regym.rl_algorithms import AgentHook
from regym.training_schemes import SelfPlayTrainingScheme
from regym.environments import generate_task, EnvType
from regym.util.experiment_parsing import initialize_agents
from regym.util.experiment_parsing import initialize_training_schemes
from regym.util.experiment_parsing import filter_relevant_configurations
from regym.rl_loops.multiagent_loops import self_play_training


def generate_test_agents(task: 'Task', sp_schemes: List, agents: List,
                         exper_config: Dict):
    for sp_scheme in sp_schemes:
        for agent in agents:
            train(task, agent, sp_scheme,
                  training_episodes=int(exper_config['training_episodes']),
                  save_interval=int(exper_config['save_interval']),
                  base_path=f"{exper_config['experiment_id']}")
            dill.dump(sp_scheme, open(f"{exper_config['experiment_id']}/{sp_scheme.name}.dill", 'wb'))


def train(task: 'Task', training_agent: 'Agent',
          self_play_scheme: SelfPlayTrainingScheme,
          training_episodes: int, save_interval: int,
          base_path: str):
    """
    :param task: Task on which agents will be trained
    :param training_agent: agent representation + training algorithm which will be trained in this process
    :param self_play_scheme: self play scheme used to meta train the param training_agent.
    :param training_episodes: total amount of training episodes
    :param save_interval: Number of episodes to elapse before saving :param: training_agent to disk
    :param base_path: Base directory from where subdirectories will be accessed to reach menageries, save episodic rewards and save checkpoints of agents.
    """

    logger = logging.getLogger(f'TRAINING: Task: {task.name}. SP: {self_play_scheme.name}. Agent: {training_agent.name}')
    logger.info('Started')

    menagerie, menagerie_path = [], f'{base_path}/menagerie'
    agents_to_benchmark = [] # Come up with better name

    if not os.path.exists(base_path):
        os.makedirs(base_path)
        os.mkdir(menagerie_path)

    completed_iterations, start_time = 0, time.time()

    trained_policy_save_directory = base_path

    for target_iteration in range(save_interval, training_episodes+1, save_interval):
        next_training_iterations = target_iteration - completed_iterations
        (menagerie, trained_agent,
         trajectories) = train_for_given_iterations(task, training_agent, self_play_scheme,
                                                    menagerie, menagerie_path,
                                                    next_training_iterations, completed_iterations, logger)
        logger.info('Training completion: {}%'.format(100 * target_iteration / training_episodes))
        del trajectories # we are not using them here
        completed_iterations += next_training_iterations
        save_trained_policy(trained_agent,
                            save_path=f'{trained_policy_save_directory}/{target_iteration}_iterations.pt',
                            logger=logger)

        agents_to_benchmark += [trained_agent.clone()]
        training_agent = trained_agent # Updating

    logger.info('FINISHED training. Total duration: {} seconds'.format(time.time() - start_time))
    return agents_to_benchmark


def save_trained_policy(trained_agent, save_path: str, logger):
    logger.info(f'Saving agent \'{trained_agent.name}\' in \'{save_path}\'')
    AgentHook(trained_agent.clone(training=False), save_path=save_path)


def train_for_given_iterations(task, training_agent, self_play_scheme,
                               menagerie, menagerie_path,
                               next_training_iterations, completed_iterations,
                               logger):

    training_start = time.time()
    (menagerie, trained_agent,
     trajectories) = self_play_training(task=task, training_agent=training_agent, self_play_scheme=self_play_scheme,
                                        target_episodes=next_training_iterations, initial_episode=completed_iterations,
                                        menagerie=menagerie, menagerie_path=menagerie_path, show_progress=True)
    training_duration = time.time() - training_start
    logger.info('Training between iterations [{}, {}]: {:.2} seconds'.format(
                completed_iterations, completed_iterations + next_training_iterations,
                training_duration))
    return menagerie, training_agent, trajectories


def initialize_experiment(experiment_config, agents_config, self_play_configs):
    env_name, requested_env_type = experiment_config['environment']
    task = generate_task(env_name, EnvType(requested_env_type))
    sp_schemes = initialize_training_schemes(self_play_configs, task)
    agents = initialize_agents(task, agents_config)

    return task, sp_schemes, agents


def load_configs(config_file_path: str):
    all_configs = yaml.load(open(config_file_path), Loader=yaml.FullLoader)
    experiment_config = all_configs['experiment']
    self_play_configs = filter_relevant_configurations(experiment_config,
                                                       target_configs=all_configs['self_play_training_schemes'],
                                                       target_key='self_play_training_schemes')
    agents_config = filter_relevant_configurations(experiment_config,
                                                   target_configs=all_configs['agents'],
                                                   target_key='algorithms')
    return experiment_config, agents_config, self_play_configs

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(description='Generates test agents for experiments of paper "On Opponent Modelling in Expert Iteration"')
    parser.add_argument('--config', required=True, help='path to YAML config file containing info about environment, self-play algorithms and agents')
    args = parser.parse_args()

    exper_config, agents_config, self_play_config = load_configs(args.config)
    task, sp_schemes, agents = \
            initialize_experiment(exper_config, agents_config, self_play_config)

    generate_test_agents(task, sp_schemes, agents, exper_config)
