package dev.openhalo.android.edge

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

const val EDGE_API_VERSION = "edge.runtime.v1"
const val RUNTIME_MODE_DEVELOPMENT = "development"
const val RUNTIME_MODE_STABLE = "stable"
val DEVELOPMENT_RUNTIME_URL: String = BuildConfig.OPENHALO_DEV_RUNTIME_URL
val DEVELOPMENT_EDGE_TOKEN: String = BuildConfig.OPENHALO_DEV_EDGE_TOKEN
val STABLE_RUNTIME_URL: String = BuildConfig.OPENHALO_STABLE_RUNTIME_URL
val STABLE_EDGE_TOKEN: String = BuildConfig.OPENHALO_STABLE_EDGE_TOKEN
val DEFAULT_RUNTIME_URL: String = DEVELOPMENT_RUNTIME_URL
val DEFAULT_EDGE_TOKEN: String = DEVELOPMENT_EDGE_TOKEN

fun runtimeUrlForMode(runtimeMode: String): String =
    if (runtimeMode == RUNTIME_MODE_STABLE) STABLE_RUNTIME_URL else DEVELOPMENT_RUNTIME_URL

fun edgeTokenForMode(runtimeMode: String): String =
    if (runtimeMode == RUNTIME_MODE_STABLE) STABLE_EDGE_TOKEN else DEVELOPMENT_EDGE_TOKEN

fun nowIso(): String = Instant.now().toString()

fun buildConnectFrame(deviceId: String, token: String): JSONObject =
    JSONObject()
        .put("api_version", EDGE_API_VERSION)
        .put("type", "connect")
        .put(
            "device",
            JSONObject()
                .put("device_id", deviceId)
                .put("device_type", "android-phone")
                .put("role", "interactive_surface")
        )
        .put("auth", JSONObject().put("token", token))

fun buildCapabilityAnnounceFrame(deviceId: String): JSONObject =
    JSONObject()
        .put("api_version", EDGE_API_VERSION)
        .put("type", "capability_announce")
        .put("device_id", deviceId)
        .put(
            "capabilities",
            JSONArray()
                .put(
                    JSONObject()
                        .put("name", "mobile.input")
                        .put("direction", "edge_to_runtime")
                        .put("kind", "event_source")
                        .put("affordances", JSONArray().put("submit_text"))
                        .put("modality", "visual_text")
                        .put("privacy", "personal")
                )
                .put(
                    JSONObject()
                        .put("name", "notification.show")
                        .put("direction", "runtime_to_edge")
                        .put("kind", "action")
                        .put(
                            "affordances",
                            JSONArray()
                                .put("notify_user")
                                .put("deliver_private_text")
                        )
                        .put("modality", "visual_text")
                        .put("content_capacity", "short_text")
                        .put("privacy", "personal")
                        .put("interruptiveness", "high")
                        .put("side_effect", "user_visible_interruptive")
                        .put(
                            "input_schema",
                            JSONObject()
                                .put("type", "object")
                                .put("required", JSONArray().put("message"))
                                .put(
                                    "properties",
                                    JSONObject().put(
                                        "message",
                                        JSONObject().put("type", "string")
                                    )
                                )
                        )
                        .put(
                            "result_schema",
                            JSONObject()
                                .put("type", "object")
                                .put("required", JSONArray().put("status"))
                        )
                )
                .put(
                    JSONObject()
                        .put("name", "notification.alert")
                        .put("direction", "runtime_to_edge")
                        .put("kind", "action")
                        .put(
                            "affordances",
                            JSONArray()
                                .put("notify_user")
                                .put("interrupt_user")
                                .put("deliver_private_text")
                        )
                        .put("modality", "visual_text")
                        .put("content_capacity", "short_text")
                        .put("privacy", "personal")
                        .put("interruptiveness", "high")
                        .put("side_effect", "user_visible_interruptive")
                        .put(
                            "input_schema",
                            JSONObject()
                                .put("type", "object")
                                .put("required", JSONArray().put("message"))
                                .put(
                                    "properties",
                                    JSONObject().put(
                                        "message",
                                        JSONObject().put("type", "string")
                                    )
                                )
                        )
                        .put(
                            "result_schema",
                            JSONObject()
                                .put("type", "object")
                                .put("required", JSONArray().put("status"))
                        )
                )
                .put(
                    JSONObject()
                        .put("name", "mobile.reply.render")
                        .put("direction", "runtime_to_edge")
                        .put("kind", "action")
                        .put("affordances", JSONArray().put("render_private_text"))
                        .put("modality", "visual_text")
                        .put("content_capacity", "medium_text")
                        .put("privacy", "personal")
                        .put("interruptiveness", "low")
                        .put("side_effect", "user_visible")
                        .put(
                            "input_schema",
                            JSONObject()
                                .put("type", "object")
                                .put("required", JSONArray().put("message"))
                                .put(
                                    "properties",
                                    JSONObject().put(
                                        "message",
                                        JSONObject().put("type", "string")
                                    )
                                )
                        )
                )
                .put(
                    JSONObject()
                        .put("name", "mobile.context")
                        .put("direction", "edge_to_runtime")
                        .put("kind", "observation_provider")
                        .put(
                            "observations",
                            JSONArray()
                                .put(
                                    JSONObject()
                                        .put("name", "mobile.app_visibility")
                                        .put(
                                            "schema",
                                            JSONObject()
                                                .put("type", "string")
                                                .put(
                                                    "enum",
                                                    JSONArray()
                                                        .put("foreground")
                                                        .put("background")
                                                        .put("unknown")
                                                )
                                        )
                                        .put("semantics", JSONArray().put("device_activity"))
                                        .put("privacy", "personal_device_state")
                                        .put("freshness_seconds", 120)
                                        .put("confidence", JSONObject().put("type", "edge_reported"))
                                )
                                .put(
                                    JSONObject()
                                        .put("name", "mobile.notification_permission")
                                        .put(
                                            "schema",
                                            JSONObject()
                                                .put("type", "string")
                                                .put(
                                                    "enum",
                                                    JSONArray()
                                                        .put("granted")
                                                        .put("denied")
                                                        .put("unknown")
                                                )
                                        )
                                        .put("semantics", JSONArray().put("permission_state"))
                                        .put("privacy", "personal_device_state")
                                        .put("freshness_seconds", 300)
                                        .put("confidence", JSONObject().put("type", "edge_reported"))
                                )
                                .put(
                                    JSONObject()
                                        .put("name", "mobile.connection_state")
                                        .put(
                                            "schema",
                                            JSONObject()
                                                .put("type", "string")
                                                .put(
                                                    "enum",
                                                    JSONArray()
                                                        .put("connected")
                                                        .put("disconnected")
                                                        .put("unknown")
                                                )
                                        )
                                        .put("semantics", JSONArray().put("edge_availability"))
                                        .put("privacy", "operational")
                                        .put("freshness_seconds", 60)
                                        .put("confidence", JSONObject().put("type", "edge_reported"))
                                )
                        )
                )
        )

