"""
Session Directory Path Management
Centralizes all session directory path definitions and provides consistent access
"""

import os
from typing import Dict, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SessionPaths:
    """Centralized session directory path management"""
    
    def __init__(self, base_sessions_dir: str = None):
        """Initialize session paths with optional custom base directory"""
        self.base_sessions_dir = base_sessions_dir or os.getenv("SESSIONS_DIR", "session_files")
        self.base_sessions_dir = os.path.abspath(self.base_sessions_dir)
        self._initialize_paths()
    
    def _initialize_paths(self):
        """Initialize all session directory paths"""
        # Main session directories
        self.sessions_dir = self.base_sessions_dir
        self.pending_dir = os.path.join(self.sessions_dir, "pending")
        self.approved_dir = os.path.join(self.sessions_dir, "approved")
        self.rejected_dir = os.path.join(self.sessions_dir, "rejected")
        self.extracted_dir = os.path.join(self.sessions_dir, "extracted")
        
        # Extracted subdirectories
        self.extracted_pending_dir = os.path.join(self.extracted_dir, "pending")
        self.extracted_approved_dir = os.path.join(self.extracted_dir, "approved")
        self.extracted_rejected_dir = os.path.join(self.extracted_dir, "rejected")
    
    def get_all_paths(self) -> Dict[str, str]:
        """Get all session directory paths as a dictionary"""
        return {
            'sessions_dir': self.sessions_dir,
            'pending_dir': self.pending_dir,
            'approved_dir': self.approved_dir,
            'rejected_dir': self.rejected_dir,
            'extracted_dir': self.extracted_dir,
            'extracted_pending_dir': self.extracted_pending_dir,
            'extracted_approved_dir': self.extracted_approved_dir,
            'extracted_rejected_dir': self.extracted_rejected_dir
        }
    
    def get_status_dir(self, status: str) -> str:
        """Get directory path for a specific status"""
        status_mapping = {
            'pending': self.pending_dir,
            'approved': self.approved_dir,
            'rejected': self.rejected_dir,
            'extracted': self.extracted_dir
        }
        
        if status not in status_mapping:
            raise ValueError(f"Unknown status: {status}. Valid statuses: {list(status_mapping.keys())}")
        
        return status_mapping[status]
    
    def get_extracted_status_dir(self, original_status: str) -> str:
        """Get extracted directory path for a specific original status"""
        extracted_mapping = {
            'pending': self.extracted_pending_dir,
            'approved': self.extracted_approved_dir,
            'rejected': self.extracted_rejected_dir
        }
        
        if original_status not in extracted_mapping:
            raise ValueError(f"Unknown original status: {original_status}. Valid statuses: {list(extracted_mapping.keys())}")
        
        return extracted_mapping[original_status]
    
    def get_required_directories(self) -> List[str]:
        """Get list of all required directories that should be created"""
        return [
            self.sessions_dir,
            self.pending_dir,
            self.approved_dir,
            self.rejected_dir,
            self.extracted_dir,
            self.extracted_pending_dir,
            self.extracted_approved_dir,
            self.extracted_rejected_dir
        ]
    
    def create_directories(self) -> bool:
        """Create all required directories"""
        try:
            for directory in self.get_required_directories():
                os.makedirs(directory, exist_ok=True)
                logger.debug(f"Created/verified directory: {directory}")
            
            logger.info(f"All session directories created/verified under: {self.sessions_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating session directories: {e}")
            return False
    
    def validate_directories(self) -> Dict[str, bool]:
        """Validate that all directories exist and are writable"""
        validation_results = {}
        
        for directory in self.get_required_directories():
            exists = os.path.exists(directory)
            writable = os.access(directory, os.W_OK) if exists else False
            validation_results[directory] = exists and writable
            
            if not exists:
                logger.warning(f"Directory does not exist: {directory}")
            elif not writable:
                logger.warning(f"Directory is not writable: {directory}")
        
        return validation_results
    
    def get_session_file_path(self, phone: str, status: str) -> str:
        """Get full path to a session file"""
        status_dir = self.get_status_dir(status)
        return os.path.join(status_dir, f"{phone}.session")
    
    def get_session_json_path(self, phone: str, status: str) -> str:
        """Get full path to a session JSON file"""
        status_dir = self.get_status_dir(status)
        return os.path.join(status_dir, f"{phone}.json")
    
    def get_folders_dict(self) -> Dict[str, str]:
        """Get folders dictionary compatible with existing code"""
        return {
            'pending': self.pending_dir,
            'approved': self.approved_dir,
            'rejected': self.rejected_dir
        }
    
    def get_folders_dict_relative(self) -> Dict[str, str]:
        """Get folders dictionary with relative paths for backward compatibility"""
        return {
            'pending': os.path.join(os.path.basename(self.sessions_dir), "pending"),
            'approved': os.path.join(os.path.basename(self.sessions_dir), "approved"),
            'rejected': os.path.join(os.path.basename(self.sessions_dir), "rejected")
        }
    
    def update_base_directory(self, new_base_dir: str):
        """Update the base sessions directory and reinitialize paths"""
        self.base_sessions_dir = os.path.abspath(new_base_dir)
        self._initialize_paths()
        logger.info(f"Session paths updated to use base directory: {self.base_sessions_dir}")


# Global session paths instance
_session_paths = None


def get_session_paths() -> SessionPaths:
    """Get the global session paths instance"""
    global _session_paths
    if _session_paths is None:
        _session_paths = SessionPaths()
    return _session_paths


def initialize_session_paths(base_dir: str = None) -> SessionPaths:
    """Initialize session paths with optional custom base directory"""
    global _session_paths
    _session_paths = SessionPaths(base_dir)
    return _session_paths


def create_all_session_directories() -> bool:
    """Create all required session directories using the global instance"""
    return get_session_paths().create_directories()


def validate_all_session_directories() -> Dict[str, bool]:
    """Validate all session directories using the global instance"""
    return get_session_paths().validate_directories()


# Constants for backward compatibility
def get_session_directory_constants():
    """Get session directory constants for backward compatibility"""
    paths = get_session_paths()
    return {
        'SESSIONS_DIR': paths.sessions_dir,
        'PENDING_DIR': paths.pending_dir,
        'APPROVED_DIR': paths.approved_dir,
        'REJECTED_DIR': paths.rejected_dir,
        'EXTRACTED_DIR': paths.extracted_dir
    }


if __name__ == "__main__":
    # Test the session paths functionality
    paths = SessionPaths()
    print("Session Paths Configuration:")
    print("=" * 40)
    
    for name, path in paths.get_all_paths().items():
        print(f"{name}: {path}")
    
    print("\nCreating directories...")
    if paths.create_directories():
        print("✅ All directories created successfully")
    else:
        print("❌ Failed to create directories")
    
    print("\nValidating directories...")
    validation = paths.validate_directories()
    for directory, is_valid in validation.items():
        status = "✅" if is_valid else "❌"
        print(f"{status} {directory}")