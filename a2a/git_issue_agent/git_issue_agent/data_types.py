from pydantic import BaseModel, Field
from typing import Literal, Optional

############
# Pydantic types for LLM response formats
############


class UserQueryJudgement(BaseModel):
    has_sufficient_information: bool = Field(False, description="Whether the user's query contains sufficient enough information to retrieve issues from github")
    explanation: str = Field(None, description="A detailed explanation as to why you made the judgement")