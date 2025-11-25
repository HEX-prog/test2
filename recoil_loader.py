"""
Recoil data loader for RCS (Recoil Control System)
Reads recoil data from recoil_data/{game}/{weapon}.txt files
"""
import os
from typing import List, Tuple, Optional, Dict

RECOIL_DATA_DIR = "recoil_data"

def get_available_games() -> List[str]:
    """Get list of available games from recoil_data directory"""
    games = []
    if os.path.exists(RECOIL_DATA_DIR):
        for item in os.listdir(RECOIL_DATA_DIR):
            item_path = os.path.join(RECOIL_DATA_DIR, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                games.append(item)
    return sorted(games)

def get_available_weapons(game: str) -> List[str]:
    """Get list of available weapons for a specific game"""
    weapons = []
    game_dir = os.path.join(RECOIL_DATA_DIR, game)
    if os.path.exists(game_dir):
        for file in os.listdir(game_dir):
            if file.endswith('.txt'):
                # Remove .txt extension
                weapon_name = file[:-4]
                weapons.append(weapon_name)
    return sorted(weapons)

def parse_recoil_file(file_path: str) -> List[Tuple[float, float, float]]:
    """
    Parse recoil data file
    Supports multiple formats:
    - delay,dx,dy (Rust format)
    - dx,dy,delay (CS2/Apex format)
    
    Returns list of (delay_ms, dx, dy) tuples
    """
    recoil_data = []
    
    if not os.path.exists(file_path):
        print(f"[WARNING] Recoil file not found: {file_path}")
        return recoil_data
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # Detect format by checking first valid line
        format_detected = None
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                try:
                    # Try to determine format
                    val1 = float(parts[0])
                    val2 = float(parts[1])
                    val3 = float(parts[2])
                    
                    # If first value is much larger than others, likely delay (Rust format)
                    # If first value is small, likely dx (CS2/Apex format)
                    if abs(val1) > 50 and abs(val2) < 10 and abs(val3) < 10:
                        format_detected = "delay_dx_dy"  # delay,dx,dy
                    else:
                        format_detected = "dx_dy_delay"  # dx,dy,delay
                    break
                except ValueError:
                    continue
        
        # Parse all lines
        for line in lines:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Try to parse the line
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                try:
                    val1 = float(parts[0])
                    val2 = float(parts[1])
                    val3 = float(parts[2])
                    
                    if format_detected == "delay_dx_dy":
                        # delay,dx,dy format (Rust)
                        delay = val1
                        dx = val2
                        dy = val3
                    else:
                        # dx,dy,delay format (CS2/Apex)
                        dx = val1
                        dy = val2
                        delay = val3
                    
                    recoil_data.append((delay, dx, dy))
                except ValueError:
                    continue  # Skip invalid lines
                    
    except Exception as e:
        print(f"[ERROR] Failed to parse recoil file {file_path}: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"[INFO] Parsed {len(recoil_data)} recoil patterns from {file_path}")
    return recoil_data

def load_recoil_data(game: str, weapon: str) -> List[Tuple[float, float, float]]:
    """
    Load recoil data for a specific game and weapon
    
    Args:
        game: Game name (e.g., "cs2", "apex", "rust")
        weapon: Weapon name (e.g., "ak47", "R301")
    
    Returns:
        List of (delay_ms, dx, dy) tuples
    """
    file_path = os.path.join(RECOIL_DATA_DIR, game, f"{weapon}.txt")
    return parse_recoil_file(file_path)

