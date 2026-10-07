"""Phase 7 — Research validation package (blueprint 5.24–5.27).

Bias/leakage detection, statistical validation, walk-forward, and
robustness testing — the validation dependency chain:
Backtesting -> Bias/Leakage -> Statistical -> Walk-Forward -> Robustness.
"""

__version__ = "7.0.0"

from data_engine.research_validation.bias import (
    BiasFinding,
    BiasDetector,
    LeakageDetector,
    OverfittingDetector,
)
from data_engine.research_validation.statistical import (
    TTestResult,
    t_test,
    confidence_interval,
    bonferroni,
    benjamini_hochberg,
    t_distribution_cdf,
    t_quantile,
    StatisticalValidator,
)
from data_engine.research_validation.walk_forward import (
    WalkForwardWindow,
    WalkForwardPlanError,
    build_walk_forward_plan,
    WalkForwardReport,
    WalkForwardValidator,
    WALK_FORWARD_PREFIX,
)
from data_engine.research_validation.robustness import (
    RobustnessError,
    RobustnessReport,
    sweep,
    plateau_analysis,
    robustness_report,
    regime_analysis,
    ROBUSTNESS_PREFIX,
)

__all__ = [
    "__version__",
    "BiasFinding",
    "BiasDetector",
    "LeakageDetector",
    "OverfittingDetector",
    "TTestResult",
    "t_test",
    "confidence_interval",
    "bonferroni",
    "benjamini_hochberg",
    "t_distribution_cdf",
    "t_quantile",
    "StatisticalValidator",
    "WalkForwardWindow",
    "WalkForwardPlanError",
    "build_walk_forward_plan",
    "WalkForwardReport",
    "WalkForwardValidator",
    "WALK_FORWARD_PREFIX",
    "RobustnessError",
    "RobustnessReport",
    "sweep",
    "plateau_analysis",
    "robustness_report",
    "regime_analysis",
    "ROBUSTNESS_PREFIX",
]
