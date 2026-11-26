"""Selection never reads held-out test metrics; no unvalidated blending."""
from config import MODEL_NAMES

def select_model(report):
    candidates=report.get('validation',{})
    if not candidates:
        return 'Historical baseline','Insufficient chronological validation data; explicitly flagged historical-frequency fallback.'
    # Exact ties use calibration, period stability, goal error, then simpler model.
    selected=min(candidates,key=lambda n:(candidates[n]['log_loss'],candidates[n]['calibration_error'],
        candidates[n]['fold_log_loss_std'],candidates[n]['goal_mae'],MODEL_NAMES.index(n)))
    m=candidates[selected]
    return selected,(f'Lowest pooled chronological validation log loss ({m["log_loss"]:.6f}); '
       f'classwise ECE={m["calibration_error"]:.6f}; fold log-loss SD={m["fold_log_loss_std"]:.6f}; '
       f'goal MAE={m["goal_mae"]:.6f}. Held-out test was not used for selection. No model blending.')
