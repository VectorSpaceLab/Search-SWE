# Memora Dataset

Conversation histories from the Memora benchmark.

## Layout

```
data/
├── weekly/<persona>/
│   └── conversations/session_NNNN.json
├── monthly/<persona>/
│   └── ...
└── quarterly/<persona>/
    └── ...
```

The three `<period>` buckets correspond to the three temporal durations in the paper. They share the same persona set; the number of generated sessions varies by period:

| Period | Days | Sessions / persona |
| --- | ---: | ---: |
| `weekly` | 7 | ~150 |
| `monthly` | 30 | ~600 |
| `quarterly` | 90 | ~2000 |

The 10 personas are: `academic_researcher`, `business_executive`, `content_writer`, `creative_designer`, `financial_analyst`, `management_consultant`, `marketing_manager`, `sales_manager`, `software_engineer`, `startup_founder`.

## Session file (`conversations/session_NNNN.json`)

```jsonc
{
  "session_id": 1,
  "session_type": "no_memory" | "memory_introduction" | "memory_update" | ...,
  "operation": "...",                  // what happened in this session
  "operation_details": { ... },
  "date": "2025-06-01",
  "persona": "academic_researcher",
  "conversation": [
    {
      "turn": 1,
      "speaker": "ai_agent" | "user",
      "message": "...",
      "share_memory": false             // true = this turn carries new memory
                                        //        the agent should retain
    },
    ...
  ]
}
```

Sessions are stored in chronological order (`session_0001.json` is the earliest). `share_memory` flags the turns that introduce information the user later expects the agent to remember (or, for forgetting sessions, to forget).

## License

The dataset is released under Apache License 2.0 (see [`LICENSE-repository.txt`](LICENSE-repository.txt)).
