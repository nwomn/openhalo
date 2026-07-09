package dev.openhalo.android.edge

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.roundToInt

data class ScreenContextNode(
    val className: String = "",
    val text: String = "",
    val contentDescription: String = "",
    val bounds: List<Int> = emptyList(),
    val clickable: Boolean = false,
    val editable: Boolean = false,
    val scrollable: Boolean = false,
    val selected: Boolean = false,
    val password: Boolean = false,
    val focused: Boolean = false
)

data class ScreenContextCapture(
    val trigger: String,
    val eventKind: String,
    val packageName: String,
    val rootClassName: String,
    val appVisibility: String,
    val serviceState: String,
    val accessibilityState: String,
    val screenState: String,
    val queueDepth: Int,
    val eventsCoalesced: Int,
    val eventsDropped: Int,
    val captureThrottled: Boolean,
    val nodes: List<ScreenContextNode>
)

private const val MAX_VISIBLE_TEXT_CHARS = 800
private const val MAX_INTERACTIVE_ELEMENTS = 30
private val SensitiveTokenPattern =
    Regex("(password|passcode|otp|验证码|密码|银行卡|credit card)", RegexOption.IGNORE_CASE)

fun buildScreenContextObservation(capture: ScreenContextCapture, observedAt: String = nowIso()): JSONObject {
    val summary = summarizeVisibleText(capture.nodes)
    val sensitivity = screenSensitivity(capture)
    val blocked = sensitivity == "blocked"
    val value = JSONObject()
        .put("trigger", capture.trigger)
        .put("event_kind", capture.eventKind)
        .put("source", "accessibility")
        .put("openhalo_app_visibility", capture.appVisibility)
        .put("edge_service_state", capture.serviceState)
        .put("accessibility_service_state", capture.accessibilityState)
        .put("screen_state", capture.screenState)
        .put("interaction_state", interactionState(capture.eventKind))
        .put("capture_mode", if (blocked) "health_only" else "accessibility_tree")
        .put("can_observe_foreground_app", !blocked && capture.accessibilityState == "enabled")
        .put("background_capture_allowed", true)
        .put("capture_pause_reason", if (blocked) "sensitive_context" else "none")
        .put("capture_queue_depth", capture.queueDepth)
        .put("events_coalesced", capture.eventsCoalesced)
        .put("events_dropped", capture.eventsDropped)
        .put("capture_throttled", capture.captureThrottled)
        .put("package_name", capture.packageName)
        .put("root_class_name", capture.rootClassName)
        .put("package_category", packageCategory(capture.packageName))
        .put("screen_kind", screenKind(capture))
        .put("user_action_observed", userActionObserved(capture.eventKind))
        .put("visible_text_summary", if (blocked) "" else summary)
        .put("ui_affordances", if (blocked) JSONArray() else uiAffordances(capture.nodes))
        .put(
            "interactive_elements",
            if (blocked) JSONArray() else interactiveElements(capture.nodes)
        )
        .put("sensitivity", sensitivity)
        .put("raw_screenshot_uploaded", false)
        .put("confidence", confidence(capture, summary))
        .put(
            "provenance",
            JSONObject()
                .put("producer", "android_accessibility_service")
                .put("raw_screenshot_uploaded", false)
                .put("node_count", capture.nodes.size)
        )
    return JSONObject()
        .put("name", "mobile.screen_context")
        .put("value", value)
        .put("observed_at", observedAt)
        .put("confidence", value.getDouble("confidence"))
}

private fun summarizeVisibleText(nodes: List<ScreenContextNode>): String {
    val text = nodes.asSequence()
        .map { visibleLabel(it) }
        .filter { it.isNotBlank() }
        .distinct()
        .joinToString(" | ")
    return redact(text).take(MAX_VISIBLE_TEXT_CHARS)
}

private fun interactiveElements(nodes: List<ScreenContextNode>): JSONArray {
    val elements = JSONArray()
    nodes.asSequence()
        .filter { it.clickable || it.editable || it.scrollable || it.selected }
        .take(MAX_INTERACTIVE_ELEMENTS)
        .forEachIndexed { index, node ->
            elements.put(
                JSONObject()
                    .put("index", index + 1)
                    .put("role", nodeRole(node))
                    .put("label", redact(visibleLabel(node)).take(80))
                    .put("bounds", JSONArray(node.bounds))
                    .put("sensitive", node.password || SensitiveTokenPattern.containsMatchIn(visibleLabel(node)))
                    .put("focused", node.focused)
            )
        }
    return elements
}

private fun uiAffordances(nodes: List<ScreenContextNode>): JSONArray {
    val affordances = linkedSetOf<String>()
    nodes.forEach { node ->
        if (node.editable) affordances += "text_input"
        if (node.clickable) affordances += "button_or_click_target"
        if (node.scrollable) affordances += "scrollable_region"
        if (node.focused) affordances += "focused_element"
    }
    return JSONArray(affordances.toList())
}

private fun screenSensitivity(capture: ScreenContextCapture): String {
    val packageName = capture.packageName.lowercase()
    if (
        packageName.contains("bank") ||
        packageName.contains("wallet") ||
        packageName.contains("pay") ||
        capture.nodes.any { it.password || SensitiveTokenPattern.containsMatchIn(visibleLabel(it)) }
    ) {
        return "blocked"
    }
    return "normal"
}

private fun visibleLabel(node: ScreenContextNode): String =
    node.text.ifBlank { node.contentDescription }.trim()

private fun redact(text: String): String =
    SensitiveTokenPattern.replace(text, "[redacted]")

private fun nodeRole(node: ScreenContextNode): String =
    when {
        node.editable -> "text_input"
        node.scrollable -> "scrollable"
        node.clickable -> "button"
        else -> "element"
    }

private fun packageCategory(packageName: String): String =
    when {
        packageName.contains("messag", ignoreCase = true) ||
            packageName.contains("chat", ignoreCase = true) -> "messaging"
        packageName.contains("browser", ignoreCase = true) ||
            packageName.contains("chrome", ignoreCase = true) -> "browser"
        packageName.contains("openhalo", ignoreCase = true) -> "openhalo"
        else -> "app"
    }

private fun screenKind(capture: ScreenContextCapture): String {
    val hasTextInput = capture.nodes.any { it.editable }
    val hasScrollable = capture.nodes.any { it.scrollable }
    return when {
        hasTextInput && hasScrollable -> "conversation_or_feed"
        hasTextInput -> "text_entry"
        hasScrollable -> "scrollable_content"
        else -> "app_screen"
    }
}

private fun interactionState(eventKind: String): String =
    if (eventKind in setOf("idle_periodic", "window_unchanged")) "idle" else "active"

private fun userActionObserved(eventKind: String): String =
    when (eventKind) {
        "view_clicked" -> "tap"
        "view_text_changed" -> "typing_or_text_edit"
        "view_scrolled" -> "scroll"
        "view_focused", "view_accessibility_focused" -> "focus_changed"
        "window_state_changed", "window_content_changed", "windows_changed" -> "screen_changed"
        else -> "unknown"
    }

private fun confidence(capture: ScreenContextCapture, summary: String): Double {
    val base = 0.56 +
        (if (summary.isNotBlank()) 0.16 else 0.0) +
        (if (capture.nodes.any { it.clickable || it.editable || it.scrollable }) 0.14 else 0.0)
    return (base.coerceIn(0.3, 0.86) * 100.0).roundToInt() / 100.0
}
