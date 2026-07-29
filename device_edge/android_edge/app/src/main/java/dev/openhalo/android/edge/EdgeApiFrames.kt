package dev.openhalo.android.edge

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.net.URISyntaxException
import java.time.Instant

const val EDGE_API_VERSION = "edge.runtime.v2"
const val RUNTIME_MODE_DEVELOPMENT = "development"
const val RUNTIME_MODE_STABLE = "stable"
val DEVELOPMENT_RUNTIME_URL: String = BuildConfig.OPENHALO_DEV_RUNTIME_URL
val STABLE_RUNTIME_URL: String = BuildConfig.OPENHALO_STABLE_RUNTIME_URL
val DEFAULT_RUNTIME_URL: String = DEVELOPMENT_RUNTIME_URL
const val DEFAULT_NOTIFICATION_TITLE = "OpenHalo"
const val AUTH_KIND_PAIRING = "pairing"
private const val SCREEN_CONTEXT_OBSERVATION_SCHEMA_TYPE = "object"

data class PairingConnectRequest(
    val pairingCode: String,
    val publicKey: String,
    val displayName: String
)

data class AuthChallenge(
    val deviceId: String,
    val audience: String,
    val sessionId: String,
    val challengeId: String,
    val nonce: String,
    val expiresAt: String
)

fun canonicalChallengePayload(challenge: AuthChallenge): String = listOf(
    "edge.runtime.v2.auth",
    challenge.audience,
    challenge.deviceId,
    challenge.sessionId,
    challenge.challengeId,
    challenge.nonce,
    challenge.expiresAt
).joinToString("\n")

fun runtimeUrlForMode(runtimeMode: String): String =
    if (runtimeMode == RUNTIME_MODE_STABLE) STABLE_RUNTIME_URL else DEVELOPMENT_RUNTIME_URL

fun nowIso(): String = Instant.now().toString()

fun buildConnectFrame(
    deviceId: String,
    audience: String,
    sessionId: String,
    pairing: PairingConnectRequest? = null
): JSONObject {
    val frame = JSONObject()
        .put("api_version", EDGE_API_VERSION)
        .put("type", "connect")
        .put(
            "device",
            JSONObject()
                .put("device_id", deviceId)
                .put("device_type", "android-phone")
                .put("role", "interactive_surface")
        )
        .put("audience", audience)
        .put("session_id", sessionId)
    if (pairing != null) {
        frame.put(
            "auth",
            JSONObject()
                .put("kind", AUTH_KIND_PAIRING)
                .put("pairing_code", pairing.pairingCode)
                .put("public_key", pairing.publicKey)
                .put("display_name", pairing.displayName)
        )
    }
    return frame
}

fun buildAuthProofFrame(challenge: AuthChallenge, signature: String): JSONObject =
    JSONObject()
        .put("api_version", EDGE_API_VERSION)
        .put("type", "auth_proof")
        .put("device_id", challenge.deviceId)
        .put("audience", challenge.audience)
        .put("session_id", challenge.sessionId)
        .put("challenge_id", challenge.challengeId)
        .put("signature", signature)

fun parseAuthChallenge(frame: JSONObject, deviceId: String, sessionId: String, audience: String): AuthChallenge? {
    if (frame.optString("type") != "auth_challenge" ||
        frame.optString("device_id") != deviceId ||
        frame.optString("session_id") != sessionId ||
        frame.optString("audience") != audience
    ) {
        return null
    }
    val challenge = frame.optJSONObject("challenge") ?: return null
    if (challenge.optInt("version") != 1) return null
    val challengeId = challenge.optString("challenge_id").trim()
    val nonce = challenge.optString("nonce").trim()
    val expiresAt = challenge.optString("expires_at").trim()
    if (challengeId.isBlank() || nonce.isBlank() || expiresAt.isBlank()) return null
    return AuthChallenge(deviceId, audience, sessionId, challengeId, nonce, expiresAt)
}

fun pairingTransportAllowed(runtimeMode: String, runtimeUrl: String): Boolean =
    runtimeMode != RUNTIME_MODE_STABLE || runtimeUrl.trim().startsWith("wss://")

fun runtimeUrlValidationError(runtimeMode: String, runtimeUrl: String): String? {
    val parsed = try {
        URI(runtimeUrl.trim())
    } catch (_: URISyntaxException) {
        return "Runtime address must be a complete WebSocket URL."
    }
    val scheme = parsed.scheme?.lowercase()
        ?: return "Runtime address must start with ws:// or wss://."
    if (scheme != "ws" && scheme != "wss") {
        return "Runtime address must start with ws:// or wss://."
    }
    if (parsed.host.isNullOrBlank()) {
        return "Runtime address must include a host name or IP address."
    }
    if (runtimeMode == RUNTIME_MODE_STABLE && scheme != "wss") {
        return "Stable Runtime connections require a wss:// address."
    }
    return null
}

