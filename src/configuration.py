import dataclasses
from dataclasses import dataclass
from typing import List

import dataconf


class ConfigurationBase:

    @staticmethod
    def fromDict(parameters: dict):
        return dataconf.dict(parameters, Configuration, ignore_unexpected=True)
        pass

    @staticmethod
    def _convert_private_value_inv(value: str):
        if value and value.startswith('pswd_'):
            return value.replace('pswd_', '#', 1)
        else:
            return value

    @classmethod
    def get_dataclass_required_parameters(cls) -> List[str]:
        """
        Return list of required parameters based on the dataclass definition (no default value)
        Returns: List[str]

        """
        return [cls._convert_private_value_inv(f.name) for f in dataclasses.fields(cls)
                if f.default == dataclasses.MISSING
                and f.default_factory == dataclasses.MISSING]


@dataclass
class Destination(ConfigurationBase):
    table_name: str = ''
    primary_key: list[str] = dataclasses.field(default_factory=list)
    incremental: bool = True


@dataclass
class Configuration(ConfigurationBase):
    organization_url: str
    endpoint: str
    destination: Destination
    columns: list[str] = dataclasses.field(default_factory=list)
    debug: bool = False
