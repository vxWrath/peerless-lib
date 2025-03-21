from typing import Any, Mapping, overload

__all__ = (
    'Namespace',
)

class Namespace[K, V](dict[K, V]):
    @overload
    def __init__(self: 'Namespace[Any, Any]', /) -> None:
        ...

    @overload
    def __init__(self: 'Namespace[str, V]', /, **kwargs: V) -> None: # type: ignore
        ...

    @overload
    def __init__(self, mapping: Mapping[K, V], /) -> None:
        ...

    @overload
    def __init__(self: 'Namespace[str, V]', mapping: Mapping[str, V], /, **kwargs: V) -> None: # type: ignore
        ...

    def __init__(self, mapping: Mapping[Any, Any]={}, /, **kwargs: V) -> None:
        super().__init__(mapping, **kwargs)

        for key, value in self.items():
            if isinstance(value, dict):
                self[key] = Namespace(value) # type: ignore
            elif isinstance(value, list):
                self[key] = [Namespace(item) if isinstance(item, dict) else item for item in value] # type: ignore

    def __getattr__(self, key: K) -> V:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'Namespace' object has no attribute '{key}'")

    def __setattr__(self, key: K, value: V) -> None:
        if isinstance(value, dict):
            self[key] = Namespace(value) # type: ignore
        elif isinstance(value, list):
            self[key] = [Namespace(item) if isinstance(item, dict) else item for item in value] # type: ignore
        else:
            self[key] = value

    def __delattr__(self, key: K) -> None:
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"'Namespace' object has no attribute '{key}'")
        
    def has(self, key: K) -> bool:
        return key in self
    
    def __repr__(self) -> str:
        return f"Namespace({super().__repr__()})"
    
    __str__ = __repr__