fun devicePairingRequired(isPaired: Boolean, pairingCode: String): Boolean =
    !isPaired && pairingCode.isBlank()

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
                        .put("interruptiveness", "medium")
                        .put("side_effect", "user_visible")
                        .put(
                            "input_schema",
                            JSONObject()
                                .put("type", "object")
                                .put("required", JSONArray().put("body"))
                                .put("additionalProperties", false)
                                .put(
                                    "properties",
                                    JSONObject()
                                        .put(
                                            "title",
                                            JSONObject().put("type", "string")
                                        )
                                        .put(
                                            "body",
                                            JSONObject()
                                                .put("type", "string")
                                                .put("minLength", 1)
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
                                .put("required", JSONArray().put("body"))
                                .put("additionalProperties", false)
                                .put(
                                    "properties",
                                    JSONObject().put(
                                        "body",
                                        JSONObject()
                                            .put("type", "string")
                                            .put("minLength", 1)
                                    )
                                )
                        )
                )
                .put(
                    JSONObject()
                        .put("name", INTERACTION_PROGRESS_CAPABILITY)
                        .put("direction", "runtime_to_edge")
                        .put("kind", "interaction_status")
                        .put("affordances", JSONArray().put("render_interaction_progress"))
                        .put("modality", "visual_status")
                        .put("privacy", "operational")
                        .put("interruptiveness", "none")
                        .put("side_effect", "user_visible")
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
                .put(
                    JSONObject()
                        .put("name", "mobile.screen_context")
                        .put("direction", "edge_to_runtime")
                        .put("kind", "observation_provider")
                        .put("source", "android_accessibility_service")
                        .put(
                            "observations",
                            JSONArray()
                                .put(
                                    JSONObject()
                                        .put("name", "mobile.screen_context")
                                        .put(
                                            "schema",
                                            JSONObject()
                                                .put("type", SCREEN_CONTEXT_OBSERVATION_SCHEMA_TYPE)
                                                .put(
                                                    "required",
                                                    JSONArray()
                                                        .put("trigger")
                                                        .put("event_kind")
                                                        .put("source")
                                                        .put("capture_mode")
                                                        .put("screen_state")
                                                        .put("package_name")
                                                        .put("root_class_name")
                                                        .put("sensitivity")
                                                        .put("raw_screenshot_uploaded")
                                                )
                                                .put(
                                                    "properties",
                                                    JSONObject()
                                                        .put("trigger", JSONObject().put("type", "string"))
                                                        .put("event_kind", JSONObject().put("type", "string"))
                                                        .put("source", JSONObject().put("type", "string"))
                                                        .put("capture_mode", JSONObject().put("type", "string"))
                                                        .put("screen_state", JSONObject().put("type", "string"))
                                                        .put("package_name", JSONObject().put("type", "string"))
                                                        .put("root_class_name", JSONObject().put("type", "string"))
                                                        .put("sensitivity", JSONObject().put("type", "string"))
                                                        .put("raw_screenshot_uploaded", JSONObject().put("type", "boolean"))
                                                )
                                        )
                                        .put("semantics", JSONArray().put("passive_screen_context"))
                                        .put("privacy", "personal_screen_context_redacted")
                                        .put("freshness_seconds", 30)
                                        .put("confidence", JSONObject().put("type", "edge_reported"))
                                )
                                .put(
                                    JSONObject()
                                        .put("name", "mobile.screen_capture_health")
                                        .put(
                                            "schema",
                                            JSONObject()
                                                .put("type", SCREEN_CONTEXT_OBSERVATION_SCHEMA_TYPE)
                                                .put(
                                                    "required",
                                                    JSONArray()
                                                        .put("accessibility_service_state")
                                                        .put("capture_mode")
                                                        .put("capture_pause_reason")
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

fun buildScreenContextObservationPushFrame(
    deviceId: String,
    observation: JSONObject
): JSONObject {
    val observations = JSONArray().put(observation)
    return JSONObject()
        .put("api_version", EDGE_API_VERSION)
        .put("type", "observation_push")
        .put("device_id", deviceId)
        .put("capability", "mobile.screen_context")
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
        .put("interaction_turn_id", actionRequest.optString("interaction_turn_id"))
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
