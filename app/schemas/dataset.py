from pydantic import BaseModel, RootModel
from typing import List, Optional, Dict, Any, Union
from enum import Enum

class Dataset(BaseModel):
    id: str
    author: str
    downloads: int
    gated: Union[bool, str]  # Can be false, "auto", or "manual"
    lastModified: str
    likes: int
    private: bool
    repoType: str
    datasetsServerInfo: Optional[Dict[str, Any]] = None
    isLikedByUser: Optional[bool] = None

class DatasetSearchResponse(BaseModel):
    datasets: List[Dataset]
    total: int
    page: int
    page_size: int  # Keep as page_size in response for backward compatibility

class Feature(BaseModel):
    dtype: str
    _type: str

class Split(BaseModel):
    name: str
    num_bytes: int
    num_examples: int
    dataset_name: str

class DownloadChecksum(BaseModel):
    num_bytes: int
    checksum: Optional[str] = None

class DatasetInfoDefault(BaseModel):
    description: str
    citation: str
    homepage: str
    license: str
    features: Dict[str, Feature]
    builder_name: str
    dataset_name: str
    config_name: str
    version: Dict[str, Any]
    splits: Dict[str, Split]
    download_checksums: Dict[str, DownloadChecksum]
    download_size: int
    dataset_size: int
    size_in_bytes: int

class DatasetInfoResponse(BaseModel):
    dataset_info: Dict[str, DatasetInfoDefault]
    pending: List
    failed: List
    partial: bool
    cardData: Optional[Dict[str, Any]] = None

class DatasetContentsResponse(RootModel):
    root: List[str]

class RepoTreeFile(BaseModel):
    path: str
    type: str
    size: int
    blob_id: Optional[str] = None
    lfs: Optional[Dict[str, Any]] = None

class DatasetFileTreeResponse(RootModel):
    root: List[RepoTreeFile]
