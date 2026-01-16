from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ServerConfig:
    """Server configuration for FTP/local filesystem access."""
    name: str
    ip: str
    port: int
    user: str
    password: str
    role: str  # "scan" | "film"
    group: str
    root: str
    prefix: str
    timeout: int
    op_deadline: float
    pool_size: int
    use_local_fs: bool = False  # True: local/network drive (os.listdir), False: FTP server
    meta: Dict[str, str] = field(default_factory=dict)


@dataclass
class SearchFilters:
    """Search filter criteria."""
    servers: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    wafer: List[str] = field(default_factory=list)
    lot: List[str] = field(default_factory=list)
    film: List[str] = field(default_factory=list)
    exact: bool = False
    regex: bool = False
    case_sensitive: bool = False
    link_recipe: bool = False


@dataclass
class Hit:
    """Search result hit."""
    server: str
    role: str
    level: str
    path: str
    recipe_linked: bool = False
    recipe_name: Optional[str] = None
    recipe_paths: Optional[List[str]] = None
    recipe_primary: Optional[str] = None
    recipe_server: Optional[str] = None
    kind: Optional[str] = None
    wafer: Optional[str] = None
    lot: Optional[str] = None
    film: Optional[str] = None
    date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()
