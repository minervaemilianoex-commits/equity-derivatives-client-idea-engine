from pathlib import Path
from typing import Tuple

import pandas as pd

from src.engine.config import EVENTS_FILE, IV_SURFACE_FILE, SPOT_HISTORY_FILE


def load_spot_history(path: Path = SPOT_HISTORY_FILE) -> pd.DataFrame:
    """
    Carica lo storico prezzi del sottostante.

    Colonne attese:
    - date
    - close
    """
    df = pd.read_csv(path)
    required_cols = {"date", "close"}

    if not required_cols.issubset(df.columns):
        raise ValueError(
            f"Spot history file must contain columns {required_cols}, found {set(df.columns)}"
        )

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    return df


def load_iv_surface(path: Path = IV_SURFACE_FILE) -> pd.DataFrame:
    """
    Carica una mini implied volatility surface sintetica.

    Colonne attese:
    - date
    - tenor_days
    - strike
    - option_type
    - iv
    """
    df = pd.read_csv(path)
    required_cols = {"date", "tenor_days", "strike", "option_type", "iv"}

    if not required_cols.issubset(df.columns):
        raise ValueError(
            f"IV surface file must contain columns {required_cols}, found {set(df.columns)}"
        )

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "tenor_days", "strike"]).reset_index(drop=True)

    return df


def load_events(path: Path = EVENTS_FILE) -> pd.DataFrame:
    """
    Carica il calendario eventi/catalyst.

    Colonne attese:
    - event_date
    - event_type
    - description
    """
    df = pd.read_csv(path)
    required_cols = {"event_date", "event_type", "description"}

    if not required_cols.issubset(df.columns):
        raise ValueError(
            f"Events file must contain columns {required_cols}, found {set(df.columns)}"
        )

    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.sort_values("event_date").reset_index(drop=True)

    return df


def load_all_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Carica tutti i dataset di base del progetto.
    """
    spot_df = load_spot_history()
    iv_df = load_iv_surface()
    events_df = load_events()

    return spot_df, iv_df, events_df