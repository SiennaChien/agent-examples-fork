from pydantic import BaseModel, Field
from typing import Literal, Optional

############
# Pydantic types for LLM response formats
############

class IssueSearchInfo(BaseModel):
    owner: str
    repo: str
    issue_numbers: list[int]