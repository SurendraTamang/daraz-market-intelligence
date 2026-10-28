# Daraz.com.np catalog slugs, VERIFIED to return listing JSON (`?ajax=true`).
#
# NOTE: Daraz's top-level nav items (mobiles-tablets, health-beauty, tv-audio,
# home-lifestyle, sports-outdoor, ...) are JS "landing" pages that DON'T serve
# the ajax listing JSON. Real catalog pages are the (sub)categories below. Each
# was confirmed to return `mods.listItems`. To add more, probe a candidate slug:
#   https://www.daraz.com.np/<slug>/?ajax=true&page=1  -> must contain "listItems".
CATEGORY_SLUGS = [
    "groceries",            # food & grocery
    "laptops",              # computing
    "tablets",              # computing / mobile
    "home-appliances",      # appliances
    "mens-fashion",         # fashion (men)
    "womens-fashion",       # fashion (women)
    "fragrances",           # beauty
    "hair-care",            # beauty
    "fashion-jewellery",    # accessories
    "kitchen-dining",       # home
    "cookware",             # home
    "toys",                 # kids
    "camping-hiking",       # sports & outdoor
    "cycling",              # sports & outdoor
]

# DARAZ_ALL=1 -> crawl EVERY category from the sitemap (5,932 slugs) instead of
# the 14 curated ones. Generate the list first: python sitemap_categories.py
# CATEGORIES_FILE=path -> one slug per line (e.g. briefs/shortlist.txt for the weekly crawl).
# CATEGORIES_FILE takes precedence over DARAZ_ALL (checked second, below).
import os as _os  # noqa: E402

if _os.getenv("DARAZ_ALL"):
    from daraz.categories_all import CATEGORY_SLUGS  # noqa: F401,F811
if _os.getenv("CATEGORIES_FILE"):
    with open(_os.environ["CATEGORIES_FILE"]) as _f:
        CATEGORY_SLUGS = [
            _line.strip() for _line in _f
            if _line.strip() and not _line.strip().startswith("#")
        ]
    if not CATEGORY_SLUGS:
        raise ValueError(f"CATEGORIES_FILE={_os.environ['CATEGORIES_FILE']} has no usable slugs")

# Page budget per category. The spider stops earlier at the first page with no "X sold"
# items or when Daraz reports noMorePages. Step 1 = 3; deepen with MAX_PAGES=102 (Daraz cap).
MAX_PAGES = int(_os.getenv("MAX_PAGES", "3"))
