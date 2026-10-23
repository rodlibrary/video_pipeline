"""Shared helpers that let every pipeline stage run on a normal workstation.

The original toolkit assumed an HPC cluster: each stage imported ``mpi4py`` and
split its work across MPI ranks, and every AI stage talked to the OpenAI
Responses API. This module removes both assumptions:

* :func:`get_comm` returns a real MPI communicator only when the stage was
  launched under ``mpirun``/``srun`` *and* ``mpi4py`` is installed. Otherwise it
  returns :class:`SerialComm`, a drop-in stand-in that behaves like a
  one-rank MPI world, so stages run as ordinary single-process Python scripts.
* :func:`create_llm_client` / :func:`chat_completion` / :func:`embed_texts`
  use the OpenAI-compatible Chat Completions and Embeddings endpoints. Set
  ``base_url`` in a config section (or ``OPENAI_BASE_URL``) to point at a
  local server such as Ollama or LM Studio, or at Gemini's OpenAI-compatible
  endpoint, instead of api.openai.com.
"""

import os
from typing import Any, Dict, List, Optional

# Environment variables set by common MPI launchers. If none are present the
# process was started directly from a terminal and should run serially.
_MPI_LAUNCHER_VARS = (
    "OMPI_COMM_WORLD_SIZE",  # Open MPI
    "PMI_SIZE",  # MPICH / Intel MPI / Hydra
    "PMIX_RANK",  # PMIx (Open MPI 5, srun --mpi=pmix)
    "MPI_LOCALNRANKS",  # MPICH
)


class SerialComm:
    """Minimal single-process replacement for ``mpi4py.MPI.COMM_WORLD``.

    Implements only the calls the pipeline uses. With one rank, a broadcast
    returns its input unchanged and a gather returns a one-element list.
    """

    def Get_rank(self) -> int:  # noqa: N802 - mirrors the mpi4py API
        return 0

    def Get_size(self) -> int:  # noqa: N802 - mirrors the mpi4py API
        return 1

    def bcast(self, obj: Any, root: int = 0) -> Any:
        return obj

    def gather(self, obj: Any, root: int = 0) -> List[Any]:
        return [obj]

    def Barrier(self) -> None:  # noqa: N802 - mirrors the mpi4py API
        return None


def launched_under_mpi() -> bool:
    return any(var in os.environ for var in _MPI_LAUNCHER_VARS)


def get_comm():
    """Return an MPI communicator when running under an MPI launcher, else a serial one."""
    if os.environ.get("AV_PIPELINE_FORCE_SERIAL") == "1" or not launched_under_mpi():
        return SerialComm()
    try:
        from mpi4py import MPI  # type: ignore
    except ImportError:
        print(
            "[pipeline] MPI launcher detected but mpi4py is not installed; running serially.",
            flush=True,
        )
        return SerialComm()
    return MPI.COMM_WORLD


def finish_stage(stage: str, processed: int, errors: List[Dict[str, str]], noun: str = "items") -> None:
    """Exit non-zero when a stage hit errors and produced nothing, so the runner stops.

    Individual bad files are tolerated (they are listed by the stage), but a
    stage where *every* attempted item failed almost always means a setup
    problem such as a bad API key, wrong model name or missing ffmpeg.
    """
    if errors and processed == 0:
        import sys

        print(
            f"[{stage}] All {len(errors)} attempted {noun} failed; stopping. "
            "The first error above usually explains why.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def expand_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def transcript_dir_for(cfg: Dict, transcript_format: str = "txt") -> str:
    """Directory where transcribe_collection.py writes transcripts of a given format."""
    base_dir = cfg.get("outputs", {}).get("base_dir", "transcripts")
    return os.path.join(expand_path(base_dir), transcript_format)


# ---------------------------------------------------------------------------
# LLM access (OpenAI or any OpenAI-compatible server)
# ---------------------------------------------------------------------------

def resolve_base_url(section_cfg: Dict) -> Optional[str]:
    return section_cfg.get("base_url") or os.environ.get("OPENAI_BASE_URL") or None


def resolve_api_key(section_cfg: Dict) -> Optional[str]:
    api_key_env = section_cfg.get("api_key_env", "OPENAI_API_KEY")
    return os.environ.get(api_key_env)


def create_llm_client(section_cfg: Dict, purpose: str = "this step"):
    """Create an OpenAI client for a config section.

    A key is required for the hosted OpenAI API. When ``base_url`` points at a
    local server (Ollama, LM Studio, llama.cpp) no real key is needed, so a
    placeholder is used if the variable is unset.
    """
    from openai import OpenAI

    api_key_env = section_cfg.get("api_key_env", "OPENAI_API_KEY")
    api_key = resolve_api_key(section_cfg)
    base_url = resolve_base_url(section_cfg)
    if not api_key:
        if base_url:
            api_key = "not-needed"
        else:
            raise EnvironmentError(
                f"Environment variable '{api_key_env}' is not set. Set it to your API key "
                f"before running {purpose}, or set `base_url` to use a local model server.",
            )
    kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def chat_completion(
    client,
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    image_b64: Optional[str] = None,
    image_mime: str = "image/jpeg",
    json_mode: bool = False,
) -> str:
    """Single-turn chat call; optionally attaches one image for vision models."""
    if image_b64:
        user_content: Any = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
        ]
    else:
        user_content = user_prompt

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or ""
    return content.strip()


def embed_texts(client, model: str, texts: List[str], batch_size: int = 100) -> List[List[float]]:
    embeddings: List[List[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        embeddings.extend(item.embedding for item in response.data)
    return embeddings
