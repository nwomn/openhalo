package dev.openhalo.android.edge

import org.json.JSONObject

const val INTERACTION_PROGRESS_CAPABILITY = "interaction.progress"
private const val INTERACTION_PROGRESS_VERSION = 1
private const val MAX_TRACKED_PROGRESS_INTERACTIONS = 32

private val SAFE_PROGRESS_PHASES = setOf(
    "deliberating",
    "researching",
    "planning",
    "executing",
    "awaiting_action_result",
    "completing",
    "completed",
    "failed",
    "cancelled"
)
private val SAFE_PROGRESS_STATES = setOf("active", "settled")
private val SAFE_PRESENTATION_HINTS = setOf(
    "working",
    "waiting",
    "completed",
    "failed",
    "cancelled"
)
private val PROGRESS_FIELDS = setOf(
    "version",
    "interaction_id",
    "interaction_turn_id",
    "sequence",
    "phase",
    "state",
    "occurred_at",
    "presentation_hint"
)
private val TERMINAL_PROGRESS_PHASES = setOf("completed", "failed", "cancelled")

data class InteractionProgress(
    val interactionId: String,
    val interactionTurnId: String?,
    val sequence: Int,
    val phase: String,
    val state: String,
    val occurredAt: String,
    val presentationHint: String
)

data class InteractionProgressState(
    val activeByInteraction: Map<String, InteractionProgress> = emptyMap(),
    val latestSequenceByInteraction: Map<String, Int> = emptyMap()
) {
    val activeProgresses: List<InteractionProgress>
        get() = activeByInteraction.values.sortedByDescending { it.occurredAt }
}

fun parseInteractionProgressFrame(
    frame: JSONObject,
    expectedDeviceId: String
): InteractionProgress? {
    if (frame.optString("type") != "interaction_progress" ||
        frame.optString("device_id") != expectedDeviceId
    ) {
        return null
    }
    val progress = frame.optJSONObject("progress") ?: return null
    if (!hasOnlyProgressFields(progress) ||
        !PROGRESS_FIELDS.all(progress::has) ||
        progress.optInt("version", -1) != INTERACTION_PROGRESS_VERSION
    ) {
        return null
    }

    val interactionId = progress.optString("interaction_id")
    val interactionTurnId = if (progress.isNull("interaction_turn_id")) {
        null
    } else {
        progress.optString("interaction_turn_id").takeIf { it.isNotBlank() }
            ?: return null
    }
    val sequence = progress.optInt("sequence", -1)
    val phase = progress.optString("phase")
    val state = progress.optString("state")
    val occurredAt = progress.optString("occurred_at")
    val presentationHint = progress.optString("presentation_hint")
    if (interactionId.isBlank() || sequence < 1 || phase !in SAFE_PROGRESS_PHASES ||
        state !in SAFE_PROGRESS_STATES || occurredAt.isBlank() ||
        presentationHint !in SAFE_PRESENTATION_HINTS
    ) {
        return null
    }
    return InteractionProgress(
        interactionId = interactionId,
        interactionTurnId = interactionTurnId,
        sequence = sequence,
        phase = phase,
        state = state,
        occurredAt = occurredAt,
        presentationHint = presentationHint
    )
}

fun reduceInteractionProgress(
    current: InteractionProgressState,
    next: InteractionProgress
): InteractionProgressState {
    if (next.sequence <= current.latestSequenceByInteraction[next.interactionId].orZero()) {
        return current
    }
    val sequences = current.latestSequenceByInteraction.toMutableMap().apply {
        remove(next.interactionId)
        put(next.interactionId, next.sequence)
        while (size > MAX_TRACKED_PROGRESS_INTERACTIONS) {
            remove(entries.iterator().next().key)
        }
    }
    val active = current.activeByInteraction.toMutableMap()
    if (next.state == "settled" || next.phase in TERMINAL_PROGRESS_PHASES) {
        active.remove(next.interactionId)
    } else {
        active.remove(next.interactionId)
        active[next.interactionId] = next
        while (active.size > MAX_TRACKED_PROGRESS_INTERACTIONS) {
            active.remove(active.entries.iterator().next().key)
        }
    }
    return InteractionProgressState(
        activeByInteraction = active,
        latestSequenceByInteraction = sequences
    )
}

fun clearInteractionProgress(
    current: InteractionProgressState,
    interactionId: String? = null
): InteractionProgressState = when {
    interactionId.isNullOrBlank() -> InteractionProgressState()
    interactionId !in current.activeByInteraction -> current
    else -> current.copy(activeByInteraction = current.activeByInteraction - interactionId)
}

private fun Int?.orZero(): Int = this ?: 0

private fun hasOnlyProgressFields(progress: JSONObject): Boolean {
    val keys = progress.keys()
    while (keys.hasNext()) {
        if (keys.next() !in PROGRESS_FIELDS) {
            return false
        }
    }
    return true
}
