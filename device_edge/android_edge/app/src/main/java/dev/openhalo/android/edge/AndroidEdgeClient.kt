package dev.openhalo.android.edge

import android.content.Context
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

data class EdgeDiagnostics(
    val runtimeMode: String = RUNTIME_MODE_DEVELOPMENT,
    val runtimeUrl: String = DEFAULT_RUNTIME_URL,
    val deviceId: String = "android-edge-${UUID.randomUUID().toString().take(8)}",
    val edgeToken: String = DEFAULT_EDGE_TOKEN,
    val serviceState: String = "stopped",
    val connectionState: String = "disconnected",
    val lastSentFrame: String = "",
    val lastReceivedFrame: String = "",
    val lastError: String = "",
    val registeredCapabilities: String = "mobile.input, notification.show, notification.alert, mobile.reply.render, mobile.context",
    val recentObservations: String = "",
    val recentActions: String = "",
    val inAppReply: String = ""
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
    private var webSocket: WebSocket? = null
    private var state = initialState

    init {
        RuntimeNotificationPresenter.ensureNotificationChannel(context)
        publish(state)
    }

    fun connect(runtimeMode: String, runtimeUrl: String, deviceId: String, edgeToken: String) {
        disconnect()
        val modeToken = edgeTokenForMode(runtimeMode)
        publish(
            state.copy(
                runtimeMode = runtimeMode,
                runtimeUrl = runtimeUrl.trim().ifBlank { runtimeUrlForMode(runtimeMode) },
                deviceId = deviceId.trim().ifBlank { state.deviceId },
                edgeToken = edgeToken.trim().ifBlank {
                    if (runtimeMode == RUNTIME_MODE_STABLE) {
                        modeToken
                    } else {
                        modeToken.ifBlank { DEFAULT_EDGE_TOKEN }
                    }
                },
                connectionState = "connecting",
                lastError = ""
            )
        )
        val request = Request.Builder().url(state.runtimeUrl).build()
        logEvent("connect_requested", "runtime_url" to state.runtimeUrl, "device_id" to state.deviceId)
        webSocket = httpClient.newWebSocket(request, listener())
    }

    fun disconnect() {
        webSocket?.close(1000, "Android edge disconnect")
        webSocket = null
        if (state.connectionState != "disconnected") {
            publish(state.copy(connectionState = "disconnected"))
        }
    }

    fun sendCurrentObservations(appVisibility: String = "foreground") {
        sendFrame(
            buildObservationPushFrame(
                deviceId = state.deviceId,
                appVisibility = appVisibility,
                notificationPermission = notificationPermissionState(),
                connectionState = state.connectionState
            )
        )
    }

    private fun listener(): WebSocketListener =
        object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                publish(state.copy(connectionState = "connected", lastError = ""))
                logEvent("connected", "runtime_url" to state.runtimeUrl, "device_id" to state.deviceId)
                sendFrame(buildConnectFrame(state.deviceId, state.edgeToken))
                sendFrame(buildCapabilityAnnounceFrame(state.deviceId))
                sendCurrentObservations()
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
                logEvent(
                    "connection_failure",
                    "error" to (t.message ?: "WebSocket failure"),
                    "http_code" to (response?.code?.toString() ?: "")
                )
                publish(
                    state.copy(
                        connectionState = "disconnected",
                        lastError = t.message ?: "WebSocket failure"
                    )
                )
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                logEvent("closed", "code" to code.toString(), "reason" to reason)
                publish(state.copy(connectionState = "disconnected"))
            }
        }

    private fun handleActionRequest(frame: JSONObject) {
        val action = frame.optJSONObject("action") ?: JSONObject()
        val capability = action.optString("capability")
        val payload = action.optJSONObject("payload") ?: JSONObject()
        val message = payload.optString("message", payload.toString())
        val details = JSONObject().put("message", message)
        val status = when (capability) {
            "notification.show" -> showNotification(message, details)
            "notification.alert" -> showUrgentNotification(message, details)
            "mobile.reply.render" -> {
                publish(
                    state.copy(
                        inAppReply = message,
                        recentActions = "Rendered mobile.reply.render at ${nowIso()}"
                    )
                )
                "ok"
            }
            else -> {
                details.put("error", "Unsupported capability: $capability")
                "error"
            }
        }
        publish(
            state.copy(
                recentActions = "$capability -> $status at ${nowIso()}",
                inAppReply = if (capability == "mobile.reply.render") message else state.inAppReply
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

    private fun showNotification(message: String, details: JSONObject): String {
        val error = RuntimeNotificationPresenter.showUrgent(context, message)
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
                    recentObservations = if (frame.optString("type") == "observation_push") {
                        "Sent mobile.context at ${nowIso()}"
                    } else {
                        state.recentObservations
                    }
                )
            )
        } else {
            logEvent(
                "send_error",
                "frame_type" to frame.optString("type"),
                "error" to "websocket_not_connected"
            )
            publish(state.copy(lastError = "WebSocket is not connected."))
        }
    }

    private fun notificationPermissionState(): String =
        if (RuntimeNotificationPresenter.canPostNotifications(context)) "granted" else "denied"

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
    }
}
