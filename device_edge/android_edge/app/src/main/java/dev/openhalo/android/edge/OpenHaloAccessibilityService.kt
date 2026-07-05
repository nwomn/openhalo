package dev.openhalo.android.edge

import android.accessibilityservice.AccessibilityService
import android.app.KeyguardManager
import android.graphics.Rect
import android.os.HandlerThread
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONObject
import java.util.ArrayDeque

class OpenHaloAccessibilityService : AccessibilityService() {
    private val workerThread = HandlerThread("OpenHaloScreenContextWorker")
    private lateinit var workerHandler: Handler
    private val pendingEvents = ArrayDeque<CaptureRequest>()
    private var scheduled = false
    private var droppedEvents = 0
    private var lastCaptureAt = 0L

    override fun onCreate() {
        super.onCreate()
        workerThread.start()
        workerHandler = Handler(workerThread.looper)
    }

    override fun onServiceConnected() {
        EdgeDiagnosticsStore.update(
            EdgeDiagnosticsStore.current().copy(screenContextState = "accessibility enabled")
        )
        maybeEmitHealth("enabled", "health_only", "none")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) {
            return
        }
        if (!AndroidEdgePreferences.screenContextObservationEnabled(applicationContext)) {
            maybeEmitHealth("enabled", "disabled", "disabled_by_user")
            return
        }
        val request = CaptureRequest(
            eventKind = eventKind(event.eventType),
            packageName = event.packageName?.toString().orEmpty(),
            className = event.className?.toString().orEmpty(),
            capturedAtMillis = System.currentTimeMillis()
        )
        if (pendingEvents.size >= MAX_PENDING_EVENTS) {
            pendingEvents.removeFirst()
            droppedEvents += 1
        }
        pendingEvents.addLast(request)
        if (!scheduled) {
            scheduled = true
            workerHandler.postDelayed(::flushCapture, UI_SETTLE_DELAY_MS)
        }
    }

    override fun onInterrupt() {
        EdgeDiagnosticsStore.update(
            EdgeDiagnosticsStore.current().copy(screenContextState = "accessibility interrupted")
        )
    }

    override fun onDestroy() {
        workerThread.quitSafely()
        super.onDestroy()
    }

    private fun flushCapture() {
        scheduled = false
        if (pendingEvents.isEmpty()) {
            return
        }
        val now = System.currentTimeMillis()
        val latest = pendingEvents.removeLast()
        val coalesced = pendingEvents.size + 1
        pendingEvents.clear()
        if (now - lastCaptureAt < MIN_CAPTURE_INTERVAL_MS) {
            droppedEvents += coalesced
            maybeEmitHealth("enabled", "health_only", "throttled")
            return
        }
        val currentScreenState = screenState()
        if (currentScreenState == "screen_off" || currentScreenState == "locked") {
            droppedEvents += coalesced
            maybeEmitHealth("enabled", "health_only", currentScreenState)
            return
        }
        lastCaptureAt = now
        val nodes = mutableListOf<ScreenContextNode>()
        rootInActiveWindow?.let { root ->
            collectNodes(root, nodes)
        }
        val observation = buildScreenContextObservation(
            ScreenContextCapture(
                trigger = "accessibility_event",
                eventKind = latest.eventKind,
                packageName = latest.packageName,
                rootClassName = latest.className,
                appVisibility = appVisibility(),
                serviceState = EdgeDiagnosticsStore.current().serviceState,
                accessibilityState = "enabled",
                screenState = currentScreenState,
                queueDepth = pendingEvents.size,
                eventsCoalesced = coalesced,
                eventsDropped = droppedEvents,
                captureThrottled = false,
                nodes = nodes
            )
        )
        val sent = ScreenContextObservationBridge.send(observation)
        EdgeDiagnosticsStore.update(
            EdgeDiagnosticsStore.current().copy(
                screenContextState = if (sent) "sent ${latest.eventKind}" else "captured, edge service disconnected",
                recentObservations = "Captured mobile.screen_context at ${nowIso()}",
                recentEvents = AndroidEdgePreferences.appendHistory(
                    applicationContext,
                    "Captured mobile.screen_context",
                    latest.packageName,
                    "event"
                )
            )
        )
    }

    private fun collectNodes(node: AccessibilityNodeInfo, out: MutableList<ScreenContextNode>) {
        if (out.size >= MAX_NODES) {
            return
        }
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        out += ScreenContextNode(
            className = node.className?.toString().orEmpty(),
            text = node.text?.toString().orEmpty(),
            contentDescription = node.contentDescription?.toString().orEmpty(),
            bounds = listOf(bounds.left, bounds.top, bounds.right, bounds.bottom),
            clickable = node.isClickable,
            editable = node.isEditable,
            scrollable = node.isScrollable,
            selected = node.isSelected,
            password = node.isPassword,
            focused = node.isFocused
        )
        for (index in 0 until node.childCount) {
            node.getChild(index)?.let { child ->
                collectNodes(child, out)
                child.recycle()
            }
        }
    }

    private fun maybeEmitHealth(
        accessibilityState: String,
        captureMode: String,
        pauseReason: String
    ) {
        val observation = JSONObject()
            .put("name", "mobile.screen_capture_health")
            .put(
                "value",
                JSONObject()
                    .put("accessibility_service_state", accessibilityState)
                    .put("capture_mode", captureMode)
                    .put("capture_pause_reason", pauseReason)
                    .put("raw_screenshot_uploaded", false)
            )
            .put("observed_at", nowIso())
            .put("confidence", 1.0)
        ScreenContextObservationBridge.send(observation)
    }

    private fun appVisibility(): String =
        if (EdgeDiagnosticsStore.current().serviceState == "foreground") "background" else "unknown"

    private fun screenState(): String {
        val powerManager = getSystemService(PowerManager::class.java)
        if (powerManager != null && !powerManager.isInteractive) {
            return "screen_off"
        }
        val keyguardManager = getSystemService(KeyguardManager::class.java)
        if (keyguardManager != null && keyguardManager.isKeyguardLocked) {
            return "locked"
        }
        return "unlocked"
    }

    private data class CaptureRequest(
        val eventKind: String,
        val packageName: String,
        val className: String,
        val capturedAtMillis: Long
    )

    companion object {
        private const val MAX_PENDING_EVENTS = 24
        private const val MAX_NODES = 80
        private const val UI_SETTLE_DELAY_MS = 500L
        private const val MIN_CAPTURE_INTERVAL_MS = 1_500L
    }
}

fun eventKind(eventType: Int): String =
    when (eventType) {
        AccessibilityEvent.TYPE_VIEW_CLICKED -> "view_clicked"
        AccessibilityEvent.TYPE_VIEW_SCROLLED -> "view_scrolled"
        AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> "view_text_changed"
        AccessibilityEvent.TYPE_VIEW_FOCUSED -> "view_focused"
        AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUSED -> "view_accessibility_focused"
        AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> "window_state_changed"
        AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> "window_content_changed"
        AccessibilityEvent.TYPE_WINDOWS_CHANGED -> "windows_changed"
        else -> "unknown"
    }
