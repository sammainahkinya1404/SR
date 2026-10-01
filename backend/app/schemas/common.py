from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# Money crosses the API as integer cents (KSh 12.50 -> 1250), never as floats.
Cents = Annotated[int, Field(ge=0)]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
