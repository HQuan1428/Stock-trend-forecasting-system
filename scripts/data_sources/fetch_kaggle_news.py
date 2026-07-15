"""Kaggle financial news dataset fetcher (manual, credential-gated).

NOT wired into `scripts/fetch_real_data.py`, `src/pipeline.py`, or any
test's default collection. See `scripts/data_sources/README.md` for the
full runbook.

Requires:

1. A free Kaggle account and API token (Account -> Create New API Token
   at https://www.kaggle.com/settings), which downloads ``kaggle.json``.
2. ``kaggle.json`` placed at ``~/.kaggle/kaggle.json`` (``chmod 600``),
   OR ``KAGGLE_USERNAME``/``KAGGLE_KEY`` set in the repo-root ``.env``
   file (copy ``.env.example`` to ``.env`` and fill it in — loaded
   automatically via ``python-dotenv``, no ``export`` needed; a real,
   pre-existing shell environment variable always takes priority).
3. ``pip install kaggle``.
4. Having opened the target dataset's page on kaggle.com at least once
   and accepted its terms — Kaggle requires this before the API will
   allow downloading some datasets, even with a valid token.

Usage:
    python3 -m scripts.data_sources.fetch_kaggle_news
    python3 -m scripts.data_sources.fetch_kaggle_news some-other/dataset-slug
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

#: A representative Kaggle financial-news dataset. Swap for any dataset
#: slug you have accepted the terms of on kaggle.com.
DEFAULT_DATASET_SLUG = "miguelaenlle/massive-stock-news-analysis-db-for-nlpbacktests"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "raw_cache" / "kaggle"

KAGGLE_JSON_PATH = Path.home() / ".kaggle" / "kaggle.json"

# Populate os.environ from the repo-root .env, without overriding any
# variable a real shell `export` already set.
load_dotenv(REPO_ROOT / ".env")


class MissingCredentialError(RuntimeError):
    """Raised when no Kaggle credentials (token file or env vars) are found."""


def require_kaggle_credentials() -> None:
    """Raise a clear, actionable error if no Kaggle credentials are configured."""
    has_json = KAGGLE_JSON_PATH.exists()
    has_env = bool(os.environ.get("KAGGLE_USERNAME")) and bool(os.environ.get("KAGGLE_KEY"))
    if not has_json and not has_env:
        raise MissingCredentialError(
            "No Kaggle credentials found.\n"
            "1. Create a free account, then Account -> Create New API "
            "Token at https://www.kaggle.com/settings\n"
            f"2. Place the downloaded file at {KAGGLE_JSON_PATH} "
            "(chmod 600), OR copy .env.example to .env and fill in "
            "KAGGLE_USERNAME and KAGGLE_KEY (or export them in your shell)\n"
            "3. pip install kaggle\n"
            "4. Open the target dataset's page on kaggle.com at least "
            "once and accept its terms — required by Kaggle before the "
            "API can download some datasets."
        )


def fetch_dataset(dataset_slug: str = DEFAULT_DATASET_SLUG) -> Path:
    """Download and unzip ``dataset_slug`` into ``CACHE_DIR`` via the Kaggle API.

    Requires Kaggle credentials (see :func:`require_kaggle_credentials`)
    and the ``kaggle`` package installed.
    """
    require_kaggle_credentials()
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:
        raise MissingCredentialError(
            "The 'kaggle' package is not installed. Run: pip install kaggle"
        ) from exc

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(dataset_slug, path=str(CACHE_DIR), unzip=True)
    return CACHE_DIR


def main(argv: Optional[List[str]] = None) -> None:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    dataset_slug = argv[0] if argv else DEFAULT_DATASET_SLUG
    print(f"Fetching Kaggle dataset {dataset_slug!r}...")
    out_dir = fetch_dataset(dataset_slug)
    print(f"  downloaded + unzipped to {out_dir}")


if __name__ == "__main__":
    main()
