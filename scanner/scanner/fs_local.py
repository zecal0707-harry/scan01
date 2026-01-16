# Re-export from common module for backward compatibility
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.fs_local import LocalAdapter, list_dirs_local

__all__ = ['LocalAdapter', 'list_dirs_local']
