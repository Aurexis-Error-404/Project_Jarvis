# jarvis.json — Project Memory Schema

## Core Rule
This file is the single source of truth for project context.
Claude reads it at every session start via read_codebase tool.
NEVER let Claude write free-text to this file — only structured fields.
NEVER include timestamps in the cached section of the system prompt.

## The Schema

```json
{
  "project": {
    "name": "Intelligent Pest Risk Estimation System",
    "stack": ["EfficientNet-B3", "Sentinel-2", "Streamlit", "FastAPI", "PyTorch"],
    "current_focus": "NDVI computation accuracy on cloudy tiles",
    "repo_root": "/src"
  },

  "decisions": [
    {
      "what": "CNN backbone",
      "chose": "EfficientNet-B3",
      "rejected": "ResNet50",
      "reason": "Better accuracy on small satellite datasets (Sentinel-2 tile size)"
    },
    {
      "what": "Anomaly detection",
      "chose": "Isolation Forest",
      "rejected": "One-Class SVM",
      "reason": "Faster inference, better on high-dimensional NDVI feature vectors"
    },
    {
      "what": "Loss function",
      "chose": "FocalLoss(gamma=2)",
      "rejected": "CrossEntropy",
      "reason": "Class imbalance in pest vs healthy tile ratio"
    }
  ],

  "open_questions": [
    "Cloud provider: AWS vs GCP for inference hosting?",
    "LOF vs Isolation Forest — is IF sufficient for edge cases?"
  ],

  "rejected_approaches": ["ResNet50", "One-Class SVM", "CrossEntropy loss"],

  "ai_config": {
    "mode": "local",
    "cloud_model": "claude-sonnet-4-20250514",
    "local_model": "ollama/codellama",
    "haiku_model": "claude-haiku-4-5-20251001"
  },

  "session_log": [
    {
      "date": "2026-01-01",
      "summary": "Fixed NDVI NaN values on cloud-masked tiles using median imputation",
      "files_touched": ["preprocessor.py", "cloud_mask.py"]
    }
  ]
}
```

## Rules for update_project_memory Tool

Only update this file when the user says one of these exact trigger phrases:
- "remember that"
- "we decided"
- "going with X"
- "lock this in"
- "note that"
- "add this to memory"

DO NOT update when user says:
- "I'm thinking about"
- "maybe"
- "what if"
- "should we"
- "considering"

When updating decisions: always add a `rejected` field and `reason` field.
When updating session_log: append, never overwrite. Max 10 entries — drop oldest.
Never add free-text fields. Only update fields that exist in the schema above.

## What Each Section Is For

**project.current_focus** — Claude uses this to make research reports project-specific.
This single field is what makes the research report mention EfficientNet-B3 instead of generic SOTA.
Update it at session start: "current focus is X"

**decisions** — Prevents Claude from suggesting already-rejected approaches.
If ResNet50 is in rejected_approaches, Claude will never suggest it.

**open_questions** — Claude surfaces relevant context when working near these topics.
Clear them when resolved: "AWS decision made, going with GCP"

**session_log** — Used by read_session_history tool to give Claude continuity across days.