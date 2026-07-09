package dev.openhalo.android.edge

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EdgeApiFramesTest {
    @Test
    fun mobileInputFrameUsesPublicEdgeApiEventShape() {
        val frame = buildMobileInputEventFrame("android-edge-test", "hello runtime")
        val payload = frame.getJSONObject("payload")

        assertEquals(EDGE_API_VERSION, frame.getString("api_version"))
        assertEquals("event_push", frame.getString("type"))
        assertEquals("android-edge-test", frame.getString("device_id"))
        assertEquals("mobile.input", frame.getString("capability"))
        assertEquals("hello runtime", payload.getString("text"))
        assertEquals("android_edge", payload.getString("input_surface"))
        assertTrue(payload.getString("observed_at").isNotBlank())
    }

    @Test
    fun actionResultFramePreservesRequestAndInteractionLineage() {
        val request = JSONObject()
            .put("request_id", "request-1")
            .put("interaction_id", "interaction-1")
        val details = JSONObject().put("message", "delivered")

        val frame = buildActionResultFrame(
            actionRequest = request,
            deviceId = "android-edge-test",
            capability = "notification.show",
            status = "ok",
            details = details
        )
        val result = frame.getJSONObject("result")

        assertEquals(EDGE_API_VERSION, frame.getString("api_version"))
        assertEquals("action_result", frame.getString("type"))
        assertEquals("request-1", frame.getString("request_id"))
        assertEquals("interaction-1", frame.getString("interaction_id"))
        assertEquals("android-edge-test", frame.getString("device_id"))
        assertEquals("ok", result.getString("status"))
        assertEquals("notification.show", result.getString("capability"))
        assertEquals("delivered", result.getJSONObject("details").getString("message"))
    }

    @Test
    fun capabilityAnnounceRegistersScreenContextObservationProvider() {
        val frame = buildCapabilityAnnounceFrame("android-edge-test")
        val capabilities = frame.getJSONArray("capabilities")
        val screenContext = (0 until capabilities.length())
            .map { capabilities.getJSONObject(it) }
            .first { it.getString("name") == "mobile.screen_context" }
        val observations = screenContext.getJSONArray("observations")
        val screenObservation = observations.getJSONObject(0)

        assertEquals("edge_to_runtime", screenContext.getString("direction"))
        assertEquals("mobile.screen_context", screenObservation.getString("name"))
        assertEquals(
            "object",
            screenObservation.getJSONObject("schema").getString("type")
        )
    }

    @Test
    fun screenContextObservationRedactsSensitiveNodesAndNeverUploadsScreenshot() {
        val observation = buildScreenContextObservation(
            ScreenContextCapture(
                trigger = "accessibility_event",
                eventKind = "view_text_changed",
                packageName = "com.example.chat",
                rootClassName = "ChatActivity",
                appVisibility = "background",
                serviceState = "foreground",
                accessibilityState = "enabled",
                screenState = "unlocked",
                queueDepth = 0,
                eventsCoalesced = 3,
                eventsDropped = 1,
                captureThrottled = false,
                nodes = listOf(
                    ScreenContextNode(
                        className = "android.widget.EditText",
                        text = "password 123456",
                        bounds = listOf(0, 100, 500, 180),
                        editable = true,
                        password = true,
                        focused = true
                    ),
                    ScreenContextNode(
                        className = "android.widget.Button",
                        text = "Send",
                        bounds = listOf(500, 100, 620, 180),
                        clickable = true
                    )
                )
            ),
            observedAt = "2026-07-05T14:24:53Z"
        )
        val value = observation.getJSONObject("value")

        assertEquals("mobile.screen_context", observation.getString("name"))
        assertEquals(false, value.getBoolean("raw_screenshot_uploaded"))
        assertEquals("blocked", value.getString("sensitivity"))
        assertEquals("health_only", value.getString("capture_mode"))
        assertEquals("", value.getString("visible_text_summary"))
        assertEquals(0, value.getJSONArray("interactive_elements").length())
    }

    @Test
    fun screenContextObservationIndexesInteractiveElementsWhenNormal() {
        val observation = buildScreenContextObservation(
            ScreenContextCapture(
                trigger = "accessibility_event",
                eventKind = "view_clicked",
                packageName = "com.example.messaging",
                rootClassName = "ChatActivity",
                appVisibility = "background",
                serviceState = "foreground",
                accessibilityState = "enabled",
                screenState = "unlocked",
                queueDepth = 0,
                eventsCoalesced = 2,
                eventsDropped = 0,
                captureThrottled = false,
                nodes = listOf(
                    ScreenContextNode(text = "Message list", scrollable = true),
                    ScreenContextNode(text = "Reply", editable = true),
                    ScreenContextNode(text = "Send", clickable = true)
                )
            )
        )
        val value = observation.getJSONObject("value")

        assertEquals("normal", value.getString("sensitivity"))
        assertEquals("accessibility_tree", value.getString("capture_mode"))
        assertEquals("com.example.messaging", value.getString("package_name"))
        assertEquals("ChatActivity", value.getString("root_class_name"))
        assertTrue(value.getString("visible_text_summary").contains("Message list"))
        assertEquals(3, value.getJSONArray("interactive_elements").length())
        assertEquals("text_input", value.getJSONArray("interactive_elements").getJSONObject(1).getString("role"))
    }

    @Test
    fun screenContextCapabilitySchemaIncludesAppIdentityFields() {
        val frame = buildCapabilityAnnounceFrame("android-edge-test")
        val capabilities = frame.getJSONArray("capabilities")
        val screenContext = (0 until capabilities.length())
            .map { capabilities.getJSONObject(it) }
            .first { it.getString("name") == "mobile.screen_context" }
        val screenObservation = screenContext
            .getJSONArray("observations")
            .getJSONObject(0)
        val schema = screenObservation.getJSONObject("schema")
        val required = schema.getJSONArray("required")
        val properties = schema.getJSONObject("properties")
        val requiredNames = (0 until required.length()).map { required.getString(it) }

        assertTrue(requiredNames.contains("package_name"))
        assertTrue(requiredNames.contains("root_class_name"))
        assertEquals("string", properties.getJSONObject("package_name").getString("type"))
        assertEquals("string", properties.getJSONObject("root_class_name").getString("type"))
    }

    @Test
    fun reconnectDelayIsBoundedBackoffPolicy() {
        assertEquals(2_000L, reconnectDelayMillis(0))
        assertEquals(2_000L, reconnectDelayMillis(1))
        assertEquals(5_000L, reconnectDelayMillis(2))
        assertEquals(10_000L, reconnectDelayMillis(3))
        assertEquals(20_000L, reconnectDelayMillis(4))
        assertEquals(30_000L, reconnectDelayMillis(5))
        assertEquals(30_000L, reconnectDelayMillis(99))
    }

    @Test
    fun backgroundObservationHeartbeatUsesBoundedSteadyStateInterval() {
        assertEquals(60_000L, backgroundObservationIntervalMillis())
    }

    @Test
    fun backgroundPermissionGuidanceCallsOutKnownManufacturerRestrictions() {
        assertEquals(
            "ready for foreground-service background observation",
            AndroidEdgeHealth.backgroundPermissionGuidance(
                manufacturer = "Google",
                batteryState = "unrestricted"
            )
        )
        assertTrue(
            AndroidEdgeHealth.backgroundPermissionGuidance(
                manufacturer = "Xiaomi",
                batteryState = "may restrict background"
            ).contains("Autostart")
        )
        assertTrue(
            AndroidEdgeHealth.backgroundPermissionGuidance(
                manufacturer = "Samsung",
                batteryState = "may restrict background"
            ).contains("Sleeping apps")
        )
    }
}
