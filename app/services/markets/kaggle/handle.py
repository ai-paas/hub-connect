from typing import NamedTuple

from fastapi import HTTPException


class KaggleModelHandle(NamedTuple):
    owner: str
    model: str
    framework: str
    variation: str


class KaggleDatasetHandle(NamedTuple):
    owner: str
    slug: str


def parse_model_handle(model_id: str) -> KaggleModelHandle:
    """Parse a Kaggle model handle into its four components.

    Accepts 3 or 4 segments:
      - owner/model/framework              (variation defaults to "default")
      - owner/model/framework/variation
    Raises HTTPException(400) for anything else.
    """
    segments = [s for s in model_id.strip("/").split("/") if s]
    if len(segments) == 3:
        owner, model, framework = segments
        return KaggleModelHandle(owner=owner, model=model, framework=framework, variation="default")
    if len(segments) == 4:
        owner, model, framework, variation = segments
        return KaggleModelHandle(owner=owner, model=model, framework=framework, variation=variation)
    raise HTTPException(
        status_code=400,
        detail=(
            "Kaggle model handle must be 3-4 segments: "
            "owner/model/framework[/variation]"
        ),
    )


def parse_dataset_handle(repo_id: str) -> KaggleDatasetHandle:
    """Parse a Kaggle dataset handle 'owner/slug'."""
    segments = [s for s in repo_id.strip("/").split("/") if s]
    if len(segments) != 2:
        raise HTTPException(
            status_code=400,
            detail="Kaggle dataset handle must be 'owner/slug'",
        )
    return KaggleDatasetHandle(owner=segments[0], slug=segments[1])


def format_model_id(handle: KaggleModelHandle) -> str:
    return f"{handle.owner}/{handle.model}/{handle.framework}/{handle.variation}"


def format_dataset_id(handle: KaggleDatasetHandle) -> str:
    return f"{handle.owner}/{handle.slug}"
