# Dashboard Design QA

## Targets

- Reference: `docs/design/dashboard-reference.png`
- Implementation: `http://localhost:8000/`
- Primary viewport: 1440 × 1024
- Responsive viewport: 390 × 844

## Visual comparison

| Area | Reference intent | Implemented result | Status |
| --- | --- | --- | --- |
| Overall composition | Dense operations dashboard with a dedicated review rail | Left navigation, central operations workspace, and sticky right review rail at desktop width | Passed |
| Theme | White surfaces with restrained bright accents | Cool-white surfaces, cobalt actions, emerald success, amber safety, coral revision states | Passed |
| Run overview | Metrics and a compact horizontal pipeline | Live run counts and eight data-backed pipeline stages | Passed |
| Selected post | Readable content preview with evidence | Full generated copy, extracted facts, source table, provider metadata, and copy action | Passed |
| Review rail | Facts, sources, quality, destination, and approval controls | Live queue navigation, quality checks, Dry Run warning, guarded approval and revision actions | Passed |
| Typography | Compact technical hierarchy | Sans-serif hierarchy with small uppercase labels and high-contrast body copy | Passed |
| Mobile | Content remains usable without page-level horizontal overflow | Bottom navigation, stacked content, scroll-contained pipeline/table, review rail below main content | Passed |

## Interaction verification

- Review queue next/previous navigation updates the selected post and evidence.
- A quality-rejected draft disables approval and explains the threshold failure.
- `Request revision` opens an accessible native dialog; Cancel closes it without triggering required-field validation.
- Approval and publication are separate explicit actions.
- The language toggle translates the complete interface and selects a validated Chinese post variant.
- `Run now` starts a background pipeline run and the page polls progress every five seconds.
- `Regenerate` and `Schedule publish` use focused native dialogs with explicit cancel actions.
- Approved posts expose separate immediate and scheduled publication choices.
- Once a schedule exists, immediate publication and duplicate scheduling are locked; revision safely cancels the old schedule.
- Dry Run messaging stays visible at the point of action.
- Dashboard mutation requests require the application-specific action header; production also requires the admin token.
- No browser console warnings or errors were present during the final pass.

## Issues found and resolved

1. **P1 — hidden Publish button remained visible:** the component display rule overrode the browser's hidden attribute. Added a global `[hidden]` rule and versioned assets.
2. **P1 — revision Cancel triggered form validation:** replaced the submit-style Cancel control with an explicit dialog-close action and verified it at desktop and mobile widths.
3. **P1 — scheduled and immediate publication could conflict:** made the choices mutually exclusive and cancel an old schedule when a draft enters revision or is regenerated.

## Final result

Passed. No open P0, P1, or P2 visual or interaction issues remain in the tested flows.
