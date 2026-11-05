from pydantic import BaseModel, ConfigDict, HttpUrl, Field


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class Celebrity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    imageUrl: HttpUrl
    sourceUrl: HttpUrl
    license: str = Field(min_length=1)
    licenseUrl: HttpUrl | None = None
    attribution: str = Field(min_length=1)


class Match(BaseModel):
    rank: int
    celebrity: Celebrity
    cosineSimilarity: float = Field(ge=-1, le=1)


class MatchResponse(BaseModel):
    matches: list[Match]
    metric: str = 'cosine_similarity'
    notice: str = 'Entertainment only. Similarity is not an identity probability.'
