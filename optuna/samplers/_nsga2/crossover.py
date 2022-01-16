from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence

import numpy as np

from optuna._transform import _SearchSpaceTransform
from optuna.distributions import BaseDistribution
from optuna.distributions import DiscreteUniformDistribution
from optuna.distributions import FloatDistribution
from optuna.distributions import IntDistribution
from optuna.distributions import IntLogUniformDistribution
from optuna.distributions import IntUniformDistribution
from optuna.distributions import LogUniformDistribution
from optuna.distributions import UniformDistribution
from optuna.samplers._nsga2._crossovers._base import BaseCrossover
from optuna.samplers._nsga2._crossovers._uniform import UniformCrossover
from optuna.study import Study
from optuna.study import StudyDirection
from optuna.trial import FrozenTrial


_NUMERICAL_DISTRIBUTIONS = (
    UniformDistribution,
    LogUniformDistribution,
    DiscreteUniformDistribution,
    FloatDistribution,
    IntUniformDistribution,
    IntLogUniformDistribution,
    IntDistribution,
)


def _try_crossover(
    parents: List[FrozenTrial],
    crossover: BaseCrossover,
    study: Study,
    rng: np.random.RandomState,
    swapping_prob: float,
    categorical_search_space: Dict[str, BaseDistribution],
    numerical_search_space: Dict[str, BaseDistribution],
    numerical_transform: Optional[_SearchSpaceTransform],
) -> Dict[str, Any]:

    child_params: Dict[str, Any] = {}

    if len(categorical_search_space) > 0:
        parents_categorical_params = np.array(
            [
                [parent.params[p] for p in categorical_search_space]
                for parent in [parents[0], parents[-1]]
            ]
        )

        categorical_crossover = UniformCrossover(swapping_prob)
        child_categorical_array = categorical_crossover.crossover(
            parents_categorical_params, rng, study, categorical_search_space
        )

        child_categorical_params = {
            param: value for param, value in zip(categorical_search_space, child_categorical_array)
        }
        child_params.update(child_categorical_params)

    if numerical_transform is None:
        return child_params

    # The following is applied only for numerical parameters.
    parents_numerical_params = np.stack(
        [
            numerical_transform.transform(
                {
                    param_key: parent.params[param_key]
                    for param_key in numerical_search_space.keys()
                }
            )
            for parent in parents
        ]
    )  # Parent individual with NUMERICAL_DISTRIBUTIONS parameter.

    child_numerical_array = crossover.crossover(
        parents_numerical_params, rng, study, numerical_search_space
    )
    child_numerical_params = numerical_transform.untransform(child_numerical_array)
    child_params.update(child_numerical_params)

    return child_params


def crossover(
    crossover: BaseCrossover,
    study: Study,
    parent_population: Sequence[FrozenTrial],
    search_space: Dict[str, BaseDistribution],
    rng: np.random.RandomState,
    swapping_prob: float,
    dominates: Callable[[FrozenTrial, FrozenTrial, Sequence[StudyDirection]], bool],
) -> Dict[str, Any]:

    numerical_search_space: Dict[str, BaseDistribution] = {}
    categorical_search_space: Dict[str, BaseDistribution] = {}
    for key, value in search_space.items():
        if isinstance(value, _NUMERICAL_DISTRIBUTIONS):
            numerical_search_space[key] = value
        else:
            categorical_search_space[key] = value

    numerical_transform: Optional[_SearchSpaceTransform] = None
    if len(numerical_search_space) != 0:
        numerical_transform = _SearchSpaceTransform(numerical_search_space)

    while True:  # Repeat while parameters lie outside search space boundaries.
        parents = _select_parents(crossover, study, parent_population, rng, dominates)
        child_params = _try_crossover(
            parents,
            crossover,
            study,
            rng,
            swapping_prob,
            categorical_search_space,
            numerical_search_space,
            numerical_transform,
        )

        if _is_contained(child_params, search_space):
            break

    return child_params


def _select_parents(
    crossover: BaseCrossover,
    study: Study,
    parent_population: Sequence[FrozenTrial],
    rng: np.random.RandomState,
    dominates: Callable[[FrozenTrial, FrozenTrial, Sequence[StudyDirection]], bool],
) -> List[FrozenTrial]:

    parents: List[FrozenTrial] = []
    for _ in range(crossover.n_parents):
        parent = _select_parent(
            study, [t for t in parent_population if t not in parents], rng, dominates
        )
        parents.append(parent)

    return parents


def _select_parent(
    study: Study,
    parent_population: Sequence[FrozenTrial],
    rng: np.random.RandomState,
    dominates: Callable[[FrozenTrial, FrozenTrial, Sequence[StudyDirection]], bool],
) -> FrozenTrial:
    population_size = len(parent_population)
    candidate0 = parent_population[rng.choice(population_size)]
    candidate1 = parent_population[rng.choice(population_size)]

    # TODO(ohta): Consider crowding distance.
    if dominates(candidate0, candidate1, study.directions):
        return candidate0
    else:
        return candidate1


def _is_contained(params: Dict[str, Any], search_space: Dict[str, BaseDistribution]) -> bool:
    for param_name in params.keys():
        param, param_distribution = params[param_name], search_space[param_name]

        if not param_distribution._contains(param_distribution.to_internal_repr(param)):
            return False
    return True
