package dev.openhalo.android.edge

import android.content.Context
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import android.os.Handler
import android.os.Looper
import java.time.Instant
import java.util.concurrent.TimeUnit

data class EdgeDiagnostics(
    val runtimeMode: String = RUNTIME_MODE_STABLE,
    val runtimeUrl: String = STABLE_RUNTIME_URL,
    val deviceId: String = "",
    val edgeToken: String = STABLE_EDGE_TOKEN,
    val serviceState: String = "stopped",
    val connectionState: String = "disconnected",
    val lastSentFrame: String = "",
    val lastReceivedFrame: String = "",
    val lastError: String = "",
    val registeredCapabilities: String = "mobile.input, notification.show, notification.alert, mobile.reply.render, mobile.context, mobile.screen_context",
    val recentObservations: String = "",
    val recentActions: String = "",
    val inAppReply: String = "",
    val recentEvents: String = "",
    val lastSuccessfulConnectionAt: String = "",
    val lastDisconnectedAt: String = "",
    val lastDisconnectReason: String = "",
    val reconnectAttempt: Int = 0,
    val reconnectStatus: String = "idle",
    val nextReconnectAt: String = "",
    val notificationHealth: String = "",
    val fullScreenAlertHealth: String = "",
    val batteryHealth: String = "",
    val screenContextState: String = "disabled",
    val backgroundObservationState: String = "inactive",
    val lastLocalObservationAt: String = "",
    val lastSuccessfulUploadAt: String = "",
    val deliveryQueueDepth: Int = 0
)

