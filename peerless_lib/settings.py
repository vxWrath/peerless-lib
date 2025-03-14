import json
from typing import Any, List, Optional, Union

from pydantic import BaseModel

from .namespace import Namespace

with open(f'peerless_lib/settings.json', 'rb') as f:
    data = json.load(f)

class Section(BaseModel):
    name: str
    key: str
    description: str
    settings: List[Union['SettingSupportsOptions', 'SettingSupportsMinMax', 'Setting']]

class Setting(BaseModel):
    name: str
    key: str
    default_value: Any
    type: str
    description: str
    required: bool
    
class SettingSupportsOptions(Setting):
    options: List['Option']

class SettingSupportsMinMax(Setting):
    minimum: Optional[float]
    maximum: Optional[float]

class Option(BaseModel):
    name: str
    description: str

SECTIONS = [Section.model_validate(s) for s in data]
SETTINGS = Namespace({x.key: x for y in SECTIONS for x in y.settings})