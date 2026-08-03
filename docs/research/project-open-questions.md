# OpenHalo Research Backlog

> These are low-frequency design questions extracted from `Project.md`. `Project.md` remains the canonical baseline and links here for research work that is not part of every implementation session.

## Open Questions

- Which device surfaces should be the first non-CLI surfaces for presence-first experiments?
- What is the smallest reliable terminal-presence signal set that is good enough for runtime push decisions without overfitting to one shell or multiplexer?
- Which concrete `openai_compatible` providers and model families should be implemented first after the shared provider boundary lands?
- What is the minimum grounding bundle every model call should receive from runtime state, snapshot, and goal context?
- When should explicit profile-selected model calls grow into automatic provider/model fallback and broader strategy routing?
- What is the smallest safe operational-control surface for the first host edge, and how should that surface be constrained so it stays inspectable?
- What is the smallest inspectable policy representation that can support model-authored or model-repaired intervention behavior without becoming opaque?
- Which feedback signals are strong enough to update presence policy automatically versus only being stored as weak evidence?
- How should the runtime prevent learned or generated policies from colliding with one another as the policy set grows over time?
- How should policy scope be constrained so independently learned rules stay as orthogonal as possible instead of silently overlapping?
- What lifecycle model should distinguish short-lived situational policy from durable long-term user preference or trust policy?
- Which parts of the presence-policy problem should be informed by external research before the first concrete design is locked in?
- What review cadence should govern early presence-policy updates, and what evidence should be strong enough to justify moving from daily review toward weekly, monthly, or longer review windows?

Current preference:

