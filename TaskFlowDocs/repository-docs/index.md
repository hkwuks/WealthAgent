# Repository documents

This index is the authoritative routing and check record for repository documents. The documents at their repository-relative source paths remain authoritative for policy content. Maintain this record first, route by phase from it, then read the routed sources. Do not copy source policy text here.

| Class | Source path | Phases | Exists | Status |
| --- | --- | --- | --- | --- |
| repository-guidance | `README.md` | design,roadmap | yes | ready |
| repository-guidance | `README.zh-CN.md` | design,roadmap | no | missing |
| repository-rule | `LICENSE` | all | yes | ready |
| repository-rule | `CONTRIBUTING.md` | design,code,commit,pr,release | no | missing |
| repository-rule | `CODE_STYLE.md` | code,review | no | missing |
| repository-guidance | `ROADMAP.md` | design,roadmap,release | no | missing |
| repository-rule | `.github/pull_request_template.md` | pr | no | missing |
| repository-rule | `.github/CODEOWNERS` | pr,review | no | optional |
| repository-rule | `CODE_OF_CONDUCT.md` | all | no | optional |
| repository-rule | `SECURITY.md` | code,review,release | no | optional |
| repository-rule | `RELEASE.md` | release | no | optional |
| repository-rule | `CHANGELOG.md` | release | no | optional |
| personal-rule | `TaskFlowDocs/repository-docs/personal.md` | all | local | local-only |

## Personal rules

Personal rules live in `TaskFlowDocs/repository-docs/personal.md`: one file, each rule in its own section with its own scope. They are local-only, never committed, and cannot override repository documents.
The table names that path as a routing location and marks it `Exists: local`. Whether a personal rule is present in this clone is reported on the session route line, not here: this file is committed and cannot carry a local-only fact without going permanently modified on the machines that have one.