class AndroidEdgeClient(
    private val context: Context,
    initialState: EdgeDiagnostics = EdgeDiagnostics(),
    private val onStateChanged: (EdgeDiagnostics) -> Unit
) {
    private val httpClient = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS)
        .build()
    private val reconnectHandler = Handler(Looper.getMainLooper())
    private var webSocket: WebSocket? = null
    private var state = initialState
    private var pendingTextCommand: String? = null
    private var currentConfig: AndroidEdgeConfig? = null
    private var manualDisconnect = false

    init {
        RuntimeNotificationPresenter.ensureNotificationChannel(context)
        publish(state)
    }

    fun connect(runtimeMode: String, runtimeUrl: String, deviceId: String, edgeToken: String) {
        reconnectHandler.removeCallbacksAndMessages(null)
        disconnect(scheduleReconnect = false)
        manualDisconnect = false
        val modeToken = edgeTokenForMode(runtimeMode)
        val config = AndroidEdgeConfig(
            runtimeMode = runtimeMode,
            runtimeUrl = runtimeUrl.trim().ifBlank { runtimeUrlForMode(runtimeMode) },
            deviceId = deviceId.trim().ifBlank { state.deviceId },
            edgeToken = edgeToken.trim().ifBlank {
                if (runtimeMode == RUNTIME_MODE_STABLE) {
                    modeToken
                } else {
                    modeToken.ifBlank { DEFAULT_EDGE_TOKEN }
                }
            }
        )
        currentConfig = config
        AndroidEdgePreferences.saveConfig(context, config)
        publish(
            state.copy(
                runtimeMode = config.runtimeMode,
                runtimeUrl = config.runtimeUrl,
                deviceId = config.deviceId,
                edgeToken = config.edgeToken,
                connectionState = "connecting",
                lastError = "",
                reconnectStatus = "connecting",
                nextReconnectAt = "",
                notificationHealth = notificationPermissionState(),
                fullScreenAlertHealth = AndroidEdgeHealth.fullScreenAlertState(context),
                batteryHealth = AndroidEdgeHealth.batteryOptimizationState(context),
                recentEvents = AndroidEdgePreferences.appendHistory(
                    context,
                    "Connection requested",
                    config.runtimeUrl
                )
            )
        )
        val request = Request.Builder().url(state.runtimeUrl).build()
        logEvent("connect_requested", "runtime_url" to state.runtimeUrl, "device_id" to state.deviceId)
        webSocket = httpClient.newWebSocket(request, listener())
    }

    fun disconnect() {
        manualDisconnect = true
        disconnect(scheduleReconnect = false)
        reconnectHandler.removeCallbacksAndMessages(null)
        publish(
            state.copy(
                reconnectStatus = "stopped",
                nextReconnectAt = "",
                lastDisconnectedAt = nowIso(),
                lastDisconnectReason = "manual stop"
            )
        )
    }

    private fun disconnect(scheduleReconnect: Boolean) {
        webSocket?.close(1000, "Android edge disconnect")
        webSocket = null
        if (state.connectionState != "disconnected") {
            publish(state.copy(connectionState = "disconnected"))
        }
        if (!scheduleReconnect) {
            reconnectHandler.removeCallbacksAndMessages(null)
        }
    }

    fun sendCurrentObservations(appVisibility: String = "foreground"): Boolean {
        sendFrame(
            buildObservationPushFrame(
                deviceId = state.deviceId,
                appVisibility = appVisibility,
                notificationPermission = notificationPermissionState(),
                connectionState = state.connectionState
            )
        )
        return state.connectionState == "connected" && webSocket != null
    }

    fun submitTextCommand(text: String) {
        val trimmed = text.trim()
        if (trimmed.isBlank()) {
            publish(state.copy(lastError = "Text command is empty."))
            return
        }
        if (state.connectionState != "connected" || webSocket == null) {
            pendingTextCommand = trimmed
            val config = AndroidEdgePreferences.loadConfig(context)
            publish(
                state.copy(
                    lastError = "",
                    recentEvents = AndroidEdgePreferences.appendHistory(
                        context,
                        "Queued mobile.input",
                        trimmed
                    )
                )
            )
            connect(config.runtimeMode, config.runtimeUrl, config.deviceId, config.edgeToken)
            return
        }
        sendTextCommandNow(trimmed)
    }

    fun sendScreenContextObservation(observation: JSONObject) {
        if (state.connectionState != "connected" || webSocket == null) {
            publish(
                state.copy(
                    screenContextState = "queued: websocket disconnected",
                    lastError = "Screen context observation skipped because WebSocket is not connected.",
                    lastLocalObservationAt = nowIso(),
                    deliveryQueueDepth = state.deliveryQueueDepth + 1
                )
            )
            return
        }
        sendFrame(buildScreenContextObservationPushFrame(state.deviceId, observation))
        publish(
            state.copy(
                screenContextState = "sent at ${nowIso()}",
                lastLocalObservationAt = nowIso(),
                recentEvents = AndroidEdgePreferences.appendHistory(
                    context,
                    "Sent mobile.screen_context",
                    observation.optJSONObject("value")?.optString("screen_kind").orEmpty(),
                    "event"
                )
            )
        )
    }

    private fun sendTextCommandNow(text: String) {
        sendFrame(buildMobileInputEventFrame(state.deviceId, text))
        publish(
            state.copy(
                recentEvents = AndroidEdgePreferences.appendHistory(
                    context,
                    "Submitted mobile.input",
                    text
                )
            )
        )
    }

    private fun listener(): WebSocketListener =
        object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                publish(
                    state.copy(
                        connectionState = "connected",
                        lastError = "",
                        lastSuccessfulConnectionAt = nowIso(),
                        reconnectAttempt = 0,
                        reconnectStatus = "connected",
                        nextReconnectAt = "",
                        notificationHealth = notificationPermissionState(),
                        fullScreenAlertHealth = AndroidEdgeHealth.fullScreenAlertState(context),
                        batteryHealth = AndroidEdgeHealth.batteryOptimizationState(context)
                    )
                )
                logEvent("connected", "runtime_url" to state.runtimeUrl, "device_id" to state.deviceId)
                sendFrame(buildConnectFrame(state.deviceId, state.edgeToken))
                sendFrame(buildCapabilityAnnounceFrame(state.deviceId))
                sendCurrentObservations()
                pendingTextCommand?.let { pending ->
                    pendingTextCommand = null
                    sendTextCommandNow(pending)
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                publish(state.copy(lastReceivedFrame = pretty(text)))
                val frame = runCatching { JSONObject(text) }.getOrNull()
                if (frame == null) {
                    logEvent("receive_error", "error" to "non_json_frame")
                    publish(state.copy(lastError = "Received non-JSON frame."))
                    return
                }
                logEvent(
                    "received_frame",
                    "frame_type" to frame.optString("type"),
                    "request_id" to frame.optString("request_id"),
                    "interaction_id" to frame.optString("interaction_id")
                )
                when (frame.optString("type")) {
                    "action_request" -> handleActionRequest(frame)
                    "error" -> {
                        logEvent(
                            "runtime_error",
                            "message" to frame.optString("message", "runtime error"),
                            "code" to frame.optString("code")
                        )
                        publish(state.copy(lastError = frame.optString("message", "runtime error")))
                    }
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                val reason = t.message ?: "WebSocket failure"
                logEvent(
                    "connection_failure",
                    "error" to reason,
                    "http_code" to (response?.code?.toString() ?: "")
                )
                publish(
                    state.copy(
                        connectionState = "disconnected",
                        lastError = reason,
                        lastDisconnectedAt = nowIso(),
                        lastDisconnectReason = reason
                    )
                )
                scheduleReconnect(reason)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                logEvent("closed", "code" to code.toString(), "reason" to reason)
                publish(
                    state.copy(
                        connectionState = "disconnected",
                        lastDisconnectedAt = nowIso(),
                        lastDisconnectReason = "closed $code ${reason.ifBlank { "no reason" }}"
                    )
                )
                if (!manualDisconnect && code != 1000) {
                    scheduleReconnect("closed $code")
                }
            }
        }

    private fun handleActionRequest(frame: JSONObject) {
        val action = frame.optJSONObject("action") ?: JSONObject()
        val capability = action.optString("capability")
        val payload = action.optJSONObject("payload") ?: JSONObject()
        val notification = parseNotificationShowPayload(payload)
        val renderedReplyBody = parseRenderedReplyBody(payload)
        val message = when (capability) {
            "notification.show" -> notification?.body.orEmpty()
            "mobile.reply.render" -> renderedReplyBody.orEmpty()
            else -> payload.optString("message", payload.toString())
        }
        val details = when (capability) {
            "notification.show" -> JSONObject()
                .put("title", notification?.title.orEmpty())
                .put("body", notification?.body.orEmpty())
            "mobile.reply.render" -> JSONObject().put("body", renderedReplyBody.orEmpty())
            else -> JSONObject().put("message", message)
        }
        val status = when (capability) {
            "notification.show" -> showNotification(notification, details)
            "notification.alert" -> showUrgentNotification(message, details)
            "mobile.reply.render" -> {
                if (renderedReplyBody == null) {
                    details.put("error", "mobile.reply.render requires a non-empty body")
                    "error"
                } else {
                    val history = AndroidEdgePreferences.appendHistory(
                        context,
                        "Rendered runtime reply",
                        message,
                        "reply"
                    )
                    publish(
                        state.copy(
                            inAppReply = message,
                            recentActions = "Rendered mobile.reply.render at ${nowIso()}",
                            recentEvents = history
                        )
                    )
                    "ok"
                }
            }
            else -> {
                details.put("error", "Unsupported capability: $capability")
                "error"
            }
        }
        publish(
            state.copy(
                recentActions = "$capability -> $status at ${nowIso()}",
                inAppReply = if (capability == "mobile.reply.render" && status == "ok") {
                    message
                } else {
                    state.inAppReply
                },
                recentEvents = AndroidEdgePreferences.appendHistory(
                    context,
                    "$capability -> $status",
                    message,
                    if (capability.startsWith("notification.")) "notification" else "event"
                )
            )
        )
        logEvent(
            "action_result",
            "capability" to capability,
            "status" to status,
            "request_id" to frame.optString("request_id"),
            "interaction_id" to frame.optString("interaction_id")
        )
        sendFrame(buildActionResultFrame(frame, state.deviceId, capability, status, details))
    }

    private fun showNotification(
        notification: NotificationShowPayload?,
        details: JSONObject
    ): String {
        if (notification == null) {
            details.put("error", "notification.show requires a non-empty body")
            return "error"
        }
        val error = RuntimeNotificationPresenter.show(
            context,
            notification.title,
            notification.body
        )
        if (error.isNotBlank()) {
            details.put("error", error)
            return "error"
        }
        return "ok"
    }

    private fun showUrgentNotification(message: String, details: JSONObject): String {
        val error = RuntimeNotificationPresenter.showUrgent(context, message)
        if (error.isNotBlank()) {
            details.put("error", error)
            return "error"
        }
        return "ok"
    }

    private fun sendFrame(frame: JSONObject) {
        val text = frame.toString()
        val isObservation = frame.optString("type") == "observation_push"
        val observedAt = nowIso()
        if (webSocket?.send(text) == true) {
            logEvent(
                "sent_frame",
                "frame_type" to frame.optString("type"),
                "device_id" to state.deviceId,
                "capability" to frame.optString("capability")
            )
            publish(
                state.copy(
                    lastSentFrame = pretty(redactSecrets(text)),
                    recentObservations = if (isObservation) {
                        "Sent ${frame.optString("capability")} at $observedAt"
                    } else {
                        state.recentObservations
                    },
                    lastLocalObservationAt = if (isObservation) observedAt else state.lastLocalObservationAt,
                    lastSuccessfulUploadAt = if (isObservation) observedAt else state.lastSuccessfulUploadAt,
                    deliveryQueueDepth = if (isObservation) 0 else state.deliveryQueueDepth,
                    recentEvents = if (isObservation) {
                        AndroidEdgePreferences.appendHistory(
                            context,
                            "Sent ${frame.optString("capability")}"
                        )
                    } else {
                        state.recentEvents
                    }
                )
            )
        } else {
            logEvent(
                "send_error",
                "frame_type" to frame.optString("type"),
                "error" to "websocket_not_connected"
            )
            publish(
                state.copy(
                    lastError = "WebSocket is not connected.",
                    lastLocalObservationAt = if (isObservation) observedAt else state.lastLocalObservationAt,
                    deliveryQueueDepth = if (isObservation) state.deliveryQueueDepth + 1 else state.deliveryQueueDepth
                )
            )
        }
    }

    private fun notificationPermissionState(): String =
        if (RuntimeNotificationPresenter.canPostNotifications(context)) "granted" else "denied"

    private fun scheduleReconnect(reason: String) {
        if (manualDisconnect) {
            return
        }
        val config = currentConfig ?: AndroidEdgePreferences.loadConfig(context)
        currentConfig = config
        val nextAttempt = (state.reconnectAttempt + 1).coerceAtMost(MAX_RECONNECT_ATTEMPT)
        val delayMs = reconnectDelayMillis(nextAttempt)
        val nextAt = Instant.now().plusMillis(delayMs).toString()
        publish(
            state.copy(
                reconnectAttempt = nextAttempt,
                reconnectStatus = "retrying in ${delayMs / 1000}s",
                nextReconnectAt = nextAt,
                lastDisconnectReason = reason,
                recentEvents = AndroidEdgePreferences.appendHistory(
                    context,
                    "Reconnect scheduled",
                    "attempt $nextAttempt after ${delayMs / 1000}s"
                )
            )
        )
        reconnectHandler.removeCallbacksAndMessages(null)
        reconnectHandler.postDelayed({
            if (!manualDisconnect && state.connectionState != "connected") {
                connect(config.runtimeMode, config.runtimeUrl, config.deviceId, config.edgeToken)
            }
        }, delayMs)
    }

    private fun publish(next: EdgeDiagnostics) {
        state = next
        onStateChanged(next)
    }

    private fun pretty(rawJson: String): String =
        runCatching { JSONObject(rawJson).toString(2) }.getOrDefault(rawJson)

    private fun redactSecrets(rawJson: String): String =
        runCatching {
            val frame = JSONObject(rawJson)
            frame.optJSONObject("auth")?.put("token", "<redacted>")
            frame.toString()
        }.getOrDefault(rawJson)

    private fun logEvent(event: String, vararg fields: Pair<String, String>) {
        val payload = JSONObject().put("event", event)
        payload.put("service_state", state.serviceState)
        fields.forEach { (key, value) ->
            if (value.isNotBlank()) {
                payload.put(key, value)
            }
        }
        Log.i(LOG_TAG, "OPENHALO_EDGE_EVENT $payload")
    }

    companion object {
        private const val LOG_TAG = "OpenHaloEdge"
        private const val MAX_RECONNECT_ATTEMPT = 5
    }
}

internal data class NotificationShowPayload(
    val title: String,
    val body: String
)

internal fun parseNotificationShowPayload(payload: JSONObject): NotificationShowPayload? {
    val body = payload.optString("body")
    if (body.isBlank()) {
        return null
    }
    val title = payload.optString("title", DEFAULT_NOTIFICATION_TITLE)
        .ifBlank { DEFAULT_NOTIFICATION_TITLE }
    return NotificationShowPayload(title = title, body = body)
}

internal fun parseRenderedReplyBody(payload: JSONObject): String? =
    listOf(payload.optString("body"), payload.optString("message"))
        .firstOrNull { it.isNotBlank() }

fun reconnectDelayMillis(attempt: Int): Long {
    val seconds = when (attempt.coerceAtLeast(1)) {
        1 -> 2L
        2 -> 5L
        3 -> 10L
        4 -> 20L
        else -> 30L
    }
    return seconds * 1000L
}
