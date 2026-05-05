import sys
sys.path.insert(0, 'src')

import tools.skill_loader as sl
from tools.skill_loader import SkillLoader, load_skill, _global_loader

print(f"Initial _global_loader: {sl._global_loader}")
print(f"Same object? {sl._global_loader is _global_loader}")

# Set to None
sl._global_loader = None

print(f"After setting to None: sl._global_loader = {sl._global_loader}")
print(f"_api._global_loader: {sl._api._global_loader if hasattr(sl, '_api') else 'N/A'}")

# Check the actual module
import tools.skill_loader._api as api
print(f"api._global_loader: {api._global_loader}")

# Try calling get_loader
loader = sl.get_loader()
print(f"get_loader() returned: {loader}")
print(f"loader.skills_dir: {loader.skills_dir}")