import argparse
import glob
import json
import os
import sys
import traceback
from typing import Dict, List, Tuple

import numpy as np
from sklearn.cluster import KMeans

import yaml
from pipeline_common import create_llm_client, embed_texts


def expand_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def load_config(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("Configuration file must define a mapping.")
    return config


def validate_config(cfg: Dict) -> Dict:
    cluster_cfg = cfg.setdefault("clustering", {})
    if not cluster_cfg.get("enabled", False):
        raise ValueError(
            "Clustering is disabled in the configuration. "
            "Set `clustering.enabled` to true.",
        )

    if cluster_cfg.get("frame_descriptions_dirs"):
        cluster_cfg["frame_descriptions_dirs"] = [
            expand_path(path) for path in cluster_cfg["frame_descriptions_dirs"]
        ]
    else:
        frame_cfg = cfg.get("frame_descriptions", {})
        if frame_cfg.get("enabled"):
            cluster_cfg["frame_descriptions_dirs"] = [
                expand_path(frame_cfg.get("output_dir", "frame_descriptions")),
            ]
        else:
            raise ValueError(
                "`clustering.frame_descriptions_dirs` must be set when frame descriptions are not enabled.",
            )

    cluster_cfg["output_dir"] = expand_path(cluster_cfg.get("output_dir", "clusters"))
    return cfg


def create_openai_client(cluster_cfg: Dict):
    return create_llm_client(cluster_cfg, purpose="clustering")


def gather_descriptions(cluster_cfg: Dict) -> List[Tuple[str, str, str]]:
    entries: List[Tuple[str, str, str]] = []
    extension = cluster_cfg.get("frame_description_extension", "txt").lstrip(".")
    max_items = cluster_cfg.get("max_items")
    for directory in cluster_cfg["frame_descriptions_dirs"]:
        pattern = os.path.join(directory, f"*/*.{extension}")
        for path in glob.glob(pattern):
            item_id = os.path.basename(path).split("_t")[0]
            with open(path, "r", encoding="utf-8") as handle:
                description = handle.read().strip()
            entries.append((item_id, path, description))
            if max_items is not None and len(entries) >= max_items:
                return entries
    return entries


def embed_descriptions(client, descriptions: List[str], cluster_cfg: Dict) -> np.ndarray:
    model = cluster_cfg.get("model", "text-embedding-3-small")
    return np.array(embed_texts(client, model, descriptions))


def perform_clustering(embeddings: np.ndarray, cluster_cfg: Dict) -> KMeans:
    n_clusters = min(cluster_cfg.get("n_clusters", 20), len(embeddings))
    n_clusters = max(n_clusters, 2)
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    kmeans.fit(embeddings)
    return kmeans


def save_clusters(
    entries: List[Tuple[str, str, str]],
    kmeans: KMeans,
    cluster_cfg: Dict,
) -> None:
    os.makedirs(cluster_cfg["output_dir"], exist_ok=True)
    assignments: Dict[int, List[Dict[str, str]]] = {}
    for (item_id, path, description), label in zip(entries, kmeans.labels_):
        assignments.setdefault(int(label), []).append(
            {
                "item_id": item_id,
                "path": path,
                "description": description,
            },
        )
    summary = {
        "n_clusters": len(assignments),
        "clusters": assignments,
    }
    with open(os.path.join(cluster_cfg["output_dir"], "clusters.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cluster frame descriptions using OpenAI embeddings to reveal recurring visual themes.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to YAML configuration file (default: ./config.yaml).",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        config = validate_config(config)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(f"Configuration error: {exc}")

    cluster_cfg = config["clustering"]
    entries = gather_descriptions(cluster_cfg)
    if not entries:
        sys.exit("No frame descriptions found for clustering.")
    if len(entries) < 2:
        print("Only one frame description found; clustering needs at least two. Skipping.")
        return

    client = create_openai_client(cluster_cfg)
    embeddings = embed_descriptions(client, [entry[2] for entry in entries], cluster_cfg)
    kmeans = perform_clustering(embeddings, cluster_cfg)
    save_clusters(entries, kmeans, cluster_cfg)

    print(f"Saved clustering results to {cluster_cfg['output_dir']}")


if __name__ == "__main__":
    main()

