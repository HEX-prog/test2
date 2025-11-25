import os
import json
import shutil
from typing import List, Dict, Any
from datetime import datetime

class ConfigManager:
    """Configuration file management system for EVENTURI-AI"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.ensure_config_dir()
    
    def ensure_config_dir(self):
        """Ensure config directory exists"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
    
    def get_config_files(self) -> List[str]:
        """Get list of all configuration files in config directory"""
        config_files = []
        if os.path.exists(self.config_dir):
            for file in os.listdir(self.config_dir):
                if file.endswith('.json'):
                    config_files.append(file[:-5])  # Remove .json extension
        return sorted(config_files)
    
    def get_config_path(self, config_name: str) -> str:
        """Get full path for a configuration file"""
        return os.path.join(self.config_dir, f"{config_name}.json")
    
    def config_exists(self, config_name: str) -> bool:
        """Check if a configuration file exists"""
        return os.path.exists(self.get_config_path(config_name))
    
    def create_config(self, config_name: str, config_data: Dict[str, Any]) -> bool:
        """Create a new configuration file"""
        try:
            config_path = self.get_config_path(config_name)
            if os.path.exists(config_path):
                return False  # Config already exists
            
            # Add metadata
            config_data['_metadata'] = {
                'created_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error creating config {config_name}: {e}")
            return False
    
    def load_config(self, config_name: str) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            config_path = self.get_config_path(config_name)
            if not os.path.exists(config_path):
                return {}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Remove metadata for actual usage
            if '_metadata' in data:
                del data['_metadata']
            
            return data
        except Exception as e:
            print(f"Error loading config {config_name}: {e}")
            return {}
    
    def save_config(self, config_name: str, config_data: Dict[str, Any]) -> bool:
        """Save configuration to file"""
        try:
            config_path = self.get_config_path(config_name)
            
            # Preserve existing metadata if available
            existing_data = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except:
                    pass
            
            # Add/update metadata
            config_data['_metadata'] = {
                'created_at': existing_data.get('_metadata', {}).get('created_at', datetime.now().isoformat()),
                'modified_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving config {config_name}: {e}")
            return False
    
    def rename_config(self, old_name: str, new_name: str) -> bool:
        """Rename a configuration file"""
        try:
            old_path = self.get_config_path(old_name)
            new_path = self.get_config_path(new_name)
            
            if not os.path.exists(old_path):
                return False
            
            if os.path.exists(new_path):
                return False  # New name already exists
            
            # Load existing data and update metadata
            with open(old_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            data['_metadata'] = data.get('_metadata', {})
            data['_metadata']['modified_at'] = datetime.now().isoformat()
            
            # Save with new name
            with open(new_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Remove old file
            os.remove(old_path)
            return True
        except Exception as e:
            print(f"Error renaming config {old_name} to {new_name}: {e}")
            return False
    
    def delete_config(self, config_name: str) -> bool:
        """Delete a configuration file"""
        try:
            config_path = self.get_config_path(config_name)
            if os.path.exists(config_path):
                os.remove(config_path)
                return True
            return False
        except Exception as e:
            print(f"Error deleting config {config_name}: {e}")
            return False
    
    def duplicate_config(self, source_name: str, new_name: str) -> bool:
        """Duplicate an existing configuration"""
        try:
            source_path = self.get_config_path(source_name)
            new_path = self.get_config_path(new_name)
            
            if not os.path.exists(source_path):
                return False
            
            if os.path.exists(new_path):
                return False  # New name already exists
            
            # Load source data and update metadata
            with open(source_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            data['_metadata'] = {
                'created_at': datetime.now().isoformat(),
                'modified_at': datetime.now().isoformat(),
                'version': '1.0',
                'duplicated_from': source_name
            }
            
            # Save with new name
            with open(new_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"Error duplicating config {source_name} to {new_name}: {e}")
            return False
    
    def get_config_info(self, config_name: str) -> Dict[str, Any]:
        """Get metadata information about a configuration"""
        try:
            config_path = self.get_config_path(config_name)
            if not os.path.exists(config_path):
                return {}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            metadata = data.get('_metadata', {})
            file_stats = os.stat(config_path)
            
            return {
                'name': config_name,
                'created_at': metadata.get('created_at', 'Unknown'),
                'modified_at': metadata.get('modified_at', 'Unknown'),
                'file_size': file_stats.st_size,
                'version': metadata.get('version', '1.0'),
                'duplicated_from': metadata.get('duplicated_from')
            }
        except Exception as e:
            print(f"Error getting config info for {config_name}: {e}")
            return {}
