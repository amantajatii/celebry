from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl, Field


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


Collection = Literal['all', 'actors', 'actresses']


class PhotoCredit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    imageUrl: HttpUrl
    sourceUrl: HttpUrl
    license: str = Field(min_length=1)
    licenseUrl: HttpUrl | None = None
    attribution: str = Field(min_length=1)


class Celebrity(PhotoCredit):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    collection: Literal['actors', 'actresses', 'unclassified'] = 'unclassified'
    referenceCount: int = Field(default=1, ge=1)
    references: list[PhotoCredit] = Field(default_factory=list)


class Match(BaseModel):
    rank: int
    celebrity: Celebrity
    cosineSimilarity: float = Field(ge=-1, le=1)


class MatchResponse(BaseModel):
    catalogSize: int = Field(ge=5)
    collection: Collection = 'all'
    matches: list[Match]
    metric: str = 'cosine_similarity'
    notice: str = 'Entertainment only. Similarity is not an identity probability.'