- Keep the project on its own minimal gateway path rather than planning around OpenClaw gateway server reuse
- Treat the earlier OpenClaw source audit as useful reference context, not as an integration roadmap
- Retain `packages/gateway-protocol` and `packages/gateway-client` only as optional reference material for future protocol organization or client transport hardening
- Treat proactive intervention as an agent-centered but presence-governed problem rather than a task-first assistant workflow
- Treat `Presence Router` as an explicit governance/policy layer inside the broader agent runtime whose scope includes whether to intervene, when, where, and with what intensity
- Prefer explicit or inspectable policy as the durable control surface for proactive behavior, while allowing agent/model loops to create, revise, and repair that policy from runtime feedback
- Prefer a review-gated policy maintenance loop in early phases: runtime and agents may prepare policy update candidates from feedback, but the user should confirm changes on a deliberate cadence before activation
- Treat intervention history and experience feedback as first-class state inputs for policy refinement
- Interpret single ignored interventions as weak evidence rather than immediate negative feedback
- Optimize policy updates against both current user experience and likely future user experience
- Treat policy review cadence itself as adaptive governance: early policy changes may be reviewed daily while the system is noisy, then gradually move toward weekly, monthly, or longer windows as behavior stabilizes
- Prefer a structured environment-understanding pipeline for early presence work: edge sensing produces normalized context observations with source metadata, confidence, and TTL; runtime context state then synthesizes those observations into the snapshot consumed by presence policy
- Prefer a centrally owned shared observation vocabulary that starts small and grows incrementally; new vocabulary should be added at the top level during edge development, validated there, and then treated as normal runtime vocabulary once accepted
- Prefer one unified heuristic-learning maintenance loop around the runtime rather than separate learning loops per layer: online behavior should use explicit mappers and lightweight reducers, while feedback-driven improvements update those components and presence policy through review-gated iterations
- Avoid adding an extra presence-only feature abstraction between context snapshot and `Presence Router`; keep the hot path shallow and let richer evidence remain available separately outside the compact snapshot
- Prefer a dual-entry proactive model: both edge/context activity and agent initiative may trigger agent proposal generation, but both should converge on the same `Presence Router`
- Prefer agent-initiative requests to carry higher salience than weak passive signals so the system feels meaningfully proactive, while still remaining constrained by presence suppression and privacy policy
- Keep the heuristic-learning reference explicit in project context so future implementation work can revisit the outer-loop design source: [Learning Beyond Gradients](https://trinkle23897.github.io/learning-beyond-gradients/#zh)
- For urgent edge-originated actions, prefer an explicit direct-action path over pretending every event should go through model-driven routing or planning
- Even when an edge requests a direct action, the runtime should still retain the event and result in shared state so continuity and auditability are preserved
- Treat the runtime's own hosting server as the first host-class `Device Edge` candidate for early non-CLI presence and operations work
- Model that host edge as a first-class device/capability participant rather than hiding it inside backend-only monitoring code
- Keep operational control in scope for that first host edge, but constrain it to an explicit capability surface rather than arbitrary shell access
- For the first host-edge control slice, prefer host-wide observation together with runtime-scoped control rather than immediate whole-server operational control
- Keep host-edge capability contracts stable while allowing the runtime-control execution backend to vary by deployment model
- For v1, implement runtime-scoped control against the current plain Python process shape first, while preserving a later adapter path for `systemd`-managed deployment
- For `runtime_control`, prefer deployment-agnostic action names such as `status`, `restart`, `reload`, and `collect_logs` over backend-specific verbs
- For `runtime.collect_logs`, prefer a structured result surface first while still carrying raw tail text for debugging compatibility
- Keep the first host edge as an independent frontend-side daemon rather than a module inside the backend runtime process
- The desktop/CLI edge should now be treated as the preferred first formal long-running interaction surface rather than only as a validation harness
- Treat terminal conversation as one capability surface inside that edge, not as a special top-level product abstraction
- The first terminal edge should support both pull-style user requests and push-style runtime interventions, but push should depend on terminal presence or activity instead of blindly printing into unattended terminals
- Model terminal-side user input, activity or idle evidence, runtime-originated message delivery, reply, and ignore or non-response as ordinary edge events and actions on the normal runtime path instead of inventing a chat-only side protocol
- Keep terminal-edge intelligence thin: local UX control may exist on the edge, but proposal formation, intervention policy, and routing authority should remain in the backend runtime
- Prefer the post-M7 milestone sequence to stay narrow and layered: M8 formal terminal edge first, M9 cloud-model agent baseline second, M10 grounding and memory third, M11 terminal/CLI interaction maturity fourth, M12 prompt/context engineering fifth, M13 proposal-formation maturity sixth, M14 model-provider connection reliability and diagnostics seventh, M15 runtime-native credential/runtime-config baseline eighth, M16 post-action deliberation/action loop ninth, M17 multi-edge interaction expansion tenth, accepted M20 Agent Harness and runtime action-loop refactor eleventh, M20.2 interaction-progress presentation twelfth, M20.3 stable Terminal Edge thirteenth, M17.8 sensitive-screen governance fourteenth, M17.9 native Windows Desktop Edge fifteenth, M17.10 Ambient Home Presence Edge sixteenth, broader M18 Agent Harness-controlled observation understanding seventeenth, M19 bounded-growth/storage-hygiene hardening eighteenth, M20.1 governed skill lifecycle nineteenth, M21 policy learning/review twentieth, M22 first packaged three-end product slice twenty-first, and M23 Home Assistant / smart-home ecosystem bridge last
- Prefer cloud-model proposal and reply generation to stay behind a provider boundary inside `Agent Runtime`, with explicit presence governance and normal edge routing still deciding whether and where anything surfaces
- Prefer a hybrid model-provider architecture for `M9`: keep a shared provider registry, model catalog, and runtime-facing profile-selection layer, while implementing only the `openai_compatible` adapter branch in the first accepted slice
- Prefer runtime call sites to select named model profiles rather than hard-coding provider/model pairs directly in business logic, so later provider swaps and model-routing changes stay configuration-driven
- Prefer OpenClaw-style separation between explicit selection, provider/auth failover, model fallback, and later strategy routing; the runtime should not silently treat those as one undifferentiated mechanism
- Defer automatic provider/model strategy routing until after the first grounded model stage, rather than hiding routing policy inside the initial `M9` provider-integration batch
- Prefer model grounding to be runtime-native: model calls should consume compact snapshot, active goals, bounded retrieved edge evidence, and durable runtime state rather than raw channel transcripts alone
- Prefer feedback-driven policy evolution to remain review-gated even after model-backed behavior arrives, so the runtime does not silently rewrite durable intervention policy from weak evidence

Current v0 milestone direction:

- Start with one desktop/CLI `Device Edge`
- Use one long-lived `Edge Session Link <-> Gateway` path
- Keep auth, presence, and state intentionally minimal
- Prove one full loop from `text.input` to `notification.show`
- Preserve room for two runtime dispatch paths: ordinary routed/deliberative handling and explicit direct-action handling

Immediate post-v0 direction:

- Extend persistence enough to support multi-edge continuity experiments cleanly
- Run more than one instance of the same edge template to prove cross-edge routing without introducing a separate one-off edge type
- Add one non-text capability so the runtime demonstrates more than a text loop

Current M2 slice direction:

- Treat same-template edge instances as separate live devices distinguished by `device_id`
- Keep routing rules intentionally simple for now: prefer another online edge with the required capability, otherwise fall back to the source device
- Preserve the direct-action fast path alongside the new ordinary cross-edge routing path
- Use this slice to validate gateway connection tracking and cross-edge action delivery before adding richer presence logic

Current M3 slice direction:

- Build explicit shared context contracts before threading richer presence logic through the live runtime path
- Store normalized runtime observations with provenance separately from raw edge event details
- Build compact snapshot reducers one field at a time, preserving `unknown` and `ambiguous` outcomes instead of forcing certainty
- After the context foundation is stable, thread snapshot-driven routing into `Presence Router` and gateway decision flow
- Use the runtime's own hosting server as the first host-class edge candidate so M3 can learn from real host telemetry rather than only typed CLI input
- Treat that host edge as both an observation source and a future operational-control surface, with a small inspectable capability boundary
- Lock the first host-edge control boundary to `host-wide observation + runtime-scoped control` so the first operational loop stays auditable and easy to test
- Keep the `runtime_control` contract deployment-agnostic and treat Python-process control as the first concrete adapter rather than the permanent execution model
- Keep `runtime_control` responses structured enough for agent reasoning and UI inspection, while allowing raw diagnostic payloads to ride alongside when helpful
- Let `runtime_control.restart` initiate restart from the independent host edge, and let post-restart confirmation arrive later through separate `runtime_health` observations rather than synchronous self-confirmation
- Capture the first host-edge daemon shape and implementation ladder explicitly in `docs/plans/2026-06-19-host-edge-v1-design.md` and `docs/plans/2026-06-19-host-edge-v1-implementation-plan.md`
- Treat the current host-edge batch as a foundation rather than a finished endpoint; keep that completion work out of M3 and carry it in later milestones instead: M4 for a mature standalone host edge, M5 for backend ingestion/context maturity on top of that input, M6 for presence/agent/action maturity on real edge input, and M7 for end-to-end operational-readiness verification
