# %%
import pandas as pd
import numpy as np
from pathlib import Path
import hickle as hkl

data_dir = Path("data")
data_file = data_dir / "07-16-21.hkl"
data = hkl.load(data_file)
# %%
# User x Doc field
df = pd.DataFrame(data).T

# User level and xp
# Number of cooked recipes
# Number of recipes in progress
# Number of skills in progress per user
# Average skill level per user
# Common recipes across users
# Common skills across users
# Number of users who've provided feedback at least once
# Number of favorited recipes per user
# Account creation dates
# last login dates
