from typing import Dict, List, Optional

import numpy as np
from chroma.algorithms.core_algorithms import (
    activation_uncertainty,
    boundary_uncertainty,
    # class_outliers,
    cluster_outliers,
)
from chroma.db.clickhouse import Clickhouse
from chroma.db.index.hnswlib import Hnswlib


# Score each datapoint in the inference data, and store the scores in the database
def score_and_store(
    training_dataset_name: str,
    inference_dataset_name: str,
    db_connection: Clickhouse,
    ann_index: Hnswlib,
    model_space: Optional[str] = "default_scope",
) -> None:

    # print all to this function
    print("running score_and_store inside")
    print("training_dataset_name", training_dataset_name)
    print("inference_dataset_name", inference_dataset_name)
    print("db_connection", db_connection)
    print("ann_index", ann_index)
    print("model_space", model_space)

    print("getting training data")
    training_data = db_connection.fetch(
        where={"model_space": model_space, "dataset": training_dataset_name}
    )
    print("training_data", len(training_data))
    print("getting inference data")
    inference_data = db_connection.fetch(
        where={"model_space": model_space, "dataset": inference_dataset_name}
    )
    print("inference_data", len(inference_data))

    print("getting the index")
    ann_index._load(model_space=model_space)

    print("activation_uncertainty_scores")
    activation_uncertainty_scores = activation_uncertainty(
        training_data=training_data, inference_data=inference_data
    )
    print("activation_uncertainty_scores", len(activation_uncertainty_scores))

    print("boundary_uncertainty_scores")
    # boundary_uncertainty_scores = boundary_uncertainty(
    #     training_data=training_data,
    #     inference_data=inference_data,
    #     ann_index=ann_index,
    #     model_space=model_space,
    # )
    boundary_uncertainty_scores = activation_uncertainty_scores

    # TODO: Fix class outliers (ANN index issue)
    # representative_class_outlier_scores, difficult_class_outlier_scores = class_outliers(
    #     training_data=training_data,
    #     inference_data=inference_data,
    #     ann_index=ann_index,
    #     model_space=model_space,
    # )
    print("cluster_outliers")
    representative_cluster_outlier_scores, difficult_cluster_outlier_scores = cluster_outliers(
        training_data=training_data, inference_data=inference_data
    )

    # Only one set of results per model space
    print("delete_results")
    db_connection.delete_results(model_space=model_space)

    # Results have singular names as arguments so they match DB schema column names
    print("add_results")
    db_connection.add_results(
        model_space=model_space,
        uuid=inference_data["uuid"].tolist(),
        activation_uncertainty=activation_uncertainty_scores,
        boundary_uncertainty=boundary_uncertainty_scores,
        # TODO: Fix class outliers (ANN index issue)
        # representative_class_outlier_score=representative_class_outlier_scores,
        # difficult_class_outlier_score=difficult_class_outlier_scores,
        representative_cluster_outlier=representative_cluster_outlier_scores,
        difficult_cluster_outlier=difficult_cluster_outlier_scores,
    )

    return None


# Given a target number of samples, and sample proportions by score type, return a list of unique URIs to label
def get_sample(
    dataset_name: str,
    n_samples: int,
    sample_proportions: Dict[str, float],
    db_connection: Clickhouse,
    model_space: Optional[str] = "default_scope",
) -> List[str]:

    total_proportions = np.sum(list(sample_proportions.values()))
    # Raise an exception if the total proportions are not between 0 and 1
    if total_proportions > 1 or total_proportions < 0:
        raise ValueError(f"Sample proportions must sum to between 0 and 1: {total_proportions}")

    # Get uris for each score type
    uris = set()
    for key, value in sample_proportions.items():
        # We random sample later
        if key == "random":
            continue

        # Raise an exception if the proportion is not between 0 and 1
        if value > 1 or value < 0:
            raise ValueError(f"Sample proportions must be between 0 and 1: {value}")

        n = int(n_samples * (value / total_proportions))
        results = db_connection.get_results_by_column(
            column_name=key, n_results=n, model_space=model_space
        )
        uris.update(results.input_uri.tolist())

    # Add random samples to fill out the sample set
    n_random = n_samples - len(uris)
    uris.update(db_connection.get_random(n=n_random, where={"model_space": model_space, "dataset": dataset_name}).input_uri.tolist())

    return list(uris)
