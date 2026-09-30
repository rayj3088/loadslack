"""
Per-model calibration.

The waste profile is model-specific and models turn over constantly. Every
release changes context economics, tokenizer behaviour, prefix-cache
granularity and reasoning-token cost, so a profile calibrated months ago drifts.

A stale or missing profile does not break anything. It degrades gracefully to
the generic baseline and says so, loudly, in the report.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

PROFILE_LIFE_S = 90 * 86400  # profiles go stale after ~a quarter


@dataclass
class ModelProfile:
    model: str
    chars_per_token: float = 4.0
    prefix_cache_block: int = 256     # tokens; prefix reuse granularity
    near_dup_max_hamming: int = 6     # tolerance tuned per tokenizer
    typical_reasoning_ratio: float = 0.0
    calibrated_at: float = 0.0
    source: str = "generic-baseline"

    @property
    def age_s(self) -> float:
        return time.time() - self.calibrated_at if self.calibrated_at else 1e12

    @property
    def stale(self) -> bool:
        return self.age_s > PROFILE_LIFE_S

    def as_dict(self) -> dict:
        return {"model": self.model, "source": self.source,
                "stale": self.stale,
                "age_days": round(self.age_s / 86400, 1)
                if self.calibrated_at else None}


GENERIC = ModelProfile(model="*")


class ProfileStore:
    """
    Loads calibration from a JSON bundle (set LOADSLACK_PROFILES to its path).
    No bundle, or an old one, and everything falls back to GENERIC with a
    visible warning.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.profiles: Dict[str, ModelProfile] = {}
        self.bundle_version = ""
        self.bundle_issued = 0.0
        if path and os.path.exists(path):
            self.load(path)

    def load(self, path: str) -> None:
        try:
            with open(path) as fh:
                raw = json.load(fh)
        except Exception:
            return
        self.bundle_version = str(raw.get("version", ""))
        self.bundle_issued = float(raw.get("issued_at", 0.0))
        for m, p in (raw.get("models") or {}).items():
            self.profiles[m] = ModelProfile(
                model=m,
                chars_per_token=float(p.get("chars_per_token", 4.0)),
                prefix_cache_block=int(p.get("prefix_cache_block", 256)),
                near_dup_max_hamming=int(p.get("near_dup_max_hamming", 6)),
                typical_reasoning_ratio=float(
                    p.get("typical_reasoning_ratio", 0.0)),
                calibrated_at=float(p.get("calibrated_at",
                                          self.bundle_issued)),
                source=f"bundle:{self.bundle_version}")

    def get(self, model: str) -> ModelProfile:
        p = self.profiles.get(model)
        if p and not p.stale:
            return p
        return p or GENERIC

    def status(self) -> dict:
        stale = [m for m, p in self.profiles.items() if p.stale]
        return {"bundle_version": self.bundle_version or None,
                "models": len(self.profiles),
                "stale_models": stale,
                "warning": None if self.profiles and not stale else
                "Running on generic baselines. Per-model calibration is "
                "absent or old; waste detection is conservative and "
                "savings are understated."}