fun buildObservationPushFrame(
    deviceId: String,
    appVisibility: String,
    notificationPermission: String,
    connectionState: String
): JSONObject {
    val observedAt = nowIso()
    val observations = JSONArray()
        .put(observation("mobile.app_visibility", appVisibility, observedAt))
        .put(observation("mobile.notification_permission", notificationPermission, observedAt))
        .put(observation("mobile.connection_state", connectionState, observedAt))
    return JSONObject()
        .put("api_version", EDGE_API_VERSION)
        .put("type", "observation_push")
        .put("device_id", deviceId)
        .put("capability", "mobile.context")
        .put("observations", observations)
        .put("payload", JSONObject().put("observations", observations))
}

fun buildMobileInputEventFrame(deviceId: String, text: String): JSONObject =
    JSONObject()
        .put("api_version", EDGE_API_VERSION)
        .put("type", "event_push")
        .put("device_id", deviceId)
        .put("capability", "mobile.input")
        .put(
            "payload",
            JSONObject()
                .put("text", text)
                .put("observed_at", nowIso())
                .put("input_surface", "android_edge")
        )

fun buildActionResultFrame(
    actionRequest: JSONObject,
    deviceId: String,
    capability: String,
    status: String,
    details: JSONObject
): JSONObject =
    JSONObject()
        .put("api_version", EDGE_API_VERSION)
        .put("type", "action_result")
        .put("request_id", actionRequest.optString("request_id"))
        .put("interaction_id", actionRequest.optString("interaction_id"))
        .put("device_id", deviceId)
        .put(
            "result",
            JSONObject()
                .put("status", status)
                .put("capability", capability)
                .put("observed_at", nowIso())
                .put("details", details)
        )

private fun observation(name: String, value: String, observedAt: String): JSONObject =
    JSONObject()
        .put("name", name)
        .put("value", value)
        .put("observed_at", observedAt)
        .put("confidence", 1.0)
