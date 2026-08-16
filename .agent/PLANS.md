# Execution Plans

Use an ExecPlan for work that spans multiple subsystems or materially changes a public contract.
Keep it in `.agent/plans/<descriptive-name>.md` and update it as implementation progresses.

An ExecPlan should contain:

1. Purpose and user-visible outcome.
2. Current-state findings with relevant file paths.
3. Proposed design and decisions.
4. Ordered implementation steps, including tests and documentation.
5. Verification commands and acceptance criteria.
6. Risks, open questions, and rollback considerations where relevant.

Plans must be self-contained enough for another contributor to continue the work safely.


## Product Roadmap

- Historic price tracking: retain and expose normalized fare observations per watch, add price-low summaries and a time-series view so users can assess current fares against prior low points.
- Direct booking: begin with explicit, user-approved deep links or provider handoff for selected offers. Evaluate full in-app booking only after choosing partners and designing authentication, payment, confirmation, changes, cancellations, and support responsibilities.